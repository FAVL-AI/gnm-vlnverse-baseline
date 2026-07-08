"""Route-invariant stop-rule recalibration study (offline; no authority).

Protocol: rule parameters are tuned ONLY on the three calibration shadow
episodes (A/B/C); the chosen configuration is then evaluated, untouched,
on the held-out D/E BASELINE logs. The truncated D/E authority logs are
listed as sources but excluded from rule evaluation (the gate cut their
approaches short). Improvement numbers on D/E are strictly retrospective
counterfactuals on logs. Every rule is a recalibration candidate or
explicitly exploratory/diagnostic; nothing here earns an improvement
claim — that requires a fresh held-out authority rerun.

Outputs: assets/experiments/recalibration/route_invariant_stop_<date>/
    summary.json, summary.csv, report.md
"""

import csv
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TUNE = ["hospital_straight_short_A", "hospital_straight_medium_B",
        "hospital_low_curvature_C"]
HELDOUT = ["authcmp_D_baseline", "authcmp_E_baseline"]
TRUNCATED = ["authcmp_D_stopauth", "authcmp_E_stopauth"]
K = 3
BASELINE_FINALS = {"authcmp_D_baseline": None, "authcmp_E_baseline": None}


def newest(prefix):
    root = REPO / "assets/experiments/trajectories"
    dirs = sorted(d for d in root.iterdir()
                  if d.is_dir() and d.name.startswith(prefix))
    return dirs[-1] if dirs else None


def load(prefix):
    d = newest(prefix)
    rows = [json.loads(l) for l in (d / "trajectory.jsonl").open()]
    ep = [r for r in rows if r["watchdog_state"] not in
          ("zeroed_hold", "goal_stop_zeroed")
          and r.get("distance_to_goal_m") is not None]
    samples, last = [], None
    travelled = 0.0
    prev_xy = None
    for r in ep:
        gd = r.get("shadow_gnm_goal_distance")
        if gd is None:
            continue
        xy = (r["robot_position_x"], r["robot_position_y"])
        if prev_xy is not None:
            travelled += ((xy[0] - prev_xy[0]) ** 2
                          + (xy[1] - prev_xy[1]) ** 2) ** 0.5
        prev_xy = xy
        if gd != last:
            samples.append({"step": r["step_idx"], "pred": gd,
                            "d2g": r["distance_to_goal_m"],
                            "odom_v": abs(r.get("odom_linear_velocity", 0.0)),
                            "progress": travelled})
            last = gd
    meta = json.loads((d / "episode_metadata.json").read_text())
    d2g_series = [s["d2g"] for s in samples]
    return {"name": prefix, "dir": d.name, "samples": samples,
            "min_d2g": min(d2g_series),
            "argmin_idx": d2g_series.index(min(d2g_series)),
            "final_d2g": meta["final_distance_to_goal_m"],
            "init_pred": samples[0]["pred"]}


def run_rule(ep, trigger):
    """k-consecutive trigger over samples; returns firing record or None."""
    consec = 0
    state = {"min_pred": float("inf"), "rise_run": 0, "prev_pred": None}
    for i, s in enumerate(ep["samples"]):
        if s["pred"] < state["min_pred"]:
            state["min_pred"] = s["pred"]
        if state["prev_pred"] is not None and s["pred"] > state["prev_pred"]:
            state["rise_run"] += 1
        elif state["prev_pred"] is not None and s["pred"] < state["prev_pred"]:
            state["rise_run"] = 0
        state["prev_pred"] = s["pred"]
        consec = consec + 1 if trigger(ep, s, state) else 0
        if consec >= K:
            pen = round(s["d2g"] - ep["min_d2g"], 3)
            return {"fires": True, "stop_step": s["step"],
                    "d2g_at_stop": round(s["d2g"], 3),
                    "pred_at_stop": round(s["pred"], 2),
                    "timing": "early" if i < ep["argmin_idx"] else "late",
                    "penalty_vs_min_m": pen,
                    "false_stop": s["d2g"] > 0.8 * ep["samples"][0]["d2g"]}
    return {"fires": False}


