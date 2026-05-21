"""Unified Chat page — ChatGPT-style.

Drop files into the chat input → they become part of the conversation context.
Spreadsheets are auto-analyzed (schema + cell counts). If the assistant emits a
```python``` block and any tabular data file is in context, the code is run in
an isolated sandbox automatically and its outputs (new files) appear as a
follow-up message with download / preview.
"""
import re
import sys
import time
from datetime import datetime
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

st.set_page_config(page_title="Chat · LLM Studio", page_icon="💬", layout="wide")
inject_global_css()
sidebar_brand()

page_header(
    "💬",
    "Chat",
    "파일을 끌어다 놓고 대화하세요. 엑셀은 자동 분석되고, pandas 코드가 생성되면 격리 환경에서 자동 실행됩니다.",
)


# ============================================================
# constants
# ============================================================
TEXT_EXTS = {
    "txt", "md", "markdown", "json", "jsonl", "yaml", "yml", "toml",
    "py", "js", "ts", "tsx", "jsx", "go", "rs", "java", "c", "cpp", "h", "hpp",
    "sh", "bash", "zsh", "html", "css", "xml", "log", "ini", "cfg", "conf", "env",
    "sql", "rb", "php", "kt", "swift", "lua", "r",
}
TABULAR_EXTS = {"xlsx", "xls", "csv", "tsv"}
TEXT_PER_FILE_LIMIT = 50 * 1024
TEXT_TOTAL_LIMIT = 200 * 1024

CODE_BLOCK_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)
GENERIC_CODE_BLOCK_RE = re.compile(r"```\s*\n(.*?)```", re.DOTALL)


# ============================================================
# helpers
# ============================================================

def ext_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def is_tabular(name: str) -> bool:
    return ext_of(name) in TABULAR_EXTS


def is_text(name: str) -> bool:
    return ext_of(name) in TEXT_EXTS


def fmt_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b/1024:.1f} KB"
    return f"{b/1024/1024:.1f} MB"


def icon_for(name: str) -> str:
    e = ext_of(name)
    return {
        "xlsx": "📗", "xls": "📗",
        "csv": "📊", "tsv": "📊",
        "json": "🗂️", "yaml": "🗂️", "yml": "🗂️", "toml": "🗂️",
        "md": "📝", "txt": "📝",
        "py": "🐍",
        "pdf": "📕",
    }.get(e, "📄")


def _flatten_multi_cols(columns) -> list[str]:
    """Flatten pandas MultiIndex columns to underscore-joined strings.

    Drops 'Unnamed: …' fillers that pandas inserts for merged cells, and
    de-duplicates the result by appending `_2`, `_3`, … so downstream code
    can always select columns by a single unique name.
    """
    raw: list[str] = []
    for c in columns:
        if isinstance(c, tuple):
            parts = [
                str(x).strip() for x in c
                if str(x).strip() and not str(x).startswith("Unnamed")
            ]
            raw.append("_".join(parts) if parts else "col")
        else:
            raw.append(str(c))
    seen: dict[str, int] = {}
    out: list[str] = []
    for name in raw:
        if name in seen:
            seen[name] += 1
            out.append(f"{name}_{seen[name]}")
        else:
            seen[name] = 1
            out.append(name)
    return out


