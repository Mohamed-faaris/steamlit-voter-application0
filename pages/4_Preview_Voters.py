from __future__ import annotations

import streamlit as st

from db import delete_voter, get_voters, init_db, update_voter, voter_vote_count
from voting_data import APP_TITLE
from pages_shared import inject_css, set_page_title


init_db()

st.set_page_config(page_title=APP_TITLE, page_icon="🗳️", layout="wide")
inject_css()

set_page_title("Preview Voters", "Review voters, edit details, and delete only unused records.")

voters = get_voters()
if not voters:
    st.info("No voters registered yet.")
    st.stop()

preview_cols = st.columns(2)
with preview_cols[0]:
    st.subheader("Voter List")
    for voter in voters:
        votes = voter_vote_count(int(voter["id"]))
        status = "Voted" if int(voter["voted"]) else "Not voted"
        st.markdown(
            f"<div class='block-card'><strong>{voter['name']}</strong><br>{voter['rfid']}<br><small>{voter['email']} · {voter['number']} · {status} · votes: {votes}</small></div>",
            unsafe_allow_html=True,
        )
        if voter["photo_blob"]:
            st.image(bytes(voter["photo_blob"]), width=180)

with preview_cols[1]:
    st.subheader("Edit / Delete")
    voter_map = {f"{row['name']} ({row['rfid']})": int(row["id"]) for row in voters}
    selected_label = st.selectbox("Select voter", list(voter_map.keys()))
    selected_id = voter_map[selected_label]
    selected_voter = next(row for row in voters if int(row["id"]) == selected_id)

    with st.form("edit_voter_form"):
        rfid = st.text_input("Card value", value=str(selected_voter["rfid"]))
        name = st.text_input("Name", value=str(selected_voter["name"]))
        number = st.text_input("Number", value=str(selected_voter["number"]))
        email = st.text_input("Email", value=str(selected_voter["email"]))
        save = st.form_submit_button("Save changes")

    if save:
        try:
            update_voter(selected_id, rfid, name, number, email)
            st.success("Voter updated.")
            st.rerun()
        except Exception as exc:
            st.error(f"Update failed: {exc}")

    votes = voter_vote_count(selected_id)
    if votes == 0:
        if st.button("Delete voter"):
            delete_voter(selected_id)
            st.success("Voter deleted.")
            st.rerun()
    else:
        st.warning("This voter has cast a vote, so delete is disabled.")
