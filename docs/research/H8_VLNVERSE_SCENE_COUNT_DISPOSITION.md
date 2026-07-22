# VLNVerse Scene-Count Discrepancy — Disposition (H8-S1, Section 22)

**Audit date / access date for all URLs:** 2026-07-22
**Repository audited:** `/home/favl/robotics/gnm-vlnverse-baseline` (branch `h23-execfix`)
**Auditor note:** read-only audit. No repository file was created, modified or deleted.

---

## 0. DISPOSITION

# `263 HOME SCENES VERIFIED`

**One-line justification:** The primary source states verbatim *"a total of 263 unique 3D scenes"*
and *"263 large-scale, interactive 3D home environment assets"*, and the released scene assets
independently enumerate to **262 scene directories that match `external/VLNTube/splits/scene_splits.json`
as an exact 1:1 set** — whereas **no VLNVerse primary source states 4,000 scenes in any unit**, so the
repository's "4,000+ scenes" claim is unsupported and must be corrected.

---

## 1. Occurrence table — every scene-count claim in the repository

Search method (tracked files only):

```bash
git grep -n "4,000"                                                       # literal
git grep -nE "4,?000" ; git grep -nE "4,?000\+?[^0-9]{0,40}scene|scene[^0-9]{0,40}4,?000"
git grep -n "263" -- '*.md' '*.txt' '*.json' '*.py' '*.sh' '*.yaml' '*.yml' '*.csv' | grep -iE "scene|vlnverse|house|environment"
git grep -nE "\b(176|177|262)\b" -- '*.md' '*.txt' '*.py' '*.sh' '*.json' | grep -iE "scene|vlnverse|trainval|split"
git grep -nEi "[0-9][0-9,]*\+? *(unique |home |3d |usd |kujiale |large-scale )*(scene|house|environment)s" -- '*.md'
git grep -nEi "(vlnverse|vlntube|upstream)[^.]{0,120}[0-9][0-9,]*\+? *scenes|[0-9][0-9,]*\+? *scenes[^.]{0,120}(vlnverse|vlntube|upstream)"
git grep -nEi "thousand|[0-9]k \*?scenes|scenes? (corpus|library|pool) of" -- '*.md'
```

The `4,?000` sweep returned 74 KB of matches; **all but one were numeric noise** — float coordinates
(`3.4000000000000004`), epoch nanoseconds (`1784000493684460628`), log filenames (`..._174000.log`)
and prim counts (`26329`). Likewise every `263` hit outside the table below was a float coordinate or
a prim count. After filtering, the complete set of genuine VLNVerse/VLNTube scene-count claims is:

| # | File | Line | Exact wording | Cited source | Source date | Status | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | `docs/paper/FleetSafe_VLN_Paper_Draft.md` | 28 | `**VLNVerse** (Lin et al.): Isaac Sim-based VLN benchmark with 4,000+ scenes, fine/coarse grained tasks, and the IAmGoodNavigator demo runner.` | `(Lin et al.)` — attribution only; no arXiv ID, no URL, no year | none stated | **ACTIVE** | ❌ **INCORRECT — the only defective claim** |
| 2 | `docs/research/GOOD_BAD_UGLY_RESEARCH_MANUSCRIPT.md` | 297–298 | `the upstream / \`scene_splits.json\` (176 trainval / 33 val_unseen / 53 test scenes) / gives the scaling target for full-protocol alignment later.` | `external/VLNTube/splits/scene_splits.json` (named explicitly) | vendored file, upstream commit 2026-04-25 | **ACTIVE** | ✅ **CORRECT — verified exactly** |
| 3 | `docs/research/GOOD_BAD_UGLY_RESEARCH_MANUSCRIPT.md` | 321–322 | `**Limitation:** one held-out scene; upstream-scale scene diversity / (262 scenes) remains future work.` | implicit — same `scene_splits.json` | vendored file, upstream commit 2026-04-25 | **ACTIVE** | ✅ **CORRECT** as a released-asset count (optional clarifying note advised) |
| 4 | `README.md` | 46 | `- 4 local Kujiale/VLNVerse scenes` | local inventory | n/a | **ACTIVE** | ✅ **CORRECT — verified** (`kujiale_0092/0118/0203/0271`) |
| 5 | `assets/experiments/training_ablation/mnv2_ema_20260708/dataset_manifest_scene_holdout.json` | 27 | `all four local scenes are upstream VLNTube trainval scenes (external/VLNTube/splits/scene_splits.json); no upstream test scene exists locally, so the local scene holdout is drawn from our own four scenes` | `external/VLNTube/splits/scene_splits.json` | 2026-07-08 campaign | **HISTORICAL** | ✅ **CORRECT — verified**; freeze, no action |
| 6 | `external/VLNTube/README.md` | 71 | `The pipeline processes only the **176 trainval scenes** by default. Val_unseen (33) and test (53) scenes are automatically skipped.` | upstream vendored file | upstream commit 2026-04-25 | **VENDORED UPSTREAM** | ⛔ **DO NOT MODIFY** — third-party MIT source; verified byte-identical to upstream |

