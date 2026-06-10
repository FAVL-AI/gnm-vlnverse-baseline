"use client";

import { useCallback, useRef, useState } from "react";
import { consoleApi, type ConsoleExecResult } from "@/lib/api";

// ── Command palette definition ────────────────────────────────────────────────

interface CommandDef {
  name: string;
  label: string;
  /** amber warning style — potentially disruptive */
  caution?: boolean;
  /** requires double-click confirm before firing */
  requireConfirm?: boolean;
}

const COMMAND_GROUPS: { section: string; commands: CommandDef[] }[] = [
  {
    section: "Perception",
    commands: [
      { name: "start_perception", label: "start perception" },
      { name: "stop_perception",  label: "stop perception",  caution: true },
    ],
  },
  {
    section: "Recording",
    commands: [
      { name: "start_rosbag", label: "start rosbag" },
      { name: "stop_rosbag",  label: "stop rosbag",  caution: true },
    ],
  },
  {
    section: "Safety",
    commands: [
      { name: "run_preflight",    label: "run preflight" },
      { name: "arm_watchdog",     label: "arm watchdog" },
      { name: "disarm_watchdog",  label: "disarm watchdog", caution: true },
    ],
  },
  {
    section: "Motion",
    commands: [
      { name: "pulse_forward",  label: "pulse forward",   requireConfirm: true },
      { name: "zero_velocity",  label: "zero velocity",   caution: true },
    ],
  },
  {
    section: "Diagnostics",
    commands: [
      { name: "show_topics", label: "show topics" },
      { name: "show_nodes",  label: "show nodes" },
      { name: "tail_logs",   label: "tail logs" },
    ],
  },
];

// ── Terminal line helpers ─────────────────────────────────────────────────────

interface TermLine {
  ts: string;
  text: string;
  kind: "info" | "ok" | "err" | "cmd";
}

function fmtTime(): string {
  return new Date().toLocaleTimeString("en-US", { hour12: false });
}

function lineClass(kind: TermLine["kind"]): string {
  switch (kind) {
    case "ok":  return "text-green-400/80";
    case "err": return "text-red-400";
    case "cmd": return "text-foreground/60";
    default:    return "text-muted-foreground/50";
  }
}

function linePrefix(kind: TermLine["kind"]): string {
  switch (kind) {
    case "ok":  return "▶";
    case "err": return "✗";
    case "cmd": return "$";
    default:    return " ";
  }
}

const MAX_LINES = 200;

// ── Component ─────────────────────────────────────────────────────────────────

export function RobotConsole() {
  const [lines, setLines]       = useState<TermLine[]>([]);
  const [inflight, setInflight] = useState<string | null>(null);
  // For double-click confirm: track which command is pending confirm
  const [pendingConfirm, setPendingConfirm] = useState<string | null>(null);
  const confirmTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const push = useCallback((line: Omit<TermLine, "ts">) => {
    const entry: TermLine = { ts: fmtTime(), ...line };
    setLines(prev => [...prev.slice(-(MAX_LINES - 1)), entry]);
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 20);
  }, []);

  const fireCommand = useCallback(async (name: string) => {
    if (inflight) return;
    setInflight(name);
    push({ kind: "cmd", text: name });
    try {
      const result: ConsoleExecResult = await consoleApi.exec(name);
      if (result.dry_run) {
        push({ kind: "info", text: result.output });
      } else if (result.ok) {
        // Multi-line stdout
        const outLines = result.output.split("\n");
        for (const l of outLines) {
          push({ kind: "ok", text: l });
        }
      } else {
        const errLines = result.output.split("\n");
        for (const l of errLines) {
          push({ kind: "err", text: l });
        }
      }
    } catch (e) {
      push({ kind: "err", text: String(e) });
    } finally {
      setInflight(null);
    }
  }, [inflight, push]);

  function handleClick(cmd: CommandDef) {
    if (inflight) return;

    if (!cmd.requireConfirm) {
      fireCommand(cmd.name);
      return;
    }

    // Double-click confirm logic
    if (pendingConfirm === cmd.name) {
      // Second click — fire
      if (confirmTimer.current) clearTimeout(confirmTimer.current);
      setPendingConfirm(null);
      fireCommand(cmd.name);
    } else {
      // First click — arm confirm
      if (confirmTimer.current) clearTimeout(confirmTimer.current);
      setPendingConfirm(cmd.name);
      confirmTimer.current = setTimeout(() => {
        setPendingConfirm(null);
      }, 2000);
      push({ kind: "info", text: `Click again to confirm: ${cmd.name}` });
    }
  }

  function handleClear() {
    setLines([]);
  }

  return (
    <div className="flex h-full overflow-hidden border border-border">
      {/* Left: command palette */}
      <div className="w-48 shrink-0 border-r border-border overflow-y-auto flex flex-col">
        {COMMAND_GROUPS.map(group => (
          <div key={group.section} className="flex flex-col">
            <div className="px-3 pt-3 pb-1 font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
              {group.section}
            </div>
            {group.commands.map(cmd => {
              const isWaiting = pendingConfirm === cmd.name;
              const isRunning = inflight === cmd.name;
              return (
                <button
                  key={cmd.name}
                  onClick={() => handleClick(cmd)}
                  disabled={!!inflight && inflight !== cmd.name}
                  className={[
                    "text-left px-3 py-1.5 border-b border-border/40 font-mono text-[9px] transition-colors",
                    cmd.caution
                      ? "text-amber-400/80 hover:text-amber-300 hover:border-amber-500/30"
                      : "text-foreground/60 hover:text-foreground hover:border-foreground/20",
                    isWaiting  ? "border-amber-500/50 text-amber-300 bg-amber-500/5" : "",
                    isRunning  ? "opacity-50 cursor-wait" : "",
                    (!!inflight && inflight !== cmd.name) ? "opacity-30 pointer-events-none" : "",
                  ].join(" ")}
                >
                  {isRunning ? (
                    <span className="animate-pulse">{cmd.label}…</span>
                  ) : isWaiting ? (
                    <span>confirm?</span>
                  ) : (
                    cmd.label
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </div>

      {/* Right: terminal output */}
      <div className="flex-1 flex flex-col overflow-hidden bg-background">
        {/* Terminal header */}
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-border shrink-0">
          <span className="font-mono text-[8px] text-muted-foreground/40 uppercase tracking-wider">
            console output
            {inflight && <span className="ml-2 text-amber-400/70 animate-pulse">running: {inflight}</span>}
          </span>
          <button
            onClick={handleClear}
            className="font-mono text-[7px] text-muted-foreground/25 hover:text-muted-foreground transition-colors"
          >
            clear
          </button>
        </div>

        {/* Lines */}
        <div className="flex-1 overflow-y-auto px-3 py-2 flex flex-col gap-0.5">
          {lines.length === 0 && (
            <div className="font-mono text-[9px] text-muted-foreground/20">
              Select a command to execute on robot.
            </div>
          )}
          {lines.map((l, i) => (
            <div key={i} className={`font-mono text-[9px] leading-4 flex gap-1.5 ${lineClass(l.kind)}`}>
              <span className="shrink-0 text-muted-foreground/30 select-none">[{l.ts}]</span>
              <span className="shrink-0 select-none">{linePrefix(l.kind)}</span>
              <span className="break-all whitespace-pre-wrap">{l.text}</span>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}
