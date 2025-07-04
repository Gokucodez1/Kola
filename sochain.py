import requests
from utils import get_ltc_address

def check_payment(expected_amount):
    address = get_ltc_address()
    response = requests.get(f"https://sochain.com/api/v2/address/LTC/{address}")
    for tx in response.json()["data"]["txs"]:
        if abs(float(tx["value"]) - expected_amount) < 0.00000001:
            return {
                "txid": tx["txid"],
                "amount": tx["value"],
                "confirmations": tx["confirmations"]
            }
    return None
