# smoke_dkim_doh.py
# Run this directly inside the Phala CVM after deployment to confirm
# DoH is reachable and returning real DKIM keys.
#
# Usage: python smoke_dkim_doh.py

from app.dkim.verifier import _doh_get_txt

print("Testing DoH lookup for google._domainkey.gmail.com ...")
records = _doh_get_txt(b"google._domainkey.gmail.com")
assert records, "FAIL — no records returned from DoH"
print(f"OK — got {len(records)} record(s)")
for r in records:
    for seg in r.strings:
        print(" ", seg[:80])
print("\nDoH is working correctly inside the CVM.")
