# Professor note — Isaac Sim live evidence stage

After the MobileNetV2-GNM ablation, we ran a small Isaac Sim live evidence
stage using the selected checkpoint. These episodes provide physical
rollout evidence, including trajectory logs, rosbags, and contact-based
Collision Rate. This is a live simulation smoke evaluation, not a full
VLNVerse benchmark.

Selected checkpoint: MobileNetV2-GNM baseline (EMA not promoted), path and
SHA-256 recorded in live_episode_summary.json. Three short episodes
(straight short/medium, low-curvature) under the full safety envelope:
velocity clamps, watchdog, emergency stop, explicit end-of-episode zeroing
(residuals recorded), PhysX chassis-contact collision logging with
wheel-floor contacts excluded. A short onboard-camera video extracted from
the rosbag accompanies the logs (kept out of git; checksum committed).
No robust-navigation claim is made.
