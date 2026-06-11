# Reproducibility and One-Command Evaluation Pack

This document explains how to reproduce the main GNM-VLNVerse Track A evidence from the repository state.

The goal is to give supervisors, reviewers, and collaborators one clear command that checks the core evidence chain:

- dataset-scene manifest generation
- test-suite validity
- required evidence files
- README release matrix
- dataset split counts
- scene IDs
- optional Isaac live trajectory demonstration

## One-command check

Run:

```bash
bash scripts/gnm/run_reproducibility_pack.sh
