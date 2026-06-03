import json, base64, httpx

eml_b64 = base64.b64encode(open("tests/fixtures/sample.eml", "rb").read()).decode()

payload = {
    "buyer_budget": 120,
    "floor_price": 60,
    "buyer_requirements": "US demographic data",
    "data_description": "US census dataset",
    "data_hash": "8eb0d327402f025f76800c61c5e5a8a9eb7f4dd75b828aa75fb1bec12a0aeead",
    "seller_proof": {
        "algorithm": "sha256",
        "chunk_count": 3,
        "chunk_hashes": [
            "7dbc0ac52b859c0da1e912cc0540efac34f317fca0c58ecadc2e335eb5f05489",
            "d923d226228953d6d1fad35e9b9906c6d54c591df2d7b26800f9b47ca64df35e",
            "535c41b0c21e5c19d4fcd921605c512abf054b15e6bda09c631c164bcbce3235"
        ],
        "root_hash": "8eb0d327402f025f76800c61c5e5a8a9eb7f4dd75b828aa75fb1bec12a0aeead"
    },
    "seller_address": "0x4812fC05e79ddc616346d10A8826B2bdf5e6ab20",
    "escrow_amount_eth": 0.001,
    "seller_email_eml": eml_b64
}

r = httpx.post(
    "https://4f385963134c20c3c698148c2864bf6dc1438858-8000.dstack-pha-prod5.phala.network/api/deals/run",
    json=payload,
    timeout=120
)

data = r.json()
print(json.dumps(data.get("dkim_verification"), indent=2))