FAMILIES = {
    "rel_min_margin": {
        "kind": "relative-progress + local-min margin",
        "params": [{"margin": m, "min_prog": 1.0} for m in (0.5, 1.0, 2.0)],
        "trigger": lambda p: (lambda ep, s, st:
                              s["progress"] >= p["min_prog"]
                              and s["pred"] >= st["min_pred"] + p["margin"]),
    },
    "trend_reversal_prog": {
        "kind": "trend reversal after minimum, progress-guarded",
        "params": [{"rise_k": rk, "min_prog": 1.0} for rk in (3, 5)],
        "trigger": lambda p: (lambda ep, s, st:
                              s["progress"] >= p["min_prog"]
                              and st["rise_run"] >= p["rise_k"]),
    },
    "normalized_pred": {
        "kind": "normalized predicted distance",
        "params": [{"frac": f} for f in (0.35, 0.5)],
        "trigger": lambda p: (lambda ep, s, st:
                              s["pred"] <= p["frac"] * ep["init_pred"]),
    },
    "hybrid_min_rise_motion": {
        "kind": "hybrid: progress + past-minimum rise + moving",
        "params": [{"margin": m, "rise_k": 2, "min_prog": 1.0,
                    "min_v": 0.05} for m in (0.5, 1.0)],
        "trigger": lambda p: (lambda ep, s, st:
                              s["progress"] >= p["min_prog"]
                              and s["pred"] >= st["min_pred"] + p["margin"]
                              and st["rise_run"] >= p["rise_k"]
                              and s["odom_v"] >= p["min_v"]),
    },
    "true_d2g_reversal": {
        "kind": "PRIVILEGED DIAGNOSTIC (uses ground-truth d2g; "
                "not deployable in ImageNav)",
        "params": [{"margin": 0.05}],
        "trigger": lambda p: (lambda ep, s, st:
                              s["progress"] >= 1.0
                              and s["d2g"] >= ep["min_d2g"] + p["margin"]
                              and s["odom_v"] >= 0.05),
    },
}


def score_tune(results):
    fired = [r for r in results if r["fires"]]
    if len(fired) < len(results) or any(r["false_stop"] for r in fired):
        return None
    return sum(r["penalty_vs_min_m"] for r in fired) / len(fired)


