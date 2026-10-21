"""Shared light-theme table appearance, preserving Streamlit grid interactions."""
from __future__ import annotations
import streamlit as st

CSS = """
<style>
/* Unified Courtside table/card visual language. */
:root { color-scheme:light; }
[data-testid="stAppViewContainer"], .stApp { background:#F5F6F8; color:#1D2C40; }
[data-testid="stDataFrame"], [data-testid="stTable"] {
  background:#FFFFFF !important;
  border:1px solid #E2E8F0 !important;
  border-radius:13px !important;
  overflow:hidden;
  box-shadow:0 1px 2px rgba(27,45,68,.025);
}
[data-testid="stDataFrame"] [data-testid="stElementToolbar"] {background:#FFFFFF;}
/* Streamlit dataframe cells are canvas-rendered on some versions. The
   official light theme in .streamlit/config.toml controls those colors. */
[data-testid="stDataFrame"] canvas {color-scheme:light;}
[data-testid="stMetric"] {background:#FFFFFF;border:1px solid #E2E8F0;border-radius:13px;}
[data-testid="stAlert"] {border-radius:12px;}
[data-testid="stVerticalBlockBorderWrapper"] {border-color:#E2E8F0 !important;}
[data-testid="stExpander"] {background:#FFFFFF; border:1px solid #E2E8F0;border-radius:12px;overflow:hidden;}
[data-testid="stWidgetLabel"] p, [data-testid="stMarkdownContainer"] label {color:#46586D;}
/* Default to readable labels on light background, including selection widgets. */
[data-testid="stRadio"] label p, [data-testid="stCheckbox"] label p {color:#26364B !important;}
div.stButton>button[kind="secondary"] {background:#FFFFFF; border-color:#DCE3EC; color:#26364B;}
div.stButton>button[kind="primary"] {background:#23354B; border-color:#23354B; color:#FFFFFF;}
div.stButton>button:hover {border-color:#7187A0;}
</style>
"""

def apply_table_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def dataframe(data=None, *args, **kwargs):
    """Consistent native sortable/exportable data grid; API forwards unchanged."""
    kwargs.setdefault("hide_index", True)
    kwargs.setdefault("use_container_width", True)
    return st.dataframe(data, *args, **kwargs)