**Only one active claim requires correction: occurrence #1.**

### Not scene-count claims (excluded after inspection)

Numerous `"4 scenes"` strings across `docs/`, `results/` and `benchmarks/` (e.g.
`50 seeds × 4 scenes × 6 conditions`, `5 methods × 4 scenes`, `Per-scene SR/OSR/NE`) refer to the
**four local Kujiale scenes** in our own experiment grid, not to the VLNVerse benchmark's size. They
are correct and out of scope.

---

## 2. Primary-source evidence

All URLs accessed **2026-07-22**.

### 2.1 arXiv:2512.19021 — Lin et al., VLNVerse (PRIMARY, AUTHORITATIVE)

- **URL:** `https://arxiv.org/abs/2512.19021` and full text `https://arxiv.org/html/2512.19021v1`
- **Title:** *VLNVerse: A Benchmark for Vision-Language Navigation with Versatile, Embodied, Realistic Simulation and Evaluation*
- **Authors:** Sihao Lin, Zerui Li, Xunyi Zhao, Gengze Zhou, Liuyi Wang, Rong Wei, Rui Tang, Juncheng Li, Hanqing Wang, Jiangmiao Pang, Anton van den Hengel, Jiajun Liu, Qi Wu
- **Submitted:** 22 December 2025

**Verbatim quotations:**

> **§3.2 (Environment Layer):** "this work introduces a set of 263 large-scale, diverse, and interactive 3D environments"

> **§3.5 (Data Volume & Statistics):** "The scale of the VLNVerse dataset is detailed in Tab. 2. Our benchmark is built upon a total of 263 unique 3D scenes"

> **§3.5 (continued):** "which are exclusively split into training (177 scenes), unseen validation (33 scenes), and test (53 scenes) sets"

> **Introduction:** "we provide 263 large-scale, interactive 3D home environment assets"

**Table 2 (Data Volume) — episode counts, with scene counts in brackets:**

| Task | Episodes | Scenes (training) |
|---|---|---|
| Fine-grained | 3,963 | 177 |
| Coarse-grained | 11,895 | 177 |
| Visual reference | 11,895 | 177 |
| Long horizon | 11,946 | 177 |
| Dialogue | 11,895 | 177 |

**The abstract contains no numeric scene count** — it says only "large-scale, extensible benchmark".
The counts appear in the Introduction, §3.2 and §3.5. **The string "4,000" / "4000" does not appear
as a scene count anywhere in the paper.**

### 2.2 Project page — `https://sihaoevery.github.io/vlnverse/`

- **Accessed:** 2026-07-22
- **Finding:** the page describes the benchmark as "large-scale" and "extensible" and shows benchmark-
  statistics visualisations, but **states no numeric count** of scenes, environments, houses, episodes
  or instructions in its text. It neither confirms nor contradicts either figure.
- **Evidentiary weight:** NEUTRAL. Not a source of the 4,000 figure.

### 2.3 HuggingFace scene dataset — `https://huggingface.co/datasets/Eyz/VLNVerse_scene`

This is the released VLNVerse USD scene asset repository — the dataset `external/VLNTube/README.md`
line 64 instructs users to download as **"Envs | USD scene files"**. It is the strongest available
primary evidence, because it is the *actual artefact* rather than a description of it.

**Dataset-card / viewer surface (verbatim):**

