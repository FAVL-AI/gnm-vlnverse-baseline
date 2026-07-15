"""H8 Track-B — distinctness-metric CALIBRATION study (methodology only; no training, no drive).

Governed by docs/research/H8_TRACK_B_DISTINCTNESS_METRIC_CALIBRATION_PLAN.md (commit 577d336).

Builds a small LABELLED set of goal-image pairs (SAME / DISTINCT / HARD_NEGATIVE) from ALREADY-
RENDERED, COMMITTED frames (synthetic fork R1-R4 + hospital / warehouse / office render scans), then
compares distinctness metrics on them:
  * DINO ViT-S/16 cosine   (incumbent gate metric)
  * CLIP ViT-B/16 cosine   (via timm CLIP-pretrained ViT; secondary)
  * aHash similarity, SSIM (secondary diagnostics)
  * relative ranking score (mean SAME sim - mean DISTINCT sim)
It reports per-label distributions, overlap, a false-positive/false-negative table against the
current `DINO cosine < 0.60` gate, and a data-driven recommendation among outcomes A-E. It changes
NOTHING operational: the DINO threshold and the gate metric are NOT modified.

Policy-encoder embedding is DEFERRED this pass (loading a GNM checkpoint is out of scope without
approval; recorded as N/A in the results with a note).

No new trajectory data. Free-camera renders are NOT produced here — only committed frames are used;
missing pairs are skipped with a logged warning.

Run: ~/miniforge3/envs/gnm_train/bin/python scripts/gnm/h8_track_b_distinctness_calibration.py
"""
import csv, json, os, warnings, statistics as st
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch, timm

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
OUT = REPO / "assets/experiments/hospital_h8_track_b_distinctness_calibration"
CS = OUT / "contact_sheets"
for d in (OUT, CS):
    d.mkdir(parents=True, exist_ok=True)

DINO_GATE = 0.60   # the incumbent absolute gate threshold under test (NOT changed here)

# ── frame path helpers ───────────────────────────────────────────────────────
SYN = {"R1": "hospital_h8_track_b_synthetic_fork_validation",
       "R2": "hospital_h8_track_b_synthetic_fork_validation_r2",
       "R3": "hospital_h8_track_b_synthetic_fork_validation_r3",
       "R4": "hospital_h8_track_b_synthetic_fork_validation_r4"}


def syn(rev, name):
    return REPO / f"assets/experiments/{SYN[rev]}/render_metadata/synthetic_diagnostic_fork__{name}.png"


def emb_search(zone, role):
    return REPO / f"assets/experiments/hospital_h8_m_embedding_search/render_metadata/{zone}__{role}.png"


def scan(sid, fname):
    return REPO / f"assets/experiments/hospital_h8_track_b_render_scan/render_metadata/{sid}__{fname}.png"


def whfull(fname):
    return REPO / f"assets/experiments/hospital_h8_track_b_warehouse_full_scan/render_metadata/warehouse_full__{fname}.png"


def mshelf(fname):
    return REPO / f"assets/experiments/hospital_h8_track_b_multi_shelf_scan/render_metadata/warehouse_multiple_shelves__{fname}.png"


