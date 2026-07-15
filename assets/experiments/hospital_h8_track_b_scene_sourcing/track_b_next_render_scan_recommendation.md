# H8-M Track-B — Next Bounded Render-Scan Recommendation (SOURCING ONLY)

**Status: recommendation only — authorises NOTHING.** No render, no scan, no collection, no drive,
no training, no promotion, no push, no tag, no recording, no 20/5/10, no closed-loop; `CL_BOUND_XY`
unchanged. This names the one scene to render-scan next *if and when* the user approves a scan.

> **No real T/Y/cross junction, no angular-branch training. Scene sourcing is the blocker, not the
> model.**

## Recommended next scan (one primary, one backup)

**Primary — `warehouse_multiple_shelves`**
- Source: `…/Simple_Warehouse/warehouse_multiple_shelves.usd` (HTTP 200, 2.3 MB; NVIDIA Isaac stock,
  research/eval, loaded by reference).
- Why: the **only untried, reachable, real-world-like** candidate whose multiple shelf rows *could*
  form a cross-aisle intersection.
- **Honest prior: LOW** — its larger sibling `warehouse_full` had only straight parallel aisles.
  This is a single, targeted test of the multi-shelf hypothesis, **not** resumed ad hoc scanning.
- Junction status: **`UNVERIFIED_UNTIL_RENDER_SCAN`**.

**Backup — `synthetic_diagnostic_fork` (`SYNTHETIC_DIAGNOSTIC_ONLY`)**
- A small authored T/Y/cross of bounded corridors (to be built to the requirements-doc geometry).
- Use if the primary render-scan finds no cross-junction, **or** if the user declines further
  stock-asset scanning (then it becomes primary).
- Guaranteed junction by construction — but still verified by the same bounded render-scan.

## Gates the render-scan must apply (unchanged, corrected method)

1. Scene-load gate.
2. Render-validity gate (decision + goal A + goal B render; non-blank; luma OK; low black).
3. Depth-openness gate (both branches median central depth ≥ 3.0 m).
4. **Open-floor guard** (all 4 cardinal depths ≥ 4.0 m ⇒ `OPEN_FLOOR_NOT_JUNCTION`).
5. Reject collinear ~180° straight-aisle "branch pairs"; require perpendicular divergence ≥ 30°.
6. **Mandatory contact-sheet / human visual verification** before any `RENDER_VALID_JUNCTION`.
7. Embedding distinctness gate (goal A vs goal B distinct, with margin).

(Drive-validation, recorded-mode, and leakage-audit gates follow only *after* a scan yields a
visually-verified junction — they are not part of the render-scan itself.)

## Decision rule for the scan result

- **≥ 1 visually-verified `RENDER_VALID_JUNCTION`** → stop and hold for review before any drive
  validation. Do not treat render-validity as drive-validity.
- **None** → do not force a claim; fall back to the `SYNTHETIC_DIAGNOSTIC_ONLY` fork, or escalate to
  sourcing a non-Isaac corridor-forked asset.

## Claim boundary

Sourcing/recommendation only. No render / drive / model / benchmark evidence; no training
authorization. Junction geometry `UNVERIFIED_UNTIL_RENDER_SCAN`. No full ImageNav claim, no SOTA, no
promotion, no autonomy claim. `CL_BOUND_XY` unchanged; incumbent retained;
`DIAGNOSTIC_ONLY_NOT_PROMOTED`.