> Total Rows: **4,000** · Total File Size: **312 GB** · Format: **Image folder** ·
> Size Category: **1K - 10K** · Modality: **Image** · Libraries: Datasets, Croissant ·
> Downloads last month: 61,738 · **"No dataset card documentation currently available"**

**API metadata** (`https://huggingface.co/api/datasets/Eyz/VLNVerse_scene`):

```
lastModified: 2026-03-30T15:36:24.000Z
cardData:     null                       <- there is NO dataset card; no scene count is asserted
tags:         ['size_categories:1K<n<10K', 'format:imagefolder', 'modality:image',
               'library:datasets', 'library:mlcroissant', 'region:us']
total files:  98,556
```

**Authoritative enumeration of the actual scene inventory** (paginated tree API,
`https://huggingface.co/api/datasets/Eyz/VLNVerse_scene/tree/main?limit=1000`, single page, complete,
not truncated):

```
total top-level entries : 263
top-level directories   : 262
top-level files         : ['.gitattributes']
  kujiale_NNNN dirs     : 255
  kujiale_NNNN_fix dirs :   7   (kujiale_0123_fix … kujiale_0129_fix)
  other dirs            :   0
scene-id range          : kujiale_0003 … kujiale_0295
file-type breakdown     : 48,553 USD files · 47,627 PNG/JPG image files
```

> ⚠️ **Methodological caution recorded:** the `siblings` field of the HF dataset API is **truncated**
> (it stops at `kujiale_0149`). An enumeration based on `siblings` yields a spurious 129/136. Only the
> **paginated tree endpoint** returns the complete, authoritative listing of 262 scene directories.
> This audit used the latter.

**→ The released VLNVerse scene set contains exactly 262 scene directories.**

---

## 3. Units analysis

The task asked whether the two numbers refer to different units. They do **not** refer to two different
official units of the same benchmark — but the "4,000" figure does have a traceable, non-scene origin.

### 3.1 What each number actually counts

| Number | Unit it actually counts | Source | Authority |
|---|---|---|---|
| **263** | unique 3D **scenes** (= "home environment assets"), split 177 train / 33 val_unseen / 53 test | arXiv:2512.19021 §3.2, §3.5, Introduction | **PRIMARY, AUTHORITATIVE** |
| **262** | released **scene directories** (USD asset bundles) | HF `Eyz/VLNVerse_scene` tree API | **PRIMARY, AUTHORITATIVE** (the artefact itself) |
| **262** | scene **IDs** in the vendored split file | `external/VLNTube/splits/scene_splits.json` (176 + 33 + 53) | **PRIMARY** (vendored upstream) |
| **3,963** | **episodes** in the fine-grained task (training split) | arXiv:2512.19021 Tab. 2 | **PRIMARY** |
| **~51,594** | **episodes** summed across all five tasks | arXiv:2512.19021 Tab. 2 | derived |
| **98,556** | **files** in the HF scene repo (48,553 USD + 47,627 images) | HF API | **PRIMARY** |
| **4,000** | **rows in the HuggingFace dataset-viewer index** of an auto-detected `imagefolder` configuration | HF viewer surface | **NOT a VLNVerse claim** — auto-generated platform metadata |
| **4** | **local** Kujiale scenes present in this repository | local inventory | **PRIMARY (local)** |

### 3.2 Exact 1:1 correspondence — scenes are the same set on both sides

The vendored split file and the released asset repository were compared as **raw ID sets**:

```
HF top-level scene dirs : 262
scene_splits.json IDs   : 262   (trainval 176 + val_unseen 33 + test 53)
IDENTICAL SETS          : True
```

Every one of the 262 IDs matches exactly — including the seven irregular `_fix` IDs
(`kujiale_0123_fix` … `kujiale_0129_fix`), which appear with the `_fix` suffix in **both** the split
file and the asset repository. This rules out any hypothesis that "scenes" and "scene variants" are
being counted differently on the two sides: **the released assets and the official split are the same
262 objects, one directory per scene.**

### 3.3 Where "4,000" almost certainly came from

The HuggingFace page for `Eyz/VLNVerse_scene` displays **"4,000 rows"** and the tag
`size_categories:1K<n<10K`. Both are **platform-derived values computed automatically by HuggingFace**,
not statements from the VLNVerse team — the API confirms `cardData: null`, i.e. *there is no dataset
card at all* and the authors assert nothing on that page.

