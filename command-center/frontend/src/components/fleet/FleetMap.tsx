"use client";

import { useMemo } from "react";
import type { RobotSnapshot } from "@/lib/api";

const W = 560;
const H = 380;
const PAD = 32;

const ROBOT_COLORS = ["#22c55e", "#6366f1", "#f59e0b", "#06b6d4", "#ec4899"];
const ZONE_RING: Record<string, string> = {
  GREEN: "#22c55e33",
  AMBER: "#f59e0b55",
  RED:   "#ef444466",
};
const ZONE_STROKE: Record<string, string> = {
  GREEN: "#22c55e",
  AMBER: "#f59e0b",
  RED:   "#ef4444",
};

function worldToSvg(
  allX: number[], allY: number[],
  px: number, py: number,
): [number, number] {
  const minX = Math.min(...allX, 0);
  const maxX = Math.max(...allX, 10);
  const minY = Math.min(...allY, 0);
  const maxY = Math.max(...allY, 10);
  const rangeX = maxX - minX || 10;
  const rangeY = maxY - minY || 10;
  const scale  = Math.min((W - PAD * 2) / rangeX, (H - PAD * 2) / rangeY);
  const offX   = PAD + ((W - PAD * 2) - rangeX * scale) / 2;
  const offY   = PAD + ((H - PAD * 2) - rangeY * scale) / 2;
  return [
    offX + (px - minX) * scale,
    H - (offY + (py - minY) * scale),
  ];
}

interface Props {
  robots: RobotSnapshot[];
  estopped: string[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}

export function FleetMap({ robots, estopped, selectedId, onSelect }: Props) {
  const { svgRobots, gridLines } = useMemo(() => {
    const xs = robots.map(r => r.odom?.x ?? 0);
    const ys = robots.map(r => r.odom?.y ?? 0);
    const toSvg = (x: number, y: number) => worldToSvg(xs, ys, x, y);

    const svgRobots = robots.map((r, i) => {
      const [cx, cy] = toSvg(r.odom?.x ?? 0, r.odom?.y ?? 0);
      const heading = r.odom?.heading ?? 0;
      const arrLen = 14;
      const ax = cx + arrLen * Math.cos(heading);
      const ay = cy - arrLen * Math.sin(heading);
      const color = ROBOT_COLORS[i % ROBOT_COLORS.length];
      const stopped = estopped.includes(r.robot_id);
      return { r, cx, cy, ax, ay, color, stopped, i };
    });

    // Grid lines at 25% intervals
    const gridLines: [number, number, number, number][] = [
      [PAD, H * 0.25, W - PAD, H * 0.25],
      [PAD, H * 0.50, W - PAD, H * 0.50],
      [PAD, H * 0.75, W - PAD, H * 0.75],
      [W * 0.25, PAD, W * 0.25, H - PAD],
      [W * 0.50, PAD, W * 0.50, H - PAD],
      [W * 0.75, PAD, W * 0.75, H - PAD],
    ];

    return { svgRobots, gridLines };
  }, [robots, estopped]);

  return (
    <svg
      width={W} height={H}
      className="bg-card border border-border block shrink-0"
    >
      {/* Grid */}
      {gridLines.map(([x1, y1, x2, y2], i) => (
        <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
          stroke="currentColor" strokeWidth={0.4} className="text-border" opacity={0.4} />
      ))}

      {/* Robots */}
      {svgRobots.map(({ r, cx, cy, ax, ay, color, stopped }) => {
        const isSelected = selectedId === r.robot_id;
        const ringColor = stopped ? "#ef444466" : (ZONE_RING[r.zone] ?? "#ffffff11");
        const strokeColor = stopped ? "#ef4444" : (ZONE_STROKE[r.zone] ?? "#ffffff");

        return (
          <g
            key={r.robot_id}
            onClick={() => onSelect?.(r.robot_id)}
            className="cursor-pointer"
          >
            {/* Zone ring */}
            <circle cx={cx} cy={cy} r={20}
              fill={ringColor} stroke={strokeColor} strokeWidth={0.8} opacity={0.7}
            />
            {/* Heading arrow */}
            {r.status !== "offline" && (
              <line x1={cx} y1={cy} x2={ax} y2={ay}
                stroke={color} strokeWidth={2} opacity={0.9} />
            )}
            {/* Robot body */}
            <circle
              cx={cx} cy={cy} r={7}
              fill={stopped ? "#ef4444" : color}
              stroke={isSelected ? "#ffffff" : "black"}
              strokeWidth={isSelected ? 2 : 0.5}
              opacity={r.status === "offline" ? 0.3 : 1.0}
            />
            {/* E-stop X */}
            {stopped && (
              <>
                <line x1={cx-4} y1={cy-4} x2={cx+4} y2={cy+4} stroke="white" strokeWidth={1.5} />
                <line x1={cx+4} y1={cy-4} x2={cx-4} y2={cy+4} stroke="white" strokeWidth={1.5} />
              </>
            )}
            {/* Label */}
            <text x={cx} y={cy + 20} textAnchor="middle"
              className="fill-muted-foreground"
              fontSize={8} fontFamily="monospace">
              {r.robot_id}
            </text>
          </g>
        );
      })}

      {/* Empty state */}
      {robots.length === 0 && (
        <text x={W / 2} y={H / 2} textAnchor="middle"
          className="fill-muted-foreground/30" fontSize={10} fontFamily="monospace">
          no robots online
        </text>
      )}

      {/* Legend */}
      <g transform={`translate(${W - PAD - 60}, ${PAD})`}>
        {[["GREEN", "#22c55e"], ["AMBER", "#f59e0b"], ["RED", "#ef4444"]].map(([z, c], i) => (
          <g key={z} transform={`translate(0, ${i * 14})`}>
            <circle cx={5} cy={5} r={4} fill={c} opacity={0.7} />
            <text x={13} y={9} fontSize={7} fontFamily="monospace" className="fill-muted-foreground/50">{z}</text>
          </g>
        ))}
      </g>
    </svg>
  );
}