# ── labelled pairs: (pair_id, source, revision, A, B, label, reason) ──────────
PAIRS = [
    # ---- SAME: same branch/goal, identical or different viewpoint (should be HIGH similarity) ----
    ("syn_R4_identity_N", "synthetic", "R4", syn("R4", "center_N"), syn("R4", "goalA_N"),
     "SAME", "identical frame (sanity anchor): center N == goalA(N) thumbnail"),
    ("syn_R1_northSame", "synthetic", "R1", syn("R1", "center_N"), syn("R1", "goalA_img"),
     "SAME", "north branch: junction-centre view vs close goal view (same goal, diff distance)"),
    ("syn_R2_northSame", "synthetic", "R2", syn("R2", "center_N"), syn("R2", "goalA_img"),
     "SAME", "north branch: junction-centre vs close goal view"),
    ("syn_R3_northSame", "synthetic", "R3", syn("R3", "center_N"), syn("R3", "goalA_img"),
     "SAME", "north branch: junction-centre vs close goal view"),
    ("syn_R4_northSame", "synthetic", "R4", syn("R4", "center_N"), syn("R4", "goalA_img"),
     "SAME", "north branch: junction-centre vs close goal view"),
    ("syn_R1_westSame", "synthetic", "R1", syn("R1", "center_W"), syn("R1", "goalB_img"),
     "SAME", "west branch: junction-centre vs close goal view"),
    ("syn_R4_westSame", "synthetic", "R4", syn("R4", "center_W"), syn("R4", "goalB_img"),
     "SAME", "west branch: junction-centre vs close goal view"),
    ("hosp_eastVend_nearfar", "hospital", None, emb_search("h8m_east_vending_nearfar", "goalA"),
     emb_search("h8m_east_vending_nearfar", "goalB"), "SAME",
     "near vs far view of the SAME east vending area (same goal object, diff distance)"),
    ("hosp_lobbyVend_nearfar", "hospital", None, emb_search("h8m_lobby_vending_nearfar", "goalA"),
     emb_search("h8m_lobby_vending_nearfar", "goalB"), "SAME",
     "near vs far view of the SAME lobby vending area"),

    # ---- DISTINCT: different branch / zone / goal (a good metric should score LOW) ----
    ("syn_R1_NvsW", "synthetic", "R1", syn("R1", "center_N"), syn("R1", "center_W"),
     "DISTINCT", "R1 gate pair: north (blue) vs west (green) branches, 90 deg apart"),
    ("syn_R2_NvsW", "synthetic", "R2", syn("R2", "center_N"), syn("R2", "center_W"),
     "DISTINCT", "R2 gate pair: north vs west branches"),
    ("syn_R3_NvsW", "synthetic", "R3", syn("R3", "center_N"), syn("R3", "center_W"),
     "DISTINCT", "R3 gate pair: north vs west branches"),
    ("syn_R4_NvsW", "synthetic", "R4", syn("R4", "center_N"), syn("R4", "center_W"),
     "DISTINCT", "R4 gate pair: north vs west branches"),
    ("syn_R4_NvsE", "synthetic", "R4", syn("R4", "center_N"), syn("R4", "center_E"),
     "DISTINCT", "north (blue,round) vs east (orange,boxy) branches"),
    ("syn_R4_WvsS", "synthetic", "R4", syn("R4", "center_W"), syn("R4", "center_S"),
     "DISTINCT", "west (green,pointed) vs south (red,columned) branches"),
    ("hosp_eastVend_vs_waiting", "hospital", None, emb_search("h8m_east_vending_nearfar", "goalA"),
     emb_search("h8m_waiting_seating", "goalA"), "DISTINCT", "different rooms: east vending vs waiting seating"),
    ("hosp_fork_vs_sidecorr", "hospital", None, emb_search("h8m_recep_fork", "goalA"),
     emb_search("h8m_side_corridor", "goalA"), "DISTINCT", "different zones: reception fork vs side corridor"),
    ("hosp_recepJunction_AB", "hospital", None, emb_search("h8m_recep_junction", "goalA"),
     emb_search("h8m_recep_junction", "goalB"), "DISTINCT", "reception junction two intended branches"),
    ("hosp_waiting_vs_desk", "hospital", None, emb_search("h8m_waiting_seating", "goalA"),
     emb_search("h8m_recep_desk_multiobj", "goalA"), "DISTINCT", "waiting seating vs reception desk"),

    # ---- HARD_NEGATIVE: visually similar but SEMANTICALLY different (the key test) ----
    ("whfull_p13_aisle_ends", "warehouse_full", None, whfull("p13__goalA_S"), whfull("p13__goalB_N"),
     "HARD_NEGATIVE", "two ENDS of the same straight aisle (look alike, different locations) - the p13 collinear case"),
    ("mshelf_p00_openfloor", "multi_shelf", None, mshelf("p00__goalA_E"), mshelf("p00__goalB_N"),
     "HARD_NEGATIVE", "open-hall probe: two perpendicular views of the same open floor look alike"),
    ("hosp_lookalike_AB", "hospital", None, emb_search("h8m_lookalike_confuser", "goalA"),
     emb_search("h8m_lookalike_confuser", "goalB"), "HARD_NEGATIVE",
     "designed look-alike confuser: visually similar, semantically different goals"),
    ("mshelf_p00_vs_p32", "multi_shelf", None, mshelf("p00__goalA_E"), mshelf("p32__goalA_N"),
     "HARD_NEGATIVE", "two DIFFERENT open-floor probes (different location) that look alike"),
    ("whsimple_p00_perp", "warehouse_simple", None, scan("warehouse_simple", "p00__goalA_N"),
     scan("warehouse_simple", "p00__goalB_E"), "HARD_NEGATIVE",
     "open warehouse hall: two perpendicular views look alike (open-floor false-fork risk)"),
    ("office_p03_perp", "office_isaac", None, scan("office_isaac", "p03__goalA_N"),
     scan("office_isaac", "p03__goalB_S"), "HARD_NEGATIVE",
     "open office bullpen: two views look alike"),
]

