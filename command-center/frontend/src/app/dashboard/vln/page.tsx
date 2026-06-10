"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface VLNStatus {
  latest_instruction: string | null;
  parsed_instruction: Record<string, unknown> | null;
  chosen_subgoal: Record<string, unknown> | null;
  model: string;
  u_nom: number[];
  u_safe: number[];
  cbf_active: boolean;
  qp_status: string;
  last_cert_safe: boolean | null;
  trace_count: number;
}

interface InstructionResult {
  instruction_id: string;
  parsed_action: string;
  label: string;
  confidence: number;
  u_nom: number[];
  u_safe: number[];
  cbf_active: boolean;
  qp_status: string;
  clarification_needed: boolean;
  explanation: string;
  latency_ms: number;
}

const PIPELINE_STEPS = [
  "Voice / Text / Image",
  "Language Grounding",
  "Subgoal / Waypoint",
  "GNM / ViNT / NoMaD → u_nom",
  "FleetSafe CBF-QP → u_safe",
  "✓ /cmd_vel",
];

function Badge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-xs font-mono font-semibold ${
        ok ? "bg-emerald-900 text-emerald-200" : "bg-red-900 text-red-200"
      }`}
    >
      {label}
    </span>
  );
}

function vel(v: number) { return v.toFixed(3); }
function pct(v: number) { return (v * 100).toFixed(0) + "%"; }

export default function VLNPage() {
  const [status, setStatus]       = useState<VLNStatus | null>(null);
  const [text, setText]           = useState("");
  const [result, setResult]       = useState<InstructionResult | null>(null);
  const [loading, setLoading]     = useState(false);
  const [stopped, setStopped]     = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [traces, setTraces]       = useState<unknown[]>([]);
  const intervalRef               = useRef<ReturnType<typeof setInterval>>();

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/vln/status`);
      if (r.ok) setStatus(await r.json());
    } catch {}
  }, []);

  const fetchTraces = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/vln/trace/latest?n=5`);
      if (r.ok) {
        const d = await r.json();
        setTraces(d.traces ?? []);
      }
    } catch {}
  }, []);

  useEffect(() => {
    fetchStatus();
    fetchTraces();
    intervalRef.current = setInterval(() => {
      fetchStatus();
      fetchTraces();
    }, 2000);
    return () => clearInterval(intervalRef.current);
  }, [fetchStatus, fetchTraces]);

  const sendInstruction = async () => {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    setStopped(false);
    try {
      const r = await fetch(`${API}/api/vln/instruction`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, source: "text" }),
      });
      if (!r.ok) throw new Error(await r.text());
      const d: InstructionResult = await r.json();
      setResult(d);
      fetchStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const emergencyStop = async () => {
    setStopped(true);
    try {
      await fetch(`${API}/api/vln/stop`, { method: "POST" });
      fetchStatus();
    } catch {}
  };

  const safeColor = (v: boolean | null) =>
    v === true ? "text-emerald-400" : v === false ? "text-red-400" : "text-zinc-400";

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6 font-mono">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">FleetSafe-VLN Command Center</h1>
        <p className="text-zinc-400 text-sm mt-1">
          Voice / Text / Image → Language Grounding → Visual Navigation Backbone → CBF-QP Safety → Robot
        </p>
      </div>

      {/* Pipeline diagram */}
      <div className="flex flex-wrap gap-1 items-center mb-6 text-xs">
        {PIPELINE_STEPS.map((s, i) => (
          <span key={i} className="flex items-center gap-1">
            <span className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200">{s}</span>
            {i < PIPELINE_STEPS.length - 1 && <span className="text-zinc-600">→</span>}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Left column */}
        <div className="flex flex-col gap-4">
          {/* Instruction input */}
          <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4">
            <h2 className="text-sm font-semibold text-zinc-300 mb-3">Language Instruction</h2>
            <textarea
              className="w-full bg-zinc-800 border border-zinc-600 rounded p-2 text-sm text-zinc-100 resize-none focus:outline-none focus:border-blue-500"
              rows={3}
              placeholder='e.g. "go to the nurse station and avoid people"'
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendInstruction(); } }}
            />
            <div className="flex gap-2 mt-2">
              <button
                className="flex-1 bg-blue-700 hover:bg-blue-600 disabled:bg-zinc-700 text-white rounded py-1.5 text-sm font-semibold transition"
                onClick={sendInstruction}
                disabled={loading || !text.trim()}
              >
                {loading ? "Processing…" : "Send Instruction"}
              </button>
              <button
                className="bg-red-800 hover:bg-red-700 text-white rounded px-4 py-1.5 text-sm font-bold transition"
                onClick={emergencyStop}
              >
                ■ STOP
              </button>
            </div>
            {stopped && <p className="text-red-400 text-xs mt-1">Emergency stop latched.</p>}
            {error && <p className="text-red-400 text-xs mt-1">Error: {error}</p>}
          </div>

          {/* Parsed instruction result */}
          {result && (
            <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4">
              <h2 className="text-sm font-semibold text-zinc-300 mb-3">
                Parsed Instruction
                <span className="ml-2 text-xs text-zinc-500">id:{result.instruction_id}</span>
              </h2>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <span className="text-zinc-400">Action</span>
                <span className="text-white font-semibold">{result.parsed_action}</span>
                <span className="text-zinc-400">Label</span>
                <span className="text-white">{result.label || "—"}</span>
                <span className="text-zinc-400">Confidence</span>
                <span className={result.confidence >= 0.6 ? "text-emerald-400" : "text-amber-400"}>
                  {pct(result.confidence)}
                </span>
                <span className="text-zinc-400">Clarification?</span>
                <Badge ok={!result.clarification_needed} label={result.clarification_needed ? "NEEDED" : "OK"} />
                <span className="text-zinc-400">Latency</span>
                <span className="text-zinc-200">{result.latency_ms.toFixed(1)} ms</span>
              </div>
              {result.explanation && (
                <p className="text-zinc-500 text-xs mt-2 border-t border-zinc-800 pt-2">{result.explanation}</p>
              )}
            </div>
          )}

          {/* Command comparison */}
          {result && (
            <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4">
              <h2 className="text-sm font-semibold text-zinc-300 mb-3">u_nom → CBF-QP → u_safe</h2>
              <div className="grid grid-cols-3 gap-3 text-xs text-center">
                <div>
                  <p className="text-zinc-500 mb-1">u_nom (nominal)</p>
                  <p className="text-amber-400 text-base font-mono">vx {vel(result.u_nom[0])}</p>
                  <p className="text-amber-400 font-mono">wz {vel(result.u_nom[1])}</p>
                </div>
                <div className="flex flex-col items-center justify-center text-zinc-600">
                  <span className="text-lg">→</span>
                  <Badge ok={result.cbf_active} label={result.cbf_active ? "CBF" : "pass"} />
                  <span className="text-zinc-600 text-xs mt-1">{result.qp_status}</span>
                </div>
                <div>
                  <p className="text-zinc-500 mb-1">u_safe (certified)</p>
                  <p className="text-emerald-400 text-base font-mono">vx {vel(result.u_safe[0])}</p>
                  <p className="text-emerald-400 font-mono">wz {vel(result.u_safe[1])}</p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right column */}
        <div className="flex flex-col gap-4">
          {/* Live status */}
          <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4">
            <h2 className="text-sm font-semibold text-zinc-300 mb-3">VLN System Status</h2>
            {status ? (
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <span className="text-zinc-400">Latest instruction</span>
                <span className="text-zinc-200 truncate">{status.latest_instruction ?? "—"}</span>
                <span className="text-zinc-400">Model</span>
                <span className="text-white font-semibold">{status.model}</span>
                <span className="text-zinc-400">u_nom</span>
                <span className="text-amber-400 font-mono">
                  [{vel(status.u_nom[0])}, {vel(status.u_nom[1])}]
                </span>
                <span className="text-zinc-400">u_safe</span>
                <span className="text-emerald-400 font-mono">
                  [{vel(status.u_safe[0])}, {vel(status.u_safe[1])}]
                </span>
                <span className="text-zinc-400">CBF active</span>
                <Badge ok={!status.cbf_active} label={status.cbf_active ? "ACTIVE" : "passive"} />
                <span className="text-zinc-400">QP status</span>
                <span className={`font-mono ${status.qp_status === "optimal" ? "text-emerald-400" : "text-zinc-400"}`}>
                  {status.qp_status}
                </span>
                <span className="text-zinc-400">Certificate safe</span>
                <span className={safeColor(status.last_cert_safe)}>
                  {status.last_cert_safe === null ? "—" : status.last_cert_safe ? "PASS" : "FAIL"}
                </span>
                <span className="text-zinc-400">Trace count</span>
                <span className="text-zinc-200">{status.trace_count}</span>
              </div>
            ) : (
              <p className="text-zinc-500 text-xs">Connecting to backend…</p>
            )}
          </div>

          {/* Camera frame placeholder */}
          <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4">
            <h2 className="text-sm font-semibold text-zinc-300 mb-2">Live Camera</h2>
            <div className="aspect-video bg-zinc-800 rounded flex items-center justify-center">
              <img
                src="http://127.0.0.1:8081/snapshot.bmp"
                alt="camera"
                className="max-h-full max-w-full rounded"
                onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
              />
              <p className="text-zinc-600 text-xs absolute">
                Camera at {"{"}127.0.0.1:8081{"}"} — start: <code>make camera-viewer</code>
              </p>
            </div>
          </div>

          {/* Recent traces */}
          {traces.length > 0 && (
            <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4">
              <h2 className="text-sm font-semibold text-zinc-300 mb-2">Recent Decisions</h2>
              <div className="space-y-1">
                {(traces as Array<Record<string, unknown>>).map((t, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs text-zinc-400 border-b border-zinc-800 pb-1">
                    <span className="text-zinc-600 w-12 shrink-0">
                      {new Date((t.ts as number) * 1000).toLocaleTimeString()}
                    </span>
                    <span className="text-zinc-200 truncate flex-1">{t.instruction as string}</span>
                    <span className="text-zinc-500 shrink-0">{t.action as string}</span>
                    {t.cbf && <Badge ok={false} label="CBF" />}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Mode explanation */}
          <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4 text-xs text-zinc-500">
            <p className="font-semibold text-zinc-400 mb-1">Motion mode</p>
            <p>All commands shown here are in <strong className="text-zinc-300">DRY-RUN</strong> mode by default.</p>
            <p className="mt-1">To enable live robot motion: <code className="text-amber-400">make vln-demo-live</code></p>
            <p className="mt-1">Voice input: <code className="text-amber-400">make voice-start-robot</code> on Jetson</p>
          </div>
        </div>
      </div>
    </div>
  );
}
