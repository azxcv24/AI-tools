import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401,E402

import time  # noqa: E402
from datetime import datetime  # noqa: E402

import streamlit as st  # noqa: E402

from components import (  # noqa: E402
    badge,
    empty_state,
    inject_global_css,
    page_header,
    sidebar_brand,
)
from shared.llm import Message, get_provider, list_providers  # noqa: E402
from shared.storage import FileManager  # noqa: E402

st.set_page_config(page_title="Chat · LLM Studio", page_icon="💬", layout="wide")
inject_global_css()
sidebar_brand()

page_header("💬", "Chat", "Provider · 모델 · 첨부 파일을 골라 대화하세요. 결과는 Files 폴더 또는 .md 로 저장됩니다.")


# ============================================================
# helpers
# ============================================================
TEXT_EXTS = {
    "txt", "md", "markdown", "csv", "tsv", "json", "jsonl", "yaml", "yml", "toml",
    "py", "js", "ts", "tsx", "jsx", "go", "rs", "java", "c", "cpp", "h", "hpp",
    "sh", "bash", "zsh", "html", "css", "xml", "log", "ini", "cfg", "conf", "env",
    "sql", "rb", "php", "kt", "swift", "lua", "r", "scala",
}
MAX_PER_FILE = 50 * 1024        # 50 KB
MAX_TOTAL    = 200 * 1024       # 200 KB


def is_text_file(name: str) -> bool:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext in TEXT_EXTS


def fmt_size(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b/1024:.1f} KB"
    return f"{b/1024/1024:.1f} MB"


def read_attachment(fm: FileManager, name: str) -> tuple[str, bool]:
    """Read a file as text, truncating at MAX_PER_FILE. Returns (text, truncated)."""
    raw = fm.read(name)
    truncated = len(raw) > MAX_PER_FILE
    if truncated:
        raw = raw[:MAX_PER_FILE]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return text, truncated


def build_attachment_context(fm: FileManager, names: list[str]) -> tuple[str, list[dict]]:
    """Concatenate selected files into a single context block. Stops at MAX_TOTAL.
    Returns (context_string, info_per_file)."""
    parts: list[str] = []
    info: list[dict] = []
    total = 0
    for n in names:
        try:
            text, truncated = read_attachment(fm, n)
        except Exception as e:
            info.append({"name": n, "size": 0, "skipped": True, "reason": str(e)})
            continue
        if total + len(text) > MAX_TOTAL:
            allowed = max(0, MAX_TOTAL - total)
            text = text[:allowed]
            truncated = True
        parts.append(f"[file: {n}]\n{text}")
        total += len(text)
        info.append({"name": n, "size": len(text), "skipped": False, "truncated": truncated})
        if total >= MAX_TOTAL:
            break
    if not parts:
        return "", info
    return "\n\n---\n\n".join(parts), info


# ============================================================
# model discovery
# ============================================================
@st.cache_data(ttl=300, show_spinner="모델 리스트 조회 중…")
def fetch_models(provider_name: str) -> tuple[list[str], str | None]:
    try:
        llm = get_provider(provider_name, model="-")
        return list(llm.list_models()), None
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


# ============================================================
# sidebar
# ============================================================
fm = FileManager(_bootstrap.UPLOADS_DIR)

