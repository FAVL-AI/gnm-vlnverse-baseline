"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  commissioningApi, fleetApi, sessionApi,
  type CommissioningStatus, type RobotSnapshot,
} from "@/lib/api";
import { useTelemetry } from "@/hooks/useTelemetry";
import { TelemetryPanel } from "@/components/TelemetryPanel";
import { StateMachine } from "@/components/commissioning/StateMachine";
import { ChecklistPanel } from "@/components/commissioning/ChecklistPanel";
import { CmdVelPreview } from "@/components/commissioning/CmdVelPreview";
import { AlertTriangle, Radio, ShieldCheck, Zap, ZapOff, Video, VideoOff, Download } from "lucide-react";

// ── State colour ──────────────────────────────────────────────────────────────

const STATE_BANNER: Record<string, { bg: string; text: string; label: string }> = {
  DISARMED:        { bg: "bg-card",                   text: "text-muted-foreground/40", label: "DISARMED" },
  MONITOR:         { bg: "bg-blue-500/10",             text: "text-blue-400",            label: "MONITOR ONLY" },
  ESTOP_VALIDATED: { bg: "bg-amber-500/10",            text: "text-amber-400",           label: "E-STOP VALIDATED" },
  ARMED:           { bg: "bg-green-500/10",            text: "text-green-400",           label: "ARMED" },
  RELAY_ENABLED:   { bg: "bg-red-500/10 border-red-500/30", text: "text-red-400",       label: "RELAY ENABLED" },
};

// ── Action button ─────────────────────────────────────────────────────────────

