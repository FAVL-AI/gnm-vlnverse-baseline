# VLNTube — Software Provenance Record (H8-S1, Section 21)

**Audit date:** 2026-07-22
**Repository audited:** `/home/favl/robotics/gnm-vlnverse-baseline` (branch `h23-execfix`)
**Vendored path:** `external/VLNTube/`
**Auditor note:** this audit is read-only. No file inside the repository was created, modified or deleted.

---

## 1. Summary disposition

VLNTube is a **real, present, MIT-licensed vendored software dependency**. It must **not** be removed.
The only defect is bibliographic: it has been positioned alongside peer-reviewed work, and **no peer-reviewed
VLNTube publication exists**. It must be cited as *software*, not as a publication.

| Field | Value |
|---|---|
| Status | PRESENT — vendored, real, in use |
| Upstream URL | `https://github.com/william13077/VLNTube` |
| Licence | MIT License |
| Copyright holder (verbatim) | `Copyright (c) 2026 V3A Group, Responsible AI Research Centre, The University of Adelaide` |
| Tree content digest | `965e4db0f8c59fa1d119de1858184bb447d954d8485cccee1db0c664b835bf75` |
| File count | 36 files |
| Total size | 341,847 bytes (440 KB on disk) |
| Git submodule? | **No** |
| Pinned ref recorded in repo? | **No** |
| Upstream commit (recovered by audit) | `7ef6afe22014f13fd97a2d4910f84fd6603e17af` (2026-04-25T12:15:17Z) |
| Modified vs upstream? | **No** — byte-identical, verified |
| Peer-reviewed publication? | **No** — verified across 5 independent indexes |

---

## 2. Upstream URL — evidence

The vendored `external/VLNTube/README.md` does **not** state its own upstream URL. The URL is recorded
in four separate places in the parent repository, all in agreement:

| File | Line | Evidence |
|---|---|---|
| `/home/favl/robotics/gnm-vlnverse-baseline/scripts/setup_vlntube.sh` | 16 | `VLNTUBE_URL="https://github.com/william13077/VLNTube"` |
| `/home/favl/robotics/gnm-vlnverse-baseline/fleetsafe_vln/datagen/vlntube_adapter.py` | 133 | `"Clone it: git clone https://github.com/william13077/VLNTube third_party/VLNTube"` |
| `/home/favl/robotics/gnm-vlnverse-baseline/docs/paper/FleetSafe_VLN_Paper_Draft.md` | 234 | `3. VLNTube — https://github.com/william13077/VLNTube` |
| `/home/favl/robotics/gnm-vlnverse-baseline/external/IAmGoodNavigator/README.md` | 8 | `| 🛠️ | **Code** | [Generaion pipeline](https://github.com/william13077/VLNTube) |` |

**Upstream repository confirmed live on 2026-07-22** via the GitHub API:

```
$ gh api repos/william13077/VLNTube --jq '{full_name,created_at,pushed_at,default_branch,license:.license.spdx_id,stargazers_count}'
{"created_at":"2026-03-29T10:27:30Z","default_branch":"main","full_name":"william13077/VLNTube",
 "license":"MIT","pushed_at":"2026-04-25T12:20:10Z","stargazers_count":27}
```

The upstream repository has **no description, no homepage, no releases and no tags**:

```
$ gh api repos/william13077/VLNTube/tags      -> []
$ gh api repos/william13077/VLNTube/releases  -> []
```

---

## 3. Licence — verbatim

Source: `/home/favl/robotics/gnm-vlnverse-baseline/external/VLNTube/LICENSE` (lines 1–3, verbatim):

```
MIT License

Copyright (c) 2026 V3A Group, Responsible AI Research Centre, The University of Adelaide
```

The remainder of the file is the unmodified standard MIT permission and warranty-disclaimer text
(lines 5–21). The licence is confirmed as `MIT` by the GitHub API `license.spdx_id` field for the
upstream repository.

**Note on attribution:** the copyright holder is an institutional group (V3A Group, Responsible AI
Research Centre, The University of Adelaide), not the GitHub account owner (`william13077`). Any
software citation must name the institutional copyright holder.

---

## 4. Local directory content digest

**Exact command used** (run from the repository root, `/home/favl/robotics/gnm-vlnverse-baseline`):

```bash
find external/VLNTube -type f -not -path '*/.git/*' | LC_ALL=C sort | xargs sha256sum | sha256sum
```

**Exact output:**

```
965e4db0f8c59fa1d119de1858184bb447d954d8485cccee1db0c664b835bf75  -
```

**Reproducibility caveat:** this digest hashes the `sha256sum` output stream, which includes the
*relative path text* `external/VLNTube/...`. It is therefore only reproducible when the command is
run from the repository root with that exact relative path. It is stable across machines provided
that condition holds.

### Supporting size metrics

