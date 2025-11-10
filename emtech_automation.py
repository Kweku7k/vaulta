import requests
import json
import time
import random
import string
from datetime import datetime

# === CONFIG ===
ENDPOINT = "https://api.emtech.com/integration/compliance/v2/remittances/events"
SANDBOX_AUTH = "Bearer eyJhbGciOiJSUzI1NiJ9.eyJhdWQiOiJFTVRFQ0giLCJjbGllbnRJZCI6InYwdnJGdE8zWmx5cFpXUTl2a00zSVJHMlpBOHFrOTM0IiwicHJvZHVjdElkIjpudWxsLCJjb21wSWQiOjEzMTIsInN1YnMiOlsiUmVtaXR0YW5jZSBBUElzIl0sImFwcElkIjo3NjIsImlzcyI6ImFwcHJvdmFsLWJhY2tlbmQtc2VydmljZSIsInR5cCI6IkRFVkVMT1BFUiIsInBvcnRhbCI6IklDIiwiZXhwIjoxNzYxMDQ2NTI3LCJ1c2VySWQiOjE1NDcsImlhdCI6MTc2MDk2MDEyN30.WXPgv9ZBPWcswctRlJGe1LzVdG2Muk_hjA95k1-59APqbEQHzbLgYQsE__e70y-HgTFJdGcfdLe8sQJ_bPBlSRG55oyi_PDsXIEjik1CRBo4AD-CZEufhafz_pP4HOKUcKdrSZFjwqX_Z5QV76sCAOehRFXXslc4nVXp46ws1nj25iqk24vW4qBSgEC19O6A-j9CqGYNqVVpYFkqfijnqXxlwY48bCSYTu-Oq-yMBWZTalF6CLl5eVnZ6ru938Pki3yKijGJ6TzviohfHveAQXAA9arYz5usQ8-wWX3a-Cv98fY17WtHtUjwKJt70g3KPlvnQQHzbi-Lv_uJMhNYPw"      # <-- replace with your sandbox key
SLACK_WEBHOOK = "https://hooks.slack.com/services/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"   # <-- replace with your Slack webhook
DAILY_LIMIT = 10        # how many events to send
INTERVAL = 20           # seconds between sends

# === VALID TRANSFER EVENTS ===
TRANSFER_EVENTS = [
    "INITIATED",
    "SUCCESS",
    "FAILED",
    "REJECTED",
    "RETURNED",
    "CHARGEBACK",
    "REVOKED",
    "OTHER"
]

# === HELPERS ===
def random_id(prefix):
    """Generate a random alphanumeric ID with a prefix."""
    return prefix + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def random_reason():
    reasons = [
        "Test Transfer for bulk remittance",
        "Automated compliance test",
        "Partner sandbox trigger",
        "System health check",
        "Simulated remittance flow"
    ]
    return random.choice(reasons)

def send_slack_message(message: str):
    """Send a notification to Slack (optional)."""
    if not SLACK_WEBHOOK:
        return
    payload = {"text": message}
    try:
        requests.post(SLACK_WEBHOOK, json=payload, timeout=10)
    except Exception as e:
        print(f"⚠️ Slack error: {e}")

# === HEADERS ===
headers = {
    "x-sandbox-app-auth": SANDBOX_AUTH,
    "Content-Type": "application/json"
}

# === MAIN LOOP ===
for i in range(DAILY_LIMIT):
    print(f"\n--- Iteration {i+1}/{DAILY_LIMIT} ---")
    print(f"Endpoint: {ENDPOINT}")
    print(f"Header keys: {list(headers.keys())}")

    payload = {
        "meta": {},
        "eventId": random_id("EVT"),
        "transferId": random_id("TRX"),
        "transferEvent": random.choice(TRANSFER_EVENTS),
        "transferEventReason": random_reason(),
        "transferEventDatetime": datetime.now().isoformat() + "Z"
    }

    print("Prepared payload:")
    try:
        print(json.dumps(payload, indent=2))
    except Exception:
        print(payload)

    print(f"Sending {payload['transferEvent']} event ({payload['eventId']})")

    try:
        response = requests.post(ENDPOINT, headers=headers, json=payload)
        status = response.status_code
        print(f"HTTP Status: {status}")
        if response.text:
            print("Response (truncated 200 chars):")
            print(response.text[:200])

        slack_msg = f"📤 *{payload['transferEvent']}* event sent — `Status {status}`\n• ID: `{payload['eventId']}`\n• Transfer: `{payload['transferId']}`\n• Time: `{payload['transferEventDatetime']}`"
        send_slack_message(slack_msg)

    except Exception as e:
        print(f"Error sending request: {e}")
        send_slack_message(f"❌ Error sending event: {e}")

    print(f"Sleeping for {INTERVAL} seconds before next iteration...")
    time.sleep(INTERVAL)

print("\nAll events processed.")