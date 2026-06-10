#!/usr/bin/env python3
"""
export_latest_capture_for_web.py — Copy latest Isaac capture into git-tracked public assets.

Vercel cannot read logs/ (gitignored runtime data). This script exports a
small, web-safe snapshot into command-center/frontend/public/evidence/isaac/latest/
so that the static Vercel build can display the capture without a backend.

Run after every new capture:
    python scripts/isaaclab/export_latest_capture_for_web.py
    git add command-center/frontend/public/evidence/
    git commit -m "evidence: update Isaac capture snapshot"
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_ROOT  = REPO_ROOT / "logs" / "hospital_benchmark"
OUT_DIR   = REPO_ROOT / "command-center" / "frontend" / "public" / "evidence" / "isaac" / "latest"

COPY_FILES = [
    "procedural_preview.png",
    "screenshot.png",
    "capture_status.json",
    "viewport_status.txt",
    "session.json",
]

USD_ASSET = (
    REPO_ROOT / "fleet_safe_vla" / "envs" / "isaaclab"
    / "hospital" / "assets" / "hospital_world.usd"
)


def find_latest_run() -> Path | None:
    latest_link = LOG_ROOT / "latest"
    if latest_link.exists() and latest_link.is_symlink():
        resolved = latest_link.resolve()
        if resolved.is_dir():
            return resolved

    # Fallback: newest dir by mtime
    dirs = sorted(
        [d for d in LOG_ROOT.iterdir() if d.is_dir() and d.name != "latest"],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    return dirs[0] if dirs else None


def build_web_status(run_dir: Path, source: dict) -> dict:
    """
    Rewrite photoreal_status.json for web delivery:
      - screenshot → web-relative path (not absolute local filesystem path)
      - usd_path   → basename only (not absolute local path)
    """
    # Determine which image file was exported
    has_screenshot = (OUT_DIR / "screenshot.png").exists()
    has_preview    = (OUT_DIR / "procedural_preview.png").exists()

    if has_screenshot:
        web_screenshot = "/evidence/isaac/latest/screenshot.png"
    elif has_preview:
        web_screenshot = "/evidence/isaac/latest/procedural_preview.png"
    else:
        web_screenshot = None

    usd_found = USD_ASSET.exists() and USD_ASSET.stat().st_size > 1000

    return {
        "status":         source.get("status", "PROCEDURAL"),
        "usd_loaded":     usd_found,
        "usd_path":       USD_ASSET.name if usd_found else None,
        "usd_size_kb":    round(USD_ASSET.stat().st_size / 1024, 1) if usd_found else 0,
        "screenshot":     web_screenshot,
        "capture_method": source.get("capture_method", "unknown"),
        "scene":          source.get("scene"),
        "scenario":       source.get("scenario"),
        "timestamp":      source.get("timestamp"),
        "isaac_version":  source.get("isaac_version"),
        # Extra fields for richer dashboard display
        "photoreal_claimed": False,
        "honest_label":   (
            "USD asset found on disk. Procedural matplotlib floor-plan preview. "
            "No Isaac Sim render captured yet — run --capture in conda isaac env for PROVEN status."
            if not has_screenshot else
            "Isaac Sim viewport capture recorded with USD asset loaded."
        ),
    }


def main() -> int:
    print(f"\n[export_capture] Log root : {LOG_ROOT}")
    print(f"[export_capture] Output   : {OUT_DIR}")

    run_dir = find_latest_run()
    if run_dir is None:
        print("[export_capture] ERROR: No runs found in logs/hospital_benchmark/")
        print("  Run first: python scripts/isaaclab/gen_proof_run.py")
        return 1

    print(f"[export_capture] Source   : {run_dir.name}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Copy files ────────────────────────────────────────────────────────────
    copied = []
    skipped = []
    for fname in COPY_FILES:
        src = run_dir / fname
        dst = OUT_DIR / fname
        if src.exists() and src.stat().st_size > 0:
            shutil.copy2(src, dst)
            copied.append(fname)
            print(f"  ✓ {fname} ({src.stat().st_size} bytes)")
        else:
            skipped.append(fname)
            # Remove stale file from previous export
            if dst.exists():
                dst.unlink()
            print(f"  - {fname} (skipped — not present or empty)")

    # ── Rewrite photoreal_status.json with web-safe paths ────────────────────
    raw_status_path = run_dir / "photoreal_status.json"
    raw_status: dict = {}
    if raw_status_path.exists():
        try:
            raw_status = json.loads(raw_status_path.read_text())
        except Exception as e:
            print(f"[export_capture] WARNING: could not parse photoreal_status.json: {e}")

    web_status = build_web_status(run_dir, raw_status)
    out_status = OUT_DIR / "photoreal_status.json"
    out_status.write_text(json.dumps(web_status, indent=2))
    print(f"  ✓ photoreal_status.json (rewritten with web paths)")

    # ── Write a README so git doesn't discard the dir ────────────────────────
    readme = OUT_DIR / "README.md"
    readme.write_text(
        "# Isaac Capture Snapshot\n\n"
        "Auto-generated by `scripts/isaaclab/export_latest_capture_for_web.py`.\n"
        "Do not edit manually — re-run the export script after each new capture.\n\n"
        f"Source run: `{run_dir.name}`\n"
        f"USD asset: `{'FOUND' if web_status['usd_loaded'] else 'MISSING'}`\n"
        f"Render status: `{web_status['status']}`\n"
        f"Photoreal claimed: `{web_status['photoreal_claimed']}`\n"
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n[export_capture] Summary")
    print(f"  copied  : {', '.join(copied) if copied else '(none)'}")
    print(f"  skipped : {', '.join(skipped) if skipped else '(none)'}")
    print(f"  usd     : {'FOUND' if web_status['usd_loaded'] else 'MISSING'}")
    print(f"  render  : {web_status['status']}")
    print(f"  image   : {web_status['screenshot'] or '(none)'}")
    print()
    print(f"[export_capture] Output → {OUT_DIR}")
    print(f"\nNext steps:")
    print(f"  git add {OUT_DIR.relative_to(REPO_ROOT)}")
    print(f"  git commit -m 'evidence: update Isaac capture snapshot'")
    print(f"  git push && cd command-center/frontend && npx vercel --prod")
    return 0


if __name__ == "__main__":
    sys.exit(main())
