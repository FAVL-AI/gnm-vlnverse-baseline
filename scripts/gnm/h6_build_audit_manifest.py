#!/usr/bin/env python3
"""Build the H6 artifact manifest (paper-trail item E).

Emits:
  h6_artifact_manifest.csv         rel_path,type,size_bytes,size_human,sha256,
                                   git_state,for_git,reason
  h6_artifact_manifest_sha256.txt  "sha256  rel_path" for every for-git=yes file,
                                   repo-root-relative (verify: run `sha256sum -c`
                                   from the repo root).

git=yes = small H6-scoped evidence/code/config (per-file sha256). git=no = large
local artifacts (raw bags, converted frames, dataset root, checkpoints, logs) —
dir-group summaries (not hashed) except the H6 checkpoints, which are hashed for
integrity. Nothing is committed by this script.
"""
import csv, hashlib, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
E = REPO / "assets/experiments/hospital_h2_collection_20260709"
HASH_MAX = 200 * 1024 * 1024
SELF = {"h6_artifact_manifest.csv", "h6_artifact_manifest_sha256.txt"}


def human(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{u}" if u == "B" else f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def gitstate(rel):
    r = subprocess.run(["git", "status", "--porcelain", "--", rel], cwd=str(REPO),
                       capture_output=True, text=True).stdout
    if r.strip():
        code = r[:2]
        if "M" in code:
            return "modified"
        if "?" in code:
            return "new(untracked)"
        return code.strip()
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=str(REPO),
                             capture_output=True, text=True).returncode == 0
    return "tracked-clean(baseline)" if tracked else "n/a"


def ext(p):
    return p.suffix.lstrip(".") or "file"


def group_size(paths):
    total = nf = 0
    for base in paths:
        if base.is_file():
            total += base.stat().st_size; nf += 1
        elif base.is_dir():
            for f in base.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size; nf += 1
    return total, nf


def main():
    rows, sha_lines = [], []

    # ---- git=yes evidence / code / config -------------------------------
    evid = [p for p in sorted(E.glob("h6_*")) if p.is_file() and p.name not in SELF]
    evid += [REPO / x for x in (
        "scripts/gnm/execution_feasibility_decider.py",
        "scripts/datasets/hospital_h6_generate_hard_routes.py",
        "scripts/gnm/h6_precheck_verdicts.py",
        "scripts/gnm/h6_record_collection.py",
        "scripts/gnm/h6_collection_reports.py",
        "scripts/gnm/h6_convert_all.sh",
        "scripts/gnm/build_h6_dataset_root.py",
        "scripts/gnm/h6_evaluate_all.py",
        "scripts/gnm/h6_governance_adjudicate.py",
        "scripts/gnm/h6_per_family_table.py",
        "scripts/gnm/h6_build_audit_manifest.py",
        "configs/gnm/gnm_h6_hard_families.yaml",
        "paper/experiment_paper_trails/README.md",
        "paper/experiment_paper_trails/h6_paper_trail.md",
    )]
    evid += sorted((REPO / "assets/experiments/hospital_h6_routes").glob("h6_*.json"))
    evid += sorted((REPO / "assets/experiments/hospital_h6_routes/rejected").glob("*.json"))

    yes_n = yes_sz = 0
    for p in evid:
        if not p.exists():
            continue
        rel = str(p.relative_to(REPO))
        sz = p.stat().st_size
        dg = sha256(p) if sz <= HASH_MAX else "(large; omitted)"
        gs = gitstate(rel)
        reason = "already committed at 024033b" if gs.startswith("tracked-clean") else ""
        rows.append([rel, ext(p), sz, human(sz), dg, gs, "yes", reason])
        if not dg.startswith("("):
            sha_lines.append(f"{dg}  {rel}")
        yes_n += 1; yes_sz += sz

    # ---- git=no large artifacts (dir-group summaries) -------------------
    groups = [
        ("assets/experiments/rosbags/h6rec_* (16)", "rosbag-sqlite3",
         sorted((REPO / "assets/experiments/rosbags").glob("h6rec_*")),
         "raw sensor recording; cold-storage/pCloud candidate"),
        ("assets/experiments/trajectories/h6rec_* (16)", "trajectory-jsonl",
         sorted((REPO / "assets/experiments/trajectories").glob("h6rec_*")),
         "raw per-step trajectory"),
        ("datasets/isaac_hospital_imagenav_v0/unassigned/h6rec_* (16)", "frames-jpg",
         sorted((REPO / "datasets/isaac_hospital_imagenav_v0/unassigned").glob("h6rec_*")),
         "converted image frames"),
        ("datasets/isaac_hospital_h6/", "dataset-root",
         [REPO / "datasets/isaac_hospital_h6"], "built dataset root (copy of frames)"),
        ("logs/h6_*.log (8)", "log",
         sorted((REPO / "logs").glob("h6_*.log")), "run logs"),
    ]
    no_sz = 0
    for label, typ, paths, reason in groups:
        tot, nf = group_size(paths)
        rows.append([label, typ, tot, human(tot),
                     f"(dir group; {nf} files; not hashed)", "new(untracked)", "no", reason])
        no_sz += tot

    # H6 checkpoints — hashed (integrity) but NOT for git
    for ck in ("checkpoints/h6_hard_families_finetune/best.pt",
               "checkpoints/h6_hard_families_finetune/latest.pt"):
        p = REPO / ck
        if p.exists():
            sz = p.stat().st_size
            dg = sha256(p) if sz <= HASH_MAX else "(large; omitted)"
            rows.append([ck, "pt", sz, human(sz), dg, gitstate(ck), "no",
                         "model weights; local + cold-storage (hashed for integrity)"])
            no_sz += sz

    # self-reference rows
    for name in sorted(SELF):
        rows.append([f"assets/experiments/hospital_h2_collection_20260709/{name}",
                     name.split(".")[-1], 0, "-", "(self; emitted by the manifest run)",
                     "new(untracked)", "yes", "the manifest itself"])

    with open(E / "h6_artifact_manifest.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rel_path", "type", "size_bytes", "size_human", "sha256",
                    "git_state", "for_git", "reason"])
        w.writerows(rows)
    (E / "h6_artifact_manifest_sha256.txt").write_text(
        "# sha256 of H6 for-git evidence files; verify from repo root:\n"
        "#   sha256sum -c assets/experiments/hospital_h2_collection_20260709/"
        "h6_artifact_manifest_sha256.txt\n" + "\n".join(sha_lines) + "\n")

    print(f"[h6-manifest] git=yes files: {yes_n}  ({human(yes_sz)} hashed)")
    print(f"[h6-manifest] git=no  large artifacts: {human(no_sz)} "
          "(bags/traj/frames/dataset/checkpoints/logs)")
    print(f"[h6-manifest] -> h6_artifact_manifest.csv, h6_artifact_manifest_sha256.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
