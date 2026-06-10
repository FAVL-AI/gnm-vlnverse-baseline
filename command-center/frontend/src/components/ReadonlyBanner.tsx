/**
 * Shown on the public Vercel deployment (NEXT_PUBLIC_DEPLOYMENT_MODE=public_readonly).
 * The robot backend, SSH controls, and live telemetry run on the local workstation only.
 */
export function ReadonlyBanner() {
  if (process.env.NEXT_PUBLIC_DEPLOYMENT_MODE !== "public_readonly") return null;

  return (
    <div className="w-full bg-amber-500/10 border-b border-amber-500/30 px-4 py-1.5 flex items-center gap-3 shrink-0">
      <span className="font-mono text-[9px] text-amber-400 font-semibold tracking-widest uppercase">
        Read-Only Public View
      </span>
      <span className="font-mono text-[8px] text-muted-foreground/60">
        Evidence tables, experiment results, and publication data only.
        Robot control, SSH, and live telemetry require the local backend.
      </span>
      <a
        href="https://github.com/FAVL-AI/FleetSafe-VisualNav-Benchmark"
        target="_blank"
        rel="noopener noreferrer"
        className="ml-auto font-mono text-[8px] text-amber-400/70 hover:text-amber-400 transition-colors"
      >
        GitHub →
      </a>
    </div>
  );
}
