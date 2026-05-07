# Streamlit Blockchain Voting Demo

## Run

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Ensure `.env` exists with `CHAIN_PRIVATE_KEY_B64`.
   - You can copy `.env.example` and replace the value.

3. Start the Flask RFID mock server:
   ```bash
   flask --app flask_rfid run --port 5001
   ```

4. Start the Streamlit app:
   ```bash
   streamlit run app.py
   ```

## Streamlit Pages

- `app.py` landing page
- `pages/1_Register.py`
- `pages/2_Vote.py`
- `pages/3_Monitor_Chain.py`
- `pages/4_Preview_Voters.py`

## Flow

- Place card on RFID reader in Flask, then register voter with face image, name, number, and email.
- Use the Vote page to read the reader value, scan face for up to 45 seconds, then cast a vote.
- Monitor Chain shows blocks, hashes, and vote totals.

## Notes

- RFID is mocked through the Flask service.
- Reader button exists only on the Flask GET page.
- Flask page also shows registered voters, voted status, and mock buttons.
- Blockchain is a SQLite-backed local demo chain.
- Candidate list is hardcoded in `voting_data.py`.
- Block signatures use the private key in `.env` and are verified on the monitor page.