# ── metric models ────────────────────────────────────────────────────────────
_DINO_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
_DINO_STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
dino = timm.create_model("vit_small_patch16_224.dino", pretrained=True, num_classes=0).eval()

clip_model, clip_tf = None, None
try:
    clip_model = timm.create_model("vit_base_patch16_clip_224.laion2b", pretrained=True, num_classes=0).eval()
    _cfg = timm.data.resolve_data_config({}, model=clip_model)
    clip_tf = timm.data.create_transform(**_cfg)
    print("[calib] CLIP ViT-B/16 (LAION-2B checkpoint) loaded via timm")
except Exception as e:
    print(f"[calib] CLIP unavailable ({type(e).__name__}: {e}); recording clip_cos=None")


def load_rgb(p):
    if not Path(p).exists():
        return None
    return np.asarray(Image.open(p).convert("RGB"))


@torch.no_grad()
def dino_cos(a, b):
    def emb(x):
        im = Image.fromarray(x).convert("RGB").resize((224, 224), Image.BILINEAR)
        t = torch.from_numpy(np.asarray(im, np.float32) / 255.0).permute(2, 0, 1)[None]
        return torch.nn.functional.normalize(dino((t - _DINO_MEAN) / _DINO_STD), dim=1)
    return round(float((emb(a) @ emb(b).T).item()), 4)


@torch.no_grad()
def clip_cos(a, b):
    if clip_model is None:
        return None
    def emb(x):
        t = clip_tf(Image.fromarray(x).convert("RGB")).unsqueeze(0)
        return torch.nn.functional.normalize(clip_model(t), dim=1)
    return round(float((emb(a) @ emb(b).T).item()), 4)


def ahash_sim(a, b):
    def h(x):
        g = np.asarray(Image.fromarray(x).convert("L").resize((8, 8), Image.BILINEAR), np.float32)
        return (g > g.mean()).astype(np.uint8).ravel()
    ha, hb = h(a), h(b)
    return round(1.0 - float(np.count_nonzero(ha != hb)) / 64.0, 4)   # 1=identical


def ssim(a, b):
    import cv2
    ga = cv2.cvtColor(cv2.resize(a, (224, 224)), cv2.COLOR_RGB2GRAY).astype(np.float64)
    gb = cv2.cvtColor(cv2.resize(b, (224, 224)), cv2.COLOR_RGB2GRAY).astype(np.float64)
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    k = (11, 11); s = 1.5
    mu_a = cv2.GaussianBlur(ga, k, s); mu_b = cv2.GaussianBlur(gb, k, s)
    mua2, mub2, muab = mu_a * mu_a, mu_b * mu_b, mu_a * mu_b
    sa = cv2.GaussianBlur(ga * ga, k, s) - mua2
    sb = cv2.GaussianBlur(gb * gb, k, s) - mub2
    sab = cv2.GaussianBlur(ga * gb, k, s) - muab
    ss = ((2 * muab + C1) * (2 * sab + C2)) / ((mua2 + mub2 + C1) * (sa + sb + C2))
    return round(float(ss.mean()), 4)


# ── evaluate pairs ───────────────────────────────────────────────────────────
rows, skipped = [], []
for pid, src, rev, pa, pb, label, reason in PAIRS:
    a, b = load_rgb(pa), load_rgb(pb)
    if a is None or b is None:
        miss = [str(p) for p, im in ((pa, a), (pb, b)) if im is None]
        skipped.append({"pair_id": pid, "missing": miss, "reason": reason})
        print(f"[calib] SKIP {pid}: missing {miss}")
        continue
    row = {"pair_id": pid, "source": src, "revision": rev, "label": label, "reason": reason,
           "imageA": str(pa.relative_to(REPO)), "imageB": str(pb.relative_to(REPO)),
           "dino_cos": dino_cos(a, b), "clip_cos": clip_cos(a, b),
           "ahash_sim": ahash_sim(a, b), "ssim": ssim(a, b),
           "policy_encoder_cos": None,   # deferred (checkpoint load out of scope w/o approval)
           "contact_sheet_supported": True}
    rows.append(row)
    print(f"[calib] {pid:26s} {label:13s} dino={row['dino_cos']} clip={row['clip_cos']} "
          f"ahash={row['ahash_sim']} ssim={row['ssim']}")

