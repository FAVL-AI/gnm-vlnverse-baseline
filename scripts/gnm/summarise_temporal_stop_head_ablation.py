from __future__ import annotations

import csv
import json
import re
from pathlib import Path


BASE_OUT = Path("results/bo_reviewer_packet/temporal_stop_head_ablation")
SUMMARY_CSV = BASE_OUT / "24_temporal_stop_head_ablation.csv"
SUMMARY_MD = BASE_OUT / "24_temporal_stop_head_ablation.md"


def main() -> None:
    rows: list[dict[str, str]] = []

    for run_dir in sorted(BASE_OUT.glob("seq*_k*")):
        match = re.match(r"seq(\d+)_k(\d+)", run_dir.name)
        if not match:
            continue

        seq_len, stable_k = match.group(1), match.group(2)
        result_csv = run_dir / "22_temporal_stop_head.csv"
        meta_json = run_dir / "22_temporal_stop_head_meta.json"

        if not result_csv.exists():
            print(f"[SKIP] missing {result_csv}")
            continue

        with result_csv.open(newline="") as f:
            reader = csv.DictReader(f)
            result_rows = list(reader)

        if not result_rows:
            print(f"[SKIP] empty {result_csv}")
            continue

        row = result_rows[0]
        row = {
            "seq_len": seq_len,
            "stable_k": stable_k,
            "best_threshold": row.get("best_threshold", ""),
            "episodes": row.get("episodes", ""),
            "SR_percent": row.get("SR_percent", ""),
            "OSR_percent": row.get("OSR_percent", ""),
            "NE_m": row.get("NE_m", ""),
            "TL_m": row.get("TL_m", ""),
            "stop_fired": row.get("stop_fired", ""),
            "mean_stop_step": row.get("mean_stop_step", ""),
            "run_dir": str(run_dir),
        }

        if meta_json.exists():
            with meta_json.open() as f:
                meta = json.load(f)
            row["feature_dim"] = str(meta.get("feature_dim", ""))
        else:
            row["feature_dim"] = ""

        rows.append(row)

    if not rows:
        raise SystemExit(f"No completed ablation rows found under {BASE_OUT}")

    def score(row: dict[str, str]) -> tuple[float, float, float]:
        sr = float(row["SR_percent"])
        osr = float(row["OSR_percent"])
        ne = float(row["NE_m"])
        return sr, osr, -ne

    rows = sorted(rows, key=score, reverse=True)
    fieldnames = [
        "seq_len",
        "stable_k",
        "best_threshold",
        "episodes",
        "SR_percent",
        "OSR_percent",
        "NE_m",
        "TL_m",
        "stop_fired",
        "mean_stop_step",
        "feature_dim",
        "run_dir",
    ]

    BASE_OUT.mkdir(parents=True, exist_ok=True)

    with SUMMARY_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    best = rows[0]

    lines = [
        "# Temporal Stop-Head Ablation",
        "",
        "This ablation evaluates the temporal neural stop head across sequence length and stable-stop confirmation window.",
        "",
        "Runtime decisions use only GNM outputs and derived temporal features. Ground-truth geometry is used only for training labels and final metrics.",
        "",
        "## Best result",
        "",
        "| seq_len | stable_k | threshold | SR | OSR | NE (m) | TL (m) | stop_fired | mean_stop_step |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {best['seq_len']} | {best['stable_k']} | {best['best_threshold']} | {float(best['SR_percent']):.1f}% | {float(best['OSR_percent']):.1f}% | {float(best['NE_m']):.2f} | {float(best['TL_m']):.2f} | {best['stop_fired']} | {best['mean_stop_step']} |",
        "",
        "## Full ablation table",
        "",
        "| seq_len | stable_k | threshold | SR | OSR | NE (m) | TL (m) | stop_fired | mean_stop_step |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in rows:
        lines.append(
            f"| {row['seq_len']} | {row['stable_k']} | {row['best_threshold']} | "
            f"{float(row['SR_percent']):.1f}% | {float(row['OSR_percent']):.1f}% | "
            f"{float(row['NE_m']):.2f} | {float(row['TL_m']):.2f} | "
            f"{row['stop_fired']} | {row['mean_stop_step']} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This table tests whether the temporal stop-head result is sensitive to the history length and the number of consecutive positive stop predictions required before stopping.",
            "",
            "The v1.0 reference setting is seq_len=8 and stable_k=3, which reached 33.3% held-out SR.",
            "",
        ]
    )

    SUMMARY_MD.write_text("\n".join(lines))

    print(f"[OK] wrote {SUMMARY_CSV}")
    print(f"[OK] wrote {SUMMARY_MD}")
    print("[BEST]", best)


if __name__ == "__main__":
    main()
