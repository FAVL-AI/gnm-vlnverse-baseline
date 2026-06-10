# Repository Governance

## Authorship policy

This repository has one author:

```
F. Van Laarhoven <F.Van-Laarhoven2@newcastle.ac.uk>
Newcastle University
```

No external tools, services, or automated systems are listed as contributors or co-authors.
The `git shortlog -sne --all` output must show exactly one author identity.

## Source-code-only rule

The following categories of files are **never committed** to this repository:

- Large datasets and trajectory RGB frame dumps.
- Generated dashboard PNGs and image sequences.
- Model checkpoints (`.pt`, `.pth`, `.ckpt`).
- Recorded ROS2 bag files.
- Isaac Sim USD assets from VLNVerse (re-downloadable from the VLNVerse project).
- Any binary or generated output that can be recreated from the source code.

These items are excluded by `.gitignore`. The source-clean check is:

```bash
git ls-files | grep -E '(\.jpg$|\.jpeg$|\.png$|\.mp4$|\.pt$|\.pth$|\.ckpt$)' \
  || echo "OK: repo is source-code clean"
```

## No tool branding

This repository does not reference, credit, or mention automated generation tools,
code assistants, or any external system in commit messages, documentation, or source files.
All content is presented as the work of the listed author.

## Review branch policy

Two review branches exist for the Bo/Rui review process:

```
review/bo-rui-gnm-vlnverse     — reviewer access branch
feature/custom-vln-office      — feature branch for custom scene work
```

Both branches track `main` exactly. Review documents are in `results/bo_reviewer_packet/`.

## Evidence policy

Generated visual evidence (dashboard PNGs, RGB frames) is not committed.
Evidence is regenerated locally from scripts:

```bash
python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
python3 scripts/gnm/replay_gnm_demo.py --prove-dataset
```

The repository stores source code, configurations, review documents, and test files only.

## Legacy content policy

Legacy FleetSafe technical content is preserved under `docs/legacy/` for reference.
It is not part of the GNM/VLNVerse baseline path and is not updated.
Legacy scripts in `scripts/` subdirectories other than `scripts/gnm/` are retained
but are not the canonical entrypoints for this repository.
