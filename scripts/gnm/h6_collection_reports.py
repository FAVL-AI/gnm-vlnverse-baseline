#!/usr/bin/env python3
"""H6 post-collection reports (9 artifacts) from the recording ledger.

Reads h6_recording_ledger.json (+ per-episode metadata) and emits, WITHOUT
any conversion or training, into the H6 collection evidence dir:
  1 h6_recording_quality_table.csv        per-episode quality
  2 h6_split_manifest.json                 episode -> split allowlist
  3 h6_route_family_coverage_table.csv     per route-type train/val/heldout
  4 h6_leakage_report.json                 episode + family disjointness asserts
  5 h6_excluded_episode_report.json        failed/incomplete eps + old rejected chain_01
  6 h6_claim_boundary.md                    scope/claim boundary (h6_plan sec 11)
  7 h6_artifact_completeness_report.json    bag + trajectory + metadata present
  8 h6_disk_report.json                     disk before/after per episode + overall
  9 h6_cleanup_dds_report.json              cleanup/DDS status per episode

Only RECORDED_OK episodes are dataset-eligible; all others are excluded with a
reason (h6_plan sec 7 discipline). Split target comes from each family's
assignment (5 train / 1 val / 2 fresh_heldout).
"""
import csv, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h6_precheck_verdicts as pc

REPO, OUT_DIR, ROUTES_DIR = pc.REPO, pc.OUT_DIR, pc.ROUTES_DIR
LEDGER = OUT_DIR / "h6_recording_ledger.json"
FAM_SPLIT = {rid: split for (rid, rtype, split) in pc.FAMILIES}
FAM_TYPE = {rid: rtype for (rid, rtype, split) in pc.FAMILIES}

CLAIM_BOUNDARY = """# H6 Collection — Claim Boundary

Internal **Isaac-Hospital-ImageNav-v0 simulation** evidence. Recordings are
**scripted-expert** demonstrations (RouteFollower on the measured occupancy
map, ExecFix holonomic base, PhysX-contact-verified), NOT learned-policy
rollouts. A **fixed placeholder goal image** is used, so this is evidence about
**route-family-diverse scripted imitation under the current pipeline**, NOT
about stronger goal-image conditioning.

- Not real-robot evidence.
- Not a public benchmark.
- No navigation-quality/success claim is made from the collection alone; it is
  a leakage-clean, decider-gated demonstration dataset for the coverage-gap test.
- Route h6_chain_01 was re-authored inside the +/-6 m runtime XY control-authority
  bound after its original placement was rejected (REJECT_XY_BOUND); the original
  is preserved as rejected evidence (see h6_excluded_routes.json).
"""


def load_ledger():
    if not LEDGER.exists():
        print(f"[reports] ERROR: ledger not found: {LEDGER}", file=sys.stderr)
        sys.exit(1)
    return json.loads(LEDGER.read_text())


