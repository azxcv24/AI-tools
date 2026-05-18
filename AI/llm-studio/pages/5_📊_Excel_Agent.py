import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401,E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from components import (  # noqa: E402
    badge,
    empty_state,
    inject_global_css,
    page_header,
    sidebar_brand,
)
from shared.execution import run_pandas_code  # noqa: E402
from shared.llm import Message, get_provider, list_providers  # noqa: E402
from shared.storage import FileManager  # noqa: E402

st.set_page_config(page_title="Excel Agent · LLM Studio", page_icon="📊", layout="wide")
inject_global_css()
sidebar_brand()

page_header(
    "📊",
    "Excel Agent",
    "엑셀·CSV 파일들을 자연어로 통합·집계·변환 — LLM 이 pandas 코드를 만들고 격리 환경에서 실행합니다.",
)

EXCEL_EXTS = {"xlsx", "xls", "csv", "tsv"}


# ============================================================
# helpers
# ============================================================

def is_excel(name: str) -> bool:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext in EXCEL_EXTS


def read_schema(path: Path) -> dict:
    try:
        if path.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(path, nrows=5)
        elif path.suffix.lower() == ".tsv":
            df = pd.read_csv(path, sep="\t", nrows=5)
        else:
            df = pd.read_csv(path, nrows=5)
        return {
            "columns": list(df.columns),
            "dtypes": {c: str(df[c].dtype) for c in df.columns},
            "head": df.head(3),
            "n_cols": len(df.columns),
        }
    except Exception as e:
        return {"error": str(e)}


def extract_code(text: str) -> str:
    """Pull the first ```python``` (or bare ```) block from LLM output."""
    if "```python" in text:
        text = text.split("```python", 1)[1]
    elif "```" in text:
        text = text.split("```", 1)[1]
    if "```" in text:
        text = text.split("```", 1)[0]
    return text.strip()


@st.cache_data(ttl=300, show_spinner="모델 리스트 조회 중…")
def fetch_models(provider_name: str) -> tuple[list[str], str | None]:
    try:
        return list(get_provider(provider_name, model="-").list_models()), None
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


# ============================================================
# sidebar — model + execution limits
# ============================================================
with st.sidebar:
    st.markdown("##### 🤖 코드 생성 모델")
    providers = list_providers()
    if "litellm" in providers:
        default_idx = providers.index("litellm")
    elif "ollama" in providers:
        default_idx = providers.index("ollama")
    else:
        default_idx = 0
    provider_name = st.selectbox("Provider", providers, index=default_idx)

    c1, c2 = st.columns([4, 1])
    c1.caption("Model")
    if c2.button("🔄", help="새로고침", use_container_width=True, key="refresh_models"):
        fetch_models.clear()
        st.rerun()

    models, err = fetch_models(provider_name)
    if err:
        st.warning(f"리스트 조회 실패\n\n```\n{err}\n```")
        model = st.text_input("Model (수동)", value="", label_visibility="collapsed")
    elif not models:
        st.info("사용 가능한 모델 없음")
        model = st.text_input("Model (수동)", value="", label_visibility="collapsed")
    else:
        key = f"excel_model__{provider_name}"
        prev = st.session_state.get(key)
        idx = models.index(prev) if prev in models else 0
        model = st.selectbox(
            "Model", models, index=idx,
            key=f"excel_select_{provider_name}", label_visibility="collapsed",
        )
        st.session_state[key] = model

    st.divider()
    st.markdown("##### 🔒 실행 제한")
    timeout = st.slider("타임아웃 (초)", 5, 300, 60, step=5)
    mem_mb = st.slider("메모리 (MB)", 128, 4096, 1024, step=128)
    st.caption("LLM 생성 코드는 격리 subprocess 에서 실행됩니다 · 메모리/CPU/FD 제한")


