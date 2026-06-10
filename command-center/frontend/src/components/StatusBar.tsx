"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export function StatusBar() {
  const [git, setGit]       = useState<{ commit: string; branch: string } | null>(null);
  const [online, setOnline]  = useState<boolean | null>(null);
  const [ts, setTs]          = useState("");

  useEffect(() => {
    api.git().then(setGit).catch(() => {});
    api.health()
      .then(() => setOnline(true))
      .catch(() => setOnline(false));
  }, []);

  useEffect(() => {
    const tick = () => setTs(new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC");
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const dot = online === null
    ? "bg-muted-foreground"
    : online
    ? "bg-green-500"
    : "bg-red-500";

  return (
    <div className="h-7 shrink-0 border-b border-border bg-card flex items-center px-4 gap-4 text-[10px] font-mono text-muted-foreground tracking-wide overflow-hidden">
      <span className="flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
        {online === null ? "connecting…" : online ? "api online" : "api offline"}
      </span>
      {git && (
        <>
          <span className="text-border">|</span>
          <span>{git.branch}</span>
          <span className="text-border">|</span>
          <span className="text-muted-foreground/60">{git.commit}</span>
        </>
      )}
      <span className="ml-auto">{ts}</span>
    </div>
  );
}
