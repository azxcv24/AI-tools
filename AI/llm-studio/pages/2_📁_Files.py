import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: F401,E402

import streamlit as st  # noqa: E402

from components import empty_state, inject_global_css, page_header, sidebar_brand  # noqa: E402
from shared.storage import FileManager  # noqa: E402

st.set_page_config(page_title="Files · LLM Studio", page_icon="📁", layout="wide")
inject_global_css()
sidebar_brand()

page_header("📁", "Files", "프롬프트에서 참조할 파일을 업로드 · 관리합니다.")

fm = FileManager(_bootstrap.UPLOADS_DIR)


def fmt_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024 or unit == "GB":
            return f"{b:.1f} {unit}" if unit != "B" else f"{b} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def icon_for(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return {
        "pdf": "📕",
        "md": "📝", "txt": "📝",
        "json": "🗂️", "yaml": "🗂️", "yml": "🗂️", "toml": "🗂️",
        "csv": "📊", "tsv": "📊",
        "xlsx": "📗", "xls": "📗",
        "docx": "📘", "doc": "📘",
        "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️", "gif": "🖼️", "webp": "🖼️",
        "py": "🐍", "js": "📜", "ts": "📜", "go": "📜", "rs": "📜",
        "zip": "🗜️", "tar": "🗜️", "gz": "🗜️",
    }.get(ext, "📄")


# ---------- upload ----------
with st.container(border=True):
    st.markdown("##### 업로드")
    st.caption(f"저장 위치: `{_bootstrap.UPLOADS_DIR}` (gitignored)")
    uploaded = st.file_uploader(
        "파일을 선택하거나 여기로 드래그",
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

if uploaded:
    saved = 0
    for f in uploaded:
        try:
            fm.save(f.name, f.getvalue())
            saved += 1
        except ValueError as e:
            st.error(f"{f.name}: {e}")
    if saved:
        st.toast(f"✅ {saved}개 파일 업로드", icon="📁")
        st.rerun()


# ---------- list ----------
files = fm.list()
total_size = sum(f.size for f in files)

c1, c2 = st.columns([2, 1])
c1.markdown(f"##### 업로드된 파일")
c1.caption(f"총 {len(files)}개 · {fmt_size(total_size)}")

if not files:
    empty_state(
        icon="📭",
        title="아직 업로드된 파일이 없습니다",
        hint="위쪽 업로더로 시작하세요. 한 번에 여러 개도 가능합니다.",
    )
else:
    for info in files:
        with st.container(border=True):
            c = st.columns([0.5, 5, 2, 2.5, 1, 1])
            c[0].markdown(
                f"<div style='font-size:1.5rem'>{icon_for(info.name)}</div>",
                unsafe_allow_html=True,
            )
            c[1].markdown(f"**{info.name}**")
            c[1].caption(f"{info.path}")
            c[2].caption("크기")
            c[2].write(fmt_size(info.size))
            c[3].caption("수정일")
            c[3].write(f"{info.modified:%Y-%m-%d %H:%M:%S}")
            c[4].download_button(
                "⬇️",
                data=fm.read(info.name),
                file_name=info.name,
                key=f"dl_{info.name}",
                use_container_width=True,
                help="다운로드",
            )
            if c[5].button("🗑️", key=f"del_{info.name}",
                           use_container_width=True, help="삭제"):
                fm.delete(info.name)
                st.toast(f"🗑️ {info.name} 삭제", icon="📁")
                st.rerun()
