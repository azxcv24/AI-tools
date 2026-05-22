"""Shared UI widgets for LLM Studio pages."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Literal

import streamlit as st

# ------------------------------------------------------------
# Global CSS — call once per page (after set_page_config)
# ------------------------------------------------------------

_CSS = """
<style>
/* tighter top padding, capped width */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 3rem !important;
    max-width: 1180px;
}

/* h1 less shouting */
h1 {
    font-weight: 700 !important;
    letter-spacing: -0.02em;
    margin-bottom: 0.25rem !important;
}

/* h2 / h3 spacing */
h2 { margin-top: 1.5rem !important; }
h3 { margin-top: 1.25rem !important; }

/* sidebar polish */
[data-testid="stSidebar"] {
    background-color: #F8FAFC;
    border-right: 1px solid #E5E7EB;
}
[data-testid="stSidebar"] .block-container {
    padding-top: 1.5rem;
}

/* inline code chips */
code {
    background-color: #EEF2FF !important;
    color: #4338CA !important;
    border-radius: 6px;
    padding: 2px 7px !important;
    font-size: 0.85em !important;
    font-weight: 500;
}

/* chat bubbles softer */
[data-testid="stChatMessage"] {
    background-color: #F8FAFC;
    border: 1px solid #E5E7EB;
    border-radius: 14px;
    padding: 12px 16px;
}

/* buttons */
.stButton button {
    border-radius: 8px;
    font-weight: 500;
    transition: all 0.15s ease;
}
.stButton button:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(99, 102, 241, 0.15);
}

/* bordered container = "card" */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px !important;
    border: 1px solid #E5E7EB !important;
    background: white;
}

/* divider thinner */
hr {
    margin: 1rem 0 !important;
    border-color: #E5E7EB !important;
}

/* hide streamlit footer */
footer { visibility: hidden; }

/* badges */
.lstudio-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    line-height: 1.4;
    vertical-align: middle;
}
.lstudio-badge.ok   { background:#DCFCE7; color:#15803D; }
.lstudio-badge.warn { background:#FEF3C7; color:#A16207; }
.lstudio-badge.err  { background:#FEE2E2; color:#B91C1C; }
.lstudio-badge.off  { background:#F1F5F9; color:#64748B; }
.lstudio-badge.info { background:#E0E7FF; color:#4338CA; }

/* status dot */
.lstudio-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 6px;
    vertical-align: middle;
}
.lstudio-dot.ok   { background:#22C55E; box-shadow:0 0 0 3px rgba(34,197,94,0.15); }
.lstudio-dot.warn { background:#F59E0B; box-shadow:0 0 0 3px rgba(245,158,11,0.15); }
.lstudio-dot.err  { background:#EF4444; box-shadow:0 0 0 3px rgba(239,68,68,0.15); }
.lstudio-dot.off  { background:#94A3B8; }

/* page hero */
.lstudio-hero {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 4px 0 12px 0;
    border-bottom: 1px solid #E5E7EB;
    margin-bottom: 1.5rem;
}
.lstudio-hero .icon {
    font-size: 2.25rem;
    line-height: 1;
}
.lstudio-hero .title {
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #0F172A;
    line-height: 1.2;
}
.lstudio-hero .subtitle {
    font-size: 0.92rem;
    color: #64748B;
    margin-top: 2px;
}

/* sidebar brand */
.lstudio-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 0 16px 0;
    border-bottom: 1px solid #E5E7EB;
    margin-bottom: 16px;
}
.lstudio-brand .logo {
    font-size: 1.5rem;
}
.lstudio-brand .name {
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.01em;
}
.lstudio-brand .ver {
    font-size: 0.7rem;
    color: #94A3B8;
    margin-left: auto;
}

/* empty state */
.lstudio-empty {
    text-align: center;
    padding: 2.5rem 1rem;
    color: #64748B;
}
.lstudio-empty .icon {
    font-size: 2.5rem;
    opacity: 0.55;
}
.lstudio-empty .title {
    font-weight: 600;
    color: #334155;
    margin-top: 8px;
}
.lstudio-empty .hint {
    font-size: 0.85rem;
    margin-top: 4px;
}
</style>
"""


def inject_global_css() -> None:
    """Inject global stylesheet. Call once per page after st.set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)


def fmt_bytes(num_bytes: float) -> str:
    """Human-readable byte size — shared by file cards and model listings."""
    if num_bytes <= 0:
        return "-"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ------------------------------------------------------------
# Widgets
# ------------------------------------------------------------

def page_header(icon: str, title: str, subtitle: str = "") -> None:
    """Consistent page hero — icon · title · subtitle."""
    sub = f'<div class="subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="lstudio-hero">'
        f'  <div class="icon">{icon}</div>'
        f'  <div><div class="title">{title}</div>{sub}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


Status = Literal["ok", "warn", "err", "off", "info"]


def badge(label: str, status: Status = "info") -> str:
    """Return HTML for a pill-shaped status badge. Use with `st.markdown(..., unsafe_allow_html=True)`."""
    return f'<span class="lstudio-badge {status}">{label}</span>'


def status_dot(status: Status = "off", label: str = "") -> str:
    """Return HTML for a colored dot + label."""
    return f'<span class="lstudio-dot {status}"></span>{label}'


def empty_state(icon: str, title: str, hint: str = "") -> None:
    """Render a centered empty-state block inside a bordered card."""
    hint_html = f'<div class="hint">{hint}</div>' if hint else ""
    with st.container(border=True):
        st.markdown(
            f'<div class="lstudio-empty">'
            f'  <div class="icon">{icon}</div>'
            f'  <div class="title">{title}</div>'
            f'  {hint_html}'
            f'</div>',
            unsafe_allow_html=True,
        )


def sidebar_brand(name: str = "LLM Studio", version: str = "v0.1") -> None:
    """Sidebar brand strip — logo · name · version."""
    st.sidebar.markdown(
        f'<div class="lstudio-brand">'
        f'  <div class="logo">🧪</div>'
        f'  <div class="name">{name}</div>'
        f'  <div class="ver">{version}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


@contextmanager
def section(title: str, subtitle: str = ""):
    """A bordered card with a heading. Use as `with section("…"):`."""
    with st.container(border=True):
        st.markdown(f"##### {title}")
        if subtitle:
            st.caption(subtitle)
        yield
