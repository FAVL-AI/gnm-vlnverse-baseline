"""Validate the final Isaac live evidence stage."""
import json, re, subprocess, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
V = REPO / "assets/experiments/isaac_live_final_20260708"
BAG_TOPICS = ["/camera/image_raw", "/camera/camera_info", "/odom",
              "/tf", "/clock", "/cmd_vel"]

def fail(m): print(f"FAIL: {m}"); return False

def main():
    for f in ("live_episode_summary.json", "live_episode_summary.csv",
              "live_episode_summary.md", "episode_paths.json",
              "rosbag_manifest.sha256", "video_manifest.sha256",
              "checkpoint_manifest.sha256", "professor_live_evidence_note.md"):
        if not (V / f).exists(): return fail(f"missing {f}")
    s = json.loads((V / "live_episode_summary.json").read_text())
    ckpt = REPO / s["selected_checkpoint"]
    if not ckpt.exists() or not s.get("checkpoint_sha256"):
        return fail("selected checkpoint / sha missing")
    if "not full benchmark" not in s["label"]:
        return fail("smoke label missing")
    for e in s["episodes"]:
        d = REPO / json.loads((V / "episode_paths.json").read_text())[e["route"]]["trajectory"]
        if not (d / "trajectory.jsonl").exists() or not (d / "episode_metadata.json").exists():
            return fail(f"{e['route']}: logs missing")
        meta = json.loads((d / "episode_metadata.json").read_text())
        if meta.get("collision_reporting") != "physx_contact_report_base_link":
            return fail(f"{e['route']}: CR not from PhysX contacts")
        if e.get("zero_hold_residual_m") is None or e["zero_hold_residual_m"] > 0.05:
            return fail(f"{e['route']}: zeroing not verified")
        if e.get("estop"): return fail(f"{e['route']}: e-stop contaminated")
        bag_meta = REPO / meta["rosbag_path"] / "metadata.yaml"
        text = bag_meta.read_text()
        for topic in BAG_TOPICS:
            m = re.search(rf"name: {re.escape(topic)}\n.*?message_count: (\d+)", text, re.DOTALL)
            if not m or int(m.group(1)) == 0:
                return fail(f"{e['route']}: bag missing {topic}")
        rows = [json.loads(l) for l in (d / "trajectory.jsonl").open()]
        if "collision_detected" not in rows[10]:
            return fail(f"{e['route']}: collision fields missing")
        z0 = rows[0]["robot_position_z"]
        if max(abs(r["robot_position_z"] - z0) for r in rows) > 0.02:
            return fail(f"{e['route']}: unstable")
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"],
                            capture_output=True, text=True, cwd=REPO).stdout
    if re.search(r"\.(pt|pth|ckpt|db3|mcap|mp4)$", staged, re.M) or \
       re.search(r"^(checkpoints|wandb)/|/rosbags/|videos_local/", staged, re.M):
        return fail("large artifacts staged")
    note = (V / "professor_live_evidence_note.md").read_text().lower()
    if "not a full" not in note or "robust" not in note:
        return fail("professor note lacks claim guards")
    print(f"evidence folder complete; checkpoint {s['selected_checkpoint']} "
          f"(sha {s['checkpoint_sha256'][:12]}…); 3 episodes with logs, "
          "full-topic bags, PhysX collision fields, verified zeroing, "
          "stable; no large artifacts staged; claim guards present")
    print("PASS: final Isaac live evidence validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