function ActionBtn({
  icon: Icon, label, onClick, variant = "default", disabled = false, pulse = false,
}: {
  icon: React.ElementType; label: string; onClick: () => void;
  variant?: "default" | "danger" | "primary" | "warning";
  disabled?: boolean; pulse?: boolean;
}) {
  const v = {
    default: "border-border text-muted-foreground hover:text-foreground hover:border-foreground/40",
    primary: "border-green-500/40 text-green-400 hover:border-green-500",
    warning: "border-amber-400/40 text-amber-400 hover:border-amber-500",
    danger:  "border-red-500/50 text-red-400 hover:border-red-500",
  }[variant];
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-2 px-3 py-2 border font-mono text-[10px] transition-colors
        ${v} ${disabled ? "opacity-30 pointer-events-none" : ""}
        ${pulse ? "animate-pulse" : ""}`}
    >
      <Icon size={12} strokeWidth={1.5} />
      {label}
    </button>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CommissioningPage() {
  const [status, setStatus]     = useState<CommissioningStatus | null>(null);
  const [robots, setRobots]     = useState<RobotSnapshot[]>([]);
  const [selectedRobot, setSelectedRobot] = useState("");
  const [busy, setBusy]         = useState(false);
  const [checking, setChecking] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [log, setLog]           = useState<string[]>([]);
  const logEndRef               = useRef<HTMLDivElement>(null);
  const telemetry               = useTelemetry();

  const pushLog = useCallback((msg: string) => {
    const ts = new Date().toLocaleTimeString("en-US", { hour12: false });
    setLog(l => [...l.slice(-100), `[${ts}] ${msg}`]);
    setTimeout(() => logEndRef.current?.scrollIntoView({ behavior: "smooth" }), 30);
  }, []);

  const applyStatus = useCallback((s: CommissioningStatus) => {
    setStatus(s);
    pushLog(s.last_event);
  }, [pushLog]);

  const call = useCallback(async (label: string, fn: () => Promise<CommissioningStatus>) => {
    setBusy(true);
    try {
      applyStatus(await fn());
    } catch (e) {
      pushLog(`ERROR: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }, [applyStatus, pushLog]);

  // Load robots + commissioning status on mount
  useEffect(() => {
    fleetApi.robots().then(r => {
      setRobots(r);
      if (r.length && !selectedRobot) setSelectedRobot(r[0].robot_id);
    }).catch(() => {});
    commissioningApi.status().then(applyStatus).catch(() => {});
    const t = setInterval(() => {
      commissioningApi.status().then(s => setStatus(s)).catch(() => {});
    }, 3000);
    return () => clearInterval(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleCheck() {
    setChecking(true);
    try { applyStatus(await commissioningApi.check()); }
    catch (e) { pushLog(`ERROR: ${String(e)}`); }
    finally { setChecking(false); }
  }

  async function toggleRecording() {
    if (sessionId) {
      try { await sessionApi.stop(sessionId); setSessionId(null); pushLog("Session stopped"); }
      catch { /* ignore */ }
    } else if (status?.robot_id) {
      try {
        const s = await sessionApi.start(status.robot_id);
        setSessionId(s.session_id);
        await commissioningApi.linkSession(s.session_id);
        pushLog(`Recording started: ${s.session_id}`);
      } catch { /* ignore */ }
    }
  }

  function downloadReport() {
    const sid = sessionId ?? status?.session_id;
    if (!sid) return;
    window.open(commissioningApi.reportUrl(sid), "_blank");
  }

  const state = status?.state ?? "DISARMED";
  const banner = STATE_BANNER[state] ?? STATE_BANNER.DISARMED;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* State banner */}
      <div className={`${banner.bg} border-b border-border px-6 py-3 flex items-center gap-4 shrink-0`}>
        <span className={`font-mono text-sm font-bold tracking-widest ${banner.text}`}>
          {banner.label}
        </span>
        {status?.robot_id && (
          <span className="font-mono text-[10px] text-muted-foreground/50">
            robot: <span className="text-foreground/70">{status.robot_id}</span>
          </span>
        )}
        {status?.last_event && (
          <span className="font-mono text-[9px] text-muted-foreground/40 truncate max-w-xs">
            {status.last_event}
          </span>
        )}

        {/* Global e-stop — always reachable */}
        <button
          onClick={() => call("E-STOP", commissioningApi.emergencyStop)}
          disabled={busy}
          className="ml-auto flex items-center gap-2 px-4 py-2 border border-red-500 text-red-400 font-mono text-[10px] font-semibold hover:bg-red-500/10 transition-colors disabled:opacity-30"
        >
          <AlertTriangle size={12} />
          E-STOP
        </button>
      </div>

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left column: state machine + actions */}
        <div className="w-56 shrink-0 border-r border-border flex flex-col gap-6 p-4 overflow-y-auto">
          <StateMachine current={state} />

          {/* Robot selector (only in DISARMED) */}
          {state === "DISARMED" && (
            <div className="flex flex-col gap-2">
              <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">Robot</div>
              <select
                value={selectedRobot}
                onChange={e => setSelectedRobot(e.target.value)}
                className="bg-background border border-border font-mono text-[9px] text-foreground px-2 py-1.5 w-full"
              >
                {robots.map(r => <option key={r.robot_id} value={r.robot_id}>{r.name}</option>)}
                {!robots.length && <option value="">No robots</option>}
              </select>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex flex-col gap-2">
            <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">Actions</div>

            {state === "DISARMED" && (
              <ActionBtn icon={Radio} label="Connect & Monitor"
                variant="primary" disabled={busy || !selectedRobot}
                onClick={() => call("connect", () => commissioningApi.connect(selectedRobot))} />
            )}

            {(state === "MONITOR" || state === "ESTOP_VALIDATED") && (
              <ActionBtn icon={ShieldCheck} label="Run E-Stop Test"
                variant="warning" disabled={busy}
                onClick={() => call("estop test", commissioningApi.estopTest)} />
            )}

            {state === "ESTOP_VALIDATED" && (
              <ActionBtn icon={Zap} label="Arm Robot"
                variant="primary" disabled={busy || !status?.can_arm}
                onClick={() => call("arm", commissioningApi.arm)} />
            )}

            {state === "ARMED" && (
              <ActionBtn icon={Zap} label="Enable Relay"
                variant="danger" pulse disabled={busy || !status?.can_relay}
                onClick={() => call("enable relay", commissioningApi.enableRelay)} />
            )}

            {state === "RELAY_ENABLED" && (
              <ActionBtn icon={ZapOff} label="Disable Relay"
                variant="warning" disabled={busy}
                onClick={() => call("disable relay", commissioningApi.disableRelay)} />
            )}

            {(state === "ARMED" || state === "RELAY_ENABLED") && (
              <ActionBtn icon={ShieldCheck} label="Disarm"
                variant="default" disabled={busy}
                onClick={() => call("disarm", commissioningApi.disarm)} />
            )}

            {state !== "DISARMED" && (
              <ActionBtn icon={Radio} label="Disconnect"
                variant="default" disabled={busy}
                onClick={() => call("disconnect", commissioningApi.disconnect)} />
            )}
          </div>

          {/* E-stop test result */}
          {status?.estop_test_result && (
            <div className={`font-mono text-[8px] border px-2 py-1.5 flex flex-col gap-0.5
              ${status.estop_test_result.passed ? "border-green-500/30 text-green-400/70" : "border-red-500/30 text-red-400"}`}>
              <span className="font-semibold">{status.estop_test_result.passed ? "✓ E-STOP PASS" : "✗ E-STOP FAIL"}</span>
              <span className="text-muted-foreground/50">{status.estop_test_result.latency_ms.toFixed(0)} ms latency</span>
            </div>
          )}
        </div>

        {/* Centre: telemetry */}
        <div className="flex-1 flex flex-col overflow-hidden border-r border-border">
          <div className="px-4 py-2 border-b border-border font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider shrink-0">
            Live Telemetry
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <TelemetryPanel />
          </div>
        </div>

        {/* Right column: checklist + cmd_vel + session + log */}
        <div className="w-64 shrink-0 flex flex-col overflow-hidden">
          <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-5">

            {/* Checklist */}
            {status && (
              <ChecklistPanel status={status} onCheck={handleCheck} checking={checking} />
            )}

            {/* cmd_vel preview */}
            <div className="border-t border-border pt-4">
              <CmdVelPreview telemetry={telemetry} state={state} />
            </div>

            {/* Session recording */}
            {state !== "DISARMED" && (
              <div className="border-t border-border pt-4 flex flex-col gap-2">
                <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">Session</div>
                <button
                  onClick={toggleRecording}
                  className={`flex items-center gap-2 px-3 py-2 border font-mono text-[9px] transition-colors
                    ${sessionId
                      ? "border-red-500/40 text-red-400 hover:border-red-500"
                      : "border-border text-muted-foreground/40 hover:border-foreground/30 hover:text-muted-foreground"}`}
                >
                  {sessionId ? <><VideoOff size={11} /> Stop Recording</> : <><Video size={11} /> Start Recording</>}
                </button>
                {sessionId && (
                  <div className="font-mono text-[8px] text-red-400/60 animate-pulse">⏺ Recording {sessionId}</div>
                )}
                {(sessionId ?? status?.session_id) && (
                  <button
                    onClick={downloadReport}
                    className="flex items-center gap-2 px-3 py-2 border border-border font-mono text-[9px] text-muted-foreground hover:border-foreground/30 hover:text-foreground transition-colors"
                  >
                    <Download size={11} /> Export Incident Report
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Event log */}
          <div className="border-t border-border flex flex-col" style={{ maxHeight: 160 }}>
            <div className="flex items-center justify-between px-3 py-1.5 shrink-0">
              <span className="font-mono text-[8px] text-muted-foreground/40 uppercase tracking-wider">Event Log</span>
              <button onClick={() => setLog([])} className="font-mono text-[7px] text-muted-foreground/20 hover:text-muted-foreground transition-colors">clear</button>
            </div>
            <div className="overflow-y-auto px-2 pb-2 flex flex-col gap-0.5">
              {log.map((line, i) => (
                <div key={i} className={`font-mono text-[8px] leading-4 ${
                  /error|fail/i.test(line) ? "text-red-400" :
                  /stop|disarm/i.test(line) ? "text-amber-400" :
                  /relay|armed|record/i.test(line) ? "text-green-400/70" :
                  "text-muted-foreground/40"
                }`}>{line}</div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
