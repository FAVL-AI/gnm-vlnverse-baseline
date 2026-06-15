# Third-Party Notices

This file documents third-party software, datasets and assets used or
referenced in this repository. Original notices and licences must not
be removed.

---

## VLNTube pipeline

| Field | Value |
|-------|-------|
| Component | VLNTube data-generation pipeline |
| Directory | `external/VLNTube/` |
| Upstream | https://github.com/william13077/VLNTube |
| Authors | V3A Group, Responsible AI Research Centre, University of Adelaide |
| Licence | MIT (see `external/VLNTube/LICENSE`) |
| Copyright | © 2026 V3A Group, Responsible AI Research Centre, The University of Adelaide |
| Usage | Instruction generation scripts (instube/), scene graph utilities, split definitions |
| Modification | Not modified; referenced as upstream dependency |
| Redistribution | Permitted under MIT licence with copyright notice retained |

The fine-grained navigation instructions in `datasets/vlntube/` were generated
by the VLNTube instube/ pipeline (Gemini API, V3A Group). They are sourced from
`Eyz/VLNVerse_data` on HuggingFace. They are not authored by the repository owner.

---

## IAmGoodNavigator

| Field | Value |
|-------|-------|
| Component | Isaac Sim navigation demonstration scripts |
| Directory | `external/IAmGoodNavigator/` |
| Upstream | https://github.com/william13077/IAmGoodNavigator |
| Authors | V3A Group (see README reference) |
| Licence | LICENCE_REVIEW_REQUIRED — no explicit licence file found in local copy |
| Usage | Demo scripts for Isaac Sim navigation; data download helpers |
| Modification | Not modified |

---

## VisualNav-Transformer (GNM / ViNT / NoMaD)

| Field | Value |
|-------|-------|
| Component | Pre-trained visual navigation models and training code |
| Directory | `third_party/visualnav-transformer/` (gitignored, populated by setup script) |
| Upstream | https://github.com/robodhruv/visualnav-transformer |
| Authors | Dhruv Shah et al., Berkeley |
| Licence | LICENCE_REVIEW_REQUIRED — check upstream repository |
| Usage | GNM model architecture, checkpoints, training utilities |
| Modification | Wrapped via `fleet_safe_vla/integrations/`; not directly modified |

---

## Eyz/VLNVerse_data (HuggingFace dataset)

| Field | Value |
|-------|-------|
| Component | VLNVerse/VLNTube prebuilt episode data |
| Source | https://huggingface.co/datasets/Eyz/VLNVerse_data |
| Authors | V3A Group, University of Adelaide |
| Licence | LICENCE_REVIEW_REQUIRED — check HuggingFace dataset card |
| Local path | `datasets/vlntube/prebuilt_data/raw_data/final_splits/` |
| Content | Episode trajectories with Gemini-generated navigation instructions |
| Usage | Source of instruction.txt content for 253 vlntube_fleetsafe episodes |
| Modification | Not modified; instruction texts copied verbatim by vlntube_runner.py |

---

## Eyz/VLNVerse_scene (HuggingFace dataset)

| Field | Value |
|-------|-------|
| Component | Kujiale indoor 3D scene assets (USD) |
| Source | https://huggingface.co/datasets/Eyz/VLNVerse_scene |
| Authors | V3A Group, University of Adelaide |
| Licence | LICENCE_REVIEW_REQUIRED — check HuggingFace dataset card |
| Content | USD scene files for kujiale_XXXX environments |
| Usage | Scene rendering in Isaac Sim for trajectory data generation |

---

## Real Kujiale/VLNTube trajectory images

| Field | Value |
|-------|-------|
| Component | Real indoor camera images from 253 episodes |
| Local path | `datasets/vlntube/train/` and `datasets/vlntube/val/` |
| Source | Rendered in Isaac Sim from Kujiale 3D scene assets |
| Authors | V3A Group, University of Adelaide |
| Licence | LICENCE_REVIEW_REQUIRED — check upstream dataset licence |
| Usage | Real-image language-grounding evaluation (Track B) |

---

## NVIDIA Isaac Sim

| Field | Value |
|-------|-------|
| Component | Physics simulation and rendering engine |
| Provider | NVIDIA Corporation |
| Licence | NVIDIA EULA (see NVIDIA developer portal) |
| Usage | Optional; required only for --generate mode in data pipeline |
| Committed | No (local install only) |

---

## CLIP (openai/clip-vit-base-patch16)

| Field | Value |
|-------|-------|
| Component | CLIP vision-language model |
| Provider | OpenAI |
| Distribution | HuggingFace Hub (downloaded on first use) |
| Licence | MIT (https://github.com/openai/CLIP/blob/main/LICENSE) |
| Usage | Text-to-image subgoal retrieval (Track B, optional) |
| Committed | No (weights not committed) |

---

## PyTorch

| Field | Value |
|-------|-------|
| Component | Deep learning framework |
| Provider | Meta AI / PyTorch Foundation |
| Licence | BSD-3-Clause |
| Usage | Model inference and tensor operations |

---

## Gemini API (Google)

| Field | Value |
|-------|-------|
| Component | Large language model API used to generate VLNTube instructions |
| Provider | Google |
| Note | API was used by the VLNTube pipeline authors (V3A Group), not by this repository |
| Outputs | Not directly owned by this repository; provenance documented in instruction_provenance/ |

---

## Legend

| Status | Meaning |
|--------|---------|
| `LICENCE_REVIEW_REQUIRED` | Licence not confirmed; do not redistribute without review |
| MIT | Standard MIT licence; confirm copyright notice retention |
| BSD-3-Clause | Standard BSD licence |
