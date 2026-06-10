# third_party/

Vendored upstream repositories required by FleetSafe integrations.

## visualnav-transformer

Upstream: https://github.com/robodhruv/visualnav-transformer

**Not committed** — the clone lives at `third_party/visualnav-transformer/` and is
gitignored (too large to vendor).  Run the setup script to populate it:

```bash
bash scripts/visualnav/setup_visualnav.sh
```

The script clones the repo, installs dependencies, verifies imports, and checks
checkpoint paths.  It will print exact next steps if any asset is missing.

## diffusion_policy

Upstream: https://github.com/real-stanford/diffusion_policy

**Not committed** — required by NoMaD adapter.  The `pip install -e` path is
non-standard (empty MAPPING); instead a `.pth` file is written to the conda
env's site-packages pointing at `third_party/diffusion_policy/`.

The setup script handles this automatically:

```bash
bash scripts/visualnav/setup_visualnav.sh
```

### Full per-model dependency matrix

| Model | Extra packages required |
|---|---|
| GNM   | (none beyond torch/torchvision/vint_train) |
| ViNT  | `efficientnet-pytorch`, `warmup_scheduler` |
| NoMaD | `diffusers==0.11.1`, `huggingface_hub==0.12.0`, `einops`, `diffusion_policy` |

All installed by `setup_visualnav.sh` into the `fleetsafe-vnav` conda env.

---

## Rule

Do not edit files under `third_party/` directly.  All FleetSafe-specific
adaptations live under `fleet_safe_vla/integrations/`.  Upstream patches
(if ever needed) must be isolated as `.patch` files with a comment explaining why.
