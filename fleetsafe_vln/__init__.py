"""FleetSafe-VLN: Certified safe multimodal embodied navigation benchmark.

Facade package over fleet_safe_vla — adds YAML-driven task/episode/suite
infrastructure, a unified simulator interface, extended safety certificates,
and CLI entry points.

Quick start:
    python -m fleetsafe_vln.benchmark.episode_runner \\
        --platform mock \\
        --task tasks/hospital_corridor.yaml \\
        --model vint \\
        --safety cbf_qp \\
        --log-dir runs/test_episode
"""

__version__ = "0.2.0"
