import json
import re
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
    render_sidebar,
    sidebar_brand,
)
from shared.execution import run_pandas_code  # noqa: E402
from shared.llm import Message, resolve  # noqa: E402
from shared.skills import Skill, get_registry, render_template  # noqa: E402
from shared.storage import FileManager  # noqa: E402

st.set_page_config(page_title="Excel Agent · LLM Studio", page_icon="📊", layout="wide")
inject_global_css()
sidebar_brand()

page_header(
    "📊",
    "Excel Agent",
    "엑셀·CSV 파일을 LLM 으로 분석. 구조 자동 인식 → 스킬·자연어로 작업 → 격리 환경 실행.",
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


@st.cache_data(ttl=300, show_spinner=False)
def count_text_cells(path_str: str) -> dict:
    path = Path(path_str)
    try:
        if path.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(path, header=None, dtype=object)
        elif path.suffix.lower() == ".tsv":
            df = pd.read_csv(path, sep="\t", header=None, dtype=object, keep_default_na=False)
        else:
            df = pd.read_csv(path, header=None, dtype=object, keep_default_na=False)
    except Exception as e:
        return {"error": str(e)}

    def has_text(v) -> bool:
        if v is None:
            return False
        if isinstance(v, float) and pd.isna(v):
            return False
        s = str(v).strip()
        return s != "" and s.lower() != "nan"

    mask = df.map(has_text) if hasattr(df, "map") else df.applymap(has_text)
    rows_total, cols_total = df.shape
    return {
        "rows_total": int(rows_total),
        "cols_total": int(cols_total),
        "rows_with_data": int(mask.any(axis=1).sum()),
        "cols_with_data": int(mask.any(axis=0).sum()),
        "cells_with_data": int(mask.sum().sum()),
    }


def extract_code(text: str) -> str:
    if "```python" in text:
        text = text.split("```python", 1)[1]
    elif "```" in text:
        text = text.split("```", 1)[1]
    if "```" in text:
        text = text.split("```", 1)[0]
    return text.strip()


def _flatten_multi(columns) -> list[str]:
    out: list[str] = []
    for c in columns:
        if isinstance(c, tuple):
            parts = [str(x) for x in c if str(x) != "nan" and not str(x).startswith("Unnamed")]
            out.append("_".join(parts).strip("_") or str(c))
        else:
            out.append(str(c))
    return out


def detect_structure(path: Path) -> dict:
    """Build the raw_preview + column_candidates payload for the structure-detect skill."""
    payload: dict = {"file_name": path.name}
    try:
        raw_df = pd.read_excel(path, header=None, nrows=15, dtype=object) if path.suffix.lower() in (".xlsx", ".xls") \
                 else (pd.read_csv(path, sep="\t", header=None, nrows=15, dtype=object, keep_default_na=False) if path.suffix.lower() == ".tsv"
                       else pd.read_csv(path, header=None, nrows=15, dtype=object, keep_default_na=False))
        payload["raw_preview"] = raw_df.fillna("").to_csv(index=False, header=False)
    except Exception as e:
        payload["raw_preview"] = f"(읽기 실패: {e})"

    candidates: dict = {}
    try:
        cols0 = list(pd.read_excel(path, header=0, nrows=3).columns) if path.suffix.lower() in (".xlsx", ".xls") \
                else list(pd.read_csv(path, nrows=3).columns)
        candidates["header=0"] = [str(c) for c in cols0]
    except Exception as e:
        candidates["header=0"] = [f"(err: {e})"]
    try:
        if path.suffix.lower() in (".xlsx", ".xls"):
            cols01 = _flatten_multi(pd.read_excel(path, header=[0, 1], nrows=3).columns)
            candidates["header=[0,1]"] = cols01
    except Exception:
        pass
    payload["column_candidates"] = json.dumps(candidates, ensure_ascii=False)
    return payload


def parse_schema_json(text: str) -> dict | None:
    """Try to extract a JSON object from the LLM response."""
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


# ============================================================
# sidebar
# ============================================================
state = render_sidebar(
    "excel-agent",
    kinds=["excel-pandas"],
    with_task=True,
    with_limits=True,
    default_system_prompt="",
)


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

schemas: dict[str, dict] = {}
if selected:
    st.markdown("##### 📋 파일별 스키마 미리보기")
    for name in selected:
        with st.expander(f"📄 `{name}`", expanded=False):
            info = read_schema(_bootstrap.UPLOADS_DIR / name)
            schemas[name] = info
            if "error" in info:
                st.error(f"읽기 실패: {info['error']}")
            else:
                stats = count_text_cells(str(_bootstrap.UPLOADS_DIR / name))
                if "error" not in stats:
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("문자 입력 행", f"{stats['rows_with_data']:,}",
                              help=f"전체 {stats['rows_total']:,}행 중")
                    m2.metric("문자 입력 열", f"{stats['cols_with_data']:,}",
                              help=f"전체 {stats['cols_total']:,}열 중")
                    m3.metric("문자 입력 셀", f"{stats['cells_with_data']:,}")
                    density = (stats["cells_with_data"] /
                               max(stats["rows_total"] * stats["cols_total"], 1)) * 100
                    m4.metric("밀도", f"{density:.1f}%")

                c1, c2 = st.columns([1, 3])
                with c1:
                    st.caption(f"컬럼 ({info['n_cols']}개)")
                    for c in info["columns"]:
                        st.markdown(f"- `{c}` · *{info['dtypes'][c]}*")
                with c2:
                    st.caption("상위 3행")
                    st.dataframe(info["head"], use_container_width=True, hide_index=True)


# ============================================================
# 1.5 🔍 구조 분석
# ============================================================
if selected:
    st.markdown("##### 🔍 구조 분석 (선택)")
    st.caption("LLM 이 raw 데이터를 읽어 비목·연차·예산 같은 키 컬럼을 자동 추론합니다.")

    if "excel_schema" not in st.session_state:
        st.session_state.excel_schema = {}

    c1, c2 = st.columns([1.2, 5])
    detect_clicked = c1.button(
        "🔍 구조 분석",
        type="secondary",
        disabled=not (selected and state.endpoint and state.model),
        use_container_width=True,
    )
    if c2.button("🗑️ 분석 결과 비우기", use_container_width=False,
                  disabled=not st.session_state.excel_schema):
        st.session_state.excel_schema = {}
        st.rerun()

    if detect_clicked:
        registry = get_registry()
        det_skill = registry.get("excel-structure-detect")
        if det_skill is None:
            st.error("내장 시드 `excel-structure-detect` 가 누락되었습니다.")
        else:
            try:
                llm = resolve(state.endpoint, model=state.model)
                for name in selected:
                    payload = detect_structure(_bootstrap.UPLOADS_DIR / name)
                    user_msg = render_template(det_skill.user_prompt_template, **payload)
                    with st.spinner(f"`{name}` 구조 분석 중…"):
                        resp = llm.chat([
                            Message(role="system", content=det_skill.system_prompt),
                            Message(role="user", content=user_msg),
                        ])
                    schema = parse_schema_json(resp.content) or {"_raw": resp.content[:500]}
                    st.session_state.excel_schema[name] = schema
                st.toast("✅ 구조 분석 완료", icon="🔍")
                st.rerun()
            except Exception as e:
                st.error(f"구조 분석 실패: {type(e).__name__}: {e}")

    # render schema editors for each analyzed file
    for name in selected:
        schema = st.session_state.excel_schema.get(name)
        if schema is None:
            continue

        with st.expander(f"📊 감지된 구조 — `{name}`", expanded=True):
            tab_form, tab_json = st.tabs(["📝 폼", "🧾 JSON"])

            with tab_form:
                # column candidates (for multiselect options)
                try:
                    cols_options = (
                        _flatten_multi(pd.read_excel(_bootstrap.UPLOADS_DIR / name,
                                                     header=[0, 1], nrows=3).columns)
                        if Path(name).suffix.lower() in (".xlsx", ".xls")
                        else list(pd.read_csv(_bootstrap.UPLOADS_DIR / name, nrows=3).columns)
                    )
                    cols_options = [str(c) for c in cols_options]
                except Exception:
                    cols_options = []

                def _multi(label: str, key: str, default: list) -> list:
                    safe_default = [d for d in (default or []) if d in cols_options]
                    return st.multiselect(
                        label, cols_options, default=safe_default,
                        key=f"schema_{name}_{key}",
                    )

                header_rows_str = st.text_input(
                    "header_rows (콤마 구분, 예: 0 또는 0,1)",
                    value=",".join(str(x) for x in (schema.get("header_rows") or [])),
                    key=f"schema_{name}_hrows",
                )
                key_cols = _multi("key_columns", "kcols", schema.get("key_columns") or [])
                year_cols = _multi("year_columns", "ycols", schema.get("year_columns") or [])
                val_cols = _multi("value_columns", "vcols", schema.get("value_columns") or [])
                cat_cols = _multi("category_columns", "ccols", schema.get("category_columns") or [])
                skip_rows_str = st.text_input(
                    "skip_rows (콤마 구분)",
                    value=",".join(str(x) for x in (schema.get("skip_rows") or [])),
                    key=f"schema_{name}_srows",
                )
                notes = st.text_input(
                    "notes", value=schema.get("notes", ""), key=f"schema_{name}_notes",
                )
                if st.button("💾 폼 → JSON 동기화", key=f"schema_{name}_sync_form"):
                    try:
                        new_schema = {
                            "header_rows": [int(x) for x in header_rows_str.split(",") if x.strip()],
                            "key_columns": key_cols,
                            "year_columns": year_cols,
                            "value_columns": val_cols,
                            "category_columns": cat_cols,
                            "skip_rows": [int(x) for x in skip_rows_str.split(",") if x.strip()],
                            "notes": notes,
                        }
                        st.session_state.excel_schema[name] = new_schema
                        st.toast(f"✏️ `{name}` 스키마 갱신", icon="💾")
                        st.rerun()
                    except Exception as e:
                        st.error(f"파싱 오류: {e}")

            with tab_json:
                json_text = st.text_area(
                    "JSON",
                    value=json.dumps(schema, ensure_ascii=False, indent=2),
                    height=200,
                    key=f"schema_{name}_json",
                )
                if st.button("💾 JSON 적용", key=f"schema_{name}_apply_json",
                             type="primary"):
                    try:
                        parsed = json.loads(json_text)
                        st.session_state.excel_schema[name] = parsed
                        st.toast(f"✏️ `{name}` 스키마 적용", icon="💾")
                        st.rerun()
                    except Exception as e:
                        st.error(f"JSON 파싱 실패: {e}")


# ============================================================
# 2. 작업 / 스킬
# ============================================================
st.markdown("##### 2️⃣ 작업 설명")
if state.skill:
    st.markdown(
        f"적용된 스킬: {badge(f'{state.skill.icon} {state.skill.name}', 'info')}",
        unsafe_allow_html=True,
    )
    st.caption(state.skill.description)
    st.caption(
        "사이드바의 **작업 설명** 텍스트는 스킬 템플릿의 `{task}` 자리에 삽입됩니다."
    )
else:
    st.caption("사이드바의 🛠 작업 설명을 직접 작성하거나, 사이드바 🧰 스킬 에서 골라 적용하세요.")

with st.expander("💡 예시 작업"):
    examples = [
        "두 파일을 합쳐서 region 별 amount 의 평균을 result.csv 로 저장",
        "비목 번호·이름별로 모든 연차의 예산을 합산하라",
        "각 파일에서 amount > 1000 인 행만 추려 filtered_<원본명>.csv 로 저장",
    ]
    for t in examples:
        st.markdown(f"- {t}")


gen_clicked = st.button(
    "⚡ pandas 코드 생성",
    type="primary",
    disabled=not (selected and state.endpoint and state.model and (state.task.strip() or state.skill)),
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

    detected = st.session_state.get("excel_schema", {})

    if state.skill:
        # use the skill's prompt
        system_prompt = state.skill.system_prompt
        user_prompt = render_template(
            state.skill.user_prompt_template,
            file_list=", ".join(selected),
            schema_json=json.dumps(detected, ensure_ascii=False, indent=2)
                        if detected else "(구조 분석 건너뜀)",
            task=state.task,
            file_name=", ".join(selected),
            raw_preview="",
            column_candidates="",
        )
    else:
        # ad-hoc — keep the original system prompt with explicit dtypes preview
        system_prompt = (
            "You are a Python data engineer. Write a single self-contained pandas script "
            "that accomplishes the user's task.\n\n"
            "RULES:\n"
            "- Output ONLY the Python code in ONE ```python``` block. No explanation.\n"
            "- Read inputs from current directory: pd.read_csv('file.csv'), pd.read_excel('file.xlsx').\n"
            "- Write outputs to current directory.\n"
            "- Use ONLY: pandas, numpy, openpyxl, and Python standard library.\n"
            "- No network, no subprocess, no eval/exec, no file ops outside cwd.\n"
            "- Use print() only for short summaries.\n\n"
            "INPUT FILES IN CURRENT DIRECTORY:\n" + "\n".join(schemas_lines)
            + (f"\n\nDETECTED STRUCTURE:\n{json.dumps(detected, ensure_ascii=False, indent=2)}"
               if detected else "")
        )
        user_prompt = state.task

    try:
        llm = resolve(state.endpoint, model=state.model)
        with st.spinner(f"`{state.model}` 로 코드 생성 중…"):
            resp = llm.chat([
                Message(role="system", content=system_prompt),
                Message(role="user", content=user_prompt),
            ])
        code = extract_code(resp.content) or resp.content
        st.session_state["excel_code"] = code
        st.session_state["excel_used_system"] = system_prompt
        st.session_state["excel_used_user"] = user_prompt
        st.session_state.pop("excel_result", None)
        st.toast("✅ 코드 생성됨", icon="⚡")
    except Exception as e:
        st.error(f"코드 생성 실패: {type(e).__name__}: {e}")


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
    timeout = state.timeout_seconds or 60
    mem_mb = state.memory_mb or 1024
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
# 4. 결과 + 스킬로 저장
# ============================================================
result = st.session_state.get("excel_result")
if result is not None:
    st.markdown("##### 4️⃣ 실행 결과")

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    c1.metric("상태", "✅ 성공" if result.ok else "❌ 실패")
    c2.metric("소요 시간", f"{result.elapsed:.2f}s")
    c3.metric("출력 파일", len(result.outputs))
    if c4.button(
        "💾 스킬로 저장",
        disabled=not result.ok,
        use_container_width=False,
        help="현재 작업·시스템·템플릿을 새 스킬로 저장",
    ):
        st.session_state["show_excel_save_dialog"] = True

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
                cc1, cc2, cc3, cc4 = st.columns([4, 2, 1.5, 2])
                cc1.markdown(f"**`{name}`**")
                cc2.caption(f"{len(data):,} bytes")
                cc3.download_button(
                    "⬇️", data=data, file_name=name, key=f"dl_{name}",
                    use_container_width=True, help="다운로드",
                )
                if cc4.button("📁 Files 에 저장", key=f"save_{name}", use_container_width=True):
                    try:
                        fm.save(name, data)
                        st.toast(f"📁 `{name}` Files 폴더에 저장", icon="💾")
                    except Exception as e:
                        st.error(f"저장 실패: {e}")

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


# ============================================================
# save-as-skill dialog
# ============================================================
@st.dialog("스킬로 저장")
def save_excel_skill_dialog():
    used_system = st.session_state.get("excel_used_system", "")
    used_user = st.session_state.get("excel_used_user", "")

    # Convert literal values back to placeholders for reuse
    template_seed = used_user
    schema_blob = json.dumps(st.session_state.get("excel_schema", {}),
                             ensure_ascii=False, indent=2)
    if schema_blob and schema_blob != "{}":
        template_seed = template_seed.replace(schema_blob, "{schema_json}")
    files_blob = ", ".join(st.session_state.get("excel_selected") or [])
    if files_blob:
        template_seed = template_seed.replace(files_blob, "{file_list}")
    if (state.task or "").strip():
        template_seed = template_seed.replace(state.task.strip(), "{task}")

    with st.form("save_excel_skill_form", border=False):
        slug = st.text_input("슬러그", placeholder="예: my-budget-summary")
        name = st.text_input("이름", placeholder="예: 우리 부서 예산 요약")
        icon = st.text_input("아이콘", value="📊", max_chars=4)
        description = st.text_input("설명 (한 줄)")
        tags_str = st.text_input("태그 (쉼표 구분)", placeholder="예: excel, budget, ko")
        st.caption("system_prompt 는 방금 사용된 프롬프트로 저장됩니다 (편집 불가).")
        with st.expander("system_prompt 미리보기"):
            st.code(used_system or "(비어있음)", language="text")
        user_template = st.text_area(
            "user_prompt_template",
            value=template_seed,
            height=180,
            help="자리표시자: {task}, {file_list}, {schema_json}",
        )

        cx, cy = st.columns(2)
        cancel = cx.form_submit_button("취소", use_container_width=True)
        save = cy.form_submit_button("💾 저장", type="primary", use_container_width=True)

    if cancel:
        st.session_state.pop("show_excel_save_dialog", None)
        st.rerun()
    if save:
        try:
            tags = tuple(t.strip() for t in (tags_str or "").split(",") if t.strip())
            new = Skill(
                slug=slug.strip(),
                name=name.strip() or slug.strip(),
                icon=icon.strip() or "📊",
                kind="excel-pandas",
                description=description.strip(),
                system_prompt=used_system,
                user_prompt_template=user_template,
                tags=tags,
                default_endpoint=state.endpoint.slug if state.endpoint else None,
                default_model=state.model or None,
            )
            saved = get_registry().save(new)
            st.toast(f"💾 `{saved.slug}` 저장", icon="🧰")
            st.session_state.pop("show_excel_save_dialog", None)
            st.rerun()
        except Exception as e:
            st.error(f"저장 실패: {type(e).__name__}: {e}")


if st.session_state.get("show_excel_save_dialog"):
    save_excel_skill_dialog()