```bash
$ find external/VLNTube -type f -not -path '*/.git/*' | wc -l
36
$ find external/VLNTube -type f -not -path '*/.git/*' -printf '%s\n' | awk '{s+=$1} END {print s}'
341847
$ du -sh external/VLNTube
440K	external/VLNTube
```

**36 files, 341,847 bytes.** Composition: 27 Python files, 6 Markdown files, 1 JSON
(`splits/scene_splits.json`), 1 shell script (`vistube/run_pipeline.sh`), 1 `LICENSE`, 1 `.gitignore`.
Module directories: `scene_graph/`, `vistube/`, `instube/`, `datatube/`, `splits/`.

---

## 5. Version / pinned-ref status

**No version or commit is recorded anywhere in the repository.** Evidence, each checked and negative:

| Check | Result |
|---|---|
| `external/VLNTube/.git/` directory | **Absent** — no Git metadata was vendored |
| `VERSION` / `version.txt` / `__version__` file in `external/VLNTube/` | **Absent** |
| Version note in `external/VLNTube/README.md` | **Absent** — no version, date or commit stated |
| Upstream Git tags | **None** (`gh api .../tags` returns `[]`) |
| Upstream GitHub releases | **None** (`gh api .../releases` returns `[]`) |
| Pinned ref in `scripts/setup_vlntube.sh` | **None** — line 49 is a bare `git clone "${VLNTUBE_URL}" "${VLNTUBE_TARGET}"` with no `--branch`, no `--depth`, and no follow-up `git checkout <sha>`. The setup script therefore always fetches whatever `main` currently points at. |
| Ref in `datasets/vlntube/vlntube_index.json` | **None** — records only `path`, `folders`, `usd_scene_count: 0`, `python_file_count: 27` |
| Ref in any config / YAML / TOML | **None found** |

### Upstream commit recovered by this audit

Although no ref is *recorded*, the exact upstream commit was **recovered forensically** and is now
unambiguous (method in §6):

```
commit 7ef6afe22014f13fd97a2d4910f84fd6603e17af
tree   c9a924d0b334...
date   2026-04-25T12:15:17Z
title  "dataset link"
```

This is upstream `main` HEAD as of 2026-07-22. All 15 upstream commits have distinct tree SHAs, so the
match resolves to exactly one commit — the recovered pin is not ambiguous.

**This recovered value is an audit finding, not a repository record.** It becomes a durable provenance
fact only once it is written into the repository (see gap G1 in §8).

---

## 6. Submodule status — CONFIRMED NOT A SUBMODULE

Your expectation is confirmed. VLNTube is a **plain vendored copy**, tracked as ordinary blobs in the
parent repository.

| Check | Result |
|---|---|
| `.gitmodules` at repository root | `ls: cannot access '.gitmodules': No such file or directory` |
| `git submodule status` | empty output (no submodules registered) |
| `external/VLNTube/.git` | does not exist (only `external/VLNTube/.gitignore` matches `.git*`) |
| `git ls-files -s external/VLNTube` | 36 entries, all mode `100644`/`100755` regular blobs — **no `160000` gitlink entry** |

A gitlink (mode `160000`) is the definitive marker of a submodule; none is present.

---

## 7. Modification vs upstream — VERIFIED UNMODIFIED

This was determined **definitively**, not inferred. Git blob SHA-1s are content-addressed and directly
comparable between our index and the GitHub tree API, so every file was compared exactly:

```bash
gh api "repos/william13077/VLNTube/git/trees/7ef6afe22014f13fd97a2d4910f84fd6603e17af?recursive=1"
# compared against: git ls-files -s external/VLNTube
```

**Result:**

```
truncated: False
upstream blobs: 36   local blobs: 36
identical:            36
ONLY LOCAL     (0): []
ONLY UPSTREAM  (0): []
CONTENT DIFFERS(0): []
```

**The vendored tree is byte-identical to upstream commit `7ef6afe2`.** No file added, none removed,
none altered. This is consistent with `scripts/setup_vlntube.sh` line 5, which states
`# Does NOT modify VLNTube source code.`

`modified_vs_upstream = false` — **verified**, not "UNKNOWN".

---

## 8. The exact provenance gap

The tree is clean and the licence is clear, so the gap is **recording**, not integrity. A reproducible
software citation needs the following, which the repository does not currently supply:

