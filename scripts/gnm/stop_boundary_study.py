"""Firing-boundary recalibration study for the temporal stop head.

Pure offline analysis of the three live hospital shadow episodes — no
Isaac, no authority, no model changes. Characterizes why the trained head
fired in episode A but not B/C, then sweeps RECALIBRATION CANDIDATE rules
against the logged signals and measures their trade-offs.

Outputs:
    assets/experiments/recalibration/stop_head_boundary_<date>/summary.json
    assets/experiments/recalibration/stop_head_boundary_<date>/summary.csv

Every rule is a recalibration candidate only. Nothing here claims
improvement; improvement requires authority episodes.
"""

import csv
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTES = ["hospital_straight_short_A", "hospital_straight_medium_B",
          "hospital_low_curvature_C"]
STABLE_K = 3
# false stop: rule fires before meaningful progress (true d2g still above
# 80% of the start distance)
FALSE_STOP_FRAC = 0.8


def newest(prefix):
    root = REPO / "assets/experiments/trajectories"
    dirs = sorted(d for d in root.iterdir()
                  if d.is_dir() and d.name.startswith(prefix))
    return dirs[-1] if dirs else None


def load_episode(prefix):
    ep_dir = newest(prefix)
    meta = json.loads((ep_dir / "episode_metadata.json").read_text())
    rows = [json.loads(l) for l in (ep_dir / "trajectory.jsonl").open()]
    ep = [r for r in rows if r["watchdog_state"] != "zeroed_hold"
          and r.get("distance_to_goal_m") is not None]
    # one sample per inference: keep rows where the GNM prediction changed
    samples, last = [], None
    for r in ep:
        gd = r.get("shadow_gnm_goal_distance")
        if gd is None:
            continue
        key = (gd, r.get("stop_probability"))
        if key != last:
            samples.append({
                "step": r["step_idx"],
                "sim_time": r["sim_time"],
                "d2g": r["distance_to_goal_m"],
                "dist_pred": gd,
                "prob": r.get("stop_probability") or 0.0,
            })
            last = key
    d2g_series = [s["d2g"] for s in samples]
    return {
        "name": prefix,
        "dir": ep_dir.name,
        "samples": samples,
        "start_d2g": d2g_series[0],
        "min_d2g": min(d2g_series),
        "final_d2g": meta["final_distance_to_goal_m"],
        "min_dist_pred": min(s["dist_pred"] for s in samples),
        "dist_pred_at_nearest": min(
            samples, key=lambda s: s["d2g"])["dist_pred"],
        "eval_hz_sim": round(len(samples) / (samples[-1]["sim_time"]
                                             - samples[0]["sim_time"]), 1),
        "current_fired_step":
            json.loads((ep_dir / "episode_metadata.json").read_text())
            .get("stop_head_would_have_stopped_step"),
    }


def eval_rule(episodes, name, kind, trigger):
    """trigger(samples, i, state) -> bool; k-consecutive firing rule."""
    per_ep = []
    for ep in episodes:
        consec, fired_at = 0, None
        state = {"min_pred": float("inf")}
        for i, s in enumerate(ep["samples"]):
            state["min_pred"] = min(state["min_pred"], s["dist_pred"])
            if trigger(ep["samples"], i, state):
                consec += 1
            else:
                consec = 0
            if consec >= STABLE_K:
                fired_at = i
                break
        if fired_at is None:
            per_ep.append({"episode": ep["name"], "fires": False})
            continue
        s = ep["samples"][fired_at]
        per_ep.append({
            "episode": ep["name"], "fires": True,
            "stop_step": s["step"],
            "true_d2g_at_stop": round(s["d2g"], 3),
            "overshoot_avoided_m": round(ep["final_d2g"] - s["d2g"], 3),
            "late_stop_m_past_nearest": round(s["d2g"] - ep["min_d2g"], 3)
            if s["d2g"] >= ep["min_d2g"] else 0.0,
            "false_stop": s["d2g"] > FALSE_STOP_FRAC * ep["start_d2g"],
        })
    fired = [e for e in per_ep if e["fires"]]
    return {
        "rule": name, "kind": kind,
        "label": "recalibration_candidate",
        "episodes_fired": len(fired),
        "episodes_missed": len(per_ep) - len(fired),
        "mean_true_d2g_at_stop": round(
            sum(e["true_d2g_at_stop"] for e in fired) / len(fired), 3)
        if fired else None,
        "mean_overshoot_avoided_m": round(
            sum(e["overshoot_avoided_m"] for e in fired) / len(fired), 3)
        if fired else None,
        "false_stops": sum(1 for e in fired if e["false_stop"]),
        "max_late_stop_m": max(
            (e["late_stop_m_past_nearest"] for e in fired), default=None),
        "per_episode": per_ep,
    }