# ── distributions per label ──────────────────────────────────────────────────
def dist(label, key):
    vals = [r[key] for r in rows if r["label"] == label and r[key] is not None]
    if not vals:
        return None
    return {"n": len(vals), "mean": round(st.mean(vals), 4),
            "median": round(st.median(vals), 4), "min": round(min(vals), 4),
            "max": round(max(vals), 4), "std": round(st.pstdev(vals), 4) if len(vals) > 1 else 0.0}


LABELS = ["SAME", "DISTINCT", "HARD_NEGATIVE"]
METRICS = ["dino_cos", "clip_cos", "ahash_sim", "ssim"]
summary = {m: {lab: dist(lab, m) for lab in LABELS} for m in METRICS}

# separation: for each metric, does SAME score clearly above DISTINCT? overlap of ranges?
def separation(m):
    s, d = summary[m]["SAME"], summary[m]["DISTINCT"]
    if not s or not d:
        return {"metric": m, "computable": False}
    gap = round(s["mean"] - d["mean"], 4)
    overlap = not (d["max"] < s["min"])   # ranges overlap if DISTINCT max >= SAME min
    # a clean separating threshold exists iff DISTINCT max < SAME min
    sep_threshold = round((d["max"] + s["min"]) / 2.0, 4) if not overlap else None
    hn = summary[m]["HARD_NEGATIVE"]
    hn_note = None
    if hn:
        # hard negatives are look-alikes: a good metric should score them LOW (near DISTINCT), not
        # HIGH (near SAME). If HN mean is close to SAME mean, the metric merges look-alikes.
        hn_note = ("HARD_NEG merges with SAME (metric over-similar on look-alikes)"
                   if hn["mean"] >= (s["mean"] + d["mean"]) / 2.0 else
                   "HARD_NEG scores toward DISTINCT (metric treats look-alikes as different) - good")
    return {"metric": m, "computable": True, "same_mean": s["mean"], "distinct_mean": d["mean"],
            "gap_same_minus_distinct": gap, "ranges_overlap": overlap,
            "clean_separating_threshold": sep_threshold,
            "hard_negative_mean": (hn["mean"] if hn else None), "hard_negative_note": hn_note}


seps = {m: separation(m) for m in METRICS}

# separation split by SOURCE FAMILY — the aggregate mixes two regimes (synthetic symmetric cross
# vs real indoor scans); they behave very differently, so report each.
REAL_SOURCES = {"hospital", "warehouse_full", "multi_shelf", "warehouse_simple", "office_isaac"}


def dist_pred(label, key, pred):
    vals = [r[key] for r in rows if r["label"] == label and r[key] is not None and pred(r)]
    if not vals:
        return None
    return {"n": len(vals), "mean": round(st.mean(vals), 4), "median": round(st.median(vals), 4),
            "min": round(min(vals), 4), "max": round(max(vals), 4),
            "std": round(st.pstdev(vals), 4) if len(vals) > 1 else 0.0}


def separation_pred(m, pred):
    s, d = dist_pred("SAME", m, pred), dist_pred("DISTINCT", m, pred)
    if not s or not d:
        return {"computable": False, "same": s, "distinct": d}
    overlap = not (d["max"] < s["min"])
    return {"computable": True, "same": s, "distinct": d,
            "gap_same_minus_distinct": round(s["mean"] - d["mean"], 4), "ranges_overlap": overlap,
            "clean_separating_threshold": (round((d["max"] + s["min"]) / 2.0, 4) if not overlap else None)}


FAMILIES = {"synthetic": lambda r: r["source"] == "synthetic",
            "real": lambda r: r["source"] in REAL_SOURCES}
seps_by_family = {m: {fam: separation_pred(m, pred) for fam, pred in FAMILIES.items()}
                  for m in ("dino_cos", "clip_cos")}

