from __future__ import annotations

import secrets

from flask import Flask, redirect, render_template_string, request, url_for

from db import add_rfid_event, clear_rfid_events, get_active_rfid_events, get_latest_rfid_event, get_voters, init_db

app = Flask(__name__)

init_db()

HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>RFID Mock Input</title>
    <style>
      body { font-family: Arial, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 32px; }
      .shell { max-width: 1120px; margin: 0 auto; display: grid; gap: 20px; }
      .card { background: #111827; border: 1px solid #334155; border-radius: 16px; padding: 24px; }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
      button { width: 100%; padding: 14px; margin-top: 12px; border-radius: 12px; border: 1px solid #475569; background: #2563eb; color: #e2e8f0; cursor: pointer; }
      button.secondary { background: #0b1220; }
      .hint { color: #94a3b8; font-size: 14px; }
      .row { display: grid; gap: 12px; }
      .saved { margin-top: 16px; padding: 12px; background: #0b1220; border-radius: 12px; border: 1px solid #334155; }
      .voters { display: grid; gap: 10px; margin-top: 14px; }
      .voter { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 12px 14px; border: 1px solid #334155; border-radius: 12px; background: #0b1220; }
      .status { font-size: 12px; padding: 4px 8px; border-radius: 999px; }
      .status.yes { background: rgba(16, 185, 129, .18); color: #86efac; }
      .status.no { background: rgba(239, 68, 68, .18); color: #fca5a5; }
      .tiny { font-size: 12px; color: #94a3b8; }
      a { color: #93c5fd; }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="card">
        <h1>RFID Admin Mock</h1>
        <p class="hint">Place a card on the RFID reader, reset the queue, and enqueue a voter's card for the Streamlit app.</p>
        <div class="grid">
          <form method="post">
            <input type="hidden" name="action" value="generate">
            <input type="hidden" name="rfid" value="{{ generated_rfid }}">
            <button type="submit">Place card on RFID reader</button>
          </form>
          <form method="post">
            <input type="hidden" name="action" value="reset">
            <button class="secondary" type="submit">Reset Queue</button>
          </form>
        </div>
        <div class="saved">
          <div>Reader value: <strong>{{ generated_rfid or 'none' }}</strong></div>
          <div>Latest unread card: <strong>{{ saved_rfid or 'none' }}</strong></div>
          <div class="hint">Unread queue is capped at 2 items. Oldest unread item is discarded when a new one arrives.</div>
        </div>
      </div>

      <div class="card">
        <h2>Active Reader Queue</h2>
        {% if active_events %}
          <div class="voters">
            {% for event in active_events %}
              <div class="voter">
                <div>
                  <div><strong>{{ event.rfid }}</strong></div>
                  <div class="tiny">{{ event.source }} · {{ event.created_at }}</div>
                </div>
                <span class="status no">Unread</span>
              </div>
            {% endfor %}
          </div>
        {% else %}
          <p class="hint">No unread reader events.</p>
        {% endif %}
      </div>

      <div class="card">
        <h2>Registered Voters</h2>
        {% if voters %}
          <div class="voters">
            {% for voter in voters %}
              <div class="voter">
                <div>
                  <div><strong>{{ voter.name }}</strong> <span class="tiny">({{ voter.rfid }})</span></div>
                  <div class="tiny">{{ voter.email }} · {{ voter.number }}</div>
                </div>
                <div style="display:grid; gap:8px; min-width: 180px;">
                  <span class="status {{ 'yes' if voter.voted else 'no' }}">{{ 'Voted' if voter.voted else 'Not voted' }}</span>
                  <form method="post">
                    <input type="hidden" name="action" value="mock_voter">
                    <input type="hidden" name="rfid" value="{{ voter.rfid }}">
                    <button class="secondary" type="submit">Mock Reader</button>
                  </form>
                </div>
              </div>
            {% endfor %}
          </div>
        {% else %}
          <p class="hint">No voters registered yet.</p>
        {% endif %}
      </div>

      <p><a href="/rfid">Refresh</a></p>
    </div>
  </body>
</html>
"""


@app.route("/", methods=["GET"])
def home():
    return redirect(url_for("rfid"))


@app.route("/rfid", methods=["GET", "POST"])
def rfid():
    if request.method == "POST":
        action = request.form.get("action", "generate").strip()
        rfid_value = request.form.get("rfid", "").strip()
        if action == "reset":
            clear_rfid_events()
        elif action in {"generate", "mock_voter"} and rfid_value:
            source = "flask-generate" if action == "generate" else "flask-mock-voter"
            add_rfid_event(rfid_value, source=source)
        return redirect(url_for("rfid"))

    latest = get_latest_rfid_event()
    generated_rfid = f"RFID-{secrets.token_hex(4).upper()}"
    voters = get_voters()
    return render_template_string(
        HTML,
        saved_rfid=latest["rfid"] if latest else "",
        generated_rfid=generated_rfid,
        active_events=get_active_rfid_events(),
        voters=voters,
    )


if __name__ == "__main__":
    app.run(port=5001, debug=True)