The repository is auto-detected as `format:imagefolder`, `modality:image`, so the viewer indexes
**image files** (of which there are 47,627), not scenes; the displayed 4,000 is a partial row count
produced under the viewer's 5 GB preview limit against a 312 GB repository.

**Therefore "4,000" is a row count over image files in a dataset-viewer preview — it is not a count of
scenes in any unit.** Reading the HF page's "4,000 rows" as "4,000+ scenes" is the most likely origin
of occurrence #1. *This origin is a well-supported inference, not documented provenance, and is
recorded as such — it does not affect the disposition, which rests on the primary counts.*

### 3.4 The 263 vs 262 residual (one scene) — minor, upstream, disclosed

There is a consistent **one-scene** difference between what the paper states and what was released:

| | Paper (arXiv:2512.19021) | Released artefacts (HF + split file) |
|---|---|---|
| train / trainval | **177** | **176** |
| val_unseen | 33 | 33 |
| test | 53 | 53 |
| **total** | **263** | **262** |

The deficit is entirely in the training split; validation and test match exactly. This is an
**upstream** inconsistency (one stated training scene was not released), not a defect in this
repository, and it is small enough not to disturb the disposition. It should nevertheless be
disclosed rather than smoothed over: the honest formulation is *"263 scenes as reported by Lin et al.;
262 released"*.

### 3.5 Local inventory

