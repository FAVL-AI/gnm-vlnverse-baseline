"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  robotApi, rosGraphApi,
  type OpResult, type RelayGuardResult, type GraphResult, type AuditEntry,
  type LatchStatus, type RelayStatus, type WatchdogStatus, type DemoStatus,
  type RealSession, type YoloStatus, type PreflightResult, type RosGraphState,
} from "@/lib/api";
import { QuickBar } from "@/components/robot-control/QuickBar";
import { RelayGuard } from "@/components/robot-control/RelayGuard";
import { AuditLog } from "@/components/robot-control/AuditLog";
import { VoiceControl } from "@/components/robot-control/VoiceControl";
import { EstopLatch } from "@/components/robot-control/EstopLatch";
import { WatchdogStatus as WatchdogPanel } from "@/components/robot-control/WatchdogStatus";
import { DemoMode } from "@/components/robot-control/DemoMode";
import { YoloMode } from "@/components/robot-control/YoloMode";
import { SessionCapture } from "@/components/robot-control/SessionCapture";
import { RobotConsole } from "@/components/robot-control/RobotConsole";
import { RosGraphVisualizer } from "@/components/RosGraphVisualizer";
import { AlertTriangle, ToggleLeft, ToggleRight } from "lucide-react";

const OP_HANDLERS: Record<string, () => Promise<OpResult>> = {
  start_agent:      () => robotApi.startAgent(),
  start_fleetsafe:  () => robotApi.startFleetsafe(),
  stop_fleetsafe:   () => robotApi.stopFleetsafe(),
  stop_conflicting: () => robotApi.stopConflicting(),
  stop_relay:       () => robotApi.relayManagedStop("manual"),
  zero:             () => robotApi.zero(),
  pulse_forward:    () => robotApi.pulseForward(),
  pulse_back:       () => robotApi.pulseBack(),
  pulse_left:       () => robotApi.pulseLeft(),
  pulse_right:      () => robotApi.pulseRight(),
};

function logClass(line: string): string {
  if (/error|fail|emergency/i.test(line)) return "text-red-400";
  if (/dry|\[dry\]/i.test(line))  return "text-amber-400/60";
  if (/\[live\]|relay on|armed/i.test(line)) return "text-red-400/80";
  if (/pass|ok|start|done/i.test(line))      return "text-green-400/70";
  return "text-muted-foreground/40";
}

