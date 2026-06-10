"use client";

import { useEffect, useState, useCallback } from "react";
import { evidenceApi, type TimelineEvent } from "@/lib/api";
import { RefreshCw } from "lucide-react";

const TYPE_STYLE: Record<string, { color: string; dot: string; label: string }> = {
  benchmark_run: { color: "text-blue-400/70",    dot: "bg-blue-500",    label: "Benchmark"  },
  evidence:      { color: "text-purple-400/70",  dot: "bg-purple-500",  label: "Evidence"   },
  audit:         { color: "text-amber-400/60",   dot: "bg-amber-500",   label: "Audit"      },
  default:       { color: "text-muted-foreground/40", dot: "bg-border",  label: "Event"     },
};

function fmtDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString("en-US", {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

export default function TimelinePage() {
  const [events, setEvents]   = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter]   = useState<string>("");

  const load = useCallback(async () => {
    setLoading(true);
    try { setEvents(await evidenceApi.timeline()); } catch { /* */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = filter
    ? events.filter(e => e.type === filter || e.source === filter)
    : events;

  // Group by date
  const groups: Map<string, TimelineEvent[]> = new Map();
  for (const e of filtered) {
    const day = new Date(e.ts * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    if (!groups.has(day)) groups.set(day, []);
    groups.get(day)!.push(e);
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="px-6 py-3 border-b border-border shrink-0 flex items-center gap-4">
        <span className="font-mono text-sm font-bold tracking-widest text-foreground/80">PROJECT TIMELINE</span>
        <span className="font-mono text-[10px] text-muted-foreground/40">{filtered.length} events</span>

        <select value={filter} onChange={e => setFilter(e.target.value)}
          className="bg-background border border-border font-mono text-[8px] text-muted-foreground px-2 py-1 ml-2">
          <option value="">All types</option>
          <option value="benchmark_run">Benchmark runs</option>
          <option value="evidence">Evidence</option>
          <option value="audit">Audit</option>
        </select>

        <button onClick={load} disabled={loading} className="ml-auto flex items-center gap-1 font-mono text-[8px] text-muted-foreground/40 hover:text-muted-foreground border border-border px-2 py-1 transition-colors disabled:opacity-30">
          <RefreshCw size={9} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading && <div className="font-mono text-[8px] text-muted-foreground/20">Loading…</div>}

        {[...groups.entries()].map(([day, dayEvents]) => (
          <div key={day} className="mb-6">
            <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-2 border-b border-border pb-1">
              {day}
            </div>
            <div className="flex flex-col gap-0.5">
              {dayEvents.map((e, i) => {
                const style = TYPE_STYLE[e.type] ?? TYPE_STYLE.default;
                return (
                  <div key={i} className="flex items-start gap-3 py-1">
                    <div className="flex flex-col items-center shrink-0 pt-1.5">
                      <div className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
                      {i < dayEvents.length - 1 && <div className="w-px flex-1 bg-border/40 mt-1" style={{ minHeight: 12 }} />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-[8px] text-muted-foreground/30 shrink-0">
                          {new Date(e.ts * 1000).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit" })}
                        </span>
                        <span className={`font-mono text-[7px] font-semibold ${style.color}`}>
                          [{style.label}]
                        </span>
                        {e.source && (
                          <span className="font-mono text-[7px] text-muted-foreground/30">{e.source}</span>
                        )}
                        {e.run_id && (
                          <span className="font-mono text-[7px] text-blue-400/40 truncate">{e.run_id}</span>
                        )}
                        {e.sha256 && (
                          <span className="font-mono text-[7px] text-green-400/30 shrink-0">#{e.sha256.slice(0, 8)}</span>
                        )}
                      </div>
                      <div className="font-mono text-[8px] text-foreground/50 truncate">{e.description}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        {!loading && filtered.length === 0 && (
          <div className="font-mono text-[8px] text-muted-foreground/20">No events yet.</div>
        )}
      </div>
    </div>
  );
}
