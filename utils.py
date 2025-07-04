import random
import string
import sqlite3
import requests
from bitcoinlib.wallets import Wallet
from datetime import datetime

# Initialize database
conn = sqlite3.connect('deals.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS deals
                 (channel_id INT PRIMARY KEY,
                  deal_code TEXT,
                  sender_id INT,
                  receiver_id INT,
                  amount_ltc REAL,
                  amount_usd REAL,
                  status TEXT)''')
conn.commit()

def generate_deal_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

def get_live_rate():
    response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd")
    return response.json()["litecoin"]["usd"]

def get_ltc_address():
    with open('ltcaddy.txt') as f:
        return f.read().strip()

def get_wif_key():
    with open('wifkey.txt') as f:
        return f.read().strip()

def send_ltc(receiver, amount):
    wallet = Wallet.import_key("escrow_bot", get_wif_key(), network='litecoin')
    tx = wallet.send_to(receiver, amount, fee=0.0001)
    return tx.txid