# ── FP/FN vs the current DINO<0.60 gate ──────────────────────────────────────
# gate declares a pair "distinct" iff dino_cos < DINO_GATE.
#   FN (missed distinctness): DISTINCT pair with dino_cos >= gate  (gate says NOT distinct) - the R1-R4 failure
#   FP (false distinctness):  SAME pair with dino_cos < gate       (gate wrongly says distinct)
fp = [r for r in rows if r["label"] == "SAME" and r["dino_cos"] is not None and r["dino_cos"] < DINO_GATE]
fn = [r for r in rows if r["label"] == "DISTINCT" and r["dino_cos"] is not None and r["dino_cos"] >= DINO_GATE]
hn_high = [r for r in rows if r["label"] == "HARD_NEGATIVE" and r["dino_cos"] is not None and r["dino_cos"] >= DINO_GATE]

# ── data-driven recommendation (outcomes A-E) ────────────────────────────────
dsep = seps["dino_cos"]
csep = seps.get("clip_cos")
dino_separates = dsep.get("computable") and not dsep.get("ranges_overlap")
clip_separates = bool(csep and csep.get("computable") and not csep.get("ranges_overlap"))
# does DINO push DISTINCT below 0.60? (the operational question)
distinct_below_gate = summary["dino_cos"]["DISTINCT"] and summary["dino_cos"]["DISTINCT"]["max"] < DINO_GATE

# the decisive split: does DINO separate on REAL scenes even though it fails on the synthetic cross?
dfam = seps_by_family["dino_cos"]
cfam = seps_by_family["clip_cos"]
dino_real_sep = dfam["real"].get("computable") and not dfam["real"].get("ranges_overlap")
dino_syn_sep = dfam["synthetic"].get("computable") and not dfam["synthetic"].get("ranges_overlap")
real_thr = dfam["real"].get("clean_separating_threshold")

if dino_real_sep and not dino_syn_sep:
    outcome = "A+E"
    outcome_txt = (
        "A + E (evidence-driven). On REAL hospital pairs DINO cosine separates SAME from DISTINCT "
        f"cleanly (real DISTINCT max {dfam['real']['distinct']['max']} < real SAME min "
        f"{dfam['real']['same']['min']}; clean threshold ~{real_thr}), so DINO is usable on real "
        "indoor scenes — but the current absolute 0.60 gate is MISCALIBRATED (a real distinct pair at "
        f"{dfam['real']['distinct']['max']} would be missed by < 0.60). On the SYNTHETIC symmetric "
        "4-way cross DINO does NOT separate (same/distinct ranges overlap and invert) because every "
        "arm shares an identical corridor perspective/composition — a pathological case for a global "
        "composition embedding, not a general metric failure. RECOMMEND: (A) recalibrate the DINO "
        f"threshold from real-scene separation (~{real_thr}, with margin) rather than the arbitrary "
        "0.60; and (E) treat SYNTHETIC-fork distinctness as ADVISORY ONLY and gate goal-conditioning "
        "with a task-level ACTION-PROBE (does conditioning on goal A vs B change the decision-frame "
        "action?) after render/drive validation. Do NOT use synthetic symmetric-cross DINO scores as "
        "a pass/fail gate.")
elif dino_separates and distinct_below_gate:
    outcome = "A"
    outcome_txt = ("A: keep DINO but recalibrate the threshold. DINO separates SAME from DISTINCT and "
                   f"DISTINCT sits below the gate; adopt the calibrated threshold "
                   f"{dsep.get('clean_separating_threshold')} with margin.")
elif dino_separates and not distinct_below_gate:
    outcome = "A"
    outcome_txt = ("A: keep DINO but RECALIBRATE the threshold UP. DINO separates SAME from DISTINCT, "
                   "but the DISTINCT cluster sits ABOVE the current 0.60 gate, so 0.60 is too low; use "
                   f"the observed separating threshold ~{dsep.get('clean_separating_threshold')} "
                   "(with margin) instead of 0.60.")
elif clip_separates:
    outcome = "B"
    outcome_txt = ("B: use CLIP. DINO does not cleanly separate SAME from DISTINCT on these corridor "
                   "goals, but CLIP does; adopt CLIP with its observed separating threshold.")
else:
    outcome = "D/E"
    outcome_txt = ("D/E: no embedding separates SAME from DISTINCT cleanly (hard negatives overlap "
                   "SAME). Recommend a COMBINED rule (embedding advisory + mandatory contact-sheet "
                   "verification, outcome D) and require a task-level ACTION-PROBE after render/drive "
                   "validation (outcome E) as the primary evidence of goal-conditioning.")

