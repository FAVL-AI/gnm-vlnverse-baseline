"use client";

import { RefreshCw } from "lucide-react";
import type { RosGraphState, RosNodeState, RosEdgeState } from "@/lib/api";

// ── Static fallback graph used when state is null ─────────────────────────────

const STATIC_NODES: RosNodeState[] = [
  { id: "fleetsafe_perception", label: "fleetsafe_perception", state: "unknown" },
  { id: "relay",                label: "relay",                state: "unknown" },
];

const STATIC_EDGES: RosEdgeState[] = [
  { id: "e_raw",   from_node: "joy",                  to_node: "fleetsafe_perception", topic: "/cmd_vel_raw",  state: "unknown" },
  { id: "e_safe",  from_node: "fleetsafe_perception",  to_node: "relay",               topic: "/cmd_vel_safe", state: "unknown" },
  { id: "e_final", from_node: "relay",                 to_node: "robot",               topic: "/cmd_vel",      state: "unknown" },
];

// ── Color helpers ─────────────────────────────────────────────────────────────

function nodeColors(state: RosNodeState["state"]) {
  switch (state) {
    case "ok":      return { fill: "rgba(34,197,94,0.15)",  stroke: "#22c55e" };
    case "warn":    return { fill: "rgba(245,158,11,0.15)", stroke: "#f59e0b" };
    case "err":     return { fill: "rgba(239,68,68,0.15)",  stroke: "#ef4444" };
    default:        return { fill: "oklch(0.3 0 0)",        stroke: "oklch(0.4 0 0)" };
  }
}

function edgeColor(state: RosEdgeState["state"]) {
  switch (state) {
    case "flowing": return "#22c55e";
    case "blocked": return "#ef4444";
    default:        return "oklch(0.4 0 0 / 50%)";
  }
}

function overallColor(overall: RosGraphState["overall"]) {
  switch (overall) {
    case "GREEN":  return "#22c55e";
    case "YELLOW": return "#f59e0b";
    case "RED":    return "#ef4444";
    case "ESTOP":  return "#ef4444";
  }
}

// ── Layout constants (viewBox 0 0 900 180) ────────────────────────────────────
// Nodes: joy(src), fleetsafe_perception, relay, robot
// x positions of node centres:
const X_JOY   = 60;
const X_FP    = 270;
const X_RELAY = 560;
const X_ROBOT = 800;
const Y_NODE  = 90;
const NODE_W  = 150;
const NODE_H  = 44;
const NODE_RX = 4;

interface NodeLayout {
  id: string;
  label: string;
  x: number;    // centre-x
  y: number;    // centre-y
  w: number;
  h: number;
  state: RosNodeState["state"];
}

function buildLayout(
  nodes: RosNodeState[],
): NodeLayout[] {
  const stateMap: Record<string, RosNodeState["state"]> = {};
  for (const n of nodes) stateMap[n.id] = n.state;

  return [
    { id: "joy",                 label: "joy / teleop",          x: X_JOY,   y: Y_NODE, w: 90,     h: NODE_H, state: "ok" },
    { id: "fleetsafe_perception",label: "fleetsafe_perception",  x: X_FP,    y: Y_NODE, w: NODE_W, h: NODE_H, state: stateMap["fleetsafe_perception"] ?? "unknown" },
    { id: "relay",               label: "relay",                 x: X_RELAY, y: Y_NODE, w: 90,     h: NODE_H, state: stateMap["relay"] ?? "unknown" },
    { id: "robot",               label: "robot",                 x: X_ROBOT, y: Y_NODE, w: 80,     h: NODE_H, state: "ok" },
  ];
}

interface EdgeLayout {
  id: string;
  x1: number; y1: number;
  x2: number; y2: number;
  topic: string;
  state: RosEdgeState["state"];
  hz?: number | null;
}

