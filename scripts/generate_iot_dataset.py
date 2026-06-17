"""
Generate the synthetic IoT industrial sensor dataset used in PAYLOADS.md.

Outputs:
  - scripts/iot_dataset.json      full 500-row dataset
  - scripts/iot_chunk_<n>.json    5 chunks of 100 rows each

Hashes are deterministic with random.seed(42).
Run from the project root: python scripts/generate_iot_dataset.py
"""
import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.props.transcript_hasher import compute_corpus_root

random.seed(42)

devices = [f"SEN-{i:03d}" for i in range(1, 21)]
base_ts = 1748700000  # 2025-05-31 ~00:00 UTC

null_pressure_indices = set(random.sample(range(500), 62))   # 12.4%
null_vibration_indices = set(random.sample(range(500), 31))  # 6.2%
anomaly_indices = set(random.sample(range(500), 79))         # 15.8%

rows = []
for i in range(500):
    is_anomaly = i in anomaly_indices
    rows.append({
        "timestamp": base_ts + i * 300,
        "device_id": devices[i % 20],
        "temperature_c": round(random.uniform(18.0, 85.0) if is_anomaly else random.uniform(18.0, 45.0), 2),
        "humidity_pct": round(random.uniform(20.0, 95.0), 2),
        "pressure_hpa": None if i in null_pressure_indices else round(random.uniform(980.0, 1050.0), 2),
        "vibration_ms2": None if i in null_vibration_indices else round(random.uniform(0.1, 12.0) if is_anomaly else random.uniform(0.1, 3.5), 3),
        "label": "anomaly" if is_anomaly else "normal",
    })

chunks = [rows[i * 100:(i + 1) * 100] for i in range(5)]
chunk_hashes = []
for n, chunk in enumerate(chunks):
    h = hashlib.sha256(json.dumps(chunk, sort_keys=True).encode()).hexdigest()
    chunk_hashes.append(h)
    out = os.path.join(os.path.dirname(__file__), f"iot_chunk_{n}.json")
    with open(out, "w") as f:
        json.dump(chunk, f, indent=2)
    print(f"Chunk {n}: {h}")

merkle_root = compute_corpus_root(chunk_hashes)
print(f"Merkle root: {merkle_root}")

full_path = os.path.join(os.path.dirname(__file__), "iot_dataset.json")
with open(full_path, "w") as f:
    json.dump(rows, f, indent=2)
print(f"Full dataset written to {full_path}")

# Quality metrics summary
null_p = sum(1 for r in rows if r["pressure_hpa"] is None)
null_v = sum(1 for r in rows if r["vibration_ms2"] is None)
n_anom = sum(1 for r in rows if r["label"] == "anomaly")
print(f"\nQuality metrics:")
print(f"  row_count: {len(rows)}")
print(f"  null pressure_hpa: {null_p} ({null_p/500:.1%})")
print(f"  null vibration_ms2: {null_v} ({null_v/500:.1%})")
print(f"  anomaly: {n_anom} ({n_anom/500:.1%}), normal: {500-n_anom} ({(500-n_anom)/500:.1%})")
