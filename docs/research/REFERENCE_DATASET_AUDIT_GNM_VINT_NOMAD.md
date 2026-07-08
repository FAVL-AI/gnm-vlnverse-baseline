# Reference Dataset Audit — GNM, ViNT, NoMaD vs our VLNTube/Kujiale setting

Claim boundary: This audit expands the project from model-only
evaluation into training-data evaluation. It does not claim superiority
over GNM, ViNT, or NoMaD. It identifies which data regimes are
comparable, which require adapters, and why matched-camera
VLNTube/Kujiale generation is the immediate controlled experiment.

## What GNM was trained on
GNM (Shah et al., 2022, "drive any robot") trained on a heterogeneous
mixture across robot platforms. The public portion listed by the
official repository: **RECON, TartanDrive, SCAND, and a modified
GoStanford2**; the paper additionally used **unreleased** data. All are
front-facing real-robot navigation datasets.

## What ViNT was trained on
ViNT (Shah et al., CoRL 2023) is a visual-navigation foundation model
trained on large, diverse existing navigation datasets — hundreds of
hours across multiple platforms (the GNM-style families above and
more), front-camera egocentric imagery, goal-image conditioning.

## What NoMaD was trained on
NoMaD (Sridhar et al., 2023) extends the family with a goal-masked
diffusion policy for goal-conditioned navigation AND goal-agnostic
exploration; reported training data is the GNM-style dataset mixture
plus **HuRoN/SACSoN**-style social-navigation data.

## Public vs unreleased boundary
Public: RECON, TartanDrive, SCAND, GoStanford2 (modified), HuRoN/SACSoN
releases. Unreleased: part of the original GNM training mixture is
explicitly not public — exact-mixture reproduction is impossible, which
itself bounds any "same-training-data" comparison claim.

## Dataset-camera convention comparison
GNM/ViNT/NoMaD data: front-facing egocentric robot cameras, real
environments, real dynamics. Our current local VLNTube/Kujiale data:
**top-down/nadir rendered frames** (verified in Stage 3C by pose-exact
re-rendering) in synthetic Kujiale interiors. These are different
visual regimes; models trained in one are out-of-distribution in the
other without adaptation.

## Task comparison
- Image-goal navigation: our current setting (goal = image) — closest
  to GNM/ViNT goal-image conditioning, but in a different camera regime.
- Goal-conditioned navigation: GNM/ViNT/NoMaD core task.
- Exploration: NoMaD's goal-agnostic mode — we do not address it.
- Language-conditioned VLN: NOT our current setting (no language in the
  control loop); any VLN claim is out of scope.

## Why our VLNTube/Kujiale top-down setting is different
It is synthetic, top-down, single-domain (Kujiale interiors), and small
(4 scenes locally). It is NOT the GNM data philosophy (cross-platform
real-robot diversity). That difference is the point of the study: we
measure what matched-view generated data does within one regime.

## Why generated Kujiale data is the right immediate expansion
It changes exactly one variable (training-data quantity/coverage) while
holding camera regime, scenes, evaluator, split and architecture fixed
— a clean causal test (Stage 4/5). External datasets would change
camera regime, domain and task distribution simultaneously.

## Why external datasets need adapters and separate claim boundaries
RECON/TartanDrive/SCAND/GoStanford2/HuRoN differ in format (bags/hdf5/
custom), camera intrinsics, action spaces and dynamics. Each needs a
documented adapter and its own claim boundary; none may silently enter
the current training set (validator-enforced elsewhere in this repo).

## What benchmark comparison is fair now
Level 1 only: original VLNTube split vs original+generated matched-view
data on the frozen kujiale_0271 scene (Stage 4/5).

## What is future work
Level 2: official GNM/ViNT/NoMaD checkpoints under OUR evaluator (needs
front-camera evaluation data or their public eval suites). Level 3:
dataset-regime comparison (top-down synthetic vs real-robot front
camera). Level 4: full matched-protocol benchmark with reproducible
commands. We are building the evidence needed to compare training-data
regimes and navigation methods under matched evaluation rules.
