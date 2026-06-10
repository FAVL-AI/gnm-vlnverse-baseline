"use client";

// Static taxonomy — no API calls needed. This page is honest by construction.

const GT_TAXONOMY = [
  {
    type: "perfect_sim_state",
    label: "Perfect Simulation Ground Truth",
    color: "border-blue-500/30 bg-blue-500/5 text-blue-400",
    badge: "VERIFIABLE",
    description: "The simulator's internal state IS the ground truth. Robot pose, obstacle positions, velocities, and collision status are exact — not approximated.",
    sources: [
      "MuJoCo episode state vector",
      "IsaacLab rigid body state",
      "Procedural scene layout (exact zone boundaries)",
    ],
    present: true,
    evidence: "52 benchmark runs with aggregate_metrics.json",
    limitations: [
      "Only valid within simulation — real-world match unverified",
      "Domain gap between sim dynamics and Yahboom M3Pro hardware not measured",
    ],
  },
  {
    type: "semantic_scene_spec",
    label: "Semantic Scene Specification GT",
    color: "border-purple-500/30 bg-purple-500/5 text-purple-400",
    badge: "SPEC-DERIVED",
    description: "Ground truth derived from the procedural scene specification — agent roles, zone assignments, and risk scores are what the designer specified.",
    sources: [
      "HospitalSceneBuilder zone annotations",
      "DynamicAgentTracker role assignments (person/wheelchair/gurney)",
      "FleetSafe CBF zone boundaries from scene spec",
    ],
    present: true,
    evidence: "Hospital scene YAML configs + IsaacLab asset library",
    limitations: [
      "Agent roles assigned procedurally, not verified by human annotation in real scenes",
      "Photoreal Isaac assets not yet captured as video evidence",
    ],
  },
  {
    type: "sensor_derived",
    label: "Sensor-Derived (Real Robot)",
    color: "border-amber-500/30 bg-amber-500/5 text-amber-400",
    badge: "SENSOR",
    description: "Data derived from Yahboom M3Pro sensors. Not verified against external ground truth — positions are from wheel odometry and IMU integration, not external motion capture.",
    sources: [
      "/odom_raw — wheel encoder integration (~11 Hz)",
      "/scan0 — LIDAR (~7 Hz)",
      "/camera/color/image_raw — RGB (~30 Hz)",
      "/camera/depth/image_raw — depth (~10 Hz)",
      "/cmd_vel_raw, /cmd_vel_safe, /cmd_vel — command paths",
    ],
    present: false,
    evidence: "No ROS2 bag sessions recorded yet",
    limitations: [
      "Odometry drifts without loop closure or external reference",
      "Camera-to-robot extrinsic calibration not verified",
      "IMU sometimes unstable at Hz check — verify before using for GT",
      "No ground-truth pose system (Vicon/Mocap) in place",
    ],
  },
  {
    type: "human_labeled",
    label: "Human-Labeled Ground Truth",
    color: "border-green-500/30 bg-green-500/5 text-green-400",
    badge: "MANUAL",
    description: "Data where a human annotator has verified the labels — agent identities, roles, collision events. Required for real-world performance claims.",
    sources: [],
    present: false,
    evidence: "No manual annotation collected yet",
    limitations: [
      "Without this, real-robot semantic role claims (person vs wheelchair vs gurney) are inference-only",
      "YOLOv8 detections on real frames are not verified against human labels",
      "Collision/near-miss events in real scenes are self-reported by the safety filter, not externally verified",
    ],
  },
  {
    type: "none",
    label: "Inference-Only (No Ground Truth)",
    color: "border-border bg-card text-muted-foreground/50",
    badge: "INFERENCE",
    description: "Model outputs, risk scores, and dashboard audit logs. These record what the system decided — not what was objectively true.",
    sources: [
      "FleetSafe zone/risk scores from perception pipeline",
      "YOLOv8 detection outputs on real or sim frames",
      "Dashboard operator audit log",
      "PPO policy outputs (when training begins)",
    ],
    present: true,
    evidence: "Dashboard audit.jsonl + sim safety_events.jsonl",
    limitations: [
      "These are system outputs — they prove the system ran, not that it was correct",
    ],
  },
];

export default function GroundTruthPage() {
  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-6 py-4 border-b border-border shrink-0">
        <div className="font-mono text-sm font-bold tracking-widest text-foreground/80">GROUND TRUTH TAXONOMY</div>
        <div className="font-mono text-[10px] text-muted-foreground/40 mt-1">
          What we can honestly claim as ground truth vs what is inference or absent.
        </div>
      </div>

      <div className="flex flex-col gap-4 p-6">
        {GT_TAXONOMY.map(gt => (
          <div key={gt.type} className={`border p-4 ${gt.color}`}>
            <div className="flex items-center gap-3 mb-2">
              <span className="font-mono text-[8px] font-bold px-1.5 py-0.5 border border-current">
                {gt.badge}
              </span>
              <span className="font-mono text-[11px] font-semibold">{gt.label}</span>
              <span className={`ml-auto font-mono text-[8px] font-semibold ${
                gt.present ? "text-green-400" : "text-red-400/70"}`}>
                {gt.present ? "✓ PRESENT" : "✗ NOT YET COLLECTED"}
              </span>
            </div>

            <p className="font-mono text-[8px] text-foreground/60 leading-relaxed mb-3">{gt.description}</p>

            {gt.sources.length > 0 && (
              <div className="mb-2">
                <div className="font-mono text-[8px] text-muted-foreground/40 mb-1">Sources:</div>
                <ul className="flex flex-col gap-0.5">
                  {gt.sources.map((s, i) => (
                    <li key={i} className="font-mono text-[8px] text-foreground/50 flex gap-1.5">
                      <span className="text-muted-foreground/30">•</span>{s}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className={`font-mono text-[8px] border-l-2 pl-2 ${gt.present ? "border-green-500/40 text-green-400/60" : "border-red-500/30 text-red-400/60"}`}>
              {gt.evidence}
            </div>

            {gt.limitations.length > 0 && (
              <div className="mt-2 pt-2 border-t border-current/20">
                <div className="font-mono text-[8px] text-muted-foreground/40 mb-1">Limitations / Caveats:</div>
                {gt.limitations.map((l, i) => (
                  <div key={i} className="font-mono text-[8px] text-amber-400/60 flex gap-1.5 leading-relaxed">
                    <span>⚠</span><span>{l}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