def r1_quality_table(rows):
    cols = ["episode_label", "route_id", "route_type", "split_target", "variant",
            "route_completed", "total_collision_count", "max_contact_streak",
            "first_collision_step", "steps", "distance_m", "rosbag_db3_bytes",
            "artifact_complete", "status"]
    with open(OUT_DIR / "h6_recording_quality_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def r2_split_manifest(eligible):
    manifest = {"train": [], "val": [], "fresh_heldout": []}
    split_map = {"train": "train", "validation": "val", "fresh_heldout": "fresh_heldout"}
    for r in eligible:
        s = split_map.get(FAM_SPLIT.get(r["route_id"]), FAM_SPLIT.get(r["route_id"]))
        manifest.setdefault(s, []).append(r["episode_label"])
    out = {"scope": "NEW H6 hard-family recordings only (allowlist; RECORDED_OK)",
           "splits": manifest,
           "counts": {k: len(v) for k, v in manifest.items()},
           "note": "downstream full-dataset split (mix with H4/H2.4 per h6_plan sec 4) "
                   "is a separate training-prep step, gated on review; not built here."}
    (OUT_DIR / "h6_split_manifest.json").write_text(json.dumps(out, indent=2))
    return manifest


def r3_coverage_table(eligible):
    types = sorted(set(FAM_TYPE.values()))
    counts = {t: {"train": 0, "val": 0, "fresh_heldout": 0} for t in types}
    smap = {"train": "train", "validation": "val", "fresh_heldout": "fresh_heldout"}
    for r in eligible:
        counts[r["route_type"]][smap.get(FAM_SPLIT[r["route_id"]], FAM_SPLIT[r["route_id"]])] += 1
    with open(OUT_DIR / "h6_route_family_coverage_table.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["route_type", "train", "val", "fresh_heldout", "total"])
        for t in types:
            c = counts[t]
            w.writerow([t, c["train"], c["val"], c["fresh_heldout"],
                        c["train"] + c["val"] + c["fresh_heldout"]])
    return counts


def r4_leakage_report(eligible, manifest):
    # episode-level: no episode in more than one split
    seen, dup = set(), []
    for s, eps in manifest.items():
        for e in eps:
            if e in seen:
                dup.append(e)
            seen.add(e)
    # family-level: fresh_heldout families disjoint from train families
    train_fams = {r["route_id"] for r in eligible if FAM_SPLIT[r["route_id"]] == "train"}
    held_fams = {r["route_id"] for r in eligible if FAM_SPLIT[r["route_id"]] == "fresh_heldout"}
    fam_overlap = sorted(train_fams & held_fams)
    out = {"episode_level_train_heldout_disjoint": not dup,
           "episode_level_duplicates": dup,
           "family_level_fresh_heldout_distinct_from_train": not fam_overlap,
           "family_overlap": fam_overlap,
           "train_families": sorted(train_fams),
           "fresh_heldout_families": sorted(held_fams),
           "leakage_clean": (not dup) and (not fam_overlap)}
    (OUT_DIR / "h6_leakage_report.json").write_text(json.dumps(out, indent=2))
    return out


def r5_excluded_report(rows):
    excluded_eps = []
    for r in rows:
        if r.get("status") != "RECORDED_OK":
            excluded_eps.append({"episode_label": r.get("episode_label"),
                                 "route_id": r.get("route_id"),
                                 "status": r.get("status"),
                                 "return_code": r.get("return_code"),
                                 "route_completed": r.get("route_completed"),
                                 "reason": r.get("status")})
    routes = []
    xr = OUT_DIR / "h6_excluded_routes.json"
    if xr.exists():
        routes = json.loads(xr.read_text())
    out = {"excluded_episodes": excluded_eps,
           "n_excluded_episodes": len(excluded_eps),
           "excluded_routes": routes,
           "exclusion_policy": "rc!=0 / partial / timed-out / incomplete-artifact / "
                               "non-RECORDED_OK; scripted-expert only; h6_plan sec 7"}
    (OUT_DIR / "h6_excluded_episode_report.json").write_text(json.dumps(out, indent=2))
    return out


def r6_claim_boundary():
    (OUT_DIR / "h6_claim_boundary.md").write_text(CLAIM_BOUNDARY)


def r7_artifact_completeness(rows):
    items = []
    for r in rows:
        items.append({"episode_label": r.get("episode_label"),
                      "rosbag_bytes": r.get("rosbag_db3_bytes", 0),
                      "artifact_complete": r.get("artifact_complete"),
                      "episode_dir": r.get("episode_dir")})
    complete = [i for i in items if i["artifact_complete"]]
    out = {"n_episodes": len(items), "n_complete": len(complete),
           "all_complete": len(complete) == len(items) and len(items) > 0,
           "items": items}
    (OUT_DIR / "h6_artifact_completeness_report.json").write_text(json.dumps(out, indent=2))
    return out


def r8_disk_report(rows):
    befores = [r["disk_before_gb"] for r in rows if r.get("disk_before_gb") is not None]
    afters = [r["disk_after_gb"] for r in rows if r.get("disk_after_gb") is not None]
    out = {"per_episode": [{"episode_label": r.get("episode_label"),
                            "disk_before_gb": r.get("disk_before_gb"),
                            "disk_after_gb": r.get("disk_after_gb")} for r in rows],
           "disk_before_first_gb": befores[0] if befores else None,
           "disk_after_last_gb": afters[-1] if afters else None,
           "min_free_gb": min(afters + befores) if (afters or befores) else None,
           "guard_gb": 150}
    (OUT_DIR / "h6_disk_report.json").write_text(json.dumps(out, indent=2))
    return out


def r9_cleanup_dds_report(rows):
    items = [{"episode_label": r.get("episode_label"),
              "cleanup_status": r.get("cleanup_status"),
              "stale_procs_after": r.get("stale_procs_after", []),
              "dds_shm_after": r.get("dds_shm_after", [])} for r in rows]
    all_clean = all(i["cleanup_status"] == "clean" for i in items) and bool(items)
    out = {"n_episodes": len(items), "all_clean": all_clean, "per_episode": items}
    (OUT_DIR / "h6_cleanup_dds_report.json").write_text(json.dumps(out, indent=2))
    return out


def main():
    rows = load_ledger()
    eligible = [r for r in rows if r.get("status") == "RECORDED_OK"]
    r1_quality_table(rows)
    manifest = r2_split_manifest(eligible)
    coverage = r3_coverage_table(eligible)
    leakage = r4_leakage_report(eligible, manifest)
    excluded = r5_excluded_report(rows)
    r6_claim_boundary()
    completeness = r7_artifact_completeness(rows)
    disk = r8_disk_report(rows)
    cleanup = r9_cleanup_dds_report(rows)
    print(f"[reports] episodes={len(rows)} eligible(RECORDED_OK)={len(eligible)} "
          f"excluded={excluded['n_excluded_episodes']}")
    print(f"[reports] split counts={manifest and {k: len(v) for k, v in manifest.items()}}")
    print(f"[reports] leakage_clean={leakage['leakage_clean']} "
          f"artifacts_all_complete={completeness['all_complete']} "
          f"cleanup_all_clean={cleanup['all_clean']}")
    print(f"[reports] 9 reports written to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
