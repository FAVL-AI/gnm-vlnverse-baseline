# Positioning vs the Image-Goal Navigation (ImageNav) Literature

**Status:** Required for Paper 1 ("Accurate and Safety-Aware Visual Navigation: Diagnosing
Stopping Reliability in Camera-Only Image-Goal Navigation"). The paper's title claims the
ImageNav task; prior drafts cited none of its literature. This document closes that gap:
citation set, per-paper positioning, ready-to-paste LaTeX, anticipated reviewer questions,
and the claim-ledger rule governing comparisons.

**The predictable reviewer attack:** *"How is this different from SLING (CoRL 2022), which
already studied the last meter of ImageNav?"* This question must be answered inside the
paper, not discovered at review.

---

## 1. Citation set (9 papers)

| Key | Paper | Venue | Role in positioning |
|---|---|---|---|
| `zhu2017target` | Zhu et al., Target-Driven Visual Navigation in Indoor Scenes Using Deep RL | ICRA 2017 | Origin of the image-goal task formulation |
| `anderson2018eval` | Anderson et al., On Evaluation of Embodied Navigation Agents | arXiv 2018 | Made *stopping* part of the task definition (success requires terminating within radius) |
| `chaplot2020nts` | Chaplot et al., Neural Topological SLAM for Visual Navigation | CVPR 2020 | Topological ImageNav line; maps as intermediate structure |
| `hahn2021nrns` | Hahn et al., No RL, No Simulation (NRNS) | NeurIPS 2021 | Standardised *what to evaluate on* (episode splits reused by later work) |
| `alhalah2022zer` | Al-Halah et al., Zero Experience Required (ZER) | CVPR 2022 | Rising-SR trend; modular transfer |
| `mezghani2022memory` | Mezghani et al., Memory-Augmented RL for Image-Goal Navigation | IROS 2022 | H2 precedent: temporal context helps — but used for search/route-following, not termination |
| `wasserman2022sling` | Wasserman et al., Last-Mile Embodied Visual Navigation (SLING) | CoRL 2022 | Closest prior work — fixes the endgame with a method |
| `yadav2023ovrl2` | Yadav et al., OVRL-V2 | arXiv 2023 | Rising-SR trend; pretraining pushes reaching up, leaving termination as residual failure |
| `krantz2023iin` | Krantz et al., Navigating to Objects Specified by Images (Instance ImageNav) | ICCV 2023 | Task-line continuation; sharpened goal specification |

## 2. Per-paper: what they did well → how we position

1. **SLING** proved the endgame is where ImageNav fails and *fixed it with a method*
   (feature correspondence + perspective-n-point pose estimation switching into a dedicated
   last-mile policy). Counter is structural, not competitive: **they fix the endgame, we
   measure it** — SR/OSR reported jointly, Δ_stop as an audited first-class quantity,
   per-episode provenance, claim gates. And their fix needs 3D points (depth) and assumes
   discrete Habitat agents with an explicit stop action to learn — both outside our boundary.
   Our setting is RGB-only, continuous GNM waypoints, **no stop action exists to learn** —
   termination must be synthesised from runtime signals. Genuinely uncovered corner, not a
   re-run of their problem.
2. **Anderson et al. 2018 (evaluation paper)** made stopping part of the task definition;
   we inherit it and expose what aggregate SR hides.
3. **NRNS** standardised *what to evaluate on*; our split lock + metric regeneration
   standardises *how a claim may be made*.
4. **Mezghani et al.** is the H2 precedent — temporal/memory context helps ImageNav — but
   they used it for search and route-following; we show it improves *termination
   specifically*, isolated by the fixed-backbone ablation.
5. **ZER / OVRL-V2** rising success rates are the motivation argument made empirical: the
   better policies get at reaching, the more of the residual failure is stopping.
6. **Zhu 2017 / Chaplot 2020 / Krantz 2023** establish the task lineage the title invokes;
   citing them removes the "title claims a task it never cites" attack entirely.

## 3. Ready-to-paste LaTeX (wired into main.tex on 2026-07-06)

Insert as a subsection in *Related Work and Research Gap*, after the
benchmarks subsection:

```latex
\subsection{Image-goal navigation and termination}
The task studied here is image-goal navigation (ImageNav): the goal is specified by an
RGB image, and success requires terminating within a fixed radius of the goal position
\cite{zhu2017target,anderson2018eval}. The task line runs from target-driven navigation
\cite{zhu2017target} through topological methods \cite{chaplot2020nts}, standardised
evaluation episodes \cite{hahn2021nrns}, modular transfer \cite{alhalah2022zer}, offline
visual pretraining \cite{yadav2023ovrl2}, and instance-level goal specification
\cite{krantz2023iin}. Rising success rates in this line strengthen rather than weaken the
present question: as agents reach the goal region more often, a larger share of the
residual failure is termination. Memory-augmented agents \cite{mezghani2022memory} showed
that temporal context helps ImageNav, but used it for search and route-following; H2
tests whether temporal evidence improves termination specifically, isolated by holding
the backbone fixed.

The closest prior work is SLING \cite{wasserman2022sling}, which identified the last
metre as the dominant ImageNav failure zone and repaired it with a method: feature
correspondence and perspective-n-point pose estimation switch the agent into a dedicated
last-mile policy. The present paper is positioned differently in three ways. First, SLING
fixes the endgame; this paper measures it, making $\Delta_{stop}$ an audited first-class
quantity with per-episode provenance rather than a byproduct of a method contribution.
Second, SLING's pose estimation lifts feature matches to 3D points and therefore uses
depth, and its agents act in discrete action spaces where an explicit stop action exists
to be learned; the setting here is RGB-only continuous waypoint control, where no stop
action exists in the backbone and termination must be synthesised from runtime signals.
Third, no numeric comparison to SLING or to the Habitat ImageNav literature is reported,
because simulator, sensor suite, and episode distribution all differ; the claim boundary
blocks such comparisons. The two lines are complementary: a SLING-style module adapted to
the RGB-only boundary is a natural candidate stop policy inside this protocol.
```

Research-gap subsection, added sentence (after "isolated as a measurable failure mode"):

```latex
Where prior work has engaged the endgame directly, it has done so as a method under
depth-assisted discrete control \cite{wasserman2022sling}; termination reliability as an
audited, first-class measurement under an RGB-only continuous-control boundary remains
uncovered.
```

## 4. Anticipated reviewer questions

**Q1. "How is this different from SLING?"**
A: SLING is a method paper that repairs last-mile failure using depth-lifted feature
correspondences and PnP inside discrete Habitat agents that possess a stop action. This
paper is a measurement paper: it audits termination as a first-class quantity (Δ_stop,
per-episode provenance, claim gates) in a setting SLING does not cover — RGB-only,
continuous waypoint control, no stop action in the backbone. A SLING-style module adapted
to RGB-only is a future candidate stop policy *inside* this protocol, which makes the two
complementary rather than competing.

**Q2. "Why are there no numbers against SLING/OVRL/ZER?"**
A: Different simulator (Isaac Sim vs Habitat), different sensors (RGB vs RGB-D), different
episode distribution (VLNVerse/Kujiale locked split vs Gibson/HM3D splits). The repo's
claim ledger explicitly blocks cross-setting numeric comparison; reporting one would be
the kind of unaudited claim the paper argues against. The comparison offered is
structural (task boundary, deployability status, what is measured), not numeric.

**Q3. "Isn't the SR–OSR gap already known?"**
A: Known as a phenomenon (SLING's motivation; OSR long reported in VLN), not as an
audited quantity. Prior work treats the gap as motivation for a method; here it is the
measured object itself — locked split, per-episode rows, deployable/diagnostic separation
— so that stop-policy claims become inspectable and repeatable.

## 5. BibTeX

Entries marked `%*` have fields not fully re-verified against the source PDF —
check at camera-ready. No page numbers are invented anywhere.

```bibtex
@inproceedings{zhu2017target,
  title     = {Target-Driven Visual Navigation in Indoor Scenes Using Deep Reinforcement Learning},
  author    = {Zhu, Yuke and Mottaghi, Roozbeh and Kolve, Eric and Lim, Joseph J. and Gupta, Abhinav and Fei-Fei, Li and Farhadi, Ali},
  booktitle = {IEEE International Conference on Robotics and Automation (ICRA)},
  year      = {2017}
}

@article{anderson2018eval,
  title   = {On Evaluation of Embodied Navigation Agents},
  author  = {Anderson, Peter and Chang, Angel and Chaplot, Devendra Singh and Dosovitskiy, Alexey and Gupta, Saurabh and Koltun, Vladlen and Kosecka, Jana and Malik, Jitendra and Mottaghi, Roozbeh and Savva, Manolis and Zamir, Amir R.},
  journal = {arXiv preprint arXiv:1807.06757},
  year    = {2018}
}

@inproceedings{chaplot2020nts,
  title     = {Neural Topological SLAM for Visual Navigation},
  author    = {Chaplot, Devendra Singh and Salakhutdinov, Ruslan and Gupta, Abhinav and Gupta, Saurabh},
  booktitle = {IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
  year      = {2020}
}

@inproceedings{hahn2021nrns,
  title     = {No RL, No Simulation: Learning to Navigate without Navigating},
  author    = {Hahn, Meera and Chaplot, Devendra Singh and Tulsiani, Shubham and Mukadam, Mustafa and Rehg, James M. and Gupta, Abhinav},
  booktitle = {Advances in Neural Information Processing Systems (NeurIPS)},
  year      = {2021}
}

@inproceedings{alhalah2022zer,
  title     = {Zero Experience Required: Plug and Play Modular Transfer Learning for Semantic Visual Navigation},
  author    = {Al-Halah, Ziad and Ramakrishnan, Santhosh K. and Grauman, Kristen},
  booktitle = {IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
  year      = {2022}
}

@inproceedings{mezghani2022memory,
  title     = {Memory-Augmented Reinforcement Learning for Image-Goal Navigation},
  author    = {Mezghani, Lina and Sukhbaatar, Sainbayar and Lavril, Thibaut and Maksymets, Oleksandr and Batra, Dhruv and Bojanowski, Piotr and Alahari, Karteek},
  booktitle = {IEEE/RSJ International Conference on Intelligent Robots and Systems (IROS)},
  year      = {2022}
}

@inproceedings{wasserman2022sling,
  title     = {Last-Mile Embodied Visual Navigation},
  author    = {Wasserman, Justin and Yadav, Karmesh and Chowdhary, Girish and Gupta, Abhinav and Jain, Unnat},
  booktitle = {Conference on Robot Learning (CoRL)},
  year      = {2022}
}

@article{yadav2023ovrl2,
  title   = {OVRL-V2: A Simple State-of-Art Baseline for ImageNav and ObjectNav},
  author  = {Yadav, Karmesh and Majumdar, Arjun and Ramrakhya, Ram and Yokoyama, Naoki and Baevski, Alexei and Kira, Zsolt and Maksymets, Oleksandr and Batra, Dhruv}, %* author list order not re-verified
  journal = {arXiv preprint arXiv:2303.07798}, %* arXiv id not re-verified
  year    = {2023}
}

@inproceedings{krantz2023iin,
  title     = {Navigating to Objects Specified by Images},
  author    = {Krantz, Jacob and Gervet, Theophile and Yadav, Karmesh and Wang, Austin and Paxton, Chris and Mottaghi, Roozbeh and Batra, Dhruv and Malik, Jitendra and Lee, Stefan and Chaplot, Devendra Singh}, %* author list order not re-verified
  booktitle = {IEEE/CVF International Conference on Computer Vision (ICCV)},
  year      = {2023}
}
```

## 6. Claim-ledger statement (repo rule)

> **No numeric comparison between this repository's Track A results and Habitat-based
> ImageNav results (SLING, ZER, OVRL, NRNS splits) is permitted in any paper, README,
> table, or talk derived from this repository.** Simulator, sensor suite, success radius
> conventions, and episode distributions differ; a numeric comparison would be an
> unaudited claim. Permitted positioning: structural complementarity — this protocol
> *measures* termination under an RGB-only continuous-control boundary; Habitat ImageNav
> methods (e.g., a SLING-style last-mile module adapted to RGB-only) are candidate stop
> policies to be evaluated *inside* this protocol in future work.

---
*Rebuilt 2026-07-06 (original session deliverable was not persisted). Wired into Paper 1
(`main.tex`) the same day: new Related-Work subsection, research-gap sentence, and 9
bibliography entries.*
