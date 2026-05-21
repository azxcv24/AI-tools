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


def read_tabular_schema(name: str, data: bytes) -> dict:
    """Return columns / dtypes / cell stats. Used to give the LLM context."""
    e = ext_of(name)
    try:
        if e in ("xlsx", "xls"):
            df_head = pd.read_excel(BytesIO(data), nrows=5)
            df_full = pd.read_excel(BytesIO(data), header=None, dtype=object)
        elif e == "tsv":
            df_head = pd.read_csv(BytesIO(data), sep="\t", nrows=5)
            df_full = pd.read_csv(BytesIO(data), sep="\t", header=None, dtype=object, keep_default_na=False)
        else:
            df_head = pd.read_csv(BytesIO(data), nrows=5)
            df_full = pd.read_csv(BytesIO(data), header=None, dtype=object, keep_default_na=False)
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
    return {
        "columns": list(df_head.columns),
        "dtypes": {c: str(df_head[c].dtype) for c in df_head.columns},
        "head": df_head.head(3),
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
            cols = ", ".join(f"`{c}` ({info['dtypes'][c]})" for c in info["columns"])
            head_str = info["head"].to_csv(index=False).strip()
            blocks.append(
                f"[file: {name}] (spreadsheet)\n"
                f"  shape: {info['rows_total']} × {info['cols_total']}  ·  "
                f"text rows={info['rows_with_data']} cols={info['cols_with_data']} cells={info['cells_with_data']}\n"
                f"  columns: {cols}\n"
                f"  head:\n```csv\n{head_str}\n```"
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
        for name, data in atts.items():
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"{icon_for(name)} `{name}`  ·  {fmt_size(len(data))}")
            if c2.button("✕", key=f"rm_{name}", help="컨텍스트에서 제거"):
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
    for m in st.session_state.chat_messages:
        with st.chat_message(m["role"]):
            # Show attachments-as-chips for user messages
            if m.get("new_attachments"):
                chips = " ".join(
                    f'<span class="lstudio-badge info">{icon_for(n)} {n}</span>'
                    for n in m["new_attachments"]
                )
                st.markdown(chips, unsafe_allow_html=True)
            st.markdown(m["content"])
            # Show sandbox output files
            if m.get("new_outputs"):
                for out_name in m["new_outputs"]:
                    out_bytes = st.session_state.chat_attachments.get(out_name)
                    if out_bytes is None:
                        continue
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([4, 2, 2])
                        c1.markdown(f"**{icon_for(out_name)} `{out_name}`**")
                        c2.caption(f"{fmt_size(len(out_bytes))}")
                        c3.download_button(
                            "⬇️ 다운로드",
                            data=out_bytes,
                            file_name=out_name,
                            key=f"dl_{m.get('id', id(m))}_{out_name}",
                            use_container_width=True,
                        )
                        # preview if tabular
                        if is_tabular(out_name):
                            try:
                                e = ext_of(out_name)
                                if e in ("xlsx", "xls"):
                                    dfp = pd.read_excel(BytesIO(out_bytes), nrows=20)
                                elif e == "tsv":
                                    dfp = pd.read_csv(BytesIO(out_bytes), sep="\t", nrows=20)
                                else:
                                    dfp = pd.read_csv(BytesIO(out_bytes), nrows=20)
                                with st.expander("👀 미리보기 (상위 20행)", expanded=False):
                                    st.dataframe(dfp, use_container_width=True, hide_index=True)
                            except Exception:
                                pass

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
        if just_added:
            chips = " ".join(
                f'<span class="lstudio-badge info">{icon_for(n)} {n}</span>'
                for n in just_added
            )
            st.markdown(chips, unsafe_allow_html=True)
        st.markdown(user_input)

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
            "사용자가 데이터 처리·집계·변환을 요청하면, 한 블록의 자족적인 ```python``` 코드를 작성하세요. "
            "현재 디렉토리에서 위에 명시된 파일명으로 직접 읽고, 결과는 같은 디렉토리에 새 파일로 저장 "
            "(예: `result.xlsx` → `df.to_excel('result.xlsx', index=False, engine='openpyxl')`). "
            "pandas / numpy / openpyxl / Python 표준 라이브러리만 사용. "
            "네트워크·subprocess·eval/exec 금지. 코드 외의 설명은 코드 블록 앞·뒤에 짧게만."
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
    code = extract_code(full) if has_executable_intent(st.session_state.chat_attachments) else None
    sandbox_elapsed: float | None = None
    if code:
        with st.chat_message("assistant"):
            with st.status("🛠️ 격리 환경에서 실행 중…", expanded=True) as status:
                result = run_pandas_code(
                    code=code,
                    inputs=dict(st.session_state.chat_attachments),
                    timeout_seconds=60,
                    memory_limit_mb=1024,
                )
                sandbox_elapsed = result.elapsed
                if result.ok:
                    status.update(
                        label=f"✅ 실행 완료 ({result.elapsed:.2f}s, 신규 파일 {len(result.outputs)}개)",
                        state="complete",
                        expanded=False,
                    )
                else:
                    status.update(
                        label=f"❌ 실행 실패 ({result.error or 'returncode='+str(result.return_code)})",
                        state="error",
                        expanded=True,
                    )
                if result.stdout.strip():
                    st.code(result.stdout, language="text")
                if result.stderr.strip():
                    st.code(result.stderr, language="text")

            # Stash new outputs into session attachments + record on assistant msg
            new_outs: list[str] = []
            for name, data in result.outputs.items():
                st.session_state.chat_attachments[name] = data
                new_outs.append(name)
            if new_outs:
                assistant_msg["new_outputs"] = new_outs
                # show each output file inline
                for out_name in new_outs:
                    out_bytes = st.session_state.chat_attachments[out_name]
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([4, 2, 2])
                        c1.markdown(f"**{icon_for(out_name)} `{out_name}`**")
                        c2.caption(f"{fmt_size(len(out_bytes))}")
                        c3.download_button(
                            "⬇️ 다운로드",
                            data=out_bytes,
                            file_name=out_name,
                            key=f"dl_new_{out_name}",
                            use_container_width=True,
                        )
                        if is_tabular(out_name):
                            try:
                                e = ext_of(out_name)
                                if e in ("xlsx", "xls"):
                                    dfp = pd.read_excel(BytesIO(out_bytes), nrows=20)
                                elif e == "tsv":
                                    dfp = pd.read_csv(BytesIO(out_bytes), sep="\t", nrows=20)
                                else:
                                    dfp = pd.read_csv(BytesIO(out_bytes), nrows=20)
                                with st.expander("👀 미리보기 (상위 20행)", expanded=True):
                                    st.dataframe(dfp, use_container_width=True, hide_index=True)
                            except Exception:
                                pass

    st.session_state.last_stats = {
        "elapsed": elapsed,
        "chunks": chunks,
        "output_tokens": out_tokens,
        "sandbox_elapsed": sandbox_elapsed,
    }
    st.rerun()
