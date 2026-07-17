"""H5-run-1 governance adjudication with the mandatory DUAL guard.

Net PROMOTE requires BOTH:
  - improvement guard on H4 held-out (SR & SPL >= incumbent, NE not materially worse)
  - non-regression guard on prior held-out (SR & SPL >= incumbent, NE not worse)
Combined aggregate reported for context. Emits cards, dual-guard DriftGuard
decision, VerdictPlane record, and adjudication.
"""
import hashlib, json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
E = REPO / "assets/experiments/hospital_h2_collection_20260709"
NE_MATERIAL = 0.1


def load(who, split):
    d = json.loads((E / f"h5_eval_{who}_{split}.json").read_text())
    return {"sr": d["SR"], "osr": d["OSR"], "spl": d["SPL"], "ne_m": d["NE"],
            "ndtw": d["nDTW"], "tl_m": d["TL"], "cls": d["CLS"], "cr": d["CR"],
            "n": d["n_episodes"]}


def sha(p):
    return hashlib.sha256((REPO / p).read_bytes()).hexdigest()


def guard(inc, cand, name):
    checks = {
        "sr": {"incumbent": inc["sr"], "candidate": cand["sr"],
               "pass": cand["sr"] >= inc["sr"]},
        "spl": {"incumbent": inc["spl"], "candidate": cand["spl"],
                "pass": cand["spl"] >= inc["spl"]},
        "ne_m": {"incumbent": inc["ne_m"], "candidate": cand["ne_m"],
                 "pass": cand["ne_m"] <= inc["ne_m"] + NE_MATERIAL,
                 "material_worsening_threshold_m": NE_MATERIAL},
    }
    return {"test": name, "n_test_episodes": cand["n"],
            "pass": all(c["pass"] for c in checks.values()), "checks": checks}


