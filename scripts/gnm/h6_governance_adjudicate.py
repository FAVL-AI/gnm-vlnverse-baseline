#!/usr/bin/env python3
"""H6 diagnostic governance adjudication (data-driven; DIAGNOSTIC_ONLY).

Mirrors the H4/H5 dual-guard DriftGuard + VerdictPlane run-card contract, but
computes every number from the H6 eval JSONs (no hardcoded metrics) and stamps
the outcome DIAGNOSTIC_ONLY_NOT_PROMOTED — promotion stays blocked pending
explicit human approval, regardless of the computed gate.

Incumbent = H1 (retained). Candidate = H6 hard-family diagnostic. H5 reported as
context. Guards vs the H1 incumbent:
  improvement guard  -> test_h6hard  (does hard-family TRAINING coverage lift the
                                      fresh HARD held-out families?)
  regression guard   -> test_prior   (continuity anchor: older held-out families)
  context            -> test_h4, test_combined
Each guard: candidate SR>=inc AND SPL>=inc AND NE<=inc+0.1 m.

Claim boundary carried through: fixed placeholder goal => NOT goal-image
conditioning; scripted-expert; not real-robot; not a public benchmark.
"""
import hashlib, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
E = REPO / "assets/experiments/hospital_h2_collection_20260709"
NE_MATERIAL = 0.1
SPLITS = ["test_h4", "test_h6hard", "test_prior", "test_combined"]


def load(model, split):
    p = E / f"h6_eval_{model}_{split}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return {"sr": d["SR"], "osr": d["OSR"], "spl": d["SPL"], "ne_m": d["NE"],
            "ndtw": d["nDTW"], "tl_m": d["TL"], "cls": d["CLS"], "cr": d["CR"],
            "n": d["n_episodes"]}


def sha(p):
    fp = REPO / p
    return hashlib.sha256(fp.read_bytes()).hexdigest() if fp.exists() else None


def guard(inc, cand, name):
    checks = {
        "sr":   {"incumbent": inc["sr"],  "candidate": cand["sr"],
                 "pass": cand["sr"] >= inc["sr"]},
        "spl":  {"incumbent": inc["spl"], "candidate": cand["spl"],
                 "pass": cand["spl"] >= inc["spl"]},
        "ne_m": {"incumbent": inc["ne_m"], "candidate": cand["ne_m"],
                 "pass": cand["ne_m"] <= inc["ne_m"] + NE_MATERIAL,
                 "material_worsening_threshold_m": NE_MATERIAL},
    }
    return {"test": name, "n_test_episodes": cand["n"],
            "pass": all(c["pass"] for c in checks.values()), "checks": checks}


def delta(inc, cand):
    return (f"SR {inc['sr']:.3f}->{cand['sr']:.3f}, SPL {inc['spl']:.3f}->"
            f"{cand['spl']:.3f}, NE {inc['ne_m']:.2f}->{cand['ne_m']:.2f} m, "
            f"nDTW {inc['ndtw']:.3f}->{cand['ndtw']:.3f} (n={cand['n']})")


