"use client";

import { useEffect, useState } from "react";
import { evidenceApi, type HeatmapData } from "@/lib/api";
import { RefreshCw } from "lucide-react";

type Layer = "collisions" | "interventions" | "path";

const LAYER_META: Record<Layer, { label: string; color: (v: number) => string }> = {
  collisions:    { label: "Collision density",     color: v => `rgba(239,68,68,${Math.min(v, 1).toFixed(2)})`    },
  interventions: { label: "Intervention density",  color: v => `rgba(245,158,11,${Math.min(v, 1).toFixed(2)})`   },
  path:          { label: "Path density",          color: v => `rgba(99,102,241,${Math.min(v * 0.6, 1).toFixed(2)})` },
};

const SVG_W = 400;
const SVG_H = 300;
const CELL  = 12;

function normalize(val: number, max: number): number {
  return max > 0 ? val / max : 0;
}

export function HeatmapOverlay() {
  const [data, setData]     = useState<HeatmapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [layer, setLayer]   = useState<Layer>("collisions");

  async function load() {
    setLoading(true);
    try { setData(await evidenceApi.heatmap()); } catch { /* */ }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  const cells  = data?.cells ?? [];
  const bounds = data?.bounds;

  // compute per-layer max for normalisation
  const maxCollision    = Math.max(1, ...cells.map(c => c.collisions));
  const maxIntervention = Math.max(1, ...cells.map(c => c.interventions));
  const maxPath         = Math.max(1, ...cells.map(c => c.path_count));

  // world→SVG mapping
  function toSvgX(wx: number) {
    if (!bounds) return 0;
    const span = bounds.x_max - bounds.x_min || 1;
    return ((wx - bounds.x_min) / span) * (SVG_W - CELL * 2) + CELL;
  }
  function toSvgY(wy: number) {
    if (!bounds) return 0;
    const span = bounds.y_max - bounds.y_min || 1;
    return SVG_H - CELL - ((wy - bounds.y_min) / span) * (SVG_H - CELL * 2);
  }

  function cellColor(c: typeof cells[0]): string {
    const { color } = LAYER_META[layer];
    if (layer === "collisions")    return color(normalize(c.collisions, maxCollision));
    if (layer === "interventions") return color(normalize(c.interventions, maxIntervention));
    return color(normalize(c.path_count, maxPath));
  }

  function cellValue(c: typeof cells[0]): number {
    if (layer === "collisions")    return c.collisions;
    if (layer === "interventions") return c.interventions;
    return c.path_count;
  }

  return (
    <div className="border border-border flex flex-col">
      {/* toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-border">
        <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">Simulation Heatmap</span>

        <div className="flex gap-1 ml-2">
          {(Object.keys(LAYER_META) as Layer[]).map(l => (
            <button
              key={l}
              onClick={() => setLayer(l)}
              className={`font-mono text-[8px] px-2 py-0.5 border transition-colors ${
                layer === l
                  ? "border-foreground/40 text-foreground/80"
                  : "border-border text-muted-foreground/40 hover:text-muted-foreground"
              }`}
            >
              {LAYER_META[l].label}
            </button>
          ))}
        </div>

        <button onClick={load} disabled={loading} className="ml-auto flex items-center gap-1 font-mono text-[8px] text-muted-foreground/40 hover:text-muted-foreground border border-border px-2 py-1 transition-colors disabled:opacity-30">
          <RefreshCw size={9} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {/* SVG canvas */}
      <div className="relative bg-card/50">
        {data?.warning && !cells.length && (
          <div className="absolute inset-0 flex items-center justify-center font-mono text-[8px] text-muted-foreground/30 p-4 text-center">
            {data.warning}
          </div>
        )}

        {loading && !cells.length && (
          <div className="absolute inset-0 flex items-center justify-center font-mono text-[8px] text-muted-foreground/20">
            Loading…
          </div>
        )}

        <svg
          viewBox={`0 0 ${SVG_W} ${SVG_H}`}
          width={SVG_W}
          height={SVG_H}
          className="w-full"
          style={{ maxHeight: 300 }}
        >
          {/* grid background */}
          <rect width={SVG_W} height={SVG_H} fill="transparent" />

          {/* axis labels */}
          {bounds && (
            <>
              <text x={CELL} y={SVG_H - 2} fontSize={7} fill="rgba(255,255,255,0.2)" fontFamily="monospace">{bounds.x_min.toFixed(0)}</text>
              <text x={SVG_W - CELL * 3} y={SVG_H - 2} fontSize={7} fill="rgba(255,255,255,0.2)" fontFamily="monospace">{bounds.x_max.toFixed(0)}</text>
            </>
          )}

          {/* heatmap cells */}
          {cells.filter(c => cellValue(c) > 0).map((c, i) => (
            <rect
              key={i}
              x={toSvgX(c.x) - CELL / 2}
              y={toSvgY(c.y) - CELL / 2}
              width={CELL}
              height={CELL}
              fill={cellColor(c)}
              rx={1}
            >
              <title>{`(${c.x},${c.y}) col:${c.collisions} int:${c.interventions} path:${c.path_count}`}</title>
            </rect>
          ))}
        </svg>
      </div>

      {/* legend */}
      <div className="flex items-center gap-6 px-4 py-2 border-t border-border">
        <div className="flex items-center gap-1.5 font-mono text-[8px] text-muted-foreground/50">
          <div className="w-2 h-2 rounded-sm bg-red-500/70" />
          {data?.total_collisions ?? 0} collisions
        </div>
        <div className="flex items-center gap-1.5 font-mono text-[8px] text-muted-foreground/50">
          <div className="w-2 h-2 rounded-sm bg-amber-500/70" />
          {data?.total_interventions ?? 0} interventions
        </div>
        <div className="flex items-center gap-1.5 font-mono text-[8px] text-muted-foreground/50">
          <div className="w-2 h-2 rounded-sm bg-indigo-500/70" />
          {data?.total_path_samples ?? 0} path samples
        </div>
        <span className="ml-auto font-mono text-[7px] text-muted-foreground/25">{cells.length} cells</span>
      </div>
    </div>
  );
}