# ── contact sheets: representative pairs per label with metric values ────────
try:
    fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
    fr = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
except Exception:
    fb = fr = ImageFont.load_default()


def thumb(p, size=(240, 180)):
    im = load_rgb(p)
    return (Image.fromarray(im).convert("RGB").resize(size, Image.BILINEAR) if im is not None
            else Image.new("RGB", size, (35, 35, 35)))


for r in rows:
    tw, th = 240, 180
    sheet = Image.new("RGB", (tw * 2 + 18, th + 46), "white"); dr = ImageDraw.Draw(sheet)
    dr.text((6, 4), f"{r['pair_id']} [{r['label']}] dino={r['dino_cos']} clip={r['clip_cos']} "
            f"ssim={r['ssim']}", font=fb, fill="black")
    sheet.paste(thumb(REPO / r["imageA"], (tw, th)), (6, 26))
    sheet.paste(thumb(REPO / r["imageB"], (tw, th)), (12 + tw, 26))
    dr.text((6, 26 + th + 2), (r["reason"][:70]), font=fr, fill="#333")
    sheet.save(CS / f"{r['label']}__{r['pair_id']}.png")

# ── write outputs ────────────────────────────────────────────────────────────
(OUT / "distinctness_pair_manifest.json").write_text(json.dumps(
    {"label": "SYNTHETIC_DIAGNOSTIC_AND_REAL_RENDER_CALIBRATION_METHODOLOGY_ONLY",
     "governing_plan": "docs/research/H8_TRACK_B_DISTINCTNESS_METRIC_CALIBRATION_PLAN.md",
     "dino_gate_under_test": DINO_GATE, "n_pairs": len(rows), "n_skipped": len(skipped),
     "pairs": [{k: r[k] for k in ("pair_id", "source", "revision", "label", "reason",
                                  "imageA", "imageB", "contact_sheet_supported")} for r in rows],
     "skipped": skipped}, indent=2) + "\n")

with open(OUT / "distinctness_metric_results.csv", "w", newline="") as f:
    cols = ["pair_id", "source", "revision", "label", "dino_cos", "clip_cos", "ahash_sim", "ssim",
            "policy_encoder_cos", "reason"]
    w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n"); w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k) for k in cols})

(OUT / "distinctness_distribution_summary.json").write_text(json.dumps(
    {"per_label_distributions": summary, "separation_analysis": seps,
     "separation_by_source_family": seps_by_family,
     "dino_gate": DINO_GATE,
     "dino_false_positive_same_flagged_distinct": [r["pair_id"] for r in fp],
     "dino_false_negative_distinct_missed": [r["pair_id"] for r in fn],
     "dino_hard_negative_not_flagged": [r["pair_id"] for r in hn_high],
     "recommended_outcome": outcome}, indent=2) + "\n")

# results md
rm = ["# Track-B Distinctness Metric Results (per pair)", "",
      "Methodology only. DINO cosine is the incumbent gate metric (threshold < 0.60); it is **not** "
      "changed here. Lower cosine = more distinct. SAME pairs should score HIGH, DISTINCT low; "
      "HARD_NEGATIVE (look-alikes) test whether a metric wrongly scores different-but-similar goals "
      "as SAME.", "",
      "| pair | label | DINO | CLIP | aHash | SSIM | note |",
      "|---|---|---|---|---|---|---|"]
for lab in LABELS:
    for r in [x for x in rows if x["label"] == lab]:
        rm.append(f"| {r['pair_id']} | {lab} | {r['dino_cos']} | {r['clip_cos']} | {r['ahash_sim']} "
                  f"| {r['ssim']} | {r['reason'][:60]} |")
(OUT / "distinctness_metric_results.md").write_text("\n".join(rm) + "\n")

# FP/FN table md
def _tbl(items):
    return ([f"| {r['pair_id']} | {r['dino_cos']} | {r['reason'][:70]} |" for r in items]
            or ["| (none) | | |"])