def main():
    data = {m: {s: load(m, s) for s in SPLITS} for m in ("h1", "h5", "h6")}
    missing = [f"h6_eval_{m}_{s}.json" for m in data for s in SPLITS
               if data[m][s] is None]
    if missing:
        print("[h6-gov] ERROR missing eval JSONs:", missing, file=sys.stderr)
        return 2

    inc, cand = data["h1"], data["h6"]
    improvement = guard(inc["test_h6hard"], cand["test_h6hard"], "h6_fresh_hard_heldout_uturn02_chain02")
    regression = guard(inc["test_prior"], cand["test_prior"], "prior_heldout_uturn_chain_ftL")
    ctx_h4 = guard(inc["test_h4"], cand["test_h4"], "h4_heldout_families_008_012_016")
    combined = guard(inc["test_combined"], cand["test_combined"], "combined_heldout_n12")
    net = "promote" if (improvement["pass"] and regression["pass"]) else "hold"

    dg = {
        "net_gate": net,
        "governance_mode": "DIAGNOSTIC_ONLY_NOT_PROMOTED",
        "rule": ("net PROMOTE would require BOTH the H6-hard-heldout improvement guard "
                 "AND the prior-heldout non-regression guard (SR & SPL >= incumbent, "
                 "NE not materially worse). Reported as diagnostic; promotion is "
                 "administratively BLOCKED pending explicit human approval regardless "
                 "of this gate."),
        "improvement_guard_h6hard": improvement,
        "regression_guard_prior_heldout": regression,
        "context_h4_heldout": ctx_h4,
        "combined_aggregate_context": combined,
        "incumbent_run": "h1_hospital_front_rgb_finetune",
        "candidate_run": "h6_hard_families_seed42",
        "note": (f"H6 vs H1 on fresh HARD held-out ({improvement['pass'] and 'guard PASS' or 'guard FAIL'}): "
                 f"{delta(inc['test_h6hard'], cand['test_h6hard'])}. "
                 f"prior held-out ({regression['pass'] and 'guard PASS' or 'guard FAIL'}): "
                 f"{delta(inc['test_prior'], cand['test_prior'])}. "
                 f"H4 held-out context: {delta(inc['test_h4'], cand['test_h4'])}. "
                 f"combined context: {delta(inc['test_combined'], cand['test_combined'])}. "
                 "Fixed placeholder goal => success/SPL measure scripted-imitation "
                 "reproduction, not goal-image conditioning."),
    }

    vp = {"action": "promote_model", "candidate": "h6_hard_families",
          "scope": "internal Isaac-Hospital-ImageNav-v0 line only",
          "verdict": "deny",
          "governance_mode": "DIAGNOSTIC_ONLY_NOT_PROMOTED",
          "matched_rule": {"match": {"tool": "model.promote",
                                     "args.driftguard_net_gate": net,
                                     "args.diagnostic_only": True},
                           "decision": "deny"},
          "reason": ("H6 is a diagnostic coverage experiment; promotion is blocked by "
                     "policy pending explicit human approval. VerdictPlane denies the "
                     f"promote action (computed dual-guard net_gate={net}).")}

    def metrics_block(m):
        return {s: {k: round(data[m][s][k], 4) for k in
                    ("sr", "osr", "spl", "ne_m", "ndtw", "tl_m", "cls")} for s in SPLITS}

    def card(run, cond, ckpt, model_key, role):
        return {"project": "gnm-vlnverse-baseline", "case_study": "h6_hard_families",
                "run_name": run, "seed": 42,
                "model": {"name": "MobileNetV2-GNM", "condition": cond,
                          "checkpoint_path": ckpt, "checkpoint_sha256": sha(ckpt),
                          "selected_by": "H6 compound-turn validation split (action loss)"
                                         if cond == "h6_candidate" else "n/a (reference)"},
                "dataset": {"name": "Isaac-Hospital-ImageNav-v0 / H6 hard-route families",
                            "camera": "Yahboom front-facing RGB (Isaac Sim)",
                            "train_episodes": 10, "val_episodes": 2,
                            "train_families": "uturn_01/chain_01/ftL_01/sharpmulti_01/tightcorr_01 (a+b)",
                            "val_family": "compound_01 (a+b)",
                            "heldout_h6hard": "uturn_02/chain_02 (n=4, fresh)",
                            "heldout_h4": "008/012/016 (n=6)",
                            "heldout_prior": "uturn/chain/ftL (n=6)",
                            "goal": "h2_weave_J (FIXED placeholder)",
                            "leakage_check": "PASS", "scripted_expert": True},
                "metrics": metrics_block(model_key),
                "collision_rate": "N/A offline (CR 0.0 by construction); recorded "
                                  "collections were 0-contact / route_completed=True",
                "governance_mode": "DIAGNOSTIC_ONLY_NOT_PROMOTED",
                "driftguard": role,
                "claim_boundary": ("Internal Isaac-Hospital-ImageNav-v0 simulation "
                                   "evidence; fixed placeholder goal => NOT goal-image "
                                   "conditioning evidence; scripted-expert imitation; "
                                   "not real-robot, not a public benchmark, no SOTA claim.")}

    adj = {
        "h6_final_adjudication": "DIAGNOSTIC_ONLY_NOT_PROMOTED",
        "experiment": "H6 hard-route-family coverage diagnostic",
        "hypothesis": ("adding CLEAN hard-route families (uturn/chain/ftL/sharpmulti/"
                       "tightcorr) to TRAINING improves success on hard held-out route "
                       "families — the H5 coverage gap, not just a balance gap"),
        "improvement_guard_h6hard": improvement["pass"],
        "regression_guard_prior_heldout": regression["pass"],
        "driftguard_net": net, "verdictplane_verdict": vp["verdict"],
        "h6hard_result": delta(inc["test_h6hard"], cand["test_h6hard"]),
        "prior_heldout_result": delta(inc["test_prior"], cand["test_prior"]),
        "h4_heldout_result": delta(inc["test_h4"], cand["test_h4"]),
        "combined_result": delta(inc["test_combined"], cand["test_combined"]),
        "final_promotion_decision": "NOT PROMOTED (DIAGNOSTIC ONLY)",
        "incumbent": "h1_hospital_front_rgb_finetune RETAINED",
        "candidate": "h6_hard_families retained as diagnostic evidence",
        "collision_regression": "none (CR 0.0 offline; collections 0-contact)",
        "small_n_caveat": "held-out sets are n=4 (h6hard) / n=6 (h4, prior) / n=12 (combined); "
                          "single-episode flips move SR by 0.17-0.25",
        "claim_boundary": ("fixed placeholder goal => NOT goal-image conditioning; "
                           "scripted-expert imitation; diagnostic only"),
        "next_options": ["accept H6 as diagnostic-only (current)",
                         "if H6 lifts hard held-out without prior regression, plan a "
                         "goal-conditioned (non-fixed-goal) follow-up before any promotion",
                         "expand hard-family variants / episodes to reduce small-n"],
    }

    (E / "h6_driftguard_decision.json").write_text(json.dumps(dg, indent=2))
    (E / "h6_verdictplane_record.json").write_text(json.dumps(vp, indent=2))
    (E / "h6_candidate_card.json").write_text(json.dumps(
        card("h6_hard_families_seed42", "h6_candidate",
             "checkpoints/h6_hard_families_finetune/best.pt", "h6",
             {"promotion_candidate": True, "incumbent": "h1_hospital_front_rgb_finetune",
              "decision": net, "governance_mode": "DIAGNOSTIC_ONLY_NOT_PROMOTED"}), indent=2))
    (E / "h6_incumbent_card.json").write_text(json.dumps(
        card("h1_hospital_front_rgb_finetune_on_h6_heldouts", "incumbent",
             "checkpoints/hospital_front_rgb_finetune/best.pt", "h1",
             {"promotion_candidate": False, "incumbent": None,
              "decision": "incumbent_reference"}), indent=2))
    (E / "h6_h5_reference_card.json").write_text(json.dumps(
        card("h5_mixed_replay_on_h6_heldouts", "h5_reference",
             "checkpoints/h5_mixed_replay_finetune/best.pt", "h5",
             {"promotion_candidate": False, "incumbent": None,
              "decision": "prior_diagnostic_reference"}), indent=2))
    (E / "h6_adjudication.json").write_text(json.dumps(adj, indent=2))

    print(json.dumps({"improvement_guard_h6hard": improvement["pass"],
                      "regression_guard_prior": regression["pass"],
                      "net_gate": net, "verdictplane": vp["verdict"],
                      "adjudication": adj["h6_final_adjudication"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
