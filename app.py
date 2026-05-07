from __future__ import annotations

import streamlit as st

from voting_data import APP_TITLE

from pages_shared import inject_css


st.set_page_config(page_title=APP_TITLE, page_icon="🗳️", layout="wide")
inject_css()

st.title(APP_TITLE)
st.caption("RFID + face verification + SQLite demo blockchain")

st.markdown(
    """
    ## Pages
    - Register voter
    - Vote with RFID + face scan
    - Monitor chain and vote totals

    Use the Streamlit sidebar to open the pages.
    """
)
