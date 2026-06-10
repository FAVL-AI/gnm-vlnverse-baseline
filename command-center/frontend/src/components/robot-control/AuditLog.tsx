"use client";

import type { AuditEntry } from "@/lib/api";

interface Props {
  entries: AuditEntry[];
}

function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("en-US", { hour12: false });
}

export function AuditLog({ entries }: Props) {
  if (!entries.length) {
    return (
      <div className="font-mono text-[8px] text-muted-foreground/20 px-1">No audit entries yet.</div>
    );
  }

  return (
    <div className="flex flex-col gap-0.5 overflow-y-auto max-h-48">
      {entries.map((e, i) => (
        <div key={i} className="flex gap-2 font-mono text-[8px] leading-4">
          <span className="text-muted-foreground/30 shrink-0">{fmtTime(e.ts)}</span>
          <span className={`shrink-0 font-semibold ${e.dry_run ? "text-amber-400/50" : "text-green-400/70"}`}>
            {e.dry_run ? "DRY" : "LIVE"}
          </span>
          <span className="text-foreground/60 truncate">{e.op}</span>
          <span className="text-muted-foreground/30 truncate flex-1">{e.result}</span>
        </div>
      ))}
    </div>
  );
}
