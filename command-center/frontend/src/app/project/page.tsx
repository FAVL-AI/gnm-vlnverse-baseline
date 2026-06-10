"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const REPO = "https://github.com/FAVL-AI/FleetSafe-VisualNav-Benchmark";

interface LiveData {
  iamgoodnavigator?: { ready?: boolean; fine_episodes?: number; coarse_episodes?: number };
  vlntube?: { repo_available?: boolean; has_real_data?: boolean; rgb_images?: number; usd_scenes?: number };
  yahboom?: { urdf_found?: boolean; status?: string };
  evidence_ready?: boolean;
}

const BEYOND_TABLE = [
  { feature: "Benchmark reference",   vlnverse: "✓",  vlntube: "—",  fleetsafe: "✓" },
  { feature: "Data gen pipeline",     vlnverse: "—",  vlntube: "✓",  fleetsafe: "✓ (indexed)" },
  { feature: "USD scenes",            vlnverse: "✓",  vlntube: "✓",  fleetsafe: "✓ (via VLNTube)" },
  { feature: "Scene graphs",          vlnverse: "—",  vlntube: "✓",  fleetsafe: "✓ (indexed)" },
  { feature: "RGB/depth sequences",   vlnverse: "—",  vlntube: "✓",  fleetsafe: "✓ (real npy)" },
  { feature: "Navigation backbone",   vlnverse: "custom", vlntube: "—", fleetsafe: "GNM/ViNT/NoMaD" },
  { feature: "Safety shield",         vlnverse: "—",  vlntube: "—",  fleetsafe: "CBF-QP ✓" },
  { feature: "Safety certificates",   vlnverse: "—",  vlntube: "—",  fleetsafe: "per-timestep JSONL" },
  { feature: "Real robot target",     vlnverse: "—",  vlntube: "—",  fleetsafe: "Yahboom M3 Pro" },
  { feature: "ROS 2 bridge",          vlnverse: "—",  vlntube: "—",  fleetsafe: "✓" },
  { feature: "Dashboard + replay",    vlnverse: "—",  vlntube: "—",  fleetsafe: "✓ NextJS" },
  { feature: "Evidence capture",      vlnverse: "—",  vlntube: "—",  fleetsafe: "✓ automated" },
];

const QUAL_EXAMPLES = [
  {
    task: "fine_0",
    instruction: "Start facing the window with cabinets below it. Turn left, keeping the cabinet on your right. Continue straight and turn right into the room ahead. Stop when you can see the chairs and the green rug.",
    scene: "vlnverse/kujiale_0010",
    source: "IAmGoodNavigator",
  },
  {
    task: "fine_1",
    instruction: "Walk forward towards the kitchen area. Turn right at the island and proceed to the dining table.",
    scene: "vlnverse/kujiale_0010",
    source: "IAmGoodNavigator",
  },
];

const PIPELINE_STAGES = [
  { name: "USD Scene",          tool: "VLNTube / Isaac Sim", status: "available" },
  { name: "Scene Graph",        tool: "VLNTube scene_graph",  status: "available" },
  { name: "Walkable Points",    tool: "VLNTube vistube",      status: "available" },
  { name: "Path Planning",      tool: "VLNTube vistube",      status: "available" },
  { name: "RGB/Depth Render",   tool: "Isaac Sim + vistube",  status: "requires_isaac" },
  { name: "Instruction Gen",    tool: "VLNTube instube",      status: "requires_gemini" },
  { name: "Training Export",    tool: "VLNTube datatube",     status: "available" },
  { name: "Safety Labels",      tool: "FleetSafe CBF-QP",     status: "available" },
];

function TopBtn({ href, label, external }: { href: string; label: string; external?: boolean }) {
  return external ? (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="px-4 py-2 text-xs font-mono font-semibold bg-zinc-800 border border-zinc-600 rounded hover:bg-zinc-700 hover:border-zinc-400 transition text-zinc-200"
    >
      {label}
    </a>
  ) : (
    <Link
      href={href}
      className="px-4 py-2 text-xs font-mono font-semibold bg-zinc-800 border border-zinc-600 rounded hover:bg-zinc-700 hover:border-zinc-400 transition text-zinc-200"
    >
      {label}
    </Link>
  );
}

