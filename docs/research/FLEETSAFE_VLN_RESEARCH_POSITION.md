# FleetSafe-VLN: Research Position

## What this project is — and what it is not

### Not simple path planning

A path planner receives a destination coordinate and finds a collision-free
trajectory. FleetSafe-VLN does not do this.

**FleetSafe-VLN is embodied Vision-Language Navigation (VLN):**

> The robot receives a natural-language instruction, perceives the environment
> through its own egocentric RGB-D camera and LiDAR, grounds the instruction
> against its visual observations, generates a nominal action through a learned
> visual navigation backbone, and then executes a formally certified safe command.

That matches the original VLN framing: following visually-grounded natural-language
navigation instructions in real indoor environments.

---

## The architecture

```
Voice / Text / Image Instruction
        ↓
InstructionIntake
        ↓
InstructionGrounder (deterministic rule-based + topomap hook)
        ↓ GroundedGoal: action_type, label, safety_constraints, nominal_vx/wz
BackboneRouter
        ↓ choose GNM | ViNT | NoMaD
VisualNav Backbone (GNM / ViNT / NoMaD)
        ↓ u_nom (nominal cmd_vel proposal)
FleetSafe CBF-QP Safety Filter
        ↓ u_safe (certified safe command)
/cmd_vel → Yahboom M3Pro
        ↓
SafetyCertificate + VLNTrace (JSONL audit logs)
```

---

## Role of each component

### GNM / ViNT / NoMaD — nominal visual navigation backbones

- GNM and ViNT are general-purpose visual navigation models (Shah et al., ICRA 2023 / CoRL 2023).
- NoMaD is a diffusion-based extension of the same family (Sridhar et al., ICRA 2024).
- In FleetSafe-VLN, these models propose a nominal action `u_nom` conditioned on
  the current RGB observation and a language-derived visual goal.
- They are **not** safety-critical controllers. Their output is **not trusted blindly**.

### Language / voice grounding layer

- Converts voice transcripts, typed text, and image references into a
  structured `GroundedGoal` with: action intent, semantic target, safety constraints.
- The baseline implementation is deterministic and fully auditable — keyword-based
  parsing with a clear explanation trace.
- Hooks exist for CLIP/VLM grounding (disabled by default).

### FleetSafe CBF-QP — formal safety shield

- Intercepts `u_nom` and solves:
  ```
  u_safe = argmin ½‖u − u_nom‖²
           s.t.  ḣ_i(x,u) + α·h_i(x) ≥ 0  ∀i
                 u_min ≤ u ≤ u_max
  ```
- Emits a per-timestep `SafetyCertificate` (JSONL).
- Proof: By the Comparison Lemma, h_i(t) ≥ 0 for all t ≥ 0 under this policy.
- Emergency stop fallback if QP is infeasible.

---

## What the core research contribution is

The contribution is **not** "we added voice to a robot." It is:

1. **Backbone-agnostic safety**: GNM, ViNT, and NoMaD are interchangeable nominal
   planners wrapped by the same CBF-QP shield.

2. **Multimodal instruction interface**: voice, text, and image prompts all
   produce the same `GroundedGoal` → same nominal policy → same safety certificate.

3. **Per-timestep formal certificates**: every command is backed by a JSONL record
   that a reviewer or regulator can inspect. Not a black box.

4. **Real + sim**: the same stack runs on the physical Yahboom M3Pro, in Gazebo,
   and in Isaac Sim.

---

## What we do NOT claim

| Claim | Verdict |
|---|---|
| GNM / ViNT alone are VLN | ❌ — they are visual navigation backbones |
| We rank on VLN-CE / R2R leaderboard | ❌ — not evaluated on those splits |
| Voice module is a research contribution | ❌ — it is a deployment modality |
| CBF proves infinite-horizon safety | ❌ — discrete-time approximation |
| LiDAR scan is perfect | ❌ — noise and blind spots exist |
| u_safe = u_nom when CBF inactive | ✅ — nominal command passes through |

---

## What we DO claim

> "FleetSafe-VLN treats GNM, ViNT, and NoMaD as nominal embodied navigation
> backbones rather than safety-critical controllers. A multimodal language
> grounding layer converts voice, text, and image prompts into structured
> navigation intent, which is then mapped to nominal control u_nom. FleetSafe
> solves a CBF-QP at every timestep to produce certified safe control u_safe,
> with formal certificates and runtime logs recorded for auditability. The system
> runs on a physical Yahboom M3Pro robot and in Isaac Sim and Gazebo simulators."

---

## Yahboom voice module

The Yahboom M3Pro ships with an A-MIC audio module and optional voice-activation
software. In FleetSafe-VLN, any voice transcript (from the robot's A-MIC, a local
Whisper model, or typed input) becomes a `VLNInstruction`. The voice module is
a **speech-to-text input adapter** — the research contribution is what happens
after the text is received, not the transcription itself.

---

## Future upgrades

| Upgrade | Status |
|---|---|
| CLIP/VLM visual grounding | Hook in `grounding.py`, disabled |
| Local Whisper ASR | Hook in `instruction_intake.py`, disabled |
| Topomap node matching | Stub in `grounding.py`, needs images |
| Real GNM/ViNT checkpoint | Adapters exist, need checkpoints loaded |
| Leaderboard evaluation | Planned — VLN-CE continuous environment |
