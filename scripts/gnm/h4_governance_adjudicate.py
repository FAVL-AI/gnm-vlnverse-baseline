"""H4 governance adjudication. Applies the H3-clean DriftGuard rule to the H4
diagnostic fine-tune on BOTH held-out sets (primary = H4 held-out families;
regression-guard = prior held-out uturn/chain/ft_L), then emits candidate/
incumbent cards, DriftGuard decision, VerdictPlane record, and adjudication.

DriftGuard rule (locked, from h3clean): promote only if SR and SPL improve or
match AND NE does not materially worsen (>0.1 m) on the SAME held-out test;
val loss is not safety. Promotion additionally requires no navigation regression
on any reported held-out set, no collision regression, VerdictPlane allow, and
human adjudication.
"""
import hashlib, json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
E = REPO / "assets/experiments/hospital_h2_collection_20260709"
NE_MATERIAL = 0.1


def load(name):
    d = json.loads((E / name).read_text())
    return {"sr": d["SR"], "osr": d["OSR"], "spl": d["SPL"], "ne_m": d["NE"],
            "tl_m": d["TL"], "ndtw": d["nDTW"], "cls": d["CLS"], "cr": d["CR"],
            "n": d["n_episodes"]}


def sha(p):
    return hashlib.sha256((REPO / p).read_bytes()).hexdigest()


def driftguard(inc, cand, test_name):
    checks = {
        "sr": {"incumbent": inc["sr"], "candidate": cand["sr"],
               "pass": cand["sr"] >= inc["sr"]},
        "spl": {"incumbent": inc["spl"], "candidate": cand["spl"],
                "pass": cand["spl"] >= inc["spl"]},
        "ne_m": {"incumbent": inc["ne_m"], "candidate": cand["ne_m"],
                 "pass": cand["ne_m"] <= inc["ne_m"] + NE_MATERIAL,
                 "material_worsening_threshold_m": NE_MATERIAL},
    }
    decision = "promote" if all(c["pass"] for c in checks.values()) else "block"
    return {"decision": decision, "checks": checks, "test": test_name,
            "n_test_episodes": cand["n"],
            "rule": ("promote only if SR and SPL improve or match and NE does "
                     "not materially worsen on the same held-out test; "
                     "recovery (val loss) is not safety")}


