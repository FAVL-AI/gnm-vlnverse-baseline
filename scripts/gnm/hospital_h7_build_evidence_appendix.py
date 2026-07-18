#!/usr/bin/env python3
"""Build the H7-Hospital evidence appendix machine artifacts.

The H7 / H7r "10-point gate PASS" is a load-bearing claim. A reviewer must be
able to trace it back to primary evidence without trusting a prose summary.
This builder regenerates, for BOTH pilots (h7_ = occluded baseline, h7r_ =
raised-mount dataset of record), the machine-verifiable evidence:

  1. Rosbag TOPIC PROOF   - parsed from each recorded bag's metadata.yaml
                            (topics + per-topic message counts + duration).
  2. Scene-gate LOG INDEX - the fail-closed scene-identity manifest per episode
                            (asset = verified Isaac Sim hospital.usd, prim count, checks).
  3. CHECKSUMS            - SHA-256 over each bag's .db3 + metadata.yaml
                            (sha256sum -c compatible, repo-relative paths) so
                            the untracked ~1.9 GB bags stay independently
                            verifiable, plus checksums over the committed
                            evidence artifacts (routes, gate manifests,
                            quality tables, generated tables).
  4. evidence_manifest.json - a single index tying command, routes, bags,
                            gate logs and checksum files together.

Nothing here recomputes results; it only hashes and transcribes existing
recorded artifacts. Re-runnable and deterministic (bag bytes are frozen).

Usage:
  /usr/bin/python3 scripts/gnm/hospital_h7_build_evidence_appendix.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone

import yaml

REPO = "/home/favl/robotics/gnm-vlnverse-baseline"
ROSBAGS = os.path.join(REPO, "assets/experiments/rosbags")
GATE_DIR = os.path.join(REPO, "assets/experiments/hospital_h7_scene_gate")
ROUTES_DIR = os.path.join(
    REPO, "assets/experiments/hospital_h7_collection/routes"
)

# base episode names, in split order (train x4, val x2, test x2)
BASES = [
    ("reception_01", "train"),
    ("corridor_01", "train"),
    ("turn_01", "train"),
    ("waiting_01", "train"),
    ("reception_02", "val"),
    ("corridor_02", "val"),
    ("turn_02", "test"),
    ("waiting_02", "test"),
]

PILOTS = {
    "h7": {
        "prefix": "h7_",
        "label": "H7 baseline (fixed camera, ~38.3% lower-third occlusion)",
        "reports": os.path.join(
            REPO, "assets/experiments/hospital_h7_collection/reports"
        ),
        "quality_table": "h7_recording_quality_table.md",
        "camera_raise_m": 0.0,
    },
    "h7r": {
        "prefix": "h7r_",
        "label": "H7r raised-mount (+0.12 m, occlusion removed) — DATASET OF RECORD",
        "reports": os.path.join(
            REPO, "assets/experiments/hospital_h7_raise_collection/reports"
        ),
        "quality_table": "h7r_recording_quality_table.md",
        "camera_raise_m": 0.12,
    },
}

# expected recorded topics for a gated ImageNav episode
EXPECTED_TOPICS = {
    "/camera/image_raw",
    "/camera/camera_info",
    "/odom",
    "/tf",
    "/clock",
    "/cmd_vel",
}


def rel(path: str) -> str:
    return os.path.relpath(path, REPO)


def sha256_file(path: str, chunk: int = 8 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def find_episode_dir(root: str, prefix: str, base: str) -> str | None:
    """Match exactly the timestamped official dir, excluding _smoke_/_valcheck_."""
    pat = re.compile(rf"^{re.escape(prefix)}{re.escape(base)}_\d{{8}}_\d{{6}}$")
    matches = [d for d in os.listdir(root) if pat.match(d)]
    if not matches:
        return None
    return sorted(matches)[0]


def parse_bag_metadata(meta_path: str) -> dict:
    with open(meta_path) as fh:
        doc = yaml.safe_load(fh)
    info = doc["rosbag2_bagfile_information"]
    topics = {}
    for entry in info["topics_with_message_count"]:
        md = entry["topic_metadata"]
        topics[md["name"]] = {
            "type": md["type"],
            "count": int(entry["message_count"]),
        }
    return {
        "storage_identifier": info.get("storage_identifier"),
        "message_count": int(info.get("message_count", 0)),
        "duration_s": round(info["duration"]["nanoseconds"] / 1e9, 3),
        "start_epoch_ns": info["starting_time"]["nanoseconds_since_epoch"],
        "topics": topics,
    }


def collect(pilot_key: str) -> dict:
    p = PILOTS[pilot_key]
    episodes = []
    for base, split in BASES:
        ep_dir = find_episode_dir(ROSBAGS, p["prefix"], base)
        if ep_dir is None:
            raise SystemExit(f"MISSING bag for {p['prefix']}{base}")
        episode_id = ep_dir
        bag_path = os.path.join(ROSBAGS, ep_dir)
        meta_path = os.path.join(bag_path, "metadata.yaml")
        db3 = [f for f in os.listdir(bag_path) if f.endswith(".db3")]
        if len(db3) != 1:
            raise SystemExit(f"expected 1 .db3 in {bag_path}, found {db3}")
        db3_path = os.path.join(bag_path, db3[0])

        gate_path = os.path.join(GATE_DIR, f"{episode_id}.json")
        route_path = os.path.join(ROUTES_DIR, f"h7_{base}.json")  # routes shared

        meta = parse_bag_metadata(meta_path)
        with open(gate_path) as fh:
            gate = json.load(fh)

        episodes.append(
            {
                "base": base,
                "split": split,
                "episode_id": episode_id,
                "family": os.path.basename(route_path),
                "route_path": route_path,
                "bag_dir": bag_path,
                "db3_path": db3_path,
                "meta_path": meta_path,
                "gate_path": gate_path,
                "meta": meta,
                "gate": gate,
            }
        )
    return {"pilot": pilot_key, "cfg": p, "episodes": episodes}


def write_topic_proof(pilot: dict, generated: str) -> str:
    cfg = pilot["cfg"]
    reports = cfg["reports"]
    md = os.path.join(reports, f"{pilot['pilot']}_rosbag_topic_proof.md")
    cv = os.path.join(reports, f"{pilot['pilot']}_rosbag_topic_proof.csv")

    all_topics = sorted(
        {t for ep in pilot["episodes"] for t in ep["meta"]["topics"]}
    )
    with open(cv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["episode_id", "storage", "duration_s", "total_msgs"]
            + [f"count{t}" for t in all_topics]
            + ["expected_topics_present"]
        )
        for ep in pilot["episodes"]:
            m = ep["meta"]
            present = EXPECTED_TOPICS.issubset(set(m["topics"]))
            w.writerow(
                [ep["episode_id"], m["storage_identifier"], m["duration_s"],
                 m["message_count"]]
                + [m["topics"].get(t, {}).get("count", 0) for t in all_topics]
                + [present]
            )

    lines = [
        f"# {pilot['pilot'].upper()} rosbag topic proof",
        "",
        f"Generated {generated}. {cfg['label']}.",
        "",
        "Each row is transcribed directly from the recorded bag's "
        "`metadata.yaml` (rosbag2 v5, sqlite3). A reviewer can independently "
        "confirm with `ros2 bag info <bag_dir>`.",
        "",
        "Expected ImageNav topics (all must be present): "
        + ", ".join(f"`{t}`" for t in sorted(EXPECTED_TOPICS)),
        "",
        "| episode_id | storage | duration_s | total_msgs | "
        + " | ".join(f"`{t}`" for t in all_topics)
        + " | all_expected |",
        "|" + "---|" * (5 + len(all_topics)),
    ]
    for ep in pilot["episodes"]:
        m = ep["meta"]
        present = EXPECTED_TOPICS.issubset(set(m["topics"]))
        row = (
            f"| {ep['episode_id']} | {m['storage_identifier']} | "
            f"{m['duration_s']} | {m['message_count']} | "
            + " | ".join(str(m["topics"].get(t, {}).get("count", 0)) for t in all_topics)
            + f" | {'PASS' if present else 'FAIL'} |"
        )
        lines.append(row)
    lines += [
        "",
        "Topic message types (from bag metadata):",
        "",
    ]
    ref = pilot["episodes"][0]["meta"]["topics"]
    for t in all_topics:
        lines.append(f"- `{t}` -> `{ref.get(t, {}).get('type', '?')}`")
    lines.append("")
    with open(md, "w") as fh:
        fh.write("\n".join(lines))
    return md


def write_gate_index(pilot: dict, generated: str) -> str:
    cfg = pilot["cfg"]
    reports = cfg["reports"]
    md = os.path.join(reports, f"{pilot['pilot']}_scene_gate_index.md")
    cv = os.path.join(reports, f"{pilot['pilot']}_scene_gate_index.csv")

    cols = [
        "episode_id", "scene_identity_pass", "asset_is_hospital_usd",
        "hospital_prim_count", "min_hospital_prims", "front_camera_path",
        "resolution", "procedural_landmark_prims", "failed_reasons",
        "isaac_sim_version", "timestamp", "gate_manifest",
    ]
    with open(cv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for ep in pilot["episodes"]:
            g = ep["gate"]
            obs = g.get("observed", {})
            w.writerow([
                g.get("episode_id"),
                g.get("scene_identity_pass"),
                g.get("asset_is_hospital_usd"),
                obs.get("hospital_prim_count"),
                g.get("min_hospital_prims"),
                obs.get("front_camera_path"),
                "x".join(str(v) for v in obs.get("resolution", [])),
                len(obs.get("procedural_landmark_prims", [])),
                ";".join(g.get("failed_reasons", [])) or "none",
                g.get("isaac_sim_version"),
                g.get("timestamp"),
                rel(ep["gate_path"]),
            ])

    lines = [
        f"# {pilot['pilot'].upper()} scene-identity gate log index",
        "",
        f"Generated {generated}. {cfg['label']}.",
        "",
        "The scene-identity gate (`hospital_scene_identity_gate.verify_hospital_scene`) "
        "runs fail-closed in the recording harness **before** `ros2 bag record` starts; "
        "on failure the harness `sys.exit(5)` and records nothing. Every bag below "
        "therefore has a PASS manifest, proving the data was recorded in the verified "
        "Isaac Sim `hospital.usd` scene (not procedural H6, and not a physical hospital).",
        "",
        "Note: the scene gate's resolution check was **declarative only** at H7/H7R "
        "capture time (observed 640x480 vs declared 1280x720; not enforced). See "
        "`H7_H7R_CAMERA_RESOLUTION_VARIANCE_AND_H8_MITIGATION.md`. Scene identity, "
        "checksum integrity and topic presence are unaffected.",
        "",
        "| episode_id | gate_pass | hospital.usd | prims (min) | landmark prims | front camera | res | manifest |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for ep in pilot["episodes"]:
        g = ep["gate"]
        obs = g.get("observed", {})
        lines.append(
            f"| {g.get('episode_id')} | {g.get('scene_identity_pass')} | "
            f"{g.get('asset_is_hospital_usd')} | "
            f"{obs.get('hospital_prim_count')} ({g.get('min_hospital_prims')}) | "
            f"{len(obs.get('procedural_landmark_prims', []))} | "
            f"`{obs.get('front_camera_path')}` | "
            f"{'x'.join(str(v) for v in obs.get('resolution', []))} | "
            f"`{rel(ep['gate_path'])}` |"
        )
    lines.append("")
    with open(md, "w") as fh:
        fh.write("\n".join(lines))
    return md


def write_checksums(pilot: dict) -> tuple[str, str]:
    cfg = pilot["cfg"]
    reports = cfg["reports"]
    bag_sums = os.path.join(reports, f"{pilot['pilot']}_bag_checksums.sha256")
    art_sums = os.path.join(reports, f"{pilot['pilot']}_evidence_checksums.sha256")

    # --- primary data: bag .db3 + metadata.yaml (sha256sum -c compatible) ---
    bag_lines = []
    for ep in pilot["episodes"]:
        for f in (ep["db3_path"], ep["meta_path"]):
            bag_lines.append(f"{sha256_file(f)}  {rel(f)}")
    with open(bag_sums, "w") as fh:
        fh.write("\n".join(bag_lines) + "\n")

    # --- committed evidence artifacts (routes, gate manifests, tables) ---
    art_paths = []
    seen = set()
    for ep in pilot["episodes"]:
        for f in (ep["route_path"], ep["gate_path"]):
            if f not in seen:
                seen.add(f)
                art_paths.append(f)
    qt = os.path.join(reports, cfg["quality_table"])
    for extra in (
        qt,
        os.path.join(reports, f"{pilot['pilot']}_rosbag_topic_proof.md"),
        os.path.join(reports, f"{pilot['pilot']}_rosbag_topic_proof.csv"),
        os.path.join(reports, f"{pilot['pilot']}_scene_gate_index.md"),
        os.path.join(reports, f"{pilot['pilot']}_scene_gate_index.csv"),
    ):
        if os.path.exists(extra):
            art_paths.append(extra)
    art_lines = [f"{sha256_file(f)}  {rel(f)}" for f in art_paths]
    with open(art_sums, "w") as fh:
        fh.write("\n".join(art_lines) + "\n")

    return bag_sums, art_sums


def main() -> None:
    # generation timestamp (UTC); the bag bytes are frozen, so the checksums and
    # transcribed topic/gate tables are deterministic regardless of when this runs.
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "generated_utc": generated,
        "claim": (
            "H7 and H7R: provenance-backed Isaac Sim hospital-scene pilot evidence, "
            "with a documented camera-resolution nonconformity. Covers scene identity, "
            "route identity, ROS 2 bag existence, required topic presence, recorded-message "
            "evidence, file-integrity verification and reproducible evidence generation. "
            "Does NOT cover dataset admission, training readiness, resolution conformity, "
            "goal conditioning, model performance or physical/real-robot deployment."
        ),
        "record_command": (
            "timeout 1800 $ISAAC_PY -u scripts/robots/m3pro_ros2_bringup.py "
            "--scene hospital --scene-gate --camera-raise <0.0|0.12> "
            "--gnm-control --route-follow <route.json> --holonomic-base "
            "--collision-report --episode --episode-name <id> "
            "--goal-id h2_weave_J --steps 6000"
        ),
        "orchestrators": [
            "scripts/gnm/hospital_h7_record_campaign.sh",
            "scripts/gnm/hospital_h7_raise_record_campaign.sh",
        ],
        "camera_resolution_conformity": {
            "status": "OPEN",
            "declared_resolution": [1280, 720],
            "observed_resolution": [640, 480],
            "gate_check_was": "declarative only (observed vs declared not compared)",
            "impact": "does NOT affect scene identity, bag existence, checksum integrity, "
                      "route identity or topic presence; means resolution conformity is NOT claimed",
            "variance_note": "assets/experiments/hospital_h7_collection/"
                             "H7_H7R_CAMERA_RESOLUTION_VARIANCE_AND_H8_MITIGATION.md",
            "h8_mitigation": "scripts/gnm/hospital_scene_identity_gate.py "
                             "verify_hospital_scene(enforce_resolution=True) fails closed on mismatch",
        },
        "pilots": {},
    }
    for key in ("h7", "h7r"):
        pilot = collect(key)
        tp = write_topic_proof(pilot, generated)
        gi = write_gate_index(pilot, generated)
        bag_sums, art_sums = write_checksums(pilot)
        gate_pass = all(
            ep["gate"].get("scene_identity_pass") is True
            for ep in pilot["episodes"]
        )
        img_ok = all(
            "/camera/image_raw" in ep["meta"]["topics"]
            for ep in pilot["episodes"]
        )
        manifest["pilots"][key] = {
            "label": pilot["cfg"]["label"],
            "camera_raise_m": pilot["cfg"]["camera_raise_m"],
            "n_episodes": len(pilot["episodes"]),
            "all_scene_gate_pass": gate_pass,
            "all_image_raw_present": img_ok,
            "episodes": [ep["episode_id"] for ep in pilot["episodes"]],
            "artifacts": {
                "topic_proof_md": rel(tp),
                "scene_gate_index_md": rel(gi),
                "bag_checksums": rel(bag_sums),
                "evidence_checksums": rel(art_sums),
                "quality_table": rel(
                    os.path.join(pilot["cfg"]["reports"],
                                 pilot["cfg"]["quality_table"])
                ),
            },
        }
        print(f"[{key}] episodes={len(pilot['episodes'])} "
              f"gate_pass={gate_pass} image_raw_all={img_ok}")
        print(f"[{key}] wrote {rel(tp)}")
        print(f"[{key}] wrote {rel(gi)}")
        print(f"[{key}] wrote {rel(bag_sums)} ({len(pilot['episodes'])*2} hashes)")
        print(f"[{key}] wrote {rel(art_sums)}")

    man_path = os.path.join(
        REPO, "assets/experiments/hospital_h7_collection/H7_EVIDENCE_MANIFEST.json"
    )
    with open(man_path, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"[manifest] wrote {rel(man_path)}")


if __name__ == "__main__":
    main()