def main():
    episodes = [load_episode(r) for r in ROUTES]

    print("── firing-boundary characterization ──")
    for ep in episodes:
        print(f"{ep['name']}: start_d2g={ep['start_d2g']:.3f} "
              f"min_d2g={ep['min_d2g']:.3f} final={ep['final_d2g']:.3f} | "
              f"dist_pred min={ep['min_dist_pred']:.2f} "
              f"at_nearest={ep['dist_pred_at_nearest']:.2f} | "
              f"eval {ep['eval_hz_sim']} Hz(sim) | "
              f"current rule fired: {ep['current_fired_step'] is not None}")

    rules = []
    rules.append(eval_rule(
        episodes, "current_prob0.5_k3", "probability",
        lambda ss, i, st: ss[i]["prob"] >= 0.5))
    for thr in (0.05, 0.2):
        rules.append(eval_rule(
            episodes, f"prob{thr}_k3", "probability",
            lambda ss, i, st, t=thr: ss[i]["prob"] >= t))
    for tau in (1.5, 2.5, 3.5, 4.5):
        rules.append(eval_rule(
            episodes, f"dist_pred<={tau}_k3", "predicted-distance",
            lambda ss, i, st, t=tau: ss[i]["dist_pred"] <= t))
    for delta in (0.5, 1.0, 2.0):
        rules.append(eval_rule(
            episodes, f"trend_reversal+{delta}_k3", "trend-after-minimum",
            lambda ss, i, st, d=delta:
                ss[i]["dist_pred"] >= st["min_pred"] + d))
    for tau, delta in ((5.0, 0.5), (6.0, 1.0)):
        rules.append(eval_rule(
            episodes, f"hybrid_pred<={tau}_rev+{delta}_k3", "hybrid",
            lambda ss, i, st, t=tau, d=delta:
                ss[i]["dist_pred"] <= t
                and ss[i]["dist_pred"] >= st["min_pred"] + d))

    print("\n── recalibration candidate sweep ──")
    hdr = (f"{'rule':32s} {'fires':>5s} {'miss':>4s} {'meanD@stop':>10s} "
           f"{'overshootAvoid':>14s} {'falseStops':>10s} {'maxLate':>8s}")
    print(hdr)
    for r in rules:
        print(f"{r['rule']:32s} {r['episodes_fired']:>5d} "
              f"{r['episodes_missed']:>4d} "
              f"{str(r['mean_true_d2g_at_stop']):>10s} "
              f"{str(r['mean_overshoot_avoided_m']):>14s} "
              f"{r['false_stops']:>10d} {str(r['max_late_stop_m']):>8s}")

    # recommendation: fires all, no false stops, best mean stop distance
    viable = [r for r in rules
              if r["episodes_missed"] == 0 and r["false_stops"] == 0]
    best = min(viable, key=lambda r: r["mean_true_d2g_at_stop"]) \
        if viable else None

    out = REPO / "assets/experiments/recalibration" / \
        f"stop_head_boundary_{date.today():%Y%m%d}"
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "study": "stop_head_firing_boundary_recalibration",
        "label": "recalibration_candidates_only_no_authority_no_improvement_claim",
        "source_episodes": [ep["dir"] for ep in episodes],
        "characterization": [
            {k: ep[k] for k in ("name", "dir", "start_d2g", "min_d2g",
                                "final_d2g", "min_dist_pred",
                                "dist_pred_at_nearest", "eval_hz_sim")}
            for ep in episodes],
        "rules": rules,
        "recommended_candidate": best["rule"] if best else None,
        "recommendation_basis": (
            "fires in all episodes with zero false stops and the smallest "
            "mean true distance at stop; candidate only — authority "
            "episodes must measure actual behaviour before any "
            "improvement claim") if best else "no viable candidate",
    }
    with open(out / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rule", "kind", "fires", "missed", "mean_d2g_at_stop",
                    "mean_overshoot_avoided_m", "false_stops",
                    "max_late_stop_m"])
        for r in rules:
            w.writerow([r["rule"], r["kind"], r["episodes_fired"],
                        r["episodes_missed"], r["mean_true_d2g_at_stop"],
                        r["mean_overshoot_avoided_m"], r["false_stops"],
                        r["max_late_stop_m"]])
    print(f"\nrecommended recalibration candidate: "
          f"{summary['recommended_candidate']}")
    print(f"summary written: {out}")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