# ============================================================
# 1. 입력 파일 선택
# ============================================================
fm = FileManager(_bootstrap.UPLOADS_DIR)
all_files = fm.list()
excel_files = [f for f in all_files if is_excel(f.name)]

st.markdown("##### 1️⃣ 입력 파일 선택")
if not excel_files:
    empty_state(
        icon="📊",
        title="엑셀·CSV 파일이 없습니다",
        hint="Files 페이지에서 .xlsx · .xls · .csv · .tsv 파일을 업로드하세요.",
    )
    st.page_link("pages/2_📁_Files.py", label="📁 Files 페이지 열기 →")
    st.stop()

opts = [f.name for f in excel_files]
labels = {f.name: f"{f.name}  ·  {f.size/1024:.1f}KB" for f in excel_files}
selected: list[str] = st.multiselect(
    "Files 폴더의 엑셀·CSV 파일",
    opts,
    format_func=lambda n: labels.get(n, n),
    key="excel_selected",
    label_visibility="collapsed",
)

# ---- schema preview ----
schemas: dict[str, dict] = {}
if selected:
    st.markdown("##### 📋 스키마 미리보기")
    for name in selected:
        with st.expander(f"📄 `{name}`", expanded=True):
            info = read_schema(_bootstrap.UPLOADS_DIR / name)
            schemas[name] = info
            if "error" in info:
                st.error(f"읽기 실패: {info['error']}")
            else:
                c1, c2 = st.columns([1, 3])
                with c1:
                    st.caption(f"컬럼 ({info['n_cols']}개)")
                    for c in info["columns"]:
                        st.markdown(f"- `{c}` · *{info['dtypes'][c]}*")
                with c2:
                    st.caption("상위 3행 미리보기")
                    st.dataframe(info["head"], use_container_width=True, hide_index=True)


# ============================================================
# 2. 작업 설명
# ============================================================
st.markdown("##### 2️⃣ 작업 설명")
example_tasks = [
    "두 파일을 합쳐서 region 별 amount 의 평균을 result.csv 로 저장",
    "모든 파일의 동일 표 항목은 평균값으로 합치고 merged.xlsx 로 저장",
    "각 파일에서 amount > 1000 인 행만 추려 filtered_<원본명>.csv 로 저장",
]
task = st.text_area(
    "무엇을 할지 자연어로 설명",
    placeholder="예: " + example_tasks[0],
    height=100,
    key="excel_task",
    label_visibility="collapsed",
)

with st.expander("💡 예시 작업 보기"):
    for t in example_tasks:
        st.markdown(f"- {t}")

gen_clicked = st.button(
    "⚡ pandas 코드 생성",
    type="primary",
    disabled=not (selected and task.strip() and model),
    use_container_width=False,
)


# ============================================================
# 3. LLM → 코드 생성
# ============================================================
if gen_clicked:
    schemas_lines = []
    for name in selected:
        info = schemas.get(name) or read_schema(_bootstrap.UPLOADS_DIR / name)
        if "error" in info:
            continue
        cols = ", ".join(f"{c} ({info['dtypes'][c]})" for c in info["columns"])
        schemas_lines.append(f"- `{name}`: {cols}")

    system_prompt = (
        "You are a Python data engineer. Write a single self-contained pandas script "
        "that accomplishes the user's task.\n\n"
        "RULES:\n"
        "- Output ONLY the Python code in ONE ```python``` block. No explanation.\n"
        "- Read inputs from current directory: pd.read_csv('file.csv'), pd.read_excel('file.xlsx').\n"
        "- Write outputs to current directory: result.to_csv('result.csv', index=False), df.to_excel('out.xlsx', index=False).\n"
        "- Use ONLY: pandas, numpy, openpyxl, and Python standard library.\n"
        "- No network, no subprocess, no eval/exec, no file ops outside cwd.\n"
        "- Use print() only for short summaries (row counts, key stats).\n\n"
        "INPUT FILES IN CURRENT DIRECTORY:\n" + "\n".join(schemas_lines)
    )

    try:
        llm = get_provider(provider_name, model=model)
        with st.spinner(f"`{model}` 로 코드 생성 중…"):
            resp = llm.chat([
                Message(role="system", content=system_prompt),
                Message(role="user", content=task),
            ])
        code = extract_code(resp.content) or resp.content
        st.session_state["excel_code"] = code
        st.session_state.pop("excel_result", None)
        st.toast("✅ 코드 생성됨", icon="⚡")
    except Exception as e:
        st.error(f"코드 생성 실패: {e}")


