import { cn } from "@/lib/utils";

type Trend = "up" | "down" | "neutral";

interface MetricCardProps {
  label: string;
  value: string | number;
  unit?: string;
  trend?: Trend;
  good?: Trend;   // which direction is "good" for colouring
  sub?: string;
  className?: string;
}

function fmt(v: string | number, unit?: string): string {
  if (typeof v === "number") {
    const s = v < 0.01 ? v.toFixed(4) : v < 1 ? (v * 100).toFixed(1) + "%" : v.toFixed(1);
    if (unit) return `${s} ${unit}`;
    // If no unit and value 0-1, treat as pct
    if (typeof v === "number" && v >= 0 && v <= 1 && !unit) {
      return (v * 100).toFixed(1) + "%";
    }
    return s;
  }
  return unit ? `${v} ${unit}` : String(v);
}

export function MetricCard({ label, value, unit, trend, good, sub, className }: MetricCardProps) {
  const trendColour =
    trend && good
      ? trend === good
        ? "text-green-500"
        : "text-red-400"
      : "text-muted-foreground";

  const arrow = trend === "up" ? "↑" : trend === "down" ? "↓" : "";

  return (
    <div className={cn(
      "border border-border bg-card p-4 flex flex-col gap-1 hover:border-foreground/20 transition-colors",
      className,
    )}>
      <span className="text-[10px] font-mono text-muted-foreground tracking-wider uppercase truncate">
        {label}
      </span>
      <span className="font-mono text-xl font-semibold tracking-tight text-foreground">
        {typeof value === "number" ? fmt(value, unit) : (unit ? `${value} ${unit}` : value)}
        {arrow && (
          <span className={`ml-1.5 text-sm ${trendColour}`}>{arrow}</span>
        )}
      </span>
      {sub && (
        <span className="text-[10px] font-mono text-muted-foreground/70 truncate">{sub}</span>
      )}
    </div>
  );
}
