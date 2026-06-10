"use client";

import { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[dashboard]", error);
  }, [error]);

  return (
    <div className="p-6 flex flex-col items-center justify-center min-h-[60vh] gap-4">
      <AlertTriangle className="w-8 h-8 text-amber-400" />
      <div className="text-center space-y-1">
        <p className="text-sm font-semibold text-foreground">Page failed to load</p>
        <p className="text-xs text-muted-foreground max-w-sm">
          An unexpected error occurred. The FleetSafe backend may be offline on this deployment.
        </p>
        {error.message && (
          <p className="text-[10px] font-mono text-muted-foreground/60 mt-1">{error.message}</p>
        )}
      </div>
      <button
        onClick={reset}
        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-border/50 hover:bg-muted/30 transition-colors"
      >
        <RefreshCw className="w-3 h-3" />
        Try again
      </button>
    </div>
  );
}