with st.sidebar:
    st.markdown("##### 모델 설정")
    providers = list_providers()
    provider_name = st.selectbox(
        "Provider",
        providers,
        index=providers.index("ollama") if "ollama" in providers else 0,
    )

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
        st.info("사용 가능한 모델이 없습니다.")
        model = st.text_input("Model (수동)", value="", label_visibility="collapsed")
    else:
        key = f"selected_model__{provider_name}"
        prev = st.session_state.get(key)
        idx = models.index(prev) if prev in models else 0
        model = st.selectbox("Model", models, index=idx,
                             key=f"select_{provider_name}", label_visibility="collapsed")
        st.session_state[key] = model

    st.divider()
    st.markdown("##### 프롬프트")
    system = st.text_area(
        "System prompt",
        value="You are a helpful assistant.",
        height=100,
        label_visibility="collapsed",
    )

    # -------- 📎 첨부 파일 --------
    st.divider()
    st.markdown("##### 📎 첨부 파일")
    all_files = fm.list()
    text_files = [f for f in all_files if is_text_file(f.name)]
    binary_files = [f for f in all_files if not is_text_file(f.name)]

    if not all_files:
        st.caption("Files 페이지에서 업로드한 텍스트 파일을 여기서 선택할 수 있습니다.")
    elif not text_files:
        st.caption(f"업로드된 {len(all_files)}개 파일이 모두 바이너리입니다.")
    else:
        opts = [f.name for f in text_files]
        labels = {f.name: f"{f.name}  ·  {fmt_size(f.size)}" for f in text_files}
        attached = st.multiselect(
            "첨부할 파일",
            opts,
            format_func=lambda n: labels.get(n, n),
            label_visibility="collapsed",
            key="attached_files",
        )
        if attached:
            st.caption(f"✅ {len(attached)}개 첨부 · 합산 한도 {MAX_TOTAL//1024} KB")

    if binary_files:
        st.caption(f"⚪ 바이너리 {len(binary_files)}개 제외 (PDF·xlsx·이미지 등은 미지원)")

    # -------- 액션 --------
    st.divider()
    st.markdown("##### 액션")
    c1, c2 = st.columns(2)
    if c1.button("🆕 새 대화", use_container_width=True):
        st.session_state.pop("chat_messages", None)
        st.session_state.pop("last_stats", None)
        st.rerun()

    has_msgs = bool(st.session_state.get("chat_messages"))

    if has_msgs:
        md = f"# Chat — {datetime.now():%Y-%m-%d %H:%M}\n\n"
        md += f"_provider: `{provider_name}` · model: `{model}`_\n\n"
        for m in st.session_state.get("chat_messages", []):
            md += f"## {m['role']}\n\n{m['content']}\n\n"
        c2.download_button(
            "💾 .md 저장",
            data=md.encode("utf-8"),
            file_name=f"chat_{datetime.now():%Y%m%d_%H%M%S}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    else:
        c2.button("💾 .md 저장", disabled=True, use_container_width=True)

    # save to Files folder
    if has_msgs:
        if st.button("📁 Files 에 저장", use_container_width=True,
                     help="현재 대화를 Files 폴더에 .md 로 저장 — 다음 대화의 첨부로 재사용 가능"):
            md = f"# Chat — {datetime.now():%Y-%m-%d %H:%M}\n\n"
            md += f"_provider: `{provider_name}` · model: `{model}`_\n\n"
            for m in st.session_state.get("chat_messages", []):
                md += f"## {m['role']}\n\n{m['content']}\n\n"
            fname = f"chat_{datetime.now():%Y%m%d_%H%M%S}.md"
            try:
                fm.save(fname, md.encode("utf-8"))
                st.toast(f"📁 `{fname}` Files 폴더에 저장", icon="💾")
            except Exception as e:
                st.error(f"저장 실패: {e}")
    else:
        st.button("📁 Files 에 저장", disabled=True, use_container_width=True)


# ============================================================
# state
# ============================================================
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []


# ============================================================
# main area
# ============================================================
attached = st.session_state.get("attached_files", [])
if attached:
    chips = " ".join(badge(f"📎 {n}", "info") for n in attached)
    st.markdown(chips, unsafe_allow_html=True)
    st.write("")

if not st.session_state.chat_messages:
    empty_state(
        icon="💬",
        title="대화를 시작하세요",
        hint=f"`{provider_name}` · `{model or '모델 미선택'}`"
        + (f" · 📎 {len(attached)}개 첨부" if attached else ""),
    )
else:
    for m in st.session_state.chat_messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    stats = st.session_state.get("last_stats")
    if stats:
        c1, c2, c3 = st.columns(3)
        c1.metric("응답 시간", f"{stats['elapsed']:.1f}s")
        c2.metric("출력 토큰", stats.get("output_tokens") or "—")
        c3.metric("청크 수", stats["chunks"])


# ============================================================
# input
# ============================================================
user_input = st.chat_input(
    f"{provider_name} / {model or '모델 미선택'} 에게 보낼 메시지…"
)
if user_input:
    if not model:
        st.error("모델을 먼저 선택하세요.")
        st.stop()

    # build attachment context (first send only? always? — always: simple, predictable)
    attach_ctx, attach_info = build_attachment_context(fm, attached) if attached else ("", [])

    st.session_state.chat_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    try:
        llm = get_provider(provider_name, model=model)
    except Exception as e:
        st.error(f"Provider 초기화 실패: {e}")
        st.stop()

    # compose system message + attachment context
    sys_parts: list[str] = []
    if system.strip():
        sys_parts.append(system.strip())
    if attach_ctx:
        sys_parts.append(
            "다음은 사용자가 참조하라고 첨부한 파일들입니다. 필요할 때 인용·활용하세요.\n\n"
            + attach_ctx
        )
    system_combined = "\n\n---\n\n".join(sys_parts)

    msgs: list[Message] = []
    if system_combined:
        msgs.append(Message(role="system", content=system_combined))
    msgs += [Message(role=m["role"], content=m["content"]) for m in st.session_state.chat_messages]

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
    st.session_state.last_stats = {
        "elapsed": elapsed, "chunks": chunks, "output_tokens": out_tokens,
    }
    st.session_state.chat_messages.append({"role": "assistant", "content": full})
    st.rerun()
