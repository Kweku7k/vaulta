import os
import requests
from db.models import Customer
# from core.config import settings

def onboard_customer_to_bridge(customer: Customer) -> dict:
    url = f"{os.getenv("BRIDGE_BASE_URL")}/customers"

    payload = {
        "type": customer.type,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "email": customer.email,
        "phone": customer.phone,
        "birth_date": customer.birth_date,
        "address": {
            "street_line_1": customer.address,  # split this later if it's JSON or multiple fields
            "country": "GH",  # You can replace this with a real field
            "city": "Accra",
            "street_line_2": "",
            "state": "Greater Accra",
            "postal_code": "00233"
        },
        "tax_identification_number": customer.tax_identification_number,
        "gov_id_image_front": customer.gov_id_image_front,
        "gov_id_image_back": customer.gov_id_image_back,
        "signed_agreement_id": customer.signed_agreement_id
    }

    headers = {
        "Authorization": f"Bearer {os.environ("BRIDGE_API_KEY")}",
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)

    response.raise_for_status()  # raises HTTPError for non-2xx
    return response.json()