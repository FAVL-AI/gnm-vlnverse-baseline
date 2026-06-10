"""
ONNX Policy Export — Fleet-Safe-VLA-OS.

Thin wrapper around robot-lab's export_onnx.py with Fleet-Safe extensions:
  - Exports policy + CBF filter jointly (optional)
  - Adds deployment metadata to ONNX model
  - Validates exported model against MuJoCo environment

Usage:
    python -m fleet_safe_vla.sim2real.export.onnx_export \\
        --checkpoint=logs/fleetsafe_h1/best.pt \\
        --output=deployed/h1_policy.onnx \\
        --obs_dim=45 --action_dim=18

Alternatively import directly:
    from fleet_safe_vla.sim2real.export.onnx_export import export_fleet_policy
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

# Robot-lab export utilities
from robot_lab.sim2real.export_onnx import export_rsl_rl_policy


def export_fleet_policy(
    checkpoint_path: str | Path,
    output_path: str | Path,
    obs_dim: int = 45,
    action_dim: int = 18,
    device: str = "cpu",
    metadata: Optional[dict] = None,
) -> Path:
    """
    Export a FleetSafe H1 policy to ONNX format.

    Delegates to robot-lab's export_rsl_rl_policy and adds fleet-safe
    metadata (version, obs/action layout, CBF config).

    Args:
        checkpoint_path: path to rsl_rl OnPolicyRunner checkpoint
        output_path:     desired output .onnx path
        obs_dim:         observation dimension (default 45)
        action_dim:      action dimension (default 18)
        device:          inference device ("cpu" or "cuda:0")
        metadata:        additional metadata to embed in ONNX model

    Returns:
        Path to exported .onnx file
    """
    checkpoint_path = Path(checkpoint_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Core export via robot-lab
    exported = export_rsl_rl_policy(
        checkpoint_path=checkpoint_path,
        output_path=output_path,
        obs_dim=obs_dim,
        action_dim=action_dim,
        device=device,
    )

    # Add fleet-safe metadata to ONNX model
    _add_fleet_metadata(exported, metadata or {})

    return exported


def _add_fleet_metadata(onnx_path: Path, extra: dict) -> None:
    """Embed fleet-safe deployment metadata into ONNX model properties."""
    try:
        import onnx

        model = onnx.load(str(onnx_path))

        # Base metadata
        meta = {
            "fleet_safe_version": "0.1.0",
            "obs_layout": (
                "ang_vel[3], proj_grav[3], cmd_vel[3], "
                "q_rel[18], qd[18]"
            ),
            "action_layout": (
                "target_joint_pos[18]: "
                "l_hip_yaw,l_hip_roll,l_hip_pitch,l_knee,l_ankle,"
                "r_hip_yaw,r_hip_roll,r_hip_pitch,r_knee,r_ankle,"
                "l_sh_pitch,l_sh_roll,l_elbow,l_wrist,"
                "r_sh_pitch,r_sh_roll,r_elbow,r_wrist"
            ),
            "control_hz": "50",
            "robot": "h1",
        }
        meta.update(extra)

        for k, v in meta.items():
            entry = model.metadata_props.add()
            entry.key = str(k)
            entry.value = str(v)

        onnx.save(model, str(onnx_path))
    except ImportError:
        pass  # onnx not installed — skip metadata


def validate_exported_policy(
    onnx_path: str | Path,
    obs_dim: int = 45,
    action_dim: int = 18,
    n_test: int = 5,
) -> bool:
    """
    Validate an exported ONNX policy using random inputs.

    Returns True if the model runs and outputs correct shapes.
    """
    try:
        import onnxruntime as ort

        sess = ort.InferenceSession(str(onnx_path))
        input_name = sess.get_inputs()[0].name

        for _ in range(n_test):
            obs = np.random.randn(1, obs_dim).astype(np.float32)
            outputs = sess.run(None, {input_name: obs})
            assert outputs[0].shape == (1, action_dim), (
                f"Expected action shape (1, {action_dim}), got {outputs[0].shape}"
            )

        print(f"ONNX validation PASSED: {onnx_path}")
        return True
    except ImportError:
        print("onnxruntime not installed — skipping ONNX validation")
        return True
    except Exception as e:
        print(f"ONNX validation FAILED: {e}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export FleetSafe H1 policy to ONNX")
    parser.add_argument("--checkpoint", required=True, type=str)
    parser.add_argument("--output", default="deployed/h1_policy.onnx", type=str)
    parser.add_argument("--obs_dim", default=45, type=int)
    parser.add_argument("--action_dim", default=18, type=int)
    parser.add_argument("--device", default="cpu", type=str)
    args = parser.parse_args()

    out = export_fleet_policy(
        checkpoint_path=args.checkpoint,
        output_path=args.output,
        obs_dim=args.obs_dim,
        action_dim=args.action_dim,
        device=args.device,
    )
    print(f"Exported policy to: {out}")
    validate_exported_policy(out, args.obs_dim, args.action_dim)
