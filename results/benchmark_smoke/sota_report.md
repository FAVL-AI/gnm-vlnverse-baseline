# FleetSafe-VisualNav Benchmark Report
Generated: 2026-05-23 03:46 UTC

## Evaluation Protocol
- Models: gnm, vint
- Scenes: hospital_corridor, cluttered_navigation, straight_corridor, narrow_passage
- Seeds per condition: 10
- Backend: mock
- d_safe: 0.5 m  |  e-stop: 0.3 m
- v_max: 0.3 m/s

## Results

| Condition | Success | Collision | SPL | Min Dist (m) | Interv% | Infer ms | CBF ms |
|-----------|---------|-----------|-----|-------------|---------|----------|--------|
| **GNM** | 22.5% [10–35%] | 47.5% [32–62%] | 0.225 | 0.457 | — | 0.1 | — |
| **GNM + FleetSafe** | 0.0% [0–0%] | 0.0% [0–0%] | 0.000 | 0.785 | 57.0% | 0.1 | 0.31 |
| **VINT** | 22.5% [10–35%] | 47.5% [32–62%] | 0.225 | 0.457 | — | 0.1 | — |
| **VINT + FleetSafe** | 0.0% [0–0%] | 0.0% [0–0%] | 0.000 | 0.785 | 57.0% | 0.1 | 0.31 |

## FleetSafe Safety Effect (Statistical Analysis)

### GNM
- Collision rate: 47.5% → 0.0%
  Δ = -47.5%
  Wilcoxon p = 0.0000
  Cohen's d = -1.345
- Min obstacle dist: 0.457 m → 0.785 m
  Δ = +0.328 m
  Wilcoxon p = 0.0000
- SPL: 0.225 → 0.000
  Δ = -0.225
- Intervention rate: 57.0% of steps

### VINT
- Collision rate: 47.5% → 0.0%
  Δ = -47.5%
  Wilcoxon p = 0.0000
  Cohen's d = -1.345
- Min obstacle dist: 0.457 m → 0.785 m
  Δ = +0.328 m
  Wilcoxon p = 0.0000
- SPL: 0.225 → 0.000
  Δ = -0.225
- Intervention rate: 57.0% of steps

## Literature Comparison

| Reference | Reported Success | Notes |
|-----------|-----------------|-------|
| GNM (Shah 2023, indoor corridors) | 45% | Indoor office corridors subset; zero-shot on unseen robots. |
| ViNT (Shah 2023, novel environments) | 52% | Zero-shot generalization to novel indoor environments. |
| NoMaD (Sridhar 2023) | — | Exploration-focused; not designed for goal-conditioned point-nav. |

## Dataset Provenance

| Condition | Training Data | FleetSafe Modification |
|-----------|--------------|------------------------|
| GNM baseline | RECON, GoStanford2, SCAND, SACSoN, TartanDrive | None |
| GNM + FleetSafe | Same as baseline | Command-layer CBF-QP only (no weight changes) |
| ViNT baseline | GNM corpus + additional web data | None |
| ViNT + FleetSafe | Same as baseline | Command-layer CBF-QP only |
| NoMaD baseline | GNM corpus | None |
| NoMaD + FleetSafe | Same as baseline | Command-layer CBF-QP only |

**Key claim:** FleetSafe is architecture-agnostic. It adds zero training overhead.
The same CBF-QP filter is applied identically to all models.

## Reproducibility

```bash
# Install dependencies
pip install -e .

# Run FleetSafe Benchmark (mock backend, ~5 min)
python scripts/benchmarks/benchmark.py --output results/benchmark

# Paper mode (50 seeds, ~50 min)
python scripts/benchmarks/benchmark.py --paper --output results/benchmark_paper

# With real checkpoints
python scripts/benchmarks/benchmark.py \
    --gnm-ckpt  third_party/visualnav-transformer/model_weights/gnm/gnm.pth \
    --vint-ckpt third_party/visualnav-transformer/model_weights/vint/vint.pth \
    --nomad-ckpt third_party/visualnav-transformer/model_weights/nomad/nomad.pth
```

## Citation

```bibtex
@inproceedings{vanlaarhoven2026fleetsafe,
  title   = {FleetSafe-VisualNav: Paradigm-Selective Command-Layer Safety
             for Visual Navigation via CBF Intervention},
  author  = {Van Laarhoven, F.},
  year    = {2026},
  note    = {Newcastle University, UK. ORCID: 0009-0006-8931-0364}
}
```
