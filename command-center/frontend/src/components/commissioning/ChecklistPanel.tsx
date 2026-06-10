"use client";

import type { CommissioningStatus } from "@/lib/api";
import { Check, X, Minus } from "lucide-react";

// Items that must pass before arming
const ARM_REQUIRED = new Set(["estop_tested"]);
const RELAY_REQUIRED = new Set(["ros2_live", "estop_tested"]);

interface Props {
  status: CommissioningStatus;
  onCheck: () => void;
  checking: boolean;
}

export function ChecklistPanel({ status, onCheck, checking }: Props) {
  const { checklist, checklist_labels, state } = status;

  const allRequired = [...ARM_REQUIRED].every(k => checklist[k]);
  const passCount = Object.values(checklist).filter(Boolean).length;
  const totalCount = Object.keys(checklist).length;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          Checklist {passCount}/{totalCount}
        </div>
        <button
          onClick={onCheck}
          disabled={checking || state === "DISARMED"}
          className="font-mono text-[8px] px-2 py-0.5 border border-border hover:border-foreground/40 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-30"
        >
          {checking ? "checking…" : "refresh"}
        </button>
      </div>

      <div className="flex flex-col gap-1">
        {Object.entries(checklist_labels).map(([key, label]) => {
          const pass = checklist[key] ?? false;
          const isArmRequired = ARM_REQUIRED.has(key);
          const isRelayRequired = RELAY_REQUIRED.has(key);
          const active = state !== "DISARMED";

          return (
            <div key={key}
              className={`flex items-center gap-2 font-mono text-[9px] px-2 py-1 border transition-colors
                ${pass ? "border-green-500/20 bg-green-500/5" :
                  active ? "border-red-500/20 bg-red-500/5" :
                  "border-border"}`}
            >
              <span className={`shrink-0 ${pass ? "text-green-400" : active ? "text-red-400/70" : "text-muted-foreground/20"}`}>
                {pass ? <Check size={10} /> : active ? <X size={10} /> : <Minus size={10} />}
              </span>
              <span className={`flex-1 ${pass ? "text-foreground/70" : active ? "text-muted-foreground/50" : "text-muted-foreground/20"}`}>
                {label}
              </span>
              {isArmRequired && (
                <span className="text-[7px] text-amber-400/60 border border-amber-400/20 px-0.5">ARM</span>
              )}
              {isRelayRequired && !isArmRequired && (
                <span className="text-[7px] text-orange-400/60 border border-orange-400/20 px-0.5">RELAY</span>
              )}
            </div>
          );
        })}
      </div>

      {!allRequired && state === "ESTOP_VALIDATED" && (
        <div className="font-mono text-[8px] text-amber-400/70 border border-amber-400/20 px-2 py-1">
          Run e-stop test to unlock arming.
        </div>
      )}
    </div>
  );
}
