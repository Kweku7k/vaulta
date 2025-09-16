import os
import httpx
from redis_client import r

EMTECH_BASE_URL = "https://api.emtech.com/integration"
EMTECH_REMITTANCE_EVENT_URL = f"{EMTECH_BASE_URL}/compliance/v2/remittances/events"
EMTECH_TOKEN_URL = f"{EMTECH_BASE_URL}/v1/auth/token"

client_id = os.getenv("EMTECH_CLIENT_ID")
client_secret = os.getenv("EMTECH_CLIENT_SECRET")

def send_remittance_event():
	"""
	Sends a remittance event to EMTECH compliance endpoint using access token from Redis.
	"""
	payload = {
		"meta": {},
		"eventId": "TESTEVENT1234",
		"transferId": "TESTTRANSFER442",
		"transferEvent": "INITIATED",
		"transferEventReason": "Test Transfer for bulk remittance",
		"transferEventDatetime": "2025-08-24T14:15:22Z"
	}
	access_token = r.get("emtech_access_token")
	if not access_token:
		raise RuntimeError("No access token found in Redis. Please authenticate first.")
	headers = {
		"x-sandbox-app-auth": access_token
	}
	try:
		response = httpx.post(EMTECH_REMITTANCE_EVENT_URL, json=payload, headers=headers, timeout=10)
		response.raise_for_status()
		return response.json()
	except Exception as e:
		raise RuntimeError(f"Failed to send remittance event: {e}")


def get_emtech_access_token(client_id: str=client_id, client_secret: str=client_secret) -> str:
	"""
	Sends clientId and clientSecret to EMTECH token endpoint, retrieves accessToken, and stores it in Redis.
	Returns the accessToken.
	"""
	payload = {
		"clientId": client_id,
		"clientSecret": client_secret
	}
	try:
		response = httpx.post(EMTECH_TOKEN_URL, json=payload, timeout=10)
		response.raise_for_status()
		data = response.json()
		access_token = data.get("accessToken")
		if not access_token:
			raise ValueError("No accessToken in response")
		# Store in Redis for future use
		r.set("emtech_access_token", access_token)
		return access_token
	except Exception as e:
		raise RuntimeError(f"Failed to get EMTECH access token: {e}")


