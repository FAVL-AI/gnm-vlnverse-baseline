#!/usr/bin/env python3
"""Corrected H6 professor PPTX. Separates (A) the procedural --scene stage
route-family DIAGNOSTIC (metrics, scene-agnostic) from (B) the real Isaac 5.1
hospital.usd TARGET-SCENE visuals, with an explicit up-front correction slide.
Plain white background, black text. Section B images are the newly-rendered
hospital contact sheets — labelled as target-scene evidence, NOT H6 training data.
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pathlib import Path

HOSP = Path("/home/favl/robotics/gnm-vlnverse-baseline/assets/experiments/"
            "hospital_h2_collection_20260709/hospital_render_exports")
OUT = "/home/favl/Desktop/H6_Professor_Update_Corrected.pptx"
BLACK, WHITE = RGBColor(0, 0, 0), RGBColor(0xFF, 0xFF, 0xFF)
AMBER = RGBColor(0x9A, 0x5A, 0x00)
FONT = "Arial"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def slide():
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid(); s.background.fill.fore_color.rgb = WHITE
    return s


def box(s, l, t, w, h):
    tf = s.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h)).text_frame
    tf.word_wrap = True
    return tf


def title(s, text, sz=30):
    tf = box(s, 0.6, 0.32, 12.1, 0.9)
    r = tf.paragraphs[0].add_run(); r.text = text
    r.font.size = Pt(sz); r.font.bold = True; r.font.name = FONT; r.font.color.rgb = BLACK


def tag(s, text, color=BLACK):
    tf = box(s, 0.62, 1.18, 12.1, 0.4)
    r = tf.paragraphs[0].add_run(); r.text = text
    r.font.size = Pt(15); r.font.bold = True; r.font.name = FONT; r.font.color.rgb = color


def body(s, lines, top=1.5, sz=18, left=0.8, width=11.9, height=5.6):
    tf = box(s, left, top, width, height)
    for i, (txt, lvl, bold) in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.level = lvl
        r = p.add_run(); r.text = ("• " if lvl == 0 else "– ") + txt
        r.font.size = Pt(sz - lvl * 2); r.font.name = FONT; r.font.bold = bold
        r.font.color.rgb = BLACK; p.space_after = Pt(6)


def mono(s, text, top, sz=16, left=0.8, width=11.9, height=3.0):
    tf = box(s, left, top, width, height)
    for i, ln in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run(); r.text = ln
        r.font.size = Pt(sz); r.font.name = "Consolas"; r.font.color.rgb = BLACK


def caption(s, text, top, sz=14, color=BLACK, bold=True):
    tf = box(s, 0.8, top, 11.7, 0.34)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = text
    r.font.size = Pt(sz); r.font.bold = bold; r.font.name = FONT; r.font.color.rgb = color


def pic(s, name, top, width):
    left = (13.333 - width) / 2
    s.shapes.add_picture(str(HOSP / name), Inches(left), Inches(top), width=Inches(width))


# 1 — Title
s = slide()
title(s, "H6 Hard-Route Coverage Diagnostic", 34)
body(s, [
    ("Camera-only Image-goal Navigation (ImageNav), Isaac Sim.", 0, False),
    ("This deck has two separate parts:", 0, True),
    ("(A) route-family coverage DIAGNOSTIC — quantitative, collected in the procedural "
     "--scene stage; scene-agnostic.", 1, False),
    ("(B) hospital TARGET-SCENE visuals — newly rendered from the real Isaac 5.1 "
     "hospital.usd; direction for the next run, not training data.", 1, False),
    ("Frank Asante Van Laarhoven  ·  13 July 2026  ·  prepared for Prof. Bo Wei", 0, False),
    ("Diagnostic evidence — NOT a promoted model. Incumbent retained.", 0, True),
], top=1.9, sz=18)

# 2 — Correction notice
s = slide()
title(s, "Correction: scene of record vs. target scene")
tag(s, "Please read before the visuals — this corrects the earlier deck.", AMBER)
body(s, [
    ("The earlier deck's frames were rendered in the bring-up DEFAULT procedural stage "
     "(--scene stage): a grey floor with a few coloured-block landmarks — NOT the Isaac "
     "hospital asset. Those images are withdrawn as hospital evidence.", 0, True),
    ("The H6 QUANTITATIVE result is unaffected: it is a route-family coverage diagnostic "
     "over trajectory geometry (u-turn, chain, etc.), which is scene-agnostic. No metric "
     "changes.", 0, False),
    ("This deck therefore separates:", 0, True),
    ("(A) the procedural-stage diagnostic METRICS (next 4 slides), from", 1, False),
    ("(B) newly-rendered REAL hospital target-scene visuals (after that).", 1, False),
    ("The Section-B images are static-camera target-scene renders — they are NOT the H6 "
     "training/evaluation frames, and no H6 metric was collected in the hospital scene.", 0, True),
    ("H6 metrics were collected in the procedural --scene stage; hospital renders validate "
     "the intended target scene for the next run.", 0, True),
], top=1.7, sz=16)

# 3 — (A) Question
s = slide()
title(s, "(A) Diagnostic — question, and why H6 after H5")
tag(s, "Section A · procedural --scene stage · quantitative")
body(s, [
    ("Models: H1 = retained incumbent; H5 = prior diagnostic (mixed-family replay); "
     "H6 = current diagnostic (added hard-route coverage).", 0, False),
    ("Question: does adding clean hard-route families (u-turn, chain, forward-then-L, "
     "sharp-multi-turn, tight-corridor) to TRAINING produce success on HELD-OUT hard "
     "families?", 0, True),
    ("H5 improved trajectory fidelity but regressed on a prior family (Success Rate "
     "0.167 → 0.000: it lost forward-then-L), and still reached no hard-family success.", 0, False),
    ("So the open question is whether this is a route-family COVERAGE gap.", 0, False),
], top=1.7)

# 4 — (A) Collected + setup
s = slide()
title(s, "(A) Diagnostic — what was collected, and the setup")
tag(s, "Section A · procedural --scene stage · quantitative")
body(s, [
    ("16/16 clean scripted-expert recordings: route completed, 0 collisions, clean "
     "shutdown; leakage-clean split (no episode or family shared across splits).", 0, False),
    ("Split: 10 training / 2 validation / 4 fresh hard held-out (unseen instances of "
     "trained route types).", 0, True),
    ("Model: General Navigation Model (GNM) with a MobileNetV2 image encoder.", 0, False),
    ("Weights-only init from the H1 incumbent, fresh optimiser, one seed; checkpoint "
     "selected on the validation split.", 0, False),
    ("Evaluation is offline Track-A (open-loop), data root fixed for every model.", 0, False),
    ("Collected in the procedural --scene stage; scene geometry is irrelevant to the "
     "route-family coverage question.", 0, True),
], top=1.7, sz=17)

# 5 — (A) Results
s = slide()
title(s, "(A) Diagnostic — results: H1 vs H5 vs H6")
tag(s, "Section A · procedural --scene stage · quantitative")
mono(s,
     "Held-out set (n)      H1  SR / NE      H5  SR / NE      H6  SR / NE\n"
     "----------------------------------------------------------------------\n"
     "H4 held-out (6)       0.00 / 14.04    0.333 / 5.02     0.333 / 6.15\n"
     "Fresh hard (4)        0.00 / 21.36    0.00  / 8.25     0.00  / 10.58\n"
     "Prior held-out (6)    0.167 / 12.76   0.000 / 7.19     0.167 / 7.73\n"
     "Combined (12)         0.083 / 13.40   0.167 / 6.10     0.250 / 6.94",
     top=1.75, sz=16)
body(s, [
    ("Best combined Success Rate (SR) = 0.25 and best normalised Dynamic Time Warping "
     "(nDTW) = 0.351 are both H6; H6 also fixes H5's prior-family regression.", 0, True),
    ("Fresh hard families: SR = 0 and Oracle Success Rate (OSR) = 0 for ALL three models.", 0, True),
    ("SR = Success Rate; NE = Navigation Error (m); OSR = Oracle SR; nDTW = normalised "
     "Dynamic Time Warping.", 0, False),
], top=3.95, sz=14)

# 6 — (A) Interpretation
s = slide()
title(s, "(A) Diagnostic — interpretation and limitations")
tag(s, "Section A · procedural --scene stage · quantitative")
body(s, [
    ("Route-family coverage helps aggregate quality and removes H5's older-family regression.", 0, True),
    ("But the model never reaches within the 3 m success radius on unseen hard-family "
     "instances (OSR = 0). Held-out routes are only a/b repeats of trained routes, so "
     "simple a/b variants are not enough.", 0, False),
    ("Limitations: fixed placeholder goal image (NOT goal-conditioning evidence); "
     "scripted-expert demos; simulation only; offline eval; small n (4/6/12); one seed.", 0, False),
    ("Diagnostic only — not promoted; incumbent retained; no state-of-the-art claim; "
     "not real-robot evidence.", 0, True),
], top=1.7, sz=17)

# 7 — (B) Hospital asset proof
s = slide()
title(s, "(B) Hospital target scene — asset verified")
tag(s, "Section B · real Isaac 5.1 hospital.usd · target hospital-scene render — not H6 training/evaluation data", AMBER)
caption(s, "Real Isaac Sim 5.1 hospital.usd — 1909 prims, RTX ray-traced, robot-height front "
        "camera (context overview shown)", 1.15, color=BLACK)
pic(s, "hospital_context_reception.png", 1.5, width=8.0)
caption(s, "Reception desk, wheelchair, vending unit, vinyl floor — the intended deployment "
        "scene. Static render, not a recorded episode.", 6.85, sz=13, color=AMBER)

# 8 — (B) Re-renders 1
s = slide()
title(s, "(B) Hospital target-scene re-renders (1 of 2)")
tag(s, "Section B · target hospital-scene render — not original H6 training/evaluation data", AMBER)
caption(s, "u-turn route-type illustration — target hospital scene", 1.15)
pic(s, "hospital_render_uturn_contact_sheet.png", 1.45, width=8.7)
caption(s, "chain route-type illustration — repaired route pattern", 4.35)
pic(s, "hospital_render_chain_contact_sheet.png", 4.65, width=8.7)

# 9 — (B) Re-renders 2
s = slide()
title(s, "(B) Hospital target-scene re-renders (2 of 2)")
tag(s, "Section B · target hospital-scene render — not original H6 training/evaluation data", AMBER)
caption(s, "compound-turn route-type illustration — validation-style route pattern", 1.15)
pic(s, "hospital_render_compound_contact_sheet.png", 1.45, width=8.7)
caption(s, "unseen chain/u-turn route-type illustration — fresh-held-out-style pattern", 4.35)
pic(s, "hospital_render_unseen_contact_sheet.png", 4.65, width=8.7)

# 10 — Conclusion + next
s = slide()
title(s, "Conclusion and next experiment")
body(s, [
    ("(A) H6 is the strongest diagnostic so far — not a promotion: hard-route coverage "
     "improves aggregate performance and fixes the older-family regression, but fresh "
     "hard-family generalisation still fails (OSR = 0).", 0, True),
    ("(B) The intended hospital scene is verified and renders correctly at robot height; "
     "the earlier grey-stage visuals are withdrawn and replaced with these target-scene "
     "renders.", 0, True),
    ("Next experiment:", 0, True),
    ("re-run collection AND evaluation with --scene hospital so metrics and visuals share "
     "one scene;", 1, False),
    ("collect instance-diverse hard routes (distinct routes, not a/b repeats);", 1, False),
    ("evaluate under a non-fixed, goal-conditioned protocol against real goal images.", 1, False),
], top=1.55, sz=18)

prs.save(OUT)
print("saved", OUT, "slides:", len(prs.slides._sldIdLst))