def read_tabular_schema(name: str, data: bytes) -> dict:
    """Return raw rows + single/multi-header column candidates + stats.

    Sending the LLM the *raw* first 15 rows (header=None) lets it spot
    merged-header patterns, forward-fill needs, and subtotal rows that
    a single-header view of head() would hide.
    """
    e = ext_of(name)
    try:
        if e in ("xlsx", "xls"):
            raw = pd.read_excel(BytesIO(data), header=None, nrows=15, dtype=object)
            df_full = pd.read_excel(BytesIO(data), header=None, dtype=object)
            cols_single = list(pd.read_excel(BytesIO(data), header=0, nrows=3).columns)
            try:
                cols_multi = _flatten_multi_cols(
                    pd.read_excel(BytesIO(data), header=[0, 1], nrows=3).columns
                )
            except Exception:
                cols_multi = []
        elif e == "tsv":
            raw = pd.read_csv(BytesIO(data), sep="\t", header=None, nrows=15,
                              dtype=object, keep_default_na=False)
            df_full = pd.read_csv(BytesIO(data), sep="\t", header=None,
                                  dtype=object, keep_default_na=False)
            cols_single = list(pd.read_csv(BytesIO(data), sep="\t", nrows=3).columns)
            cols_multi = []
        else:
            raw = pd.read_csv(BytesIO(data), header=None, nrows=15,
                              dtype=object, keep_default_na=False)
            df_full = pd.read_csv(BytesIO(data), header=None,
                                  dtype=object, keep_default_na=False)
            cols_single = list(pd.read_csv(BytesIO(data), nrows=3).columns)
            cols_multi = []
    except Exception as e:  # noqa: F841
        return {"error": str(e)}

    def has_text(v):
        if v is None:
            return False
        if isinstance(v, float) and pd.isna(v):
            return False
        s = str(v).strip()
        return s != "" and s.lower() != "nan"

    mask = df_full.map(has_text) if hasattr(df_full, "map") else df_full.applymap(has_text)
    rows_total, cols_total = df_full.shape
    raw_csv = raw.fillna("").to_csv(index=False, header=False).strip()

    return {
        "raw_preview": raw_csv,
        "cols_single_header": [str(c) for c in cols_single],
        "cols_multi_header": [str(c) for c in cols_multi],
        "rows_total": int(rows_total),
        "cols_total": int(cols_total),
        "rows_with_data": int(mask.any(axis=1).sum()),
        "cols_with_data": int(mask.any(axis=0).sum()),
        "cells_with_data": int(mask.sum().sum()),
    }


def read_text_truncated(data: bytes) -> tuple[str, bool]:
    truncated = len(data) > TEXT_PER_FILE_LIMIT
    snippet = data[:TEXT_PER_FILE_LIMIT] if truncated else data
    try:
        return snippet.decode("utf-8"), truncated
    except UnicodeDecodeError:
        return snippet.decode("utf-8", errors="replace"), truncated


def build_file_context(attachments: dict[str, bytes]) -> str:
    """Build a system-prompt suffix describing every file currently in context."""
    if not attachments:
        return ""
    blocks: list[str] = []
    total_text = 0
    for name, data in attachments.items():
        e = ext_of(name)
        if e in TABULAR_EXTS:
            info = read_tabular_schema(name, data)
            if "error" in info:
                blocks.append(f"[file: {name}] (읽기 실패: {info['error']})")
                continue
            blocks.append(
                f"[file: {name}] (spreadsheet)\n"
                f"  shape: {info['rows_total']} × {info['cols_total']}  ·  "
                f"text rows={info['rows_with_data']} cols={info['cols_with_data']} "
                f"cells={info['cells_with_data']}\n"
                f"  columns when read with header=0:\n    {info['cols_single_header']}\n"
                + (f"  columns when read with header=[0,1] (flattened):\n    "
                   f"{info['cols_multi_header']}\n"
                   if info.get('cols_multi_header') else "")
                + f"  raw first 15 rows (header=None, CSV):\n"
                  f"```csv\n{info['raw_preview']}\n```"
            )
        elif e in TEXT_EXTS:
            text, truncated = read_text_truncated(data)
            if total_text + len(text) > TEXT_TOTAL_LIMIT:
                text = text[: max(0, TEXT_TOTAL_LIMIT - total_text)]
                truncated = True
            total_text += len(text)
            tail = "  (truncated)" if truncated else ""
            blocks.append(f"[file: {name}]{tail}\n```\n{text}\n```")
        else:
            blocks.append(f"[file: {name}] (binary, {fmt_size(len(data))} — content not shown)")
    return (
        "현재 대화에 첨부된 파일 목록과 메타데이터입니다. 코드를 작성할 때는 "
        "이 파일들을 현재 디렉토리에서 같은 이름으로 읽을 수 있다고 가정하세요.\n\n"
        + "\n\n".join(blocks)
    )


def extract_code(text: str) -> str | None:
    m = CODE_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    m = GENERIC_CODE_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def has_executable_intent(attachments: dict[str, bytes]) -> bool:
    """Decide whether to auto-run generated code: only if any tabular file is present."""
    return any(is_tabular(n) for n in attachments)


# ============================================================
# unified file card — used for both input attachments and sandbox outputs
# ============================================================

