"""Suite runner — run a full benchmark suite across models and platforms.

CLI usage:
    python -m fleetsafe_vln.benchmark.suite_runner \\
        --suite configs/benchmark/fleetsafe_vln_v0.yaml \\
        --models gnm vint nomad \\
        --platforms mock isaac gazebo real_robot \\
        --log-dir runs/suite_v0
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from fleetsafe_vln.benchmark.episode_runner import EpisodeRunner
from fleetsafe_vln.benchmark.metrics import EpisodeResult, print_leaderboard
from fleetsafe_vln.benchmark.task_schema import load_task

try:
    import yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False


def load_suite_config(path: str | Path) -> dict:
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    if p.suffix in (".yaml", ".yml"):
        if not _YAML_OK:
            raise ImportError("pyyaml required: pip install pyyaml")
        return yaml.safe_load(raw)
    return json.loads(raw)


class SuiteRunner:
    """Run all (task × model × platform) combinations in a suite config."""

    def __init__(
        self,
        suite_config: dict,
        models: Optional[List[str]] = None,
        platforms: Optional[List[str]] = None,
        log_dir: Optional[str] = None,
        safety: str = "cbf_qp",
        fail_fast: bool = False,
        dry_run: bool = False,
    ):
        self._cfg = suite_config
        self._models = models or suite_config.get("models", ["mock"])
        self._platforms = platforms or suite_config.get("platforms", ["mock"])
        self._safety = safety
        self._fail_fast = fail_fast
        self._dry_run = dry_run

        ts = time.strftime("%Y%m%d_%H%M%S")
        suite_name = suite_config.get("suite_id", "suite")
        self._log_dir = Path(log_dir or f"runs/{suite_name}_{ts}")
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> List[EpisodeResult]:
        tasks_cfg = self._cfg.get("tasks", [])
        if not tasks_cfg:
            print("⚠️  No tasks defined in suite config.")
            return []

        combos = [
            (t["path"], model, platform)
            for t in tasks_cfg
            for model in self._models
            for platform in self._platforms
        ]

        print(f"[suite_runner] {len(combos)} combinations")
        print(f"  Tasks:     {[t['path'] for t in tasks_cfg]}")
        print(f"  Models:    {self._models}")
        print(f"  Platforms: {self._platforms}")
        print(f"  Log dir:   {self._log_dir}")
        print()

        if self._dry_run:
            print("[suite_runner] DRY RUN — no episodes executed.")
            return []

        results: List[EpisodeResult] = []
        failed = 0

        for i, (task_path, model, platform) in enumerate(combos, 1):
            print(f"[{i}/{len(combos)}] {task_path} | {model} | {platform}")
            try:
                task = load_task(task_path)
            except Exception as e:
                print(f"  ❌ Could not load task: {e}")
                failed += 1
                if self._fail_fast:
                    break
                continue

            episode_log = self._log_dir / f"{task.task_id}_{model}_{platform}"
            runner = EpisodeRunner(
                task=task,
                platform=platform,
                model=model,
                safety=self._safety,
                log_dir=str(episode_log),
            )

            try:
                result = runner.run()
                results.append(result)
                print(f"  ✓ success={result.success}  spl={result.spl:.3f}  "
                      f"cert_validity={result.certificate_validity_rate:.3f}")
            except SystemExit as e:
                print(f"  ❌ Episode exited: {e}")
                failed += 1
                if self._fail_fast:
                    break
            except Exception as e:
                print(f"  ❌ Episode error: {e}")
                failed += 1
                if self._fail_fast:
                    break

        self._save_summary(results)

        print()
        print("=" * 60)
        print(f"Suite complete: {len(results)}/{len(combos)} succeeded, {failed} failed")
        print()
        print_leaderboard(results)

        return results

    def _save_summary(self, results: List[EpisodeResult]) -> None:
        summary = {
            "suite_id": self._cfg.get("suite_id", ""),
            "models": self._models,
            "platforms": self._platforms,
            "total_episodes": len(results),
            "success_rate": sum(r.success for r in results) / max(1, len(results)),
            "mean_spl": sum(r.spl for r in results) / max(1, len(results)),
            "mean_cert_validity": sum(r.certificate_validity_rate for r in results) / max(1, len(results)),
            "results": [r.to_dict() for r in results],
        }
        path = self._log_dir / "suite_summary.json"
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\n[suite_runner] Summary saved to {path}")


# ── CLI entry point ────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run a FleetSafe-VLN benchmark suite",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--suite", required=True, help="Path to suite config YAML")
    p.add_argument("--models", nargs="+", default=None,
                   help="Override models from suite config (gnm vint nomad mock)")
    p.add_argument("--platforms", nargs="+", default=None,
                   help="Override platforms from suite config (mock isaac gazebo real_robot)")
    p.add_argument("--safety", default="cbf_qp", choices=["cbf_qp", "none"])
    p.add_argument("--log-dir", default=None)
    p.add_argument("--fail-fast", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        suite_cfg = load_suite_config(args.suite)
    except Exception as e:
        print(f"❌ Failed to load suite config: {e}")
        return 1

    runner = SuiteRunner(
        suite_config=suite_cfg,
        models=args.models,
        platforms=args.platforms,
        log_dir=args.log_dir,
        safety=args.safety,
        fail_fast=args.fail_fast,
        dry_run=args.dry_run,
    )
    results = runner.run()
    success_rate = sum(r.success for r in results) / max(1, len(results)) if results else 0.0
    return 0 if success_rate >= 0.5 else 1


if __name__ == "__main__":
    sys.exit(main())