def main():
    tune_eps = [load(p) for p in TUNE]
    held_eps = [load(p) for p in HELDOUT]
    base_finals = {ep["name"]: ep["final_d2g"] for ep in held_eps}

    rules_out = []
    for fam, spec in FAMILIES.items():
        best = None
        for params in spec["params"]:
            trig = spec["trigger"](params)
            res = [run_rule(ep, trig) for ep in tune_eps]
            sc = score_tune(res)
            if sc is not None and (best is None or sc < best["score"]):
                best = {"params": params, "score": sc, "tune_results": res}
        label = ("privileged_diagnostic" if fam == "true_d2g_reversal"
                 else "recalibration_candidate")
        if best is None:
            rules_out.append({"family": fam, "kind": spec["kind"],
                              "label": label, "tuned": False,
                              "note": "no parameterisation fired all "
                                      "tuning episodes without false stops"})
            continue
        trig = spec["trigger"](best["params"])
        held = {ep["name"]: run_rule(ep, trig) for ep in held_eps}
        improved = {n: (r["fires"] and r["d2g_at_stop"] < base_finals[n])
                    for n, r in held.items()}
        rules_out.append({
            "family": fam, "kind": spec["kind"], "label": label,
            "tuned": True, "chosen_params": best["params"],
            "tune_mean_penalty_m": round(best["score"], 3),
            "tune_fired": f"{sum(r['fires'] for r in best['tune_results'])}"
                          f"/{len(tune_eps)}",
            "heldout": {n: r for n, r in held.items()},
            "heldout_fired": f"{sum(r['fires'] for r in held.values())}"
                             f"/{len(held_eps)}",
            "heldout_false_stops": sum(
                1 for r in held.values() if r["fires"] and r["false_stop"]),
            "would_improve_heldout_vs_baseline_final": improved,
            "transfer_ok": all(r["fires"] and not r["false_stop"]
                               for r in held.values()),
        })

    rules_out.append({
        "family": "absolute_dist_pred_gate", "label": "REJECTED",
        "kind": "absolute predicted-distance threshold (dist_pred<=4.5,k=3)",
        "note": "rejected out-of-sample in commit 8b625eb: fired early on "
                "held-out reverse route (stop at true d2g 1.479/1.103 m), "
                "worse than no-stop baseline by +0.992/+0.608 m",
    })
    rules_out.append({
        "family": "live_domain_logistic_fit", "label": "exploratory",
        "kind": "learned live-domain calibration model",
        "note": "deferred: only 3 independent tuning episodes; fitting "
                "would be in-sample noise. Requires a larger live episode "
                "set before it is meaningful.",
    })

    viable = [r for r in rules_out
              if r.get("transfer_ok") and r["label"] == "recalibration_candidate"]
    preferred = min(
        viable,
        key=lambda r: sum(v["penalty_vs_min_m"]
                          for v in r["heldout"].values()) / len(r["heldout"])
    ) if viable else None

    out = (REPO / "assets/experiments/recalibration"
           / f"route_invariant_stop_{date.today():%Y%m%d}")
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "study": "route_invariant_stop_recalibration",
        "protocol": "tuned on A/B/C only; D/E baselines held out as "
                    "validation; D/E authority logs excluded (truncated)",
        "label": "no_authority_no_improvement_claim",
        "sources_tune": [ep["dir"] for ep in tune_eps],
        "sources_heldout_validation": [ep["dir"] for ep in held_eps],
        "sources_listed_truncated": [newest(p).name for p in TRUNCATED],
        "heldout_baseline_finals": base_finals,
        "rules": rules_out,
        "preferred_candidate": preferred["family"] if preferred else None,
        "preferred_params": preferred["chosen_params"] if preferred else None,
        "next_step": "held-out authority rerun with the preferred candidate "
                     "on NEW goals before any improvement claim",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["family", "label", "tuned", "params", "tune_fired",
                    "heldout_fired", "heldout_false_stops", "transfer_ok"])
        for r in rules_out:
            w.writerow([r["family"], r["label"], r.get("tuned", ""),
                        json.dumps(r.get("chosen_params", "")),
                        r.get("tune_fired", ""), r.get("heldout_fired", ""),
                        r.get("heldout_false_stops", ""),
                        r.get("transfer_ok", "")])

    lines = ["# Route-invariant stop recalibration report\n",
             "Absolute predicted-distance gate: **REJECTED** "
             "(held-out failure, commit 8b625eb).\n"]
    for r in rules_out:
        if r.get("tuned"):
            hd = "; ".join(
                f"{n}: {'fires@'+str(v['d2g_at_stop'])+'m ('+v['timing']+')' if v['fires'] else 'no fire'}"
                for n, v in r["heldout"].items())
            lines.append(f"- **{r['family']}** ({r['label']}): params "
                         f"{r['chosen_params']}, tune {r['tune_fired']}, "
                         f"held-out {r['heldout_fired']} [{hd}] "
                         f"transfer_ok={r['transfer_ok']}")
        else:
            lines.append(f"- **{r['family']}** ({r['label']}): "
                         f"{r.get('note','')}")
    lines.append(f"\nPreferred candidate: **{summary['preferred_candidate']}**"
                 f" {summary['preferred_params']}" if preferred
                 else "\nNo candidate survived held-out validation.")
    lines.append("\nNo improvement claim: authority rerun on fresh held-out "
                 "goals is required first.")
    (out / "report.md").write_text("\n".join(lines) + "\n")

    print(json.dumps({k: summary[k] for k in
                      ("preferred_candidate", "preferred_params")}, indent=2))
    for r in rules_out:
        if r.get("tuned"):
            print(f"{r['family']:28s} tune={r['tune_fired']} "
                  f"heldout={r['heldout_fired']} "
                  f"false={r['heldout_false_stops']} "
                  f"transfer_ok={r['transfer_ok']} "
                  f"improve={r['would_improve_heldout_vs_baseline_final']}")
        else:
            print(f"{r['family']:28s} [{r['label']}] {r.get('note','')[:60]}")
    print(f"outputs: {out}")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