| ID | Gap | Why it matters | Status |
|---|---|---|---|
| **G1** | **No commit SHA recorded in-repo.** Nothing in the repository states which upstream revision was vendored. | Without a pinned ref, "VLNTube" names a moving target. A reader cloning via `scripts/setup_vlntube.sh` today gets upstream `main` HEAD, which may differ from what our results were produced with. This is the single most serious gap. | Recoverable now — `7ef6afe22014f13fd97a2d4910f84fd6603e17af` was recovered by this audit and can be written into the repo. |
| **G2** | **No vendoring date recorded.** No record of when the copy was taken. | Combined with G1, a reader cannot reconstruct the dependency state at experiment time. | Bounded by evidence: upstream commit is 2026-04-25; vendored file mtimes are 2026-06-10; first committed in `67b0383` (2026-06-10). |
| **G3** | **No content digest recorded.** No checksum or manifest of the vendored tree exists in the repository. | Nothing lets a reader verify their copy matches ours without network access to GitHub. | Closed by this audit: `965e4db0f8c5…bf75`. |
| **G4** | **Upstream has no tag, release or version number.** | There is no citable version string; the commit SHA is the *only* possible version identifier. | Upstream-side, not fixable by us. Makes G1 mandatory rather than optional. |
| **G5** | **No software citation entry exists.** No `CITATION.cff`, BibTeX `@software` entry, or reference-list entry for VLNTube. `docs/paper/FleetSafe_VLN_Paper_Draft.md` line 234 lists it as a bare URL under a heading shared with peer-reviewed works. | Presenting a bare URL adjacent to peer-reviewed citations invites a reader to assume a publication exists. | Open — wording in §10 addresses this. |
| **G6** | **No archival snapshot / DOI.** The dependency is a personal GitHub account with no institutional mirror, no Zenodo deposit and no Software Heritage archive. | If `william13077/VLNTube` is deleted or made private, the dependency becomes unreproducible; the vendored copy would be the only surviving artefact. Note the copyright holder is an *institution* but the host is a *personal account* — an elevated disappearance risk. | Open — mitigated in practice by the fact that the full tree is vendored in-repo. |
| **G7** | **Upstream provenance of VLNTube itself is unstated.** The upstream repository has no description, no homepage, no paper link and no author list; authorship is asserted only by the MIT copyright line. | The link between VLNTube and the VLNVerse paper is *not documented by either side* (see §9). | Open — must not be asserted without evidence. |

---

## 9. Publication check — independent re-verification

The previous negative finding was **not assumed**. It was independently re-tested on **2026-07-22**
across five sources, including three authoritative bibliographic indexes.

### 9.1 What was searched, and what was found

| # | Source | Query / URL | Result |
|---|---|---|---|
| 1 | **arXiv API** (authoritative) | `http://export.arxiv.org/api/query?search_query=all:VLNTube&max_results=20` | **`opensearch:totalResults` = 0.** Zero entries. |
| 2 | **DBLP API** (authoritative CS bibliography) | `https://dblp.org/search/publ/api?q=VLNTube&format=json` | **`hits.@total` = "0"`.** Zero publications. |
| 3 | **OpenAlex API** (authoritative, ~250M works) | `https://api.openalex.org/works?search=VLNTube&per-page=10` | **`meta.count` = 0.** Zero works. |
| 4 | **Crossref API** (DOI registry) | `https://api.crossref.org/works?query.bibliographic=VLNTube&rows=5` | **`total-results` = 0.** Zero registered DOIs. |
| 5 | **Web search** (Google-Scholar-style) | `VLNTube vision-language navigation data generation pipeline paper` | No VLNTube paper. Returned only unrelated VLN data-generation work (arXiv 2412.09082 NavGen, 2307.15644, 2406.02208 VLN-MP, 2402.03561 VLN-Video). |
| 6 | **Web search** (exact-token) | `"VLNTube" arXiv paper publication` | No VLNTube paper. Returned unrelated VLN papers (AgentVLN 2603.17670, StreamVLN 2507.05240, VLN-R1 2506.17221) and, on fallback, non-academic "paper tube" manufacturing pages — the classic signature of a token with no academic footprint. |
| 7 | **Semantic Scholar API** | `https://api.semanticscholar.org/graph/v1/paper/search?query=VLNTube` | **INCONCLUSIVE — HTTP 429 (rate limited)** on three attempts. No result obtained. This source neither supports nor contradicts the finding. |
| 8 | **VLNVerse paper full text** (cross-check) | `https://arxiv.org/html/2512.19021v1` | **The string "VLNTube" does not appear anywhere in the VLNVerse paper.** Neither does "IAmGoodNavigator". The paper refers to its data pipeline only descriptively, as a *"two-stage generation pipeline"*. |

### 9.2 Finding

**`publication_verified = false`.** No peer-reviewed, preprint, or DOI-registered VLNTube publication
exists. Four independent authoritative indexes (arXiv, DBLP, OpenAlex, Crossref) each returned a hard
zero. Semantic Scholar was rate-limited and is recorded as inconclusive; it does not change the
conclusion, since a work indexed by Semantic Scholar but absent from all four of arXiv, DBLP, OpenAlex
and Crossref is not a realistic outcome for a peer-reviewed paper.

### 9.3 Important negative finding — do not assert a VLNVerse↔VLNTube link

