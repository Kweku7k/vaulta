import os
import requests
baseUrl = "https://api.bridge.xyz/v0"

def get_all_transactions():
    apiUrl = f"{baseUrl}/transfers"
    headers = {"Api-Key":os.getenv('BRIDGE_LIVE_API_KEY')}
    response = requests.get(apiUrl, headers=headers)
    if response.status_code == 200:
        transactions = response.json()
        return transactions
    else:
        return None