export default function ProjectPage() {
  const [live, setLive] = useState<LiveData | null>(null);

  const fetchLive = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/vln-hub/live`);
      if (r.ok) setLive(await r.json());
    } catch {}
  }, []);

  useEffect(() => { fetchLive(); }, [fetchLive]);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 font-mono">
      {/* Hero */}
      <div className="border-b border-zinc-800 px-6 py-12 max-w-5xl mx-auto">
        <div className="flex items-center gap-3 mb-2">
          <span className="text-[10px] bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-400 tracking-widest">
            WORKING DRAFT
          </span>
          <span className="text-[10px] text-zinc-600">results pending</span>
        </div>
        <h1 className="text-4xl font-bold text-white mb-3 leading-tight">
          FleetSafe-VLN
        </h1>
        <p className="text-zinc-400 text-base max-w-2xl leading-relaxed">
          Safety-Certified Visual-Language Navigation with Isaac Sim and Yahboom ROSMASTER M3 Pro.
          Extends VLNVerse + VLNTube with CBF-QP formal safety, per-timestep certificates,
          and real-robot closure.
        </p>

        {/* CTA buttons */}
        <div className="flex flex-wrap gap-2 mt-6">
          <TopBtn href="/dashboard/vln-hub" label="Dashboard" />
          <TopBtn href="/dashboard/demo" label="Demo" />
          <TopBtn href="/dashboard/evidence" label="Evidence" />
          <TopBtn href="/docs/paper/FleetSafe_VLN_Paper_Draft.md" label="Paper (draft)" external />
          <TopBtn href={REPO} label="Code" external />
          <TopBtn href="https://huggingface.co/datasets/Eyz/VLNVerse_scene" label="Data" external />
        </div>

        {/* Live status mini-bar */}
        {live && (
          <div className="mt-4 flex flex-wrap gap-3 text-[10px]">
            <span className={`px-2 py-1 rounded ${live.iamgoodnavigator?.ready ? "bg-emerald-900 text-emerald-300" : "bg-zinc-800 text-zinc-500"}`}>
              IAmGoodNavigator {live.iamgoodnavigator?.ready ? `✓ (${live.iamgoodnavigator.fine_episodes}+${live.iamgoodnavigator.coarse_episodes} eps)` : "not ready"}
            </span>
            <span className={`px-2 py-1 rounded ${live.vlntube?.has_real_data ? "bg-emerald-900 text-emerald-300" : "bg-zinc-800 text-zinc-500"}`}>
              VLNTube {live.vlntube?.has_real_data ? "✓ real data" : "no data yet"}
            </span>
            <span className={`px-2 py-1 rounded ${live.yahboom?.urdf_found ? "bg-emerald-900 text-emerald-300" : "bg-amber-900 text-amber-300"}`}>
              Yahboom {live.yahboom?.urdf_found ? "URDF ready" : "URDF missing"}
            </span>
          </div>
        )}
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8 space-y-12">

        {/* Qualitative examples */}
        <section>
          <h2 className="text-lg font-semibold text-zinc-200 mb-4 border-b border-zinc-800 pb-2">
            Qualitative Examples
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {QUAL_EXAMPLES.map((ex, i) => (
              <div key={i} className="bg-zinc-900 rounded-lg border border-zinc-700 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[9px] bg-zinc-800 rounded px-1.5 py-0.5 text-zinc-400">{ex.source}</span>
                  <span className="text-[9px] text-zinc-600">{ex.task} · {ex.scene}</span>
                </div>
                <p className="text-xs text-zinc-300 leading-relaxed italic">"{ex.instruction}"</p>
                <div className="mt-3 aspect-video bg-zinc-800 rounded flex items-center justify-center">
                  <p className="text-[10px] text-zinc-600 text-center">
                    Isaac Sim FloatingCamera view<br />(captured after running episode)
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Trajectory visualization */}
        <section>
          <h2 className="text-lg font-semibold text-zinc-200 mb-4 border-b border-zinc-800 pb-2">
            Trajectory Visualization
          </h2>
          <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4">
            <div className="aspect-video bg-zinc-800 rounded flex items-center justify-center mb-3">
              <p className="text-[10px] text-zinc-600 text-center">
                Planned vs actual trajectory overlay<br />
                (rendered after episode run)
              </p>
            </div>
            <p className="text-xs text-zinc-500">
              Scene: <code className="text-zinc-400">vlnverse/kujiale_0010</code> ·
              Start: [2.43, 5.76] · Goal: [3.73, 1.26] ·
              Geo distance: pending episode run
            </p>
          </div>
        </section>

        {/* Interactive demo */}
        <section>
          <h2 className="text-lg font-semibold text-zinc-200 mb-4 border-b border-zinc-800 pb-2">
            Interactive Demo
          </h2>
          <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4 text-xs space-y-2">
            <p className="text-zinc-300 font-semibold">Quick start (requires Isaac Sim):</p>
            <code className="block bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-amber-300">
              bash scripts/setup_iamgoodnavigator.sh --download
            </code>
            <code className="block bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-amber-300">
              bash scripts/run_iamgoodnavigator_episode.sh fine 0
            </code>
            <p className="text-zinc-500">
              Then in Isaac Sim: Perspective → Cameras → FloatingCamera
            </p>
            <p className="text-zinc-500">
              Or one-command: <code className="text-zinc-400">bash scripts/run_real_imported_vln_demo.sh</code>
            </p>
            <div className="mt-3 pt-3 border-t border-zinc-800">
              <Link href="/dashboard/vln-hub" className="text-blue-400 hover:text-blue-300 mr-4">
                → VLN Hub Dashboard
              </Link>
              <Link href="/dashboard/demo" className="text-blue-400 hover:text-blue-300">
                → Live Demo
              </Link>
            </div>
          </div>
        </section>

        {/* VLNTube pipeline */}
        <section>
          <h2 className="text-lg font-semibold text-zinc-200 mb-4 border-b border-zinc-800 pb-2">
            VLNTube Data Pipeline
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            {PIPELINE_STAGES.map((s, i) => (
              <div key={i} className={`rounded border p-3 ${
                s.status === "available"       ? "bg-zinc-900 border-zinc-700" :
                s.status === "requires_isaac"  ? "bg-zinc-900 border-amber-900" :
                                                 "bg-zinc-900 border-zinc-800"
              }`}>
                <p className="font-semibold text-zinc-300 mb-1">{s.name}</p>
                <p className="text-zinc-500 text-[10px]">{s.tool}</p>
                <p className={`mt-1 text-[10px] font-mono ${
                  s.status === "available"      ? "text-emerald-400" :
                  s.status === "requires_isaac" ? "text-amber-400"   :
                                                  "text-zinc-600"
                }`}>
                  {s.status === "available" ? "✓ ready" :
                   s.status === "requires_isaac" ? "requires Isaac Sim" :
                   "requires Gemini"}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Benchmark statistics */}
        <section>
          <h2 className="text-lg font-semibold text-zinc-200 mb-4 border-b border-zinc-800 pb-2">
            Benchmark Statistics
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            {[
              { label: "Fine episodes",   value: live?.iamgoodnavigator?.fine_episodes ?? 10 },
              { label: "Coarse episodes", value: live?.iamgoodnavigator?.coarse_episodes ?? 10 },
              { label: "RGB/depth seqs",  value: live?.vlntube?.rgb_images ?? "2 (sample)" },
              { label: "Safety modes",    value: 3 },
            ].map((s, i) => (
              <div key={i} className="bg-zinc-900 border border-zinc-700 rounded p-3 text-center">
                <p className="text-2xl font-bold text-white">{s.value}</p>
                <p className="text-zinc-500 text-[10px] mt-1">{s.label}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-[11px] border-collapse">
              <thead>
                <tr className="border-b border-zinc-700">
                  <th className="text-left py-2 px-3 text-zinc-400">Mode</th>
                  <th className="text-left py-2 px-3 text-zinc-400">SR</th>
                  <th className="text-left py-2 px-3 text-zinc-400">SPL</th>
                  <th className="text-left py-2 px-3 text-zinc-400">CBF Rate</th>
                  <th className="text-left py-2 px-3 text-zinc-400">cert_safe</th>
                </tr>
              </thead>
              <tbody>
                {["baseline (none)", "log_only", "cbf_qp"].map((mode) => (
                  <tr key={mode} className="border-b border-zinc-800">
                    <td className="py-1.5 px-3 text-zinc-300 font-mono">{mode}</td>
                    <td className="py-1.5 px-3 text-zinc-600">TBD</td>
                    <td className="py-1.5 px-3 text-zinc-600">TBD</td>
                    <td className="py-1.5 px-3 text-zinc-600">{mode === "cbf_qp" ? "TBD" : mode === "log_only" ? "TBD" : "0"}</td>
                    <td className="py-1.5 px-3 text-zinc-600">{mode === "cbf_qp" ? "100% (target)" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-zinc-600 text-[10px] mt-1">Results pending Isaac Sim episode runs.</p>
          </div>
        </section>

        {/* Safety certificate stats */}
        <section>
          <h2 className="text-lg font-semibold text-zinc-200 mb-4 border-b border-zinc-800 pb-2">
            Safety Statistics
          </h2>
          <div className="bg-zinc-900 border border-zinc-700 rounded p-4 text-xs">
            <div className="grid grid-cols-3 gap-4 text-center">
              {[
                { label: "Certificate tiers", value: "3" },
                { label: "Target cert_safe", value: "100%" },
                { label: "CBF alpha", value: "0.5" },
              ].map((s, i) => (
                <div key={i}>
                  <p className="text-xl font-bold text-white">{s.value}</p>
                  <p className="text-zinc-500 text-[10px] mt-1">{s.label}</p>
                </div>
              ))}
            </div>
            <p className="text-zinc-500 mt-3 text-[10px]">
              d_safe = 0.8m · estop_dist = 0.5m · min_human_distance = 1.2m
            </p>
          </div>
        </section>

        {/* FleetSafe Beyond table */}
        <section>
          <h2 className="text-lg font-semibold text-zinc-200 mb-4 border-b border-zinc-800 pb-2">
            FleetSafe Beyond VLNVerse / VLNTube
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px] border-collapse">
              <thead>
                <tr className="border-b border-zinc-700">
                  <th className="text-left py-2 px-3 text-zinc-400">Feature</th>
                  <th className="text-center py-2 px-3 text-zinc-400">VLNVerse</th>
                  <th className="text-center py-2 px-3 text-zinc-400">VLNTube</th>
                  <th className="text-center py-2 px-3 text-emerald-400">FleetSafe</th>
                </tr>
              </thead>
              <tbody>
                {BEYOND_TABLE.map((row, i) => (
                  <tr key={i} className="border-b border-zinc-800">
                    <td className="py-1.5 px-3 text-zinc-300">{row.feature}</td>
                    <td className="py-1.5 px-3 text-center text-zinc-500">{row.vlnverse}</td>
                    <td className="py-1.5 px-3 text-center text-zinc-500">{row.vlntube}</td>
                    <td className="py-1.5 px-3 text-center text-emerald-400 font-semibold">{row.fleetsafe}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Footer */}
        <div className="border-t border-zinc-800 pt-6 text-[10px] text-zinc-600">
          <p>FleetSafe-VLN · Frank Leroy Van-Laarhoven · Newcastle University</p>
          <p className="mt-1">
            ORCID: 0009-0006-8931-0364 ·{" "}
            <a href={REPO} className="text-zinc-500 hover:text-zinc-300" target="_blank" rel="noreferrer">
              {REPO}
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