It is tempting to cite the VLNVerse paper (arXiv:2512.19021) *as* the VLNTube publication. **Do not.**

- The VLNVerse paper never names VLNTube.
- The VLNTube repository never names the VLNVerse paper.
- The two are *materially* connected — VLNTube's README links the `Eyz/VLNVerse_scene`,
  `Eyz/SceneMeta`, `Eyz/SceneSummary` and `Eyz/VLNVerse_data` HuggingFace datasets, and
  `external/VLNTube/splits/scene_splits.json` matches the released VLNVerse scene set exactly
  (see the Section 22 disposition) — and the described architectures correspond (A* on dilated
  occupancy maps; scene-graph priors; multi-agent instruction refinement).
- But correspondence is **not** an authorship or citation claim. Neither party has documented the
  relationship, so asserting "VLNTube is the VLNVerse pipeline, cite Lin et al." would be an
  inference presented as a fact.

The defensible position: cite VLNTube as software on its own terms; cite Lin et al. separately for
VLNVerse; state the relationship, if at all, as observed rather than authoritative.

---

## 10. Approved repository-safe wording

The template was corrected against what was actually found. Two substantive corrections were needed:
the digest and licence are no longer aspirational ("should be cited … including") but **available and
stated**, and the unrecorded-but-recovered commit is now included, since a citation without a revision
is not reproducible for a dependency that has no tags or releases.

### 10.1 Primary wording — use this

> VLNTube is used as a software dependency and trajectory-rendering component. It is vendored under
> `external/VLNTube/` and is cited as software, not as a publication: upstream repository
> `https://github.com/william13077/VLNTube`, MIT License (Copyright (c) 2026 V3A Group, Responsible AI
> Research Centre, The University of Adelaide), upstream revision
> `7ef6afe22014f13fd97a2d4910f84fd6603e17af`, local content digest
> `sha256:965e4db0f8c59fa1d119de1858184bb447d954d8485cccee1db0c664b835bf75` (36 files, 341,847 bytes).
> The vendored tree was verified byte-identical to that upstream revision. Upstream publishes no tags
> or releases, so the commit hash is the only available version identifier. **No peer-reviewed VLNTube
> publication has been verified** (arXiv, DBLP, OpenAlex and Crossref each return zero results as of
> 2026-07-22).

### 10.2 Short form — for a related-work or dependency line

> VLNTube (software; `https://github.com/william13077/VLNTube`, MIT, rev `7ef6afe2`) is used as a data-
> generation and trajectory-rendering dependency, vendored at `external/VLNTube/`. No peer-reviewed
> VLNTube publication has been verified.

### 10.3 Suggested BibTeX `@software` entry

```bibtex
@software{vlntube,
  title        = {VLNTube: A pipeline for generating Vision-Language Navigation training data
                  from indoor 3D scenes},
  author       = {{V3A Group, Responsible AI Research Centre, The University of Adelaide}},
  year         = {2026},
  note         = {Software. MIT License. No peer-reviewed publication.
                  Vendored revision 7ef6afe22014f13fd97a2d4910f84fd6603e17af;
                  content digest sha256:965e4db0f8c59fa1d119de1858184bb447d954d8485cccee1db0c664b835bf75},
  url          = {https://github.com/william13077/VLNTube},
  urldate      = {2026-07-22}
}
```

### 10.4 Wording that must NOT be used

- ❌ "VLNTube (Lin et al.)" — no such publication; conflates VLNTube with the VLNVerse paper.
- ❌ Listing VLNTube as a bare numbered URL in a reference list alongside peer-reviewed entries
  (current state, `docs/paper/FleetSafe_VLN_Paper_Draft.md` line 234).
- ❌ "the VLNTube paper", "as described in VLNTube", "VLNTube et al."
- ❌ Any citation omitting the revision — upstream has no tags, so an unversioned citation is
  irreproducible by construction.

---

## 11. Files examined (all read-only)

```
/home/favl/robotics/gnm-vlnverse-baseline/external/VLNTube/LICENSE
/home/favl/robotics/gnm-vlnverse-baseline/external/VLNTube/README.md
/home/favl/robotics/gnm-vlnverse-baseline/external/VLNTube/splits/scene_splits.json
/home/favl/robotics/gnm-vlnverse-baseline/scripts/setup_vlntube.sh
/home/favl/robotics/gnm-vlnverse-baseline/fleetsafe_vln/datagen/vlntube_adapter.py
/home/favl/robotics/gnm-vlnverse-baseline/datasets/vlntube/vlntube_index.json
/home/favl/robotics/gnm-vlnverse-baseline/docs/paper/FleetSafe_VLN_Paper_Draft.md
/home/favl/robotics/gnm-vlnverse-baseline/external/IAmGoodNavigator/README.md
```

No repository file was created, modified or deleted. No state-changing Git command was run.