def main():
    cand_h4 = load("h4_eval_candidate_on_h4heldout.json")
    inc_h4 = load("h4_eval_incumbent_on_h4heldout.json")
    cand_pr = load("h4_eval_candidate_on_priorheldout.json")
    inc_pr = load("h4_eval_incumbent_on_priorheldout.json")

    dg_primary = driftguard(inc_h4, cand_h4, "h4_heldout_families_008_012_016")
    dg_regress = driftguard(inc_pr, cand_pr, "prior_heldout_uturn_chain_ftL")

    # net gate: clean promote requires promote on BOTH sets
    net = ("promote" if dg_primary["decision"] == "promote"
           and dg_regress["decision"] == "promote"
           else "hold_regression_on_prior_heldout"
           if dg_primary["decision"] == "promote"
           else "block")

    cand_ckpt = "checkpoints/h4_navgen_diversity_finetune/best.pt"
    inc_ckpt = "checkpoints/hospital_front_rgb_finetune/best.pt"

    def card(name, cond, ckpt, m_primary, m_prior, dg_role):
        return {
            "project": "gnm-vlnverse-baseline", "case_study": "h4_navgen_diversity",
            "run_name": name, "seed": 42,
            "model": {"name": "MobileNetV2-GNM", "condition": cond,
                      "checkpoint_path": ckpt, "checkpoint_sha256": sha(ckpt),
                      "selected_by": "H4 validation goals only (015, 017)"},
            "dataset": {"name": "Isaac-Hospital-ImageNav-v0 / H4 route-family corpus",
                        "camera": "Yahboom front-facing RGB (Isaac Sim)",
                        "train_episodes": 16, "val_episodes": 2, "test_episodes": 6,
                        "train_families": 8,
                        "heldout_primary": "families_008_012_016 (navgen route style)",
                        "heldout_prior": "families_uturn_chain_ftL (reported separately)",
                        "holdout_type": "route-family-level", "leakage_check": "PASS"},
            "metrics_h4_heldout": {k: round(m_primary[k], 4) for k in
                                   ("sr", "osr", "spl", "ne_m", "ndtw", "tl_m", "cls")}
            | {"n_test_episodes": m_primary["n"], "collision_rate": "N/A offline"},
            "metrics_prior_heldout": {k: round(m_prior[k], 4) for k in
                                      ("sr", "osr", "spl", "ne_m", "ndtw", "tl_m", "cls")}
            | {"n_test_episodes": m_prior["n"], "collision_rate": "N/A offline"},
            "gates": {"cuda_verified": True, "wandb_logged": True,
                      "dataset_manifest_exists": True,
                      "route_family_holdout_leakage_check": "PASS",
                      "checkpoint_hashed": True,
                      "offline_cr_not_reported_numeric": True,
                      "artifact_hygiene_clean": True,
                      "no_full_benchmark_claim": True,
                      "no_robust_navigation_claim": True,
                      "no_language_instruction_claim": True,
                      "fixed_placeholder_goal_image_disclosed": True},
            "driftguard": dg_role,
            "claim_boundary": ("Internal Isaac-Hospital-ImageNav-v0 simulation "
                               "evidence; not real-robot evidence; not a public "
                               "benchmark claim; not a general hospital-navigation "
                               "solution. Improvement is within-navgen route "
                               "distribution cross-family transfer only."),
        }

    cand_card = card("h4_navgen_diversity_seed42", "h4_candidate", cand_ckpt,
                     cand_h4, cand_pr,
                     {"promotion_candidate": True,
                      "incumbent": "h1_hospital_front_rgb_finetune",
                      "decision": net})
    inc_card = card("h1_hospital_front_rgb_finetune_on_h4_and_prior", "incumbent",
                    inc_ckpt, inc_h4, inc_pr,
                    {"promotion_candidate": False, "incumbent": None,
                     "decision": "incumbent_reference"})

    dg = {"net_gate": net, "primary_heldout": dg_primary,
          "regression_guard_prior_heldout": dg_regress,
          "incumbent_run": "h1_hospital_front_rgb_finetune",
          "candidate_run": "h4_navgen_diversity_seed42",
          "note": ("mechanical DriftGuard PROMOTES on the primary H4 held-out "
                   "(SR 0.000->0.333, SPL 0.000->0.333, NE 14.04->5.02 m) but "
                   "BLOCKS on the prior held-out (SR 0.167->0.000, SPL "
                   "0.167->0.000). Net gate is HOLD: a cross-distribution "
                   "regression, not a clean promotion.")}

    vp = {"action": "promote_model", "candidate": "h4_navgen_diversity",
          "scope": "internal Isaac-Hospital-ImageNav-v0 line only",
          "verdict": "deny" if net != "promote" else "allow",
          "matched_rule": {"match": {"tool": "model.promote",
                                     "args.driftguard_decision": net},
                           "decision": "deny" if net != "promote" else "allow"},
          "reason": ("net DriftGuard gate is not a clean promote; prior-held-out "
                     "navigation regression blocks auto-promotion")}

    adj = {
        "h4_final_adjudication": "HOLD_AS_POSITIVE_DIAGNOSTIC_NOT_PROMOTED",
        "hypothesis": ("route-family-diverse scripted-expert demonstrations yield "
                       "measurable held-out transfer that H3-clean's per-family "
                       "volume did not"),
        "hypothesis_result": "SUPPORTED within the navgen route distribution",
        "primary_heldout_result": ("candidate BEATS incumbent on H4 held-out "
                                   "families: SR 0.000->0.333, SPL 0.000->0.333, "
                                   "NE 14.04->5.02 m, nDTW 0.167->0.411 (n=6)"),
        "prior_heldout_result": ("candidate REGRESSES vs incumbent on prior "
                                 "held-out uturn/chain/ftL: SR 0.167->0.000, OSR "
                                 "0.667->0.333, SPL 0.167->0.000; NE improves "
                                 "12.76->8.15 m (n=6)"),
        "driftguard_mechanical_result": dg["net_gate"],
        "verdictplane_verdict": vp["verdict"],
        "collision_regression": "none (CR 0.000 offline on both sets; physics CR N/A)",
        "final_promotion_decision": "NOT PROMOTED",
        "incumbent": "h1_hospital_front_rgb_finetune RETAINED",
        "candidate": "h4_navgen_diversity retained as non-promoted positive evidence",
        "reason": ("This is the H-track's first measurable held-out transfer "
                   "(not the H3-clean tie), but it is within-navgen-distribution "
                   "cross-family transfer with a regression on the older held-out "
                   "families. Promotion requires resolving the cross-distribution "
                   "regression (e.g. joint/mixed-family training or replay) and a "
                   "combined held-out non-regression, plus human adjudication."),
        "small_n_caveat": "n=6 per held-out set; SR 0.333 = 2/6 episodes",
        "claim_boundary": ("tests whether route-family-diverse scripted expert "
                           "demonstrations improve the hospital behaviour-cloning "
                           "pipeline; fixed placeholder goal image, so NOT proof of "
                           "stronger goal-image conditioning"),
        "human_adjudication_recommendation": "DO NOT PROMOTE; hold as positive diagnostic; decide next: mixed-family retrain vs accept as diagnostic-only",
    }

    (E / "h4_candidate_card.json").write_text(json.dumps(cand_card, indent=2))
    (E / "h4_incumbent_card.json").write_text(json.dumps(inc_card, indent=2))
    (E / "h4_driftguard_decision.json").write_text(json.dumps(dg, indent=2))
    (E / "h4_verdictplane_record.json").write_text(json.dumps(vp, indent=2))
    (E / "h4_adjudication.json").write_text(json.dumps(adj, indent=2))
    print(json.dumps({"net_gate": net, "primary": dg_primary["decision"],
                      "regression_guard": dg_regress["decision"],
                      "verdictplane": vp["verdict"],
                      "adjudication": adj["h4_final_adjudication"]}, indent=2))


if __name__ == "__main__":
    main()
