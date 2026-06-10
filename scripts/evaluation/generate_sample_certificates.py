#!/usr/bin/env python3
"""Generate a small sample JSONL certificate file for testing and demos.

Usage:
    python3 scripts/evaluation/generate_sample_certificates.py
    python3 scripts/evaluation/generate_sample_certificates.py --output /tmp/my_certs.jsonl --n 50
"""

from __future__ import annotations

import argparse
import json
import math
import random


def generate(n: int, d_safe: float, seed: int, output: str):
    random.seed(seed)
    lines = []
    for i in range(n):
        dist = 0.6 + random.uniform(0, 1.5)
        h = round(dist ** 2 - d_safe ** 2, 4)
        cbf = dist < 0.8
        cert = {
            "timestamp": round(i * 0.1, 2),
            "model_name": random.choice(["gnm", "vint", "nomad"]),
            "u_nom": [round(random.uniform(0.0, 0.3), 3), round(random.uniform(-0.2, 0.2), 3)],
            "u_safe": [round(0.1 if cbf else random.uniform(0.1, 0.3), 3), round(random.uniform(-0.1, 0.1), 3)],
            "h_min": h,
            "min_dist_m": round(dist, 4),
            "cbf_active": cbf,
            "qp_status": "optimal",
            "constraint_margin_min": round(h * 0.1, 4),
            "latency_ms": round(random.uniform(5.0, 40.0), 1),
            "safe": True,
            "notes": "",
        }
        lines.append(json.dumps(cert))

    with open(output, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"[FleetSafe] Wrote {n} sample certificates → {output}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/tmp/fleetsafe_sample_certs.jsonl")
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--d-safe", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    generate(args.n, args.d_safe, args.seed, args.output)


if __name__ == "__main__":
    main()