function buildEdgeLayout(
  edges: RosEdgeState[],
  nodeLayouts: NodeLayout[],
): EdgeLayout[] {
  const pos: Record<string, { x: number; y: number; w: number }> = {};
  for (const n of nodeLayouts) pos[n.id] = { x: n.x, y: n.y, w: n.w };

  return edges.map(e => {
    const from = pos[e.from_node];
    const to   = pos[e.to_node];
    if (!from || !to) return null;
    return {
      id: e.id,
      x1: from.x + from.w / 2,
      y1: from.y,
      x2: to.x   - to.w / 2,
      y2: to.y,
      topic: e.topic,
      state: e.state,
      hz: e.hz,
    };
  }).filter(Boolean) as EdgeLayout[];
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface RosGraphProps {
  state: RosGraphState | null;
  loading?: boolean;
  onRefresh?: () => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function RosGraphVisualizer({ state, loading, onRefresh }: RosGraphProps) {
  const overall   = state?.overall ?? "RED";
  const nodes     = state?.nodes  ?? STATIC_NODES;
  const edges     = state?.edges  ?? STATIC_EDGES;

  const nodeLayouts = buildLayout(nodes);
  const edgeLayouts = buildEdgeLayout(edges, nodeLayouts);

  const oc = state ? overallColor(overall) : "oklch(0.4 0 0)";

  return (
    <div className="relative border-b border-border bg-card" style={{ height: "12rem" }}>
      {/* Header bar */}
      <div className="absolute top-0 left-0 right-0 flex items-center px-4 py-1.5 border-b border-border z-10">
        <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          CBF-QP Safety Pipeline
        </span>
        {state && (
          <span className="ml-3 font-mono text-[9px]" style={{ color: oc }}>
            {state.estop_latched ? "E-STOP LATCHED" :
             state.intervention_active ? `INTERVENTION — ${state.unsafe_publisher ?? "unknown publisher"}` :
             `${overall}`}
          </span>
        )}
        {loading && (
          <span className="ml-2">
            <RefreshCw size={9} className="animate-spin text-muted-foreground/40" />
          </span>
        )}
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="ml-auto font-mono text-[8px] text-muted-foreground/30 hover:text-muted-foreground transition-colors"
          >
            refresh
          </button>
        )}
      </div>

      {/* SVG */}
      <svg
        viewBox="0 0 900 160"
        preserveAspectRatio="xMidYMid meet"
        className="absolute inset-0 w-full h-full"
        style={{ paddingTop: 28 }}
      >
        <defs>
          <marker id="arrowhead-green"  markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#22c55e" />
          </marker>
          <marker id="arrowhead-red"    markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#ef4444" />
          </marker>
          <marker id="arrowhead-unknown" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="oklch(0.4 0 0 / 50%)" />
          </marker>
          <style>{`
            @keyframes dash-flow {
              from { stroke-dashoffset: 24; }
              to   { stroke-dashoffset: 0; }
            }
            .edge-flowing {
              stroke-dasharray: 6 3;
              animation: dash-flow 0.8s linear infinite;
            }
          `}</style>
        </defs>

        {/* Edges */}
        {edgeLayouts.map(e => {
          const stroke  = edgeColor(e.state);
          const markerId =
            e.state === "flowing" ? "arrowhead-green" :
            e.state === "blocked" ? "arrowhead-red"   : "arrowhead-unknown";
          const isFlowing = e.state === "flowing";

          // mid-point for topic label
          const mx = (e.x1 + e.x2) / 2;
          const my = e.y1 - 14;

          return (
            <g key={e.id}>
              <line
                x1={e.x1} y1={e.y1}
                x2={e.x2 - 8} y2={e.y2}
                stroke={stroke}
                strokeWidth={isFlowing ? 1.5 : 1}
                className={isFlowing ? "edge-flowing" : undefined}
                markerEnd={`url(#${markerId})`}
              />
              {/* Topic label */}
              <text
                x={mx} y={my}
                textAnchor="middle"
                fontFamily="monospace"
                fontSize="8"
                fill="oklch(0.5 0 0)"
              >
                {e.topic}
                {e.hz != null ? ` ${e.hz.toFixed(1)}Hz` : ""}
              </text>
            </g>
          );
        })}

        {/* Nodes */}
        {nodeLayouts.map(n => {
          const { fill, stroke } = nodeColors(n.state);
          return (
            <g key={n.id}>
              <rect
                x={n.x - n.w / 2}
                y={n.y - n.h / 2}
                width={n.w}
                height={n.h}
                rx={NODE_RX}
                fill={fill}
                stroke={stroke}
                strokeWidth={1}
              />
              <text
                x={n.x}
                y={n.y + 1}
                textAnchor="middle"
                dominantBaseline="middle"
                fontFamily="monospace"
                fontSize="10"
                fill="oklch(0.85 0 0)"
              >
                {n.label}
              </text>
              {/* CBF-QP annotation for perception node */}
              {n.id === "fleetsafe_perception" && (
                <text
                  x={n.x}
                  y={n.y + n.h / 2 + 10}
                  textAnchor="middle"
                  fontFamily="monospace"
                  fontSize="7"
                  fill="oklch(0.5 0 0)"
                >
                  CBF-QP filter
                </text>
              )}
            </g>
          );
        })}

        {/* Overall state badge top-right */}
        <text
          x={885} y={32}
          textAnchor="end"
          fontFamily="monospace"
          fontSize="14"
          fontWeight="bold"
          fill={state ? oc : "oklch(0.35 0 0)"}
        >
          {state ? overall : "OFFLINE"}
        </text>

        {/* Legend strip bottom */}
        {[
          { label: "GREEN",  color: "#22c55e"                 },
          { label: "YELLOW", color: "#f59e0b"                 },
          { label: "RED",    color: "#ef4444"                 },
          { label: "ESTOP",  color: "#ef4444"                 },
        ].map((item, i) => (
          <g key={item.label} transform={`translate(${40 + i * 90}, 148)`}>
            <rect width={10} height={10} rx={2} fill={`${item.color}33`} stroke={item.color} strokeWidth={1} />
            <text x={14} y={9} fontFamily="monospace" fontSize="7" fill="oklch(0.5 0 0)">
              {item.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
