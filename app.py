from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

st.set_page_config(
    page_title="SentiOH",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.login import require_login, render_account_panel
from ui.branding import inject_brand_typography
from ui.single_dashboard import render

inject_brand_typography(st)

user = require_login(st)
if user is None:
    st.stop()

render_account_panel(st, user)
render(st, current_user=user)
