# Literature correction plan — VLNTube and VLNVerse

**No repository change has been made.** This is analysis and a proposed plan.
Occurrence inventory: `../evidence/vlntube_occurrences.json`, `../evidence/vlntube_tracked_files.txt`.

## 1. Material correction to the audit's literature finding

The Part L review reported that *"VLNTube does not exist as a findable primary publication."*
That is correct **and incomplete**, and acting on it as a blanket removal would be wrong.

**VLNTube exists as software.** It is a real, vendored pipeline at `external/VLNTube/`
(`william13077/VLNTube`, LICENSE present, modules `scene_graph/`, `vistube/`, `instube/`, `datatube/`)
which this project genuinely depends on for Kujiale data generation. The project's own paper draft
already cites it correctly as a GitHub URL (`docs/paper/FleetSafe_VLN_Paper_Draft.md:234`), not as a
paper.

So the correction is narrower and sharper than "remove VLNTube":

> **VLNTube is a citable software artifact, not a peer-reviewed publication. It may be referenced as
> software with a repository URL and an access date. It must not be cited as a paper, described as
> "established" or "published" work, or used to lend published standing to a claim.**

Note the vendored copy is **not** a git submodule and `.gitmodules` does not exist — so there is no
pinned upstream commit. A software citation needs one; recording the vendored tree's digest is the
minimum.

## 2. Occurrence inventory — 167 tracked files

| Class | Files | Action |
| --- | ---: | --- |
| **A** — generated artifact paths (`datasets/vlntube_generated/...` in checksums, manifests, batch records) | 71 | **No change.** Historical evidence; renaming would break checksums and rewrite history. |
| **B** — build/tooling paths (`.gitignore`, `Makefile`, `scripts/*.sh`) | 17 | **No change.** These are real filesystem paths to a real dependency. |
| **C** — vendored upstream code | 3 | **No change** to upstream files. Add a provenance note recording the source URL and vendored-tree digest. |
| **D** — source-code identifiers (configs, converters, indexers, `vlntube.yaml`) | 61 | **No change.** Module and config names for a real dependency. |
| **E** — **paper claims** | **1** | **CORRECT.** `docs/paper/FleetSafe_VLN_Paper_Draft.md` |
| **F** — documentation claims | 11 | **Review individually** — separate path references from standing claims. |
| **G** — other (dashboard UI, dataset index) | 3 | Review labels only. |

**Only ~12 files (classes E, F, G) contain claims. The other 155 are paths and identifiers to a real
dependency and must be left alone.**

## 3. Specific corrections in `docs/paper/FleetSafe_VLN_Paper_Draft.md`

| Line | Current | Problem | Proposed |
| --- | --- | --- | --- |
| 9 | "extends VLNVerse and the VLNTube data-generation pipeline" | acceptable — names a pipeline | keep, add software citation |
| 15 | "VLNVerse and VLNTube **have established** strong simulation pipelines" | "established" implies published standing VLNTube lacks | "VLNVerse (Lin et al.) and the VLNTube data-generation pipeline (software) provide …" |
| 30 | "**VLNTube** (william13077/VLNTube): Data-generation pipeline …" | correct already | keep; add access date + digest |
| 234 | "3. VLNTube — https://github.com/william13077/VLNTube" | correct form | move to a **Software** subsection, distinct from the paper bibliography |

## 4. A second, independent discrepancy — VLNVerse scene count

The project describes VLNVerse as *"Isaac Sim-based VLN benchmark with **4,000+ scenes**"*
(`FleetSafe_VLN_Paper_Draft.md:28`), citing `https://sihaoevery.github.io/vlnverse/` and the
HuggingFace dataset `Eyz/VLNVerse_scene`.

The verified primary publication (Lin et al., arXiv:2512.19021) reports **263 home scenes**.

Same first author, same Isaac Sim basis — but the numbers differ by more than an order of magnitude.
**Do not silently reconcile this.** Possible explanations: different releases; the 4,000+ figure counts
scene *variants* or USD assets rather than scenes; or the project figure is simply wrong. The action is
to check the project figure against the cited primary source and correct whichever is unsupported,
recording which source each number came from. **A number in our paper must be traceable to the source
we cite for it.**

## 5. Existing finding worth preserving

`docs/research/GOOD_BAD_UGLY_RESEARCH_MANUSCRIPT.md:419` already records that
*"VLNTube frames are TOP-DOWN (bird's-eye), not first-person."* This is a significant, correct,
previously-established limitation and it should be **retained and made more prominent**, not removed —
it directly explains why the Kujiale/VLNTube regime is not a first-person image-goal setting and
therefore why the hospital recapture is necessary.

## 6. GNM / ViNT / NoMaD comparison boundary

Discuss as architectural and methodological related work. **Do not place their reported numbers in a
direct comparative table with ours** unless all of the following are compatible: task; dataset;
robot/simulator; success radius; stopping rule; collision definition; evaluation split;
confidence-interval methodology.

They are not compatible. The verified review found these papers report no success radius, no stop
criterion, no enumerated episode set, no collision-detector specification and no seeds/CIs/significance
tests; GNM's headline figure is *mean progress towards the goal*, not a success rate at all.

**Approved wording:**

> GNM, ViNT and NoMaD provide important visual-navigation baselines, but their published evaluation
> protocols do not expose all the stopping-threshold and uncertainty details needed for direct
> numerical comparison with our hospital experiment. We therefore compare methods conceptually and
> reproduce metrics under one explicitly pre-registered protocol.

## 7. Bibliography actions

**Keep (verified primary sources, 10 entries in `references.bib.tmp`):** GNM (ICRA 2023), ViNT
(CoRL 2023, PMLR 229:711–733), NoMaD (ICRA 2024), Anderson et al. (arXiv preprint — flag as *not*
peer-reviewed), Ilharco et al. (ViGIL @ NeurIPS 2019), Jain et al. (ACL 2019), Yokoyama et al.
(IROS 2021), VLNVerse (arXiv:2512.19021 — preprint), Francis et al. (ACM THRI 14(2)),
Hirose et al. SACSoN (IEEE RA-L 9(1)).

**Reclassify:** VLNTube → `@software` / `@misc` with repository URL, access date and vendored-tree
digest. Never `@inproceedings` or `@article`.

**Flag preprint status explicitly** for Anderson et al. and VLNVerse — both are preprints, and
Anderson et al. is the source of our SPL definition, so its status should be stated.

## 8. Historical-record policy

**Do not silently delete historical statements.** Where a committed document made an unsupported
claim, annotate it in place with a dated correction note referencing this plan, or record the
correction in a register. The audit trail of what we believed and when is itself evidence.

- **Active paper / deck / README claims:** correct before anything goes out.
- **Historical records** (`assets/experiments/**`, campaign summaries, past professor updates):
  annotate as superseded; do not rewrite.
- **Bibliography:** reclassify VLNTube; do not remove the dependency.

## 9. Verification before any of this is applied

1. Independently re-verify VLNTube's publication status (a paper may have appeared since).
2. Fetch `https://sihaoevery.github.io/vlnverse/` and the HuggingFace dataset card, and reconcile the
   scene count against arXiv:2512.19021.
3. Confirm `external/VLNTube/LICENSE` permits the vendoring and citation form used.
4. Record the vendored tree digest so the software citation is reproducible.