def main():
    ic_h4, cc_h4 = load("inc", "test_h4"), load("cand", "test_h4")
    ic_pr, cc_pr = load("inc", "test_prior"), load("cand", "test_prior")
    ic_cb, cc_cb = load("inc", "test_combined"), load("cand", "test_combined")

    improvement = guard(ic_h4, cc_h4, "h4_heldout_families_008_012_016")
    regression = guard(ic_pr, cc_pr, "prior_heldout_uturn_chain_ftL")
    combined = guard(ic_cb, cc_cb, "combined_heldout_n12")

    net = "promote" if (improvement["pass"] and regression["pass"]) else "hold"

    dg = {
        "net_gate": net,
        "rule": ("net PROMOTE requires BOTH the H4-heldout improvement guard AND "
                 "the prior-heldout non-regression guard to pass (SR & SPL >= "
                 "incumbent, NE not materially worse); combined aggregate is "
                 "context, not a substitute"),
        "improvement_guard_h4_heldout": improvement,
        "regression_guard_prior_heldout": regression,
        "combined_aggregate_context": combined,
        "incumbent_run": "h1_hospital_front_rgb_finetune",
        "candidate_run": "h5_mixed_replay_seed42",
        "note": ("improvement guard PASSES (SR 0.000->0.333, SPL 0.000->0.333, NE "
                 "14.04->5.02 m — H4 gain PRESERVED). regression guard FAILS on "
                 "SR/SPL (0.167->0.000) though NE improves 12.76->7.19 m. The "
                 "SR/SPL prior-heldout regression is a single-episode flip (1/6 -> "
                 "0/6) at n=6; combined aggregate improves (SR 0.083->0.167, SPL "
                 "0.083->0.167, NE 13.40->6.10 m, nDTW 0.222->0.336; OSR "
                 "0.833->0.667). Net gate HOLD: strict dual-guard not met."),
    }

    vp = {"action": "promote_model", "candidate": "h5_mixed_replay",
          "scope": "internal Isaac-Hospital-ImageNav-v0 line only",
          "verdict": "allow" if net == "promote" else "deny",
          "matched_rule": {"match": {"tool": "model.promote",
                                     "args.driftguard_net_gate": net},
                           "decision": "allow" if net == "promote" else "deny"},
          "reason": ("dual-guard not satisfied: prior-heldout SR/SPL regression "
                     "blocks auto-promotion despite preserved H4 gain and improved "
                     "NE / combined aggregate")}

    def card(name, cond, ckpt, dg_role):
        return {"project": "gnm-vlnverse-baseline", "case_study": "h5_mixed_replay",
                "run_name": name, "seed": 42,
                "model": {"name": "MobileNetV2-GNM", "condition": cond,
                          "checkpoint_path": ckpt, "checkpoint_sha256": sha(ckpt),
                          "selected_by": "H5 validation (both distributions) only"},
                "dataset": {"name": "Isaac-Hospital-ImageNav-v0 / H5 mixed-replay",
                            "camera": "Yahboom front-facing RGB (Isaac Sim)",
                            "train_episodes": 24, "val_episodes": 4,
                            "train_mix": "16 H4 NavGen + 8 H2.4 older demos",
                            "heldout_h4": "008/012/016 (n=6)",
                            "heldout_prior": "uturn/chain/ftL (n=6)",
                            "leakage_check": "PASS", "h1_included": False},
                "metrics_h4_heldout": {k: round(cc_h4[k] if cond != "incumbent"
                                       else ic_h4[k], 4) for k in
                                       ("sr", "osr", "spl", "ne_m", "ndtw")},
                "metrics_prior_heldout": {k: round(cc_pr[k] if cond != "incumbent"
                                          else ic_pr[k], 4) for k in
                                          ("sr", "osr", "spl", "ne_m", "ndtw")},
                "metrics_combined": {k: round(cc_cb[k] if cond != "incumbent"
                                     else ic_cb[k], 4) for k in
                                     ("sr", "osr", "spl", "ne_m", "ndtw")},
                "collision_rate": "N/A offline",
                "driftguard": dg_role,
                "claim_boundary": ("Internal Isaac-Hospital-ImageNav-v0 simulation "
                                   "evidence; fixed placeholder goal image => NOT "
                                   "goal-image-conditioning evidence; not real-robot, "
                                   "not a public benchmark. H2.4 val are b-variants "
                                   "of trained families => model-selection only, NOT "
                                   "older-family held-out generalisation.")}

    adj = {
        "h5_final_adjudication": "HOLD_NOT_PROMOTED_OUTCOME_B",
        "hypothesis": ("mixing H4 diversity with H2.4 older-family replay preserves "
                       "H4 gains while removing the prior-family regression"),
        "hypothesis_result": ("PARTIALLY supported: H4 gain preserved and NE / "
                              "combined aggregate improved, but prior-heldout SR/SPL "
                              "regression NOT removed"),
        "h4_heldout_result": ("PRESERVED — candidate SR 0.333 / SPL 0.333 / NE 5.02 m "
                              "vs incumbent 0.000 / 0.000 / 14.04 m (improvement guard PASS)"),
        "prior_heldout_result": ("SR/SPL still regress (0.167->0.000) though NE improves "
                                 "12.76->7.19 m; regression guard FAIL; the SR gap is a "
                                 "single episode (1/6->0/6) at n=6"),
        "combined_aggregate_result": ("candidate better on SR 0.083->0.167, SPL "
                                      "0.083->0.167, NE 13.40->6.10 m, nDTW 0.222->0.336; "
                                      "OSR worse 0.833->0.667 (n=12)"),
        "driftguard_net": net, "verdictplane_verdict": vp["verdict"],
        "collision_regression": "none (CR 0.000 offline on all sets; physics CR N/A)",
        "final_promotion_decision": "NOT PROMOTED",
        "incumbent": "h1_hospital_front_rgb_finetune RETAINED",
        "candidate": "h5_mixed_replay retained as diagnostic evidence (strongest so far)",
        "reason": ("Outcome B: H4 improvement preserved but prior-family SR/SPL "
                   "non-regression not achieved. Per the pre-registered rule, "
                   "promotion needs BOTH guards; do not promote on H4 improvement "
                   "alone, on combined-aggregate improvement alone, or on a small-n "
                   "tie. Reading: replaying older TRAIN families (H2.4) does not by "
                   "itself restore SUCCESS on older HELD-OUT families of route types "
                   "no training set covers (uturn/chain/ftL) — a coverage gap, not "
                   "just a balance gap; NE improved broadly."),
        "small_n_caveat": "n=6 per held-out set; prior-heldout SR regression = 1 episode",
        "claim_boundary": ("evidence about route-family-diverse scripted imitation "
                           "under the current pipeline; fixed placeholder goal image "
                           "=> NOT stronger goal-image conditioning"),
        "next_options": ["H5-run-2: rebalance older-family sampling toward parity",
                         "H6: add uturn/chain/ftL-type route families to TRAINING "
                         "(reassign via new split manifest, fresh held-out) to test "
                         "the coverage hypothesis directly",
                         "accept H5 as diagnostic-only"],
    }

    (E / "h5_candidate_card.json").write_text(json.dumps(
        card("h5_mixed_replay_seed42", "h5_candidate",
             "checkpoints/h5_mixed_replay_finetune/best.pt",
             {"promotion_candidate": True,
              "incumbent": "h1_hospital_front_rgb_finetune", "decision": net}),
        indent=2))
    (E / "h5_incumbent_card.json").write_text(json.dumps(
        card("h1_hospital_front_rgb_finetune_on_h5_heldouts", "incumbent",
             "checkpoints/hospital_front_rgb_finetune/best.pt",
             {"promotion_candidate": False, "incumbent": None,
              "decision": "incumbent_reference"}), indent=2))
    (E / "h5_driftguard_decision.json").write_text(json.dumps(dg, indent=2))
    (E / "h5_verdictplane_record.json").write_text(json.dumps(vp, indent=2))
    (E / "h5_adjudication.json").write_text(json.dumps(adj, indent=2))

    print(json.dumps({"improvement_guard": improvement["pass"],
                      "regression_guard": regression["pass"],
                      "net_gate": net, "verdictplane": vp["verdict"],
                      "adjudication": adj["h5_final_adjudication"]}, indent=2))


if __name__ == "__main__":
    main()
