# Quick Start

**Full guide:** [docs/USAGE.md](docs/USAGE.md) | **README:** [README.md](README.md)

---

## Prerequisites

- Python 3.10+
- PyTorch 2.2+
- Local copy of FleetSafe-VisualNav-Benchmark dataset

---

## Installation

```bash
git clone https://github.com/FAVL-AI/gnm-vlnverse-baseline.git
cd gnm-vlnverse-baseline
pip install -e .                     # base
pip install -e '.[language]'         # CLIP retrieval (Track B)
```

---

## Link dataset

```bash
bash scripts/gnm/link_vlntube_data.sh /path/to/vlntube
python3 scripts/gnm/check_demo_ready.py
```

---

## Track A

```bash
# Reproduce baseline metrics (SR/OSR/NE)
python3 scripts/gnm/evaluate_track_b.py --split val --methods oracle last

# Export live dashboard (no GUI)
python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
```

Results: `results/bo_reviewer_packet/`

---

## Track B

```bash
# Instruction-provenance audit (Gate B)
python3 scripts/gnm/audit_track_b_language_data.py

# Target-exposure audit
python3 scripts/gnm/audit_instruction_target_exposure.py

# Dev-set method selection (7 methods, 238 train episodes)
python3 scripts/gnm/dev_set_method_selection.py

# Language-dependence controls (critical: see README for interpretation)
python3 scripts/gnm/language_dependence_controls.py --split train
```

Results: `results/track_b_language/`

> **Important:** All VLNTube trajectories end exactly at goal_pos. SR@3m = 1.000
> is achievable by the route prior alone, regardless of instruction content.
> Language dependence is not demonstrated on this dataset.

---

## Tests

```bash
python3 -m pytest -q          # full suite (~1815 passing)
```

---

## Further reading

- [README.md](README.md) — research scope, results, claim boundaries
- [docs/USAGE.md](docs/USAGE.md) — step-by-step workflow for all 20 documented tasks
- [data/track_b_annotations/DATASET_CARD.md](data/track_b_annotations/DATASET_CARD.md) — manifest schema and split discipline
- [results/track_b_language/language_dependence_controls/train/report.md](results/track_b_language/language_dependence_controls/train/report.md) — full language-dependence analysis (train split)
