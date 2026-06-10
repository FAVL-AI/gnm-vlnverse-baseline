"use client";

import { Fragment, useEffect, useState } from "react";
import { replayApi, type CompareResult, type SafetyEvent } from "@/lib/api";
import { TrajectoryViewer } from "./TrajectoryViewer";
import { ReplayTimeline } from "./ReplayTimeline";

function MetaDiff({ a, b }: { a: Record<string,unknown>|null; b: Record<string,unknown>|null }) {
  const keys = ["success", "spl", "collision_count", "intervention_count", "inference_latency_ms_mean"];
  return (
    <div className="grid grid-cols-3 gap-x-4 gap-y-0.5 font-mono text-[9px]">
      <span className="text-muted-foreground/50 uppercase tracking-wider">metric</span>
      <span className="text-amber-400/70 uppercase tracking-wider">baseline</span>
      <span className="text-green-400/70 uppercase tracking-wider">FleetSafe</span>
      {keys.map(k => {
        const va = a?.[k];
        const vb = b?.[k];
        const fmtVal = (v: unknown) => {
          if (v === null || v === undefined) return "—";
          if (typeof v === "boolean") return v ? "✓" : "✗";
          if (typeof v === "number") return v % 1 === 0 ? v.toString() : v.toFixed(3);
          return String(v);
        };
        return (
          <Fragment key={k}>
            <span className="text-muted-foreground/50">{k.replace(/_/g, " ")}</span>
            <span className="text-foreground/70">{fmtVal(va)}</span>
            <span className="text-foreground/70">{fmtVal(vb)}</span>
          </Fragment>
        );
      })}
    </div>
  );
}

interface Props {
  runA: string;
  runB: string;
  epId: string;
}

export function ReplaySideBySide({ runA, runB, epId }: Props) {
  const [data, setData] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setStep(0);
    replayApi.compare(runA, runB, epId)
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [runA, runB, epId]);

  if (loading) return (
    <div className="font-mono text-[10px] text-muted-foreground/30 p-4">Loading comparison…</div>
  );
  if (error || !data) return (
    <div className="font-mono text-[10px] text-red-400 p-4">{error ?? "No data"}</div>
  );

  const totalSteps = Math.max(data.a.trajectory.length, data.b.trajectory.length);
  const allEvents: SafetyEvent[] = [...data.a.events, ...data.b.events];

  return (
    <div className="flex flex-col gap-4">
      <MetaDiff a={data.a.meta} b={data.b.meta} />

      <div className="flex gap-4 items-start flex-wrap">
        <div className="flex flex-col gap-1">
          <div className="font-mono text-[9px] text-amber-400/70 uppercase tracking-wider mb-1">Baseline</div>
          <TrajectoryViewer
            trajectory={data.a.trajectory}
            events={data.a.events}
            currentStep={step}
            color="#f59e0b"
          />
        </div>
        <div className="flex flex-col gap-1">
          <div className="font-mono text-[9px] text-green-400/70 uppercase tracking-wider mb-1">FleetSafe</div>
          <TrajectoryViewer
            trajectory={data.b.trajectory}
            events={data.b.events}
            currentStep={step}
            color="#22c55e"
          />
        </div>
      </div>

      <ReplayTimeline
        totalSteps={totalSteps}
        currentStep={step}
        events={allEvents}
        onSeek={setStep}
      />
    </div>
  );
}
