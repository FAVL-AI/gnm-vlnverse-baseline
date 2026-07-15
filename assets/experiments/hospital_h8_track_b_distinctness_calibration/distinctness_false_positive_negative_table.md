# Track-B Distinctness — False-Positive / False-Negative Table (vs DINO cosine < 0.60 gate)

Gate rule under test: a pair is called **distinct** iff DINO cosine < 0.6.

- **False NEGATIVE** = a truly DISTINCT pair the gate MISSES (DINO >= 0.60 -> gate says 'not distinct'). This is the R1-R4 synthetic-fork failure mode.
- **False POSITIVE** = a truly SAME pair the gate wrongly flags as distinct (DINO < 0.60).
- **HARD_NEGATIVE not flagged** = a look-alike (different location) the gate treats as not-distinct (DINO >= 0.60) — expected/acceptable, listed for transparency.

## False negatives (DISTINCT missed): 7
| pair | DINO | reason |
|---|---|---|
| syn_R1_NvsW | 0.7956 | R1 gate pair: north (blue) vs west (green) branches, 90 deg apart |
| syn_R2_NvsW | 0.6163 | R2 gate pair: north vs west branches |
| syn_R3_NvsW | 0.6535 | R3 gate pair: north vs west branches |
| syn_R4_NvsW | 0.6912 | R4 gate pair: north vs west branches |
| syn_R4_NvsE | 0.6708 | north (blue,round) vs east (orange,boxy) branches |
| syn_R4_WvsS | 0.6318 | west (green,pointed) vs south (red,columned) branches |
| hosp_fork_vs_sidecorr | 0.6841 | different zones: reception fork vs side corridor |

## False positives (SAME wrongly flagged distinct): 1
| pair | DINO | reason |
|---|---|---|
| syn_R2_northSame | 0.5878 | north branch: junction-centre vs close goal view |

## Hard negatives with DINO >= 0.60 (not flagged distinct): 3
| pair | DINO | reason |
|---|---|---|
| mshelf_p00_openfloor | 0.6664 | open-hall probe: two perpendicular views of the same open floor look a |
| whsimple_p00_perp | 0.6786 | open warehouse hall: two perpendicular views look alike (open-floor fa |
| office_p03_perp | 0.6648 | open office bullpen: two views look alike |