`datasets/vlntube/` holds **4** scenes — `kujiale_0092`, `kujiale_0118`, `kujiale_0203`,
`kujiale_0271` — verified from both `datasets/vlntube/envs/` and the distinct scene IDs across the
`train/` and `val/` episode directories. All four are members of the upstream **`trainval`** split
(confirming the existing note in `dataset_manifest_scene_holdout.json`, occurrence #5). No upstream
`test`-split scene is present locally.

`datasets/vlntube/vlntube_index.json` records `"usd_scene_count": 0` and `"usd_scenes": []` — the
local corpus was delivered as pre-generated episode folders, without composed scene USDs. This is
already disclosed honestly in `GOOD_BAD_UGLY_RESEARCH_MANUSCRIPT.md` §"The Ugly".

**The local inventory is 4 scenes — 1.5% of the upstream 262. Nothing in this repository has ever
exercised anything approaching either 263 or 4,000 scenes.**

---

## 4. Disposition and justification

### `263 HOME SCENES VERIFIED`

**Justification, from primary evidence only:**

1. **The 263 figure is directly verified, verbatim, in the primary source.** arXiv:2512.19021 states
   it three independent times — "a total of 263 unique 3D scenes" (§3.5), "a set of 263 large-scale,
   diverse, and interactive 3D environments" (§3.2), and "263 large-scale, interactive 3D home
   environment assets" (Introduction) — with an explicit 177/33/53 split. The word *home* in the
   Introduction confirms these are home scenes.

2. **The figure is corroborated by the artefact itself.** The released HF scene repository enumerates
   to 262 scene directories, and that ID set is **exactly identical** to the 262 IDs in the vendored
   `external/VLNTube/splits/scene_splits.json`. Two independent released artefacts agree with each
   other and sit within one scene of the paper's stated total.

3. **The 4,000 figure has no primary support in any unit.** It appears in **no** VLNVerse primary
   source: not in the paper, not on the project page, and not in any authored dataset card (the HF
   dataset has `cardData: null` — the authors assert nothing there). The only place 4,000 occurs is an
   auto-generated HuggingFace viewer row count over an `imagefolder` index of image files, produced
   under a 5 GB preview limit on a 312 GB repository. A row count of preview images is not a scene
   count.

4. **Why not `4,000+ CLAIM VERIFIED FROM DIFFERENT SCOPE`:** rejected — no scope, split, variant
   expansion, or asset-level aggregation of VLNVerse yields ~4,000 scenes. The nearest genuine
   ~4,000-magnitude quantity in any primary source is **3,963 fine-grained *episodes*** (Tab. 2), which
   is (a) episodes, not scenes, and (b) *below* 4,000, so it cannot support a "4,000+" claim either.

5. **Why not `CLAIMS REFER TO DIFFERENT UNITS`:** rejected — this disposition would require two
   *authored* claims, each true in its own unit. There is no VLNVerse-authored 4,000 claim to
   reconcile; there is one authored claim (263 scenes) and one misreading of auto-generated platform
   metadata. The repository sentence asserts the unit explicitly — "4,000+ **scenes**" — and that
   assertion is false in the unit it names.

6. **Why not `UNRESOLVED — CLAIM SUSPENDED`:** rejected — resolution did not require guessing. The
   primary source was retrieved and quoted verbatim, and the released artefact was independently
   enumerated and shown to match the vendored split file exactly. The evidence is direct and
   mutually corroborating.

---

## 5. Proposed corrections

Presented as proposals only. **No repository file was modified by this audit.**

### 5.1 Occurrence #1 — `docs/paper/FleetSafe_VLN_Paper_Draft.md` line 28 (REQUIRED)

Current:

> **VLNVerse** (Lin et al.): Isaac Sim-based VLN benchmark with 4,000+ scenes, fine/coarse grained tasks, and the IAmGoodNavigator demo runner. FleetSafe-VLN uses VLNVerse as the benchmark reference and IAmGoodNavigator as the demo loader.

Proposed:

> **VLNVerse** (Lin et al., arXiv:2512.19021): Isaac Sim-based VLN benchmark built on 263 unique 3D home scenes (177 train / 33 unseen-val / 53 test; 262 scene directories are released), with fine/coarse grained tasks and the IAmGoodNavigator demo runner. FleetSafe-VLN uses VLNVerse as the benchmark reference and IAmGoodNavigator as the demo loader. This work exercises 4 of these scenes locally.

Rationale: replaces the unsupported figure with the verified one; adds the arXiv ID so the claim is
checkable; discloses the 263/262 residual; and states the local coverage so the reader cannot mistake
the benchmark's scale for ours.

### 5.2 Occurrence #3 — `GOOD_BAD_UGLY_RESEARCH_MANUSCRIPT.md` line 322 (OPTIONAL)

`(262 scenes)` is correct as a released-asset count. Optionally clarify to
`(262 released scenes; 263 reported by Lin et al.)` so it cannot later read as inconsistent with the
corrected paper draft.

### 5.3 Occurrences #2, #4, #5 — NO ACTION

Verified correct.

### 5.4 Occurrence #6 — `external/VLNTube/README.md` line 71 — DO NOT MODIFY

Third-party MIT-licensed vendored source, verified byte-identical to upstream commit
`7ef6afe22014f13fd97a2d4910f84fd6603e17af`. Editing it would silently fork the dependency and
invalidate the content digest recorded in the Section 21 provenance record.

---

## 6. Evidence index

| Source | URL / path | Accessed | Role |
|---|---|---|---|
| VLNVerse paper (abstract) | `https://arxiv.org/abs/2512.19021` | 2026-07-22 | PRIMARY |
| VLNVerse paper (full text) | `https://arxiv.org/html/2512.19021v1` | 2026-07-22 | PRIMARY — source of all verbatim counts |
| VLNVerse project page | `https://sihaoevery.github.io/vlnverse/` | 2026-07-22 | NEUTRAL — no numbers stated |
| HF scene dataset (card/viewer) | `https://huggingface.co/datasets/Eyz/VLNVerse_scene` | 2026-07-22 | PRIMARY — origin of the "4,000 rows" surface |
| HF dataset API | `https://huggingface.co/api/datasets/Eyz/VLNVerse_scene` | 2026-07-22 | PRIMARY — `cardData: null`, 98,556 files |
| HF tree API (paginated) | `.../tree/main?limit=1000` | 2026-07-22 | PRIMARY — authoritative 262-scene enumeration |
| Vendored split file | `/home/favl/robotics/gnm-vlnverse-baseline/external/VLNTube/splits/scene_splits.json` | 2026-07-22 | PRIMARY — 262 IDs, exact match to HF |
| Local scene inventory | `/home/favl/robotics/gnm-vlnverse-baseline/datasets/vlntube/` (+ symlink targets) | 2026-07-22 | PRIMARY (local) — 4 scenes |
| Local index | `/home/favl/robotics/gnm-vlnverse-baseline/datasets/vlntube/vlntube_index.json` | 2026-07-22 | PRIMARY (local) — `usd_scene_count: 0` |