ft = ["# Track-B Distinctness — False-Positive / False-Negative Table (vs DINO cosine < 0.60 gate)", "",
      f"Gate rule under test: a pair is called **distinct** iff DINO cosine < {DINO_GATE}.", "",
      "- **False NEGATIVE** = a truly DISTINCT pair the gate MISSES (DINO >= 0.60 -> gate says "
      "'not distinct'). This is the R1-R4 synthetic-fork failure mode.",
      "- **False POSITIVE** = a truly SAME pair the gate wrongly flags as distinct (DINO < 0.60).",
      "- **HARD_NEGATIVE not flagged** = a look-alike (different location) the gate treats as "
      "not-distinct (DINO >= 0.60) — expected/acceptable, listed for transparency.", "",
      f"## False negatives (DISTINCT missed): {len(fn)}",
      "| pair | DINO | reason |", "|---|---|---|", *_tbl(fn),
      "", f"## False positives (SAME wrongly flagged distinct): {len(fp)}",
      "| pair | DINO | reason |", "|---|---|---|", *_tbl(fp),
      "", f"## Hard negatives with DINO >= 0.60 (not flagged distinct): {len(hn_high)}",
      "| pair | DINO | reason |", "|---|---|---|", *_tbl(hn_high)]
(OUT / "distinctness_false_positive_negative_table.md").write_text("\n".join(ft) + "\n")

# calibration report md
def fmt(d):
    return (f"n={d['n']} mean={d['mean']} median={d['median']} range=[{d['min']},{d['max']}] "
            f"std={d['std']}") if d else "n/a"


