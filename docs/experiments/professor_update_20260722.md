# Weekly update — Frank Asante Van Laarhoven — 2026-07-22

This week's audit found that the hospital camera and trajectory recordings are technically substantial,
and the raised camera has solved the previous lower-frame obstruction. However, none of the recordings
can yet be used as a formal training or held-out evaluation dataset because most episodes lack their
own captured goal image, many start poses are incorrect, and controller labels do not reliably identify
whether GNM was actually controlling the robot. I have therefore finalised the dataset protocol,
success threshold and literature-grounded metric definitions, and prepared the navigable-map extension
required before a clean hospital recapture.

## What I need from you

**One approval, before any recording happens.** I have pre-registered the hospital success radius at
**τ = 0.50 m**, with success defined as finishing within 0.50 m of the goal, at a linear speed of
0.05 m/s or less, held for at least one continuous second, with an explicit stop action emitted. I will
report sensitivity at 0.25 / 0.50 / 0.75 / 1.00 m, but 0.50 m is the single primary result and the
others exist only to characterise sensitivity — not to pick the best-looking number afterwards.
Track A's Kujiale results keep their original τ = 3.0 m, and the two will never be shown as
equivalent. **If you are content with 0.50 m, I will lock it into the dataset configuration, the route
manifest and the evaluation specification.**

## What is now decided

- **1280 × 720 is the canonical acquisition resolution.** The existing 640 × 480 recordings are already
  disqualified for other reasons, so lowering the standard would rescue nothing, and the extra detail
  cannot be recovered later. Training images will be downsampled deterministically from the master.
- **The 0.12 m camera raise is locked provisionally.** The evidence is clean: all 39 recordings without
  it lost the bottom ~38 % of every frame to the chassis; 23 of 24 with it are completely clear.
- **All 157 existing recordings become immutable evidence** — 13 demonstration, 126 diagnostic,
  18 permanently rejected. None enters the training set. I am not editing any of them; the wrong labels
  are themselves the finding, and overwriting them would destroy the audit trail.
- **A secondary pose-aligned success metric** (within 0.50 m *and* within 30° of the goal heading) will
  be reported alongside the primary one. Arriving in the right place facing the wrong way is a real
  image-goal failure that a position-only success rate cannot see.

## The correction that matters most

The 13 good recordings cannot be repaired by editing metadata. Image-goal navigation defines the task
by the goal *image*, and the correct goal image is the view from the goal pose. An episode that never
visited a given pose contains no frame taken there — assigning one would be fabricated ground truth.
So the recapture is not a convenience; it is the only honest route.

I have restructured the capture order so this cannot recur: **goal images are captured and hash-locked
before any route data is recorded.** A route episode that cannot resolve its goal to an already-locked
record is rejected before it starts. Substitution becomes structurally impossible rather than merely
discouraged.

## Sequencing consequence

The first Isaac session must be a **map-extension and validation session, not data collection.** The
H8-S split currently leaks because the proven-navigable lobby is too small to hold enough physically
distinct held-out goal locations — coordinates (1.0, −0.2) and (1.2, 0.0) are each forced to serve two
splits. That is structural, not a manifest error, so it can only be fixed by enlarging the
render-confirmed navigable map. That session will also produce the navmesh we need for SPL, nDTW, SDTW
and CLS, none of which we can compute today.

## Two literature corrections

**VLNTube** is real *software* — a data-generation pipeline we vendor and depend on — but I could not
find it as a peer-reviewed publication. I will cite it as software with a repository URL and pinned
digest, and remove any wording implying published standing. I am not removing the dependency, only the
citation form.

**A discrepancy I want to flag rather than quietly fix:** our paper draft describes VLNVerse as having
4,000+ scenes, but the primary publication I verified (Lin et al., arXiv:2512.19021) reports 263 home
scenes. Same author, same simulator, but an order of magnitude apart. I will reconcile it against the
cited source before anything goes out.

On the baselines: GNM, ViNT and NoMaD do not publish a success radius, a stopping rule, a collision
definition or confidence intervals, and GNM's headline number is mean progress toward the goal rather
than a success rate. I will discuss them as related work but will not put their numbers in a direct
comparison table with ours.

## What I can show you now

Contact sheets of genuine `hospital.usd` recordings — reception desk, wheelchair, glass doors, vinyl
floor — at full frame; the before/after camera-raise comparison, which is a clean self-contained
result; and trajectory plots showing the execution problem plainly.

## Next two weeks

Clear the two blockers that need no Isaac — the image-to-pose time-alignment procedure and the dataset
builder — then bring you the map-extension session plan for authorisation.