def render_file_card(name: str, data: bytes, *, key_prefix: str, expanded: bool = False) -> None:
    """Render a bordered file card: name + size + download + tabular preview."""
    with st.container(border=True):
        c1, c2, c3 = st.columns([4, 2, 2])
        c1.markdown(f"**{icon_for(name)} `{name}`**")
        c2.caption(fmt_size(len(data)))
        c3.download_button(
            "⬇️ 다운로드",
            data=data,
            file_name=name,
            key=f"{key_prefix}_dl_{name}",
            use_container_width=True,
        )
        if is_tabular(name):
            try:
                e = ext_of(name)
                if e in ("xlsx", "xls"):
                    dfp = pd.read_excel(BytesIO(data), nrows=30)
                elif e == "tsv":
                    dfp = pd.read_csv(BytesIO(data), sep="\t", nrows=30)
                else:
                    dfp = pd.read_csv(BytesIO(data), nrows=30)
                with st.expander(f"👀 미리보기 (상위 30행 · 전체 {len(data):,} bytes)",
                                 expanded=expanded):
                    st.dataframe(dfp, use_container_width=True, hide_index=True)
            except Exception as e:
                with st.expander("👀 미리보기 (읽기 실패)", expanded=False):
                    st.caption(f"`{type(e).__name__}: {e}`")
        elif is_text(name):
            try:
                text, truncated = read_text_truncated(data)
                with st.expander(f"👀 텍스트 미리보기{' (truncated)' if truncated else ''}",
                                 expanded=False):
                    st.code(text[:5000], language=ext_of(name) or "text")
            except Exception:
                pass


# ============================================================
# session state
# ============================================================
if "chat_messages" not in st.session_state:
    # each msg: {role, content, [new_attachments?], [new_outputs?]}
    st.session_state.chat_messages = []
if "chat_attachments" not in st.session_state:
    # Cumulative: every file that's been attached or produced as sandbox output.
    # Used to build context + for "방금 그 파일" follow-ups.
    st.session_state.chat_attachments = {}  # name -> bytes


# ============================================================
# sidebar
# ============================================================
state = render_sidebar("chat", kinds=["chat-system", "excel-pandas"])