export default function RobotControlPage() {
  const [dryRun, setDryRun]               = useState(true);
  const [host, setHost]                   = useState("…");
  const [busy, setBusy]                   = useState(false);
  const [guardResult, setGuardResult]     = useState<RelayGuardResult | null>(null);
  const [guardLoading, setGuardLoading]   = useState(false);
  const [graphResult, setGraphResult]     = useState<GraphResult | null>(null);
  const [auditEntries, setAuditEntries]   = useState<AuditEntry[]>([]);
  const [voiceMap, setVoiceMap]           = useState<Record<string, string>>({});
  const [log, setLog]                     = useState<string[]>([]);
  const [showVoice, setShowVoice]         = useState(false);
  const [latchStatus, setLatchStatus]     = useState<LatchStatus | null>(null);
  const [relayStatus, setRelayStatus]     = useState<RelayStatus | null>(null);
  const [watchdogStatus, setWatchdogStatus] = useState<WatchdogStatus | null>(null);
  const [demoStatus, setDemoStatus]       = useState<DemoStatus | null>(null);
  const [yoloStatus, setYoloStatus]       = useState<YoloStatus | null>(null);
  const [activeSession, setActiveSession] = useState<RealSession | null>(null);
  const [preflightResult, setPreflightResult] = useState<PreflightResult | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [rosGraph, setRosGraph]           = useState<RosGraphState | null>(null);
  const [rosGraphLoading, setRosGraphLoading] = useState(false);
  const logEndRef                         = useRef<HTMLDivElement>(null);

  const push = useCallback((msg: string) => {
    const ts = new Date().toLocaleTimeString("en-US", { hour12: false });
    setLog(prev => [...prev.slice(-200), `[${ts}] ${msg}`]);
    setTimeout(() => logEndRef.current?.scrollIntoView({ behavior: "smooth" }), 30);
  }, []);

  const refreshAudit    = useCallback(async () => { try { setAuditEntries(await robotApi.auditLog(50)); } catch { /* */ } }, []);
  const refreshLatch    = useCallback(async () => { try { setLatchStatus(await robotApi.estopStatus()); } catch { /* */ } }, []);
  const refreshRelay    = useCallback(async () => { try { setRelayStatus(await robotApi.relayStatus()); } catch { /* */ } }, []);
  const refreshWd       = useCallback(async () => { try { setWatchdogStatus(await robotApi.watchdogStatus()); } catch { /* */ } }, []);
  const refreshDemo     = useCallback(async () => { try { setDemoStatus(await robotApi.demoStatus()); } catch { /* */ } }, []);
  const refreshYolo     = useCallback(async () => { try { setYoloStatus(await robotApi.yoloStatus()); } catch { /* */ } }, []);
  const refreshRosGraph = useCallback(async () => {
    setRosGraphLoading(true);
    try { setRosGraph(await rosGraphApi.state()); } catch { /* */ }
    finally { setRosGraphLoading(false); }
  }, []);

  useEffect(() => {
    robotApi.status().then(s => { setDryRun(s.dry_run); setHost(s.host); }).catch(() => {});
    robotApi.voiceMap().then(r => setVoiceMap(r.map)).catch(() => {});
    refreshAudit(); refreshLatch(); refreshRelay(); refreshWd(); refreshDemo(); refreshYolo();
    refreshRosGraph();

    const t = setInterval(() => {
      refreshAudit(); refreshLatch(); refreshRelay(); refreshWd(); refreshDemo(); refreshYolo();
      refreshRosGraph();
    }, 3000);
    return () => clearInterval(t);
  }, [refreshAudit, refreshLatch, refreshRelay, refreshWd, refreshDemo, refreshYolo, refreshRosGraph]);

  async function toggleDryRun() {
    try {
      const r = await robotApi.setDryRun(!dryRun);
      setDryRun(r.dry_run);
      push(`Dry-run ${r.dry_run ? "enabled" : "DISABLED — commands execute on robot"}`);
    } catch { push("ERROR: failed to toggle dry-run"); }
  }

  async function runRelayGuard() {
    setGuardLoading(true);
    try {
      const r = await robotApi.relayGuard();
      setGuardResult(r);
      push(`Relay guard: ${r.pass ? "PASS" : "FAIL"} (${r.checks.filter(c => c.pass).length}/${r.checks.length} ok)`);
    } catch (e) { push(`ERROR: relay guard — ${String(e)}`); }
    finally { setGuardLoading(false); }
  }

  async function handleLatch() {
    try { const r = await robotApi.estopLatch("manual"); setLatchStatus(r); push("E-stop latched"); }
    catch (e) { push(`ERROR: latch — ${String(e)}`); }
  }

  async function handleClear() {
    try { const r = await robotApi.estopClear("operator"); setLatchStatus(r); push("E-stop latch cleared"); }
    catch (e) { push(`ERROR: clear — ${String(e)}`); }
  }

  async function handleRelayStart() {
    setBusy(true);
    try {
      const r = await robotApi.relayManagedStart();
      push(r.ok ? "[LIVE] Relay ENABLED via managed start" : `ERROR: ${r.error}`);
      refreshRelay();
    } catch (e) { push(`ERROR: relay start — ${String(e)}`); }
    finally { setBusy(false); }
  }

  async function handleWdStart() {
    try { await robotApi.watchdogStart(); refreshWd(); push("Watchdog armed"); }
    catch { push("ERROR: watchdog start"); }
  }

  async function handleWdStop() {
    try { await robotApi.watchdogStop(); refreshWd(); push("Watchdog disarmed"); }
    catch { push("ERROR: watchdog stop"); }
  }

  async function runPreflight() {
    setPreflightLoading(true);
    try {
      const r = await robotApi.preflight();
      setPreflightResult(r);
      if (r.pass) {
        push(`Preflight PASS — no blocked /cmd_vel publishers`);
      } else {
        push(`Preflight FAIL — UNSAFE_CMDVEL_PUBLISHER: ${r.blocked.join(", ")}`);
      }
    } catch (e) { push(`ERROR: preflight — ${String(e)}`); }
    finally { setPreflightLoading(false); }
  }

  async function killLaunchSource(nodeName: string) {
    setBusy(true);
    try {
      const r = await robotApi.killLaunchSource(nodeName);
      push(`${r.dry_run ? "[DRY]" : "[LIVE]"} kill ${nodeName}: ${r.ok ? "killed" : `ERROR: ${r.error}`}`);
      await runPreflight();
    } catch (e) { push(`ERROR: kill ${nodeName} — ${String(e)}`); }
    finally { setBusy(false); }
  }

  async function handleDemoStart() {
    setBusy(true);
    try {
      const r = await robotApi.demoStart();
      push(r.ok ? "Demo started" : `Demo rejected: ${r.state}`);
      refreshDemo();
    } catch (e) { push(`ERROR: demo — ${String(e)}`); }
    finally { setBusy(false); }
  }

  async function handleDemoAbort() {
    try { await robotApi.demoAbort(); push("Demo aborted"); refreshDemo(); }
    catch { push("ERROR: demo abort"); }
  }

  async function handleYoloStart() {
    setBusy(true);
    try {
      const r = await robotApi.yoloStart();
      push(r.ok ? `${r.dry_run ? "[DRY]" : "[LIVE]"} YOLO node started` : `ERROR: ${String((r as { error?: string }).error ?? "unknown")}`);
      refreshYolo();
    } catch (e) { push(`ERROR: yolo start — ${String(e)}`); }
    finally { setBusy(false); }
  }

  async function handleYoloStop() {
    setBusy(true);
    try {
      const r = await robotApi.yoloStop();
      push(r.ok ? "YOLO node stopped → mock mode" : `ERROR: ${String((r as { error?: string }).error ?? "unknown")}`);
      refreshYolo();
    } catch (e) { push(`ERROR: yolo stop — ${String(e)}`); }
    finally { setBusy(false); }
  }

  async function handleSessionStart(robotId: string) {
    setBusy(true);
    try {
      const r = await robotApi.sessionStart(robotId);
      setActiveSession(r);
      push(`${r.ok ? "[REC]" : "ERROR:"} Session started: ${r.session_id} (${r.n_topics} topics)`);
    } catch (e) { push(`ERROR: session start — ${String(e)}`); }
    finally { setBusy(false); }
  }

  async function handleSessionStop(sessionId: string) {
    setBusy(true);
    try {
      const r = await robotApi.sessionStop(sessionId);
      setActiveSession(r);
      const hash = r.sha256 ? r.sha256.slice(0, 12) : "no hash";
      push(`Session stopped: ${sessionId} — evidence #${hash} (${r.duration_s?.toFixed(0) ?? "?"}s)`);
    } catch (e) { push(`ERROR: session stop — ${String(e)}`); }
    finally { setBusy(false); }
  }

  async function handleAction(id: string) {
    if (id === "relay_guard")  { return runRelayGuard(); }
    if (id === "verify_graph") {
      try {
        const r = await robotApi.graph();
        setGraphResult(r);
        push(`Graph: ${r.nodes.length} nodes, ${r.topics.length} topics`);
      } catch (e) { push(`ERROR: graph — ${String(e)}`); }
      return;
    }
    if (id === "audit")  { return refreshAudit(); }
    if (id === "voice")  { setShowVoice(v => !v); return; }
    if (id === "start_relay") { return handleRelayStart(); }

    const fn = OP_HANDLERS[id];
    if (!fn) return;
    setBusy(true);
    try {
      const r = await fn();
      const tag = r.dry_run ? "[DRY]" : "[LIVE]";
      push(`${tag} ${id}: ${r.ok ? (r.output ?? "ok") : `ERROR: ${r.error}`}`);
      refreshAudit(); refreshRelay();
    } catch (e) { push(`ERROR: ${id} — ${String(e)}`); }
    finally { setBusy(false); }
  }

  function handleVoice(opId: string, phrase: string) {
    push(`VOICE: "${phrase}" → ${opId}`);
    handleAction(opId);
  }

  const relayLocked = !guardResult?.pass;
  const estopLatched = latchStatus?.latched ?? false;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ROS Graph — full width, fixed height */}
      <RosGraphVisualizer
        state={rosGraph}
        loading={rosGraphLoading}
        onRefresh={refreshRosGraph}
      />

      {/* Header */}
      <div className={`flex items-center gap-4 px-6 py-3 border-b border-border shrink-0 ${
        estopLatched ? "bg-red-500/5" : ""
      }`}>
        <span className="font-mono text-sm font-bold tracking-widest text-foreground/80">
          ROBOT CONTROL
        </span>
        <span className="font-mono text-[10px] text-muted-foreground/50">{host}</span>

        {estopLatched && (
          <span className="font-mono text-[9px] text-red-400 font-semibold border border-red-500/60 px-2 py-1 animate-pulse">
            ⚡ E-STOP LATCHED
          </span>
        )}

        {preflightResult && !preflightResult.pass && (
          <span className="font-mono text-[9px] text-red-400 font-semibold border border-red-500/60 px-2 py-1 animate-pulse">
            ⛔ UNSAFE_CMDVEL_PUBLISHER
          </span>
        )}

        <button
          onClick={toggleDryRun}
          className={`ml-2 flex items-center gap-1.5 font-mono text-[9px] px-2 py-1 border transition-colors
            ${dryRun
              ? "border-amber-500/30 text-amber-400/70 hover:border-amber-500"
              : "border-red-500/60 text-red-400 animate-pulse"}`}
        >
          {dryRun ? <><ToggleLeft size={11} /> DRY RUN</> : <><ToggleRight size={11} /> LIVE MODE</>}
        </button>

        <button
          onClick={() => handleAction("zero")}
          disabled={busy}
          className="ml-auto flex items-center gap-2 px-4 py-2 border border-red-500 text-red-400
            font-mono text-[10px] font-semibold hover:bg-red-500/10 transition-colors disabled:opacity-30"
        >
          <AlertTriangle size={12} /> E-STOP / ZERO
        </button>
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left: quick bar */}
        <div className="w-60 shrink-0 border-r border-border p-4 overflow-y-auto">
          <QuickBar onAction={handleAction} busy={busy} relayLocked={relayLocked || estopLatched} />
        </div>

        {/* Centre: safety panels */}
        <div className="flex-1 flex flex-col gap-3 p-4 overflow-y-auto border-r border-border">

          {/* Preflight — must pass before any motion test */}
          <div className="border border-border p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
                Safe Motion Preflight
              </span>
              <div className="flex items-center gap-2">
                {preflightResult && (
                  <span className={`font-mono text-[8px] font-semibold px-1.5 py-0.5 border ${
                    preflightResult.pass
                      ? "border-green-500/40 text-green-400/80"
                      : "border-red-500/60 text-red-400 animate-pulse"
                  }`}>
                    {preflightResult.pass ? "PASS" : "UNSAFE_CMDVEL_PUBLISHER"}
                  </span>
                )}
                <button
                  onClick={runPreflight}
                  disabled={preflightLoading || busy}
                  className="font-mono text-[8px] px-2 py-0.5 border border-border hover:border-foreground/30
                    text-muted-foreground/50 hover:text-foreground/70 transition-colors disabled:opacity-30"
                >
                  {preflightLoading ? "checking…" : "run preflight"}
                </button>
              </div>
            </div>

            {preflightResult && (
              <div className="space-y-1">
                {preflightResult.publishers.length === 0 && (
                  <div className="font-mono text-[8px] text-muted-foreground/40">
                    {preflightResult.dry_run ? "dry_run — no SSH probe" : "No /cmd_vel publishers detected"}
                  </div>
                )}
                {preflightResult.publishers.map(pub => (
                  <div key={pub.node} className="flex items-center gap-2">
                    <span className={`font-mono text-[8px] w-14 shrink-0 ${
                      pub.verdict === "BLOCKED" ? "text-red-400" : "text-green-400/70"
                    }`}>
                      {pub.verdict}
                    </span>
                    <span className="font-mono text-[8px] text-foreground/60 flex-1 truncate">{pub.node}</span>
                    {pub.verdict === "BLOCKED" && (
                      <button
                        onClick={() => killLaunchSource(pub.node)}
                        disabled={busy}
                        className="font-mono text-[7px] px-1.5 py-0.5 border border-red-500/40
                          text-red-400/80 hover:bg-red-500/10 transition-colors disabled:opacity-30 shrink-0"
                      >
                        kill source
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* E-stop latch */}
          <EstopLatch
            status={latchStatus}
            onLatch={handleLatch}
            onClear={handleClear}
            busy={busy}
          />

          {/* Relay guard */}
          <div className="border border-border p-3">
            <RelayGuard
              result={guardResult}
              loading={guardLoading}
              onCheck={runRelayGuard}
              onConfirmRelay={handleRelayStart}
              busy={busy || estopLatched}
            />
          </div>

          {/* Watchdog */}
          <div className="border border-border p-3">
            <WatchdogPanel
              status={watchdogStatus}
              onStart={handleWdStart}
              onStop={handleWdStop}
              busy={busy}
            />
          </div>

          {/* Demo mode */}
          <div className="border border-border p-3">
            <DemoMode
              status={demoStatus}
              onStart={handleDemoStart}
              onAbort={handleDemoAbort}
              busy={busy}
              estopLatched={estopLatched}
            />
          </div>

          {/* YOLO mode */}
          <div className="border border-border p-3">
            <YoloMode
              status={yoloStatus}
              onStart={handleYoloStart}
              onStop={handleYoloStop}
              busy={busy}
            />
          </div>

          {/* Session capture */}
          <div className="border border-border p-3">
            <SessionCapture
              session={activeSession}
              robotId={host}
              onStart={handleSessionStart}
              onStop={handleSessionStop}
              busy={busy}
            />
          </div>

          {/* Graph */}
          {graphResult && (
            <div className="border border-border p-3 grid grid-cols-2 gap-4">
              <div>
                <div className="font-mono text-[8px] text-muted-foreground/40 mb-1">Nodes ({graphResult.nodes.length})</div>
                {graphResult.nodes.map(n => (
                  <div key={n} className={`font-mono text-[8px] ${n.includes("fleetsafe") ? "text-green-400/70" : "text-foreground/50"}`}>{n}</div>
                ))}
              </div>
              <div>
                <div className="font-mono text-[8px] text-muted-foreground/40 mb-1">Topics ({graphResult.topics.length})</div>
                {graphResult.topics.map(t => (
                  <div key={t} className={`font-mono text-[8px] ${
                    t.includes("cmd_vel_safe") ? "text-green-400/70" :
                    t.includes("cmd_vel") ? "text-amber-400/70" : "text-foreground/40"}`}>{t}</div>
                ))}
              </div>
            </div>
          )}

          {/* Voice */}
          {showVoice && (
            <div className="border border-border p-3">
              <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-2">
                Voice (say &quot;Neo …&quot;)
              </div>
              <VoiceControl voiceMap={voiceMap} onCommand={handleVoice} />
            </div>
          )}
        </div>

        {/* Console panel */}
        <div className="w-80 shrink-0 border-r border-border flex flex-col overflow-hidden">
          <div className="px-4 py-2.5 border-b border-border shrink-0">
            <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">Robot Console</span>
          </div>
          <div className="flex-1 overflow-hidden">
            <RobotConsole />
          </div>
        </div>

        {/* Right: audit + event log */}
        <div className="w-72 shrink-0 flex flex-col overflow-hidden">
          <div className="px-4 py-2.5 border-b border-border shrink-0 flex items-center justify-between">
            <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">Audit Log</span>
            <button onClick={refreshAudit} className="font-mono text-[8px] text-muted-foreground/30 hover:text-muted-foreground transition-colors">refresh</button>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            <AuditLog entries={auditEntries} />
          </div>

          <div className="border-t border-border flex flex-col" style={{ maxHeight: 220 }}>
            <div className="flex items-center justify-between px-3 py-1.5 shrink-0">
              <span className="font-mono text-[8px] text-muted-foreground/40 uppercase tracking-wider">Event Log</span>
              <button onClick={() => setLog([])} className="font-mono text-[7px] text-muted-foreground/20 hover:text-muted-foreground transition-colors">clear</button>
            </div>
            <div className="overflow-y-auto px-2 pb-2 flex flex-col gap-0.5">
              {log.map((line, i) => (
                <div key={i} className={`font-mono text-[8px] leading-4 ${logClass(line)}`}>{line}</div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