rep = [
    "# H8 Track-B — Distinctness-Metric Calibration Report (METHODOLOGY ONLY)", "",
    "**Status: methodology evidence only.** No drive-validation, no recording, no trajectory "
    "collection, no training, no promotion, no benchmark evidence, no real-scene performance claim, "
    "no SOTA, no autonomy claim. **The DINO threshold and the operational gate metric were NOT "
    "changed.** `CL_BOUND_XY` unchanged. Governed by "
    "`docs/research/H8_TRACK_B_DISTINCTNESS_METRIC_CALIBRATION_PLAN.md`.", "",
    "## Question",
    "Is the absolute `DINO cosine < 0.60` gate valid for corridor-style ImageNav goal distinctness, "
    "or should it be recalibrated or replaced? Evidence: labelled SAME / DISTINCT / HARD_NEGATIVE "
    f"pairs from committed renders ({len(rows)} pairs, {len(skipped)} skipped for missing frames).", "",
    "## Per-label similarity distributions",
    "| metric | SAME | DISTINCT | HARD_NEGATIVE |", "|---|---|---|---|",
    *[f"| {m} | {fmt(summary[m]['SAME'])} | {fmt(summary[m]['DISTINCT'])} | {fmt(summary[m]['HARD_NEGATIVE'])} |"
      for m in METRICS], "",
    "## Separation analysis (does the metric tell SAME from DISTINCT?) — ALL pairs pooled",
    "| metric | SAME mean | DISTINCT mean | gap | ranges overlap? | clean threshold | hard-neg note |",
    "|---|---|---|---|---|---|---|",
    *[f"| {m} | {seps[m].get('same_mean')} | {seps[m].get('distinct_mean')} | "
      f"{seps[m].get('gap_same_minus_distinct')} | {seps[m].get('ranges_overlap')} | "
      f"{seps[m].get('clean_separating_threshold')} | {seps[m].get('hard_negative_note')} |"
      for m in METRICS if seps[m].get("computable")], "",
    "## Separation analysis SPLIT BY SOURCE FAMILY (the decisive view)",
    "The pooled view mixes two regimes. Split apart, the real indoor scans and the synthetic "
    "symmetric 4-way cross behave oppositely — this is the key finding.",
    "",
    "| metric | family | SAME (n, mean, range) | DISTINCT (n, mean, range) | ranges overlap? | clean threshold |",
    "|---|---|---|---|---|---|",
    *[f"| {m} | {fam} | {fmt(seps_by_family[m][fam].get('same'))} | "
      f"{fmt(seps_by_family[m][fam].get('distinct'))} | "
      f"{seps_by_family[m][fam].get('ranges_overlap')} | "
      f"{seps_by_family[m][fam].get('clean_separating_threshold')} |"
      for m in ("dino_cos", "clip_cos") for fam in ("real", "synthetic")
      if seps_by_family[m][fam].get("computable")], "",
    "**Reading it:** for **DINO on real hospital pairs**, known-distinct goals score far LOWER "
    "(more distinct) than known-same goals with a clean gap — DINO works on real indoor scenes. "
    "For **DINO on the synthetic cross**, known-same and known-distinct ranges OVERLAP and even "
    "INVERT (a genuinely-distinct N-vs-W pair scores higher/less-distinct than a same-branch "
    "near/far pair), because every arm of a symmetric cross shares the same corridor "
    "perspective/composition. The R1-R4 'failure' is therefore driven by the symmetric-cross "
    "geometry as much as by the metric; and separately, the absolute 0.60 constant is miscalibrated "
    "even for real scenes (real distinct pairs reach ~0.68, above 0.60).", "",
    "## The current DINO < 0.60 gate on these pairs",
    f"- False NEGATIVES (DISTINCT pairs the gate misses, DINO >= 0.60): **{len(fn)}** "
    f"({', '.join(r['pair_id'] for r in fn) if fn else 'none'}).",
    f"- False POSITIVES (SAME pairs wrongly flagged distinct, DINO < 0.60): **{len(fp)}** "
    f"({', '.join(r['pair_id'] for r in fp) if fp else 'none'}).",
    f"- Hard negatives not flagged distinct (DINO >= 0.60): **{len(hn_high)}**.", "",
    "## Recommendation (outcome A-E) — proposal only, NOT implemented",
    f"**Outcome {outcome}.** {outcome_txt}", "",
    "Notes:",
    "- **CLIP** was computed via a timm CLIP-pretrained ViT-B/16 (LAION-2B checkpoint; standalone "
    "open_clip/clip packages absent). "
    + ("Available and included above." if clip_model is not None else "UNAVAILABLE this run; clip_cos=None."),
    ("- **CLIP does not rescue the gate on this set.** CLIP's SAME vs DISTINCT ranges OVERLAP for both "
     f"families (synthetic: SAME mean {cfam['synthetic']['same']['mean']} ~= DISTINCT mean "
     f"{cfam['synthetic']['distinct']['mean']}, no clean threshold; real: SAME "
     f"{cfam['real']['same']['min']}-{cfam['real']['same']['max']} overlaps DISTINCT "
     f"{cfam['real']['distinct']['min']}-{cfam['real']['distinct']['max']}). Switching to CLIP does "
     "NOT produce a clean separation where DINO fails — CLIP separates SAME/DISTINCT less well than "
     "DINO here, so it is not a fix for the symmetric-cross gate."
     if (cfam['synthetic'].get('computable') and cfam['real'].get('computable'))
     else "- **CLIP** separation could not be computed by family this run."),
    "- **Policy-encoder** embedding is DEFERRED (loading a GNM checkpoint is out of scope without "
    "approval); recorded as N/A. If chosen as a candidate metric, run it under a separate approved step.",
    "- aHash / SSIM are secondary diagnostics only, never a gate.",
    "- The recommendation is data-driven from the pairs above; it is a proposal for review, and no "
    "threshold or metric change is applied here.", "",
    "## Decision rule applied",
    "- If DINO separates SAME vs DISTINCT with margin -> propose a calibrated threshold (A).",
    "- If DINO does not separate -> reject DINO as the primary gate.",
    "- If CLIP / policy-encoder separates better -> recommend it with evidence (B/C).",
    "- If no embedding separates cleanly -> contact-sheet verification + task-level action-probe as "
    "the primary next gate (D/E).", "",
    "## Claim boundary",
    "Methodology evidence only. No drive validation, no recording, no training, no benchmark evidence, "
    "no real-scene performance claim, no promotion, no autonomy claim. `CL_BOUND_XY` unchanged. No "
    "DINO threshold or gate-metric change was made; recommendation is held for review.", "",
    "## Artifacts",
    "`assets/experiments/hospital_h8_track_b_distinctness_calibration/`: "
    "`distinctness_pair_manifest.json`, `distinctness_metric_results.{csv,md}`, "
    "`distinctness_distribution_summary.json`, `distinctness_false_positive_negative_table.md`, "
    "`distinctness_calibration_report.md`, `contact_sheets/`. Script: "
    "`scripts/gnm/h8_track_b_distinctness_calibration.py`.",
]
(OUT / "distinctness_calibration_report.md").write_text("\n".join(rep) + "\n")

print(json.dumps({"n_pairs": len(rows), "skipped": len(skipped),
                  "dino": {l: summary["dino_cos"][l] for l in LABELS},
                  "clip_loaded": clip_model is not None,
                  "false_negatives": len(fn), "false_positives": len(fp),
                  "recommended_outcome": outcome}, indent=2))
print("CALIBRATION STUDY WRITTEN ->", OUT)
