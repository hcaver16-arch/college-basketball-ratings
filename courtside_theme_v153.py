"""Courtside V153 — light blue/teal presentation system; no data changes."""
import streamlit as st

def apply_v153_theme():
    st.markdown("""
<style>
:root {
  --cs-navy:#152b57; --cs-blue:#2054c5; --cs-teal:#08ad9e;
  --cs-ink:#152748; --cs-muted:#637994; --cs-bg:#f0f4fb;
  --cs-border:#d9e4f4; --cs-card:#f9fbff;
}
.stApp, [data-testid="stAppViewContainer"] {background:linear-gradient(165deg,#f2f7ff 0%,#edf2fb 55%,#f5f8fd 100%) !important;color:var(--cs-ink)}
[data-testid="stHeader"] {background:rgba(240,244,251,.95) !important}
[data-testid="stSidebar"] {background:#eaf2fc !important;border-right:1px solid #d7e2f2}
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {border-color:#d9e4f4}
h1,h2,h3,h4 {color:#142a53 !important}
h1 {letter-spacing:-.045em}
[data-testid="stMetric"] {background:linear-gradient(140deg,#ffffff,#eff8fb) !important;border:1px solid #d2e4f2 !important;border-radius:14px !important;box-shadow:0 3px 12px rgba(27,64,129,.05)}
[data-testid="stVerticalBlockBorderWrapper"] {border-color:#d9e4f4 !important;border-radius:15px !important}
div.stButton>button[kind="primary"] {background:#2054c5 !important;border-color:#2054c5 !important;color:#fff !important;box-shadow:0 2px 8px rgba(32,84,197,.16)}
div.stButton>button[kind="primary"] p {color:#fff !important}
div.stButton>button[kind="secondary"] {background:#f9fbff !important;border:1px solid #cbdaf0 !important;color:#1b355f !important}
div.stButton>button[kind="secondary"] p {color:#1b355f !important}
div.stButton>button:hover {border-color:#08ad9e !important;box-shadow:0 2px 10px rgba(8,173,158,.10)}
div[data-testid="stProgress"] [role="progressbar"]>div {background:#08ad9e}
[data-testid="stDataFrame"] {border:1px solid #dbe6f5;border-radius:12px;overflow:hidden}
[data-testid="stCaptionContainer"] p {color:#637994 !important}
.court-rank-card,.court-highlight-card {background:#f9fbff !important;border-color:#dbe6f5 !important;box-shadow:0 3px 12px rgba(30,72,140,.05)}
.court-section-head h3 {color:#173b87 !important}
.court-rank-num {color:#2054c5 !important}
.court-highlight-margin strong {color:#078f84 !important}
.cs153-banner {background:linear-gradient(115deg,#102b58 0%,#17449b 48%,#087eaa 76%,#0dbbad 100%);color:white;padding:24px 28px;border-radius:17px;position:relative;overflow:hidden;box-shadow:0 6px 22px rgba(19,58,122,.16);margin-bottom:14px}
.cs153-banner:after {content:"";position:absolute;width:220px;height:220px;border:2px solid rgba(255,255,255,.16);border-radius:50%;right:60px;top:-100px;box-shadow:0 0 0 38px rgba(255,255,255,.045),0 0 0 80px rgba(255,255,255,.035);pointer-events:none}
.cs153-kicker {font-size:11px;font-weight:800;letter-spacing:.16em;color:#a3fff4;text-transform:uppercase}
.cs153-banner h2 {color:white !important;font-size:clamp(1.5rem,3vw,2.3rem);margin:.3rem 0;line-height:1.14}
.cs153-banner p {color:#e0edff;font-size:.93rem;margin:0;max-width:640px}
.cs153-chips {display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.cs153-chip {border:1px solid rgba(255,255,255,.3);border-radius:24px;padding:5px 12px;color:white;background:rgba(255,255,255,.11);font-size:12px}
@media(max-width:700px){.cs153-banner{padding:18px 16px}.cs153-banner h2{font-size:1.5rem}}
</style>
""",unsafe_allow_html=True)