# ============================================================
# 3b. 생성된 코드 (편집 가능)
# ============================================================
if st.session_state.get("excel_code"):
    st.markdown("##### 3️⃣ 생성된 pandas 코드")
    st.caption("실행 전에 직접 수정할 수 있습니다.")
    code = st.text_area(
        "code",
        value=st.session_state["excel_code"],
        height=320,
        key="excel_code_editor",
        label_visibility="collapsed",
    )

    c1, c2 = st.columns([1, 4])
    run_clicked = c1.button(
        "▶️ 격리 환경에서 실행",
        type="primary",
        disabled=not selected,
        use_container_width=True,
    )
    c2.markdown(
        f"<div style='padding-top:8px'>{badge(f'타임아웃 {timeout}s', 'info')} "
        f"{badge(f'메모리 {mem_mb}MB', 'info')}</div>",
        unsafe_allow_html=True,
    )

    if run_clicked:
        inputs = {name: fm.read(name) for name in selected}
        with st.spinner(f"실행 중… (최대 {timeout}s)"):
            result = run_pandas_code(
                code,
                inputs,
                timeout_seconds=timeout,
                memory_limit_mb=mem_mb,
            )
        st.session_state["excel_result"] = result


# ============================================================
# 4. 결과
# ============================================================
result = st.session_state.get("excel_result")
if result is not None:
    st.markdown("##### 4️⃣ 실행 결과")

    c1, c2, c3 = st.columns(3)
    c1.metric("상태", "✅ 성공" if result.ok else "❌ 실패")
    c2.metric("소요 시간", f"{result.elapsed:.2f}s")
    c3.metric("출력 파일", len(result.outputs))

    if result.error:
        st.error(f"오류: {result.error}")

    if result.stdout.strip():
        with st.expander("📤 표준 출력", expanded=result.ok):
            st.code(result.stdout, language="text")

    if result.stderr.strip():
        with st.expander("⚠️ 표준 에러", expanded=not result.ok):
            st.code(result.stderr, language="text")

    if result.outputs:
        st.markdown("##### 📦 출력 파일")
        for name, data in result.outputs.items():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([4, 2, 1.5, 2])
                c1.markdown(f"**`{name}`**")
                c2.caption(f"{len(data):,} bytes")
                c3.download_button(
                    "⬇️",
                    data=data,
                    file_name=name,
                    key=f"dl_{name}",
                    use_container_width=True,
                    help="다운로드",
                )
                if c4.button("📁 Files 에 저장", key=f"save_{name}", use_container_width=True):
                    try:
                        fm.save(name, data)
                        st.toast(f"📁 `{name}` Files 폴더에 저장", icon="💾")
                    except Exception as e:
                        st.error(f"저장 실패: {e}")

                # quick preview for tabular outputs
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                try:
                    if ext == "csv":
                        df = pd.read_csv(BytesIO(data), nrows=20)
                    elif ext == "tsv":
                        df = pd.read_csv(BytesIO(data), sep="\t", nrows=20)
                    elif ext in ("xlsx", "xls"):
                        df = pd.read_excel(BytesIO(data), nrows=20)
                    else:
                        df = None
                except Exception:
                    df = None
                if df is not None:
                    with st.expander("👀 미리보기 (상위 20행)", expanded=False):
                        st.dataframe(df, use_container_width=True, hide_index=True)