with st.sidebar:
    st.divider()
    st.markdown("##### 📦 세션 파일")
    atts: dict[str, bytes] = st.session_state.chat_attachments
    if not atts:
        st.caption("아직 첨부된 파일이 없습니다.")
    else:
        st.caption(f"{len(atts)}개 · 본문 카드에서 미리보기 / 다운로드")
        for name, data in atts.items():
            c1, c2, c3 = st.columns([5, 1, 1])
            c1.markdown(f"{icon_for(name)} `{name}`")
            c1.caption(fmt_size(len(data)))
            c2.download_button(
                "⬇️",
                data=data,
                file_name=name,
                key=f"sb_dl_{name}",
                help="다운로드",
                use_container_width=True,
            )
            if c3.button("✕", key=f"rm_{name}", help="컨텍스트에서 제거",
                         use_container_width=True):
                st.session_state.chat_attachments.pop(name, None)
                st.toast(f"제거: {name}", icon="🗑️")
                st.rerun()

    st.divider()
    st.markdown("##### 액션")
    c1, c2 = st.columns(2)
    if c1.button("🆕 새 대화", use_container_width=True):
        st.session_state.chat_messages = []
        st.session_state.chat_attachments = {}
        st.session_state.pop("last_stats", None)
        st.rerun()
    has_msgs = bool(st.session_state.chat_messages)
    if has_msgs:
        # build markdown export
        md = f"# Chat — {datetime.now():%Y-%m-%d %H:%M}\n\n"
        md += (
            f"_endpoint: `{state.endpoint.slug if state.endpoint else '-'}` · "
            f"model: `{state.model}`_\n\n"
        )
        for m in st.session_state.chat_messages:
            md += f"## {m['role']}\n\n{m['content']}\n\n"
            if m.get("new_attachments"):
                md += f"_(첨부: {', '.join(m['new_attachments'])})_\n\n"
            if m.get("new_outputs"):
                md += f"_(생성된 파일: {', '.join(m['new_outputs'])})_\n\n"
        c2.download_button(
            "💾 .md",
            data=md.encode("utf-8"),
            file_name=f"chat_{datetime.now():%Y%m%d_%H%M%S}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    else:
        c2.button("💾 .md", disabled=True, use_container_width=True)


# ============================================================
# main area — replay history
# ============================================================
endpoint_label = state.endpoint.name if state.endpoint else "엔드포인트 미선택"

if not st.session_state.chat_messages:
    hint_parts = [f"`{endpoint_label}` · `{state.model or '모델 미선택'}`"]
    if state.skill:
        hint_parts.append(f"🧰 `{state.skill.name}`")
    if st.session_state.chat_attachments:
        hint_parts.append(f"📎 {len(st.session_state.chat_attachments)}개 첨부")
    empty_state(
        icon="💬",
        title="대화를 시작하세요",
        hint="  ·  ".join(hint_parts) + "  ·  파일은 아래 📎 버튼이나 드래그-드롭",
    )
else:
    for mi, m in enumerate(st.session_state.chat_messages):
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            # Input attachments (user message) — preview cards
            if m.get("new_attachments"):
                for att_name in m["new_attachments"]:
                    att_bytes = st.session_state.chat_attachments.get(att_name)
                    if att_bytes is None:
                        st.caption(f"📎 `{att_name}` (세션에서 제거됨)")
                        continue
                    render_file_card(
                        att_name, att_bytes,
                        key_prefix=f"hist_{mi}_in",
                        expanded=False,
                    )
            # Sandbox output files (assistant message)
            if m.get("new_outputs"):
                for out_name in m["new_outputs"]:
                    out_bytes = st.session_state.chat_attachments.get(out_name)
                    if out_bytes is None:
                        continue
                    render_file_card(
                        out_name, out_bytes,
                        key_prefix=f"hist_{mi}_out",
                        expanded=False,
                    )
            # Sandbox status/notes
            if m.get("sandbox_note"):
                st.caption(f"🛠️ {m['sandbox_note']}")
            if m.get("sandbox_stdout"):
                with st.expander("📤 stdout", expanded=False):
                    st.code(m["sandbox_stdout"], language="text")
            if m.get("sandbox_stderr"):
                with st.expander("⚠️ stderr", expanded=False):
                    st.code(m["sandbox_stderr"], language="text")

    stats = st.session_state.get("last_stats")
    if stats:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("응답 시간", f"{stats['elapsed']:.1f}s")
        c2.metric("출력 토큰", stats.get("output_tokens") or "—")
        c3.metric("청크 수", stats["chunks"])
        c4.metric("실행 시간", f"{stats.get('sandbox_elapsed', 0):.2f}s" if stats.get("sandbox_elapsed") else "—")


# ============================================================
# input area — file uploader + chat input
# ============================================================
st.markdown("##### 📎 파일 첨부 (선택)")
new_files = st.file_uploader(
    "이번 메시지에 추가할 파일 (Excel · CSV · 텍스트 · …)",
    accept_multiple_files=True,
    key=f"chat_uploader__{len(st.session_state.chat_messages)}",
    label_visibility="collapsed",
)

prompt_placeholder = f"{endpoint_label} / {state.model or '모델 미선택'} 에게 메시지…"
user_input = st.chat_input(prompt_placeholder)


# ============================================================
# message handling
# ============================================================
if user_input:
    if not state.endpoint:
        st.error("엔드포인트가 없습니다. Settings 에서 추가하세요.")
        st.stop()
    if not state.model:
        st.error("모델을 먼저 선택하세요.")
        st.stop()

    # 1) Add freshly uploaded files into session-wide context
    just_added: list[str] = []
    if new_files:
        for f in new_files:
            data = f.getvalue()
            st.session_state.chat_attachments[f.name] = data
            just_added.append(f.name)

    # 2) Record user message
    user_msg = {
        "role": "user",
        "content": user_input,
        "new_attachments": just_added or None,
    }
    st.session_state.chat_messages.append(user_msg)

    with st.chat_message("user"):
        st.markdown(user_input)
        if just_added:
            for att_name in just_added:
                att_bytes = st.session_state.chat_attachments.get(att_name)
                if att_bytes is not None:
                    render_file_card(
                        att_name, att_bytes,
                        key_prefix=f"new_user_{len(st.session_state.chat_messages)}",
                        expanded=True,
                    )

    # 3) Build LLM messages
    try:
        llm = resolve(state.endpoint, model=state.model)
    except Exception as e:
        st.error(f"엔드포인트 초기화 실패: {e}")
        st.stop()

    sys_parts: list[str] = []
    if state.system_prompt.strip():
        sys_parts.append(state.system_prompt.strip())
    file_ctx = build_file_context(st.session_state.chat_attachments)
    if file_ctx:
        sys_parts.append(file_ctx)
    # If tabular files are present, nudge the LLM toward executable pandas code.
    if has_executable_intent(st.session_state.chat_attachments):
        sys_parts.append(
            "이 대화에는 표 형식 파일(엑셀·CSV)이 첨부되어 있다. 사용자가 분석·요약·집계·변환·"
            "병합·필터·정렬 등 **어떤 데이터 작업이라도 요청하면**, 답변은 반드시 다음 형식이어야 한다:\n"
            "\n"
            "**규칙**\n"
            "1. 무엇을 할지 한두 문장 요약 후 하나의 자족적인 ```python``` 코드 블록만.\n"
            "2. 파일은 위에 명시된 파일명으로 현재 디렉토리에서 직접 읽기.\n"
            "3. **헤더 판단**: 위 컨텍스트의 `raw first 15 rows` + `columns when read with header=[0,1]` "
            "결과를 보고 다단 헤더 여부를 판단. 다단이면 아래 헬퍼를 그대로 복사해 사용:\n"
            "\n"
            "```python\n"
            "def flatten_cols(cols):\n"
            "    raw = []\n"
            "    for c in cols:\n"
            "        if isinstance(c, tuple):\n"
            "            parts = [str(x).strip() for x in c\n"
            "                     if str(x).strip() and not str(x).startswith('Unnamed')]\n"
            "            raw.append('_'.join(parts) if parts else 'col')\n"
            "        else:\n"
            "            raw.append(str(c))\n"
            "    seen = {}\n"
            "    out = []\n"
            "    for n in raw:\n"
            "        if n in seen:\n"
            "            seen[n] += 1\n"
            "            out.append(f'{n}_{seen[n]}')\n"
            "        else:\n"
            "            seen[n] = 1\n"
            "            out.append(n)\n"
            "    return out\n"
            "\n"
            "df = pd.read_excel('파일명.xlsx', header=[0, 1])\n"
            "df.columns = flatten_cols(df.columns)\n"
            "```\n"
            "\n"
            "   이 헬퍼는 중복 이름을 `_2`, `_3` 으로 자동 dedupe 하므로 그 뒤에 컬럼명을 다시 "
            "rename 하지 마라. **컨텍스트에 표시된 `cols_multi` 와 동일한 이름이 나온다.**\n"
            "4. 키 컬럼이 병합된 셀로 인해 NaN 이어지면 `df[키컬럼] = df[키컬럼].ffill()`.\n"
            "5. `소 계` / `합계` / `총계` / `총합` 같이 텍스트만 든 합계 행은 그룹 연산 전 제외 "
            "(`df = df[~df[키].astype(str).str.strip().isin(['소 계','합계','총계','총합'])]`).\n"
            "6. **숫자 컬럼 강제 변환**: 다단 헤더 엑셀은 모든 컬럼이 object 로 들어올 수 있다. "
            "키 컬럼을 뺀 나머지 후보 컬럼을 `pd.to_numeric(df[col], errors='coerce')` 로 변환한 뒤 "
            "`select_dtypes(include='number')` 로 집계 대상 컬럼을 잡아라. 그러지 않으면 출력에 "
            "한두 컬럼만 남게 된다.\n"
            "7. 그룹 연산 시 키 컬럼의 dtype 이 object 일 수 있으니 `astype(str)` 적절히 사용.\n"
            "8. **반드시 결과를 새 파일로 저장**: 기본 `result.xlsx` "
            "(`df.to_excel('result.xlsx', index=False, engine='openpyxl')`).\n"
            "9. `print()` 으로 행 수·합계 한 줄 요약 출력.\n"
            "10. 사용자가 명백히 '코드 없이 보여만 줘' 일 때만 코드 생략 가능.\n"
            "\n"
            "허용 라이브러리: pandas / numpy / openpyxl / Python 표준 라이브러리만. "
            "네트워크·subprocess·eval/exec·경로 탈출 금지."
        )
    system_combined = "\n\n---\n\n".join(sys_parts)

    msgs: list[Message] = []
    if system_combined:
        msgs.append(Message(role="system", content=system_combined))
    msgs += [Message(role=m["role"], content=m["content"]) for m in st.session_state.chat_messages]

    # 4) Stream assistant reply
    with st.chat_message("assistant"):
        placeholder = st.empty()
        full = ""
        chunks = 0
        t0 = time.time()
        last_raw = None
        try:
            for chunk in llm.stream(msgs):
                full += chunk.delta
                chunks += 1
                last_raw = chunk.raw
                placeholder.markdown(full + " ▌")
            placeholder.markdown(full)
        except Exception as e:
            st.error(f"호출 실패: {e}")
            st.stop()

    elapsed = time.time() - t0
    out_tokens = (last_raw or {}).get("eval_count") if isinstance(last_raw, dict) else None

    assistant_msg = {"role": "assistant", "content": full}
    st.session_state.chat_messages.append(assistant_msg)

    # 5) Auto sandbox execution (Code Interpreter behavior)
    tabular_present = has_executable_intent(st.session_state.chat_attachments)
    code = extract_code(full) if tabular_present else None
    sandbox_elapsed: float | None = None

    if tabular_present and not code:
        # LLM gave only prose — explain why no result card appears.
        note = (
            "표 파일이 첨부돼 있지만 응답에 ```python``` 코드 블록이 없어 sandbox 실행을 건너뛰었습니다. "
            "결과 파일을 받으려면 '결과 엑셀로 저장해줘' / '비목별 합산 해서 result.xlsx 로 만들어줘' "
            "같이 명시적으로 요청하세요."
        )
        assistant_msg["sandbox_note"] = note
        with st.chat_message("assistant"):
            st.info(f"ℹ️ {note}")

    elif code:
        with st.chat_message("assistant"):
            with st.status("🛠️ 격리 환경에서 실행 중…", expanded=True) as status:
                result = run_pandas_code(
                    code=code,
                    inputs=dict(st.session_state.chat_attachments),
                    timeout_seconds=60,
                    memory_limit_mb=1024,
                )
                sandbox_elapsed = result.elapsed

                # ----- status header -----
                if result.ok and result.outputs:
                    status.update(
                        label=f"✅ 실행 완료 — {result.elapsed:.2f}s · 신규 파일 {len(result.outputs)}개",
                        state="complete",
                        expanded=True,
                    )
                elif result.ok and not result.outputs:
                    status.update(
                        label=f"⚠️ 실행 성공했지만 신규 파일이 없음 ({result.elapsed:.2f}s) "
                              f"— `to_excel` / `to_csv` 호출이 누락된 듯",
                        state="complete",
                        expanded=True,
                    )
                else:
                    status.update(
                        label=f"❌ 실행 실패 ({result.error or 'returncode='+str(result.return_code)})",
                        state="error",
                        expanded=True,
                    )

                # ----- stdout / stderr -----
                if result.stdout.strip():
                    st.markdown("**stdout**")
                    st.code(result.stdout, language="text")
                if result.stderr.strip():
                    st.markdown("**stderr**")
                    st.code(result.stderr, language="text")
                if result.ok and not result.outputs and not result.stdout.strip():
                    st.caption(
                        "코드는 정상 종료됐는데 표준 출력도 새 파일도 없어요. "
                        "다음 메시지에서 '결과를 result.xlsx 로 저장해줘' 등으로 다시 요청하세요."
                    )

            # ----- persist into assistant msg for history replay -----
            if result.stdout.strip():
                assistant_msg["sandbox_stdout"] = result.stdout
            if result.stderr.strip():
                assistant_msg["sandbox_stderr"] = result.stderr
            if not result.ok:
                assistant_msg["sandbox_note"] = (
                    f"실행 실패: {result.error or 'returncode='+str(result.return_code)}"
                )

            # ----- stash new outputs + render cards -----
            new_outs: list[str] = []
            for name, data in result.outputs.items():
                st.session_state.chat_attachments[name] = data
                new_outs.append(name)
            if new_outs:
                assistant_msg["new_outputs"] = new_outs
                st.markdown("**📦 생성된 파일**")
                for out_name in new_outs:
                    out_bytes = st.session_state.chat_attachments[out_name]
                    render_file_card(
                        out_name, out_bytes,
                        key_prefix=f"new_out_{len(st.session_state.chat_messages)}",
                        expanded=True,
                    )

    st.session_state.last_stats = {
        "elapsed": elapsed,
        "chunks": chunks,
        "output_tokens": out_tokens,
        "sandbox_elapsed": sandbox_elapsed,
    }
    st.rerun()
