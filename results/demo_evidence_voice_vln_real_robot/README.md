# FleetSafe Voice-Conditioned VLN Real-Robot Evidence

This folder contains a real M3Pro dry-run evidence capture for FleetSafe-VLN.

## Demonstrated capability

A spoken navigation instruction was published to:

`/fleetsafe/instruction_voice`

The VLN controller processed the instruction, used live robot LiDAR and camera state, generated a nominal navigation command, applied the CBF safety layer, and wrote both trace and certificate evidence.

## Key certificate result

- Input source: voice
- Camera observed: true
- Safety QP status: optimal
- CBF active: true
- Safe decision: true
- Dry-run mode: true
- Effective LiDAR clearance: approximately 0.334 m
- Safety radius: 0.20 m

## Interpretation

The robot did not physically move because the controller was launched in dry-run mode. However, the full perception-language-safety pipeline executed and produced a certified safe command.

This evidence supports the claim that FleetSafe-VLN is not only a path-following system, but a voice/text/image-conditioned embodied navigation stack with auditable safety certificates.
