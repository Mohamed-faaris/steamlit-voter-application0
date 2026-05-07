from __future__ import annotations

import time

import streamlit as st

from blockchain import Transaction, add_vote_block, validate_chain, verify_block_signature
from db import (
    get_blocks,
    get_candidates,
    get_latest_rfid_event,
    get_vote_counts,
    get_votes,
    get_voter_by_rfid,
    init_db,
    insert_vote,
    mark_voted,
    upsert_voter,
)
from face_utils import analyze_image, annotate_face_boxes, compare_image_with_blob, crop_face, image_array_to_bytes, image_array_to_encoding_blob
from voting_data import APP_TITLE, FACE_SCAN_SECONDS


init_db()


def inject_css() -> None:
    st.markdown(
        """
        <style>
          .stApp {
            background:
              radial-gradient(circle at top left, rgba(37,99,235,.18), transparent 30%),
              radial-gradient(circle at top right, rgba(16,185,129,.14), transparent 32%),
              linear-gradient(180deg, #08111f 0%, #0b1220 100%);
            color: #e5eefb;
          }
          .block-card {
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 18px;
            padding: 18px;
            box-shadow: 0 18px 40px rgba(0,0,0,.28);
          }
          .metric-box {
            background: linear-gradient(180deg, rgba(15,23,42,.9), rgba(15,23,42,.55));
            border: 1px solid rgba(148, 163, 184, 0.16);
            border-radius: 16px;
            padding: 16px;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def set_page_title(title: str, subtitle: str) -> None:
    st.markdown(f"# {title}")
    st.caption(subtitle)


def latest_rfid_value() -> str:
    latest = get_latest_rfid_event()
    return latest["rfid"] if latest else ""


def registration_page() -> None:
    set_page_title("Register Voter", "Store RFID, face template, and contact details.")
    st.write("Register a voter before voting. Generate the RFID in Flask, then capture the face image here.")
    current_rfid = latest_rfid_value()
    st.text_input("Card on RFID reader", value=current_rfid, disabled=True)
    if current_rfid:
        st.success(f"Card detected: {current_rfid}")
    else:
        st.warning("Place card on RFID reader.")
    name = st.text_input("Name")
    number = st.text_input("Number")
    email = st.text_input("Email")
    face_input = st.camera_input("Capture face image")
    upload_input = st.file_uploader("Or upload face image", type=["png", "jpg", "jpeg"])
    submitted = st.button("Register voter")

    image_bytes = upload_input.getvalue() if upload_input is not None else None
    if face_input is not None:
        image_bytes = face_input.getvalue()

    if image_bytes:
        image, locations, _, warnings = analyze_image(image_bytes)
        st.image(annotate_face_boxes(image, locations), caption="Face detection preview", use_container_width=True)
        for warning in warnings:
            st.warning(warning)

    if submitted:
        if not all([current_rfid.strip(), name.strip(), number.strip(), email.strip(), image_bytes]):
            st.error("Place card on RFID reader and provide all voter details plus a face image.")
            return
        if not current_rfid:
            st.error("Place card on RFID reader first.")
            return
        try:
            image, locations, _, _ = analyze_image(image_bytes)
            face_crop = crop_face(image, locations[0]) if locations else image
            face_blob = image_array_to_encoding_blob(face_crop)
            photo_blob = image_array_to_bytes(face_crop)
            upsert_voter(current_rfid.strip(), name.strip(), number.strip(), email.strip(), face_blob, photo_blob)
            st.success("Voter registered successfully.")
        except Exception as exc:
            st.error(f"Registration failed: {exc}")


def vote_page() -> None:
    set_page_title("Vote", f"RFID + face scan within {FACE_SCAN_SECONDS} seconds.")
    rfid = latest_rfid_value()
    st.info(f"Card on RFID reader: {rfid or 'none'}")

    if "scan_started_at" not in st.session_state:
        st.session_state.scan_started_at = None
    if "scan_match_ready" not in st.session_state:
        st.session_state.scan_match_ready = False
    if "matched_voter_id" not in st.session_state:
        st.session_state.matched_voter_id = None

    voter = get_voter_by_rfid(rfid) if rfid else None
    if voter is None and rfid:
        st.warning("No voter found for this card. Register first or use a registered card.")
    if voter is not None and int(voter["voted"]) == 1:
        st.error("This voter has already voted.")
        st.stop()

    if st.button("Start face scan"):
        st.session_state.scan_started_at = time.time()
        st.session_state.scan_match_ready = False
        st.session_state.matched_voter_id = None

    if st.session_state.scan_started_at:
        elapsed = int(time.time() - st.session_state.scan_started_at)
        remaining = max(0, FACE_SCAN_SECONDS - elapsed)
        st.info(f"Face scan active. {remaining} seconds remaining.")
        scan_input = st.camera_input("Capture scan frame")
        upload_scan = st.file_uploader("Or upload scan frame", type=["png", "jpg", "jpeg"], key="scan_upload")
        scan_bytes = None
        if scan_input is not None:
            scan_bytes = scan_input.getvalue()
        elif upload_scan is not None:
            scan_bytes = upload_scan.getvalue()

        if scan_bytes:
            image, locations, _, warnings = analyze_image(scan_bytes)
            st.image(annotate_face_boxes(image, locations), caption="Scan frame preview", use_container_width=True)
            for warning in warnings:
                st.warning(warning)

        if scan_bytes and voter is not None:
            matched = compare_image_with_blob(scan_bytes, voter["face_blob"])
            if matched:
                st.session_state.scan_match_ready = True
                st.session_state.matched_voter_id = int(voter["id"])
                st.success("Face matched. You may vote now.")
            else:
                st.error("Face not recognized. Keep scanning or restart.")

        if remaining == 0 and not st.session_state.scan_match_ready:
            st.session_state.scan_started_at = None
            st.error("Scan window expired. Restart from RFID step.")
            st.stop()

    if st.session_state.scan_match_ready and voter is not None:
        candidates = get_candidates()
        candidate_names = [f"{row['symbol']} {row['name']} - {row['party']}" for row in candidates]
        selected = st.selectbox("Select candidate", candidate_names)
        if st.button("Submit vote"):
            candidate = next(row for row in candidates if f"{row['symbol']} {row['name']} - {row['party']}" == selected)
            tx = Transaction(
                type="vote",
                candidate_id=int(candidate["id"]),
                candidate_name=str(candidate["name"]),
            )
            tx_hash = add_vote_block(tx)
            insert_vote(int(voter["id"]), int(candidate["id"]), tx_hash)
            mark_voted(int(voter["id"]))
            st.success("Vote stored on the local blockchain.")
            st.session_state.scan_started_at = None
            st.session_state.scan_match_ready = False
            st.session_state.matched_voter_id = None
            st.rerun()


def monitor_page() -> None:
    set_page_title("Monitor Chain", "Inspect blocks, transactions, and vote totals.")
    blocks = get_blocks()
    votes = get_votes()
    counts = get_vote_counts()
    chain_errors = validate_chain(blocks)

    c1, c2, c3 = st.columns(3)
    c1.metric("Chain height", len(blocks) - 1)
    c2.metric("Votes cast", len(votes))
    c3.metric("Integrity", "OK" if not chain_errors else "Broken")

    if chain_errors:
        st.error("; ".join(chain_errors))

    st.subheader("Vote totals")
    cols = st.columns(len(counts)) if counts else []
    for idx, row in enumerate(counts):
        with cols[idx]:
            st.markdown(
                f"<div class='metric-box'><h3>{row['symbol']} {row['name']}</h3><p>{row['party']}</p><h2>{row['vote_count']}</h2></div>",
                unsafe_allow_html=True,
            )

    st.subheader("Blocks")
    for block in blocks:
        with st.expander(f"Block {block['block_index']} · {block['hash'][:12]}…", expanded=block["block_index"] == 0):
            st.write(
                {
                    "index": block["block_index"],
                    "timestamp": block["timestamp"],
                    "previous_hash": block["previous_hash"],
                    "hash": block["hash"],
                    "signature": block["signature"][:24] + "…" if block["signature"] else "",
                    "nonce": block["nonce"],
                    "transactions": block["transactions_json"],
                    "signature_valid": verify_block_signature(str(block["hash"]), str(block["signature"])),
                }
            )

    st.subheader("Vote transactions")
    for vote in votes:
        st.markdown(
            f"<div class='block-card'><strong>{vote['candidate_name']}</strong> · {vote['candidate_party']}<br><small>{vote['created_at']} · tx {vote['tx_hash'][:16]}…</small></div>",
            unsafe_allow_html=True,
        )
