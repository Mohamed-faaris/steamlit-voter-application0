from __future__ import annotations

import streamlit as st

from voting_data import APP_TITLE
from pages_shared import inject_css, registration_page


st.set_page_config(page_title=APP_TITLE, page_icon="🗳️", layout="wide")
inject_css()
registration_page()
