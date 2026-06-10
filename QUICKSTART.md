# GNM-VLNVerse Baseline — Quickstart

Minimal command path to reproduce the GNM/VLNVerse baseline proof.

The proof path runs without Isaac Sim GUI.

---

## 1. Bootstrap

```bash
git clone git@github.com:FAVL-AI/gnm-vlnverse-baseline.git
cd gnm-vlnverse-baseline

bash scripts/gnm/bootstrap_demo_env.sh
source .venv/bin/activate
```

---

## 2. Link Data

```bash
bash scripts/gnm/link_vlntube_data.sh /path/to/vlntube
python3 scripts/gnm/check_demo_ready.py
```

Expected readiness result:

```text
Overall: PASS — ready to run the proof pipeline.
```

---

## 3. Dataset Proof

```bash
python3 scripts/gnm/replay_gnm_demo.py --prove-dataset
```

Expected output includes:

```text
Train trajectories : 238
Val trajectories   : 15
SR                 : 20.0%
OSR                : 46.7%
NE                 : 6.51 m
```

---

## 4. Dashboard Export

```bash
python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
```

This generates local dashboard frames under:

```text
results/bo_reviewer_packet/live_dashboard/
```

Generated dashboard frames are not committed to Git.

---

## 5. Manual Dry-Runs

```bash
python3 scripts/gnm/manual_testdrive.py --dry-run
python3 scripts/gnm/replay_manual_testdrive.py --dry-run
python3 scripts/gnm/convert_manual_testdrive_to_gnm.py --dry-run
```

---

## 6. Tests

```bash
python3 -m pytest tests/gnm -q
```

Expected result: all tests pass. Torch-dependent model tests skip only if PyTorch is absent.

---

## Optional Isaac Sim Replay

Isaac Sim replay is optional and environment-dependent.

```bash
conda activate isaac

LIVE_DASHBOARD=1 AUTO_PLAY=1 SHOW_GNM_PANELS=1 MAX_STEPS=100000 \
python scripts/gnm/replay_gnm_demo.py
```

For manual driving:

```bash
conda activate isaac
MODE=custom_office python scripts/gnm/manual_testdrive.py
```

If Isaac GUI is unstable, use the non-GUI dashboard export as the reliable evidence path.

---

## Repository

[https://github.com/FAVL-AI/gnm-vlnverse-baseline](https://github.com/FAVL-AI/gnm-vlnverse-baseline)
