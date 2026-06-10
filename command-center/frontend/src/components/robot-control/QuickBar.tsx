"use client";

import { useEffect, useCallback } from "react";
import {
  Cpu, Zap, ZapOff, Square, ArrowUp, ArrowDown, ArrowLeft, ArrowRight,
  Network, ShieldCheck, Mic, FileText, Ban,
} from "lucide-react";

export type QuickAction = {
  id: string;
  key: string;
  label: string;
  icon: React.ElementType;
  variant: "default" | "danger" | "warning" | "primary" | "muted";
  disabled?: boolean;
};

const ACTIONS: QuickAction[] = [
  { id: "start_agent",      key: "1", label: "µROS Agent",      icon: Cpu,        variant: "muted"    },
  { id: "start_fleetsafe",  key: "2", label: "FleetSafe",       icon: ShieldCheck, variant: "primary"  },
  { id: "stop_fleetsafe",   key: "3", label: "Stop FS",         icon: Ban,        variant: "warning"  },
  { id: "stop_conflicting", key: "4", label: "Kill Joy",        icon: Ban,        variant: "warning"  },
  { id: "start_relay",      key: "5", label: "Relay ON",        icon: Zap,        variant: "danger"   },
  { id: "stop_relay",       key: "6", label: "Relay OFF",       icon: ZapOff,     variant: "warning"  },
  { id: "zero",             key: "E", label: "E-STOP / Zero",   icon: Square,     variant: "danger"   },
  { id: "pulse_forward",    key: "I", label: "Fwd Pulse",       icon: ArrowUp,    variant: "default"  },
  { id: "pulse_back",       key: "K", label: "Rev Pulse",       icon: ArrowDown,  variant: "default"  },
  { id: "pulse_left",       key: "J", label: "Left Pulse",      icon: ArrowLeft,  variant: "default"  },
  { id: "pulse_right",      key: "L", label: "Right Pulse",     icon: ArrowRight, variant: "default"  },
  { id: "relay_guard",      key: "S", label: "Safety Check",    icon: ShieldCheck, variant: "muted"   },
  { id: "verify_graph",     key: "V", label: "Verify Graph",    icon: Network,    variant: "muted"    },
  { id: "voice",            key: "M", label: "Voice (Neo…)",    icon: Mic,        variant: "muted"    },
  { id: "audit",            key: "A", label: "Audit Log",       icon: FileText,   variant: "muted"    },
];

const VARIANT_CLASS: Record<string, string> = {
  default: "border-border text-muted-foreground hover:text-foreground hover:border-foreground/40",
  primary: "border-green-500/40 text-green-400 hover:border-green-500",
  warning: "border-amber-400/40 text-amber-400 hover:border-amber-500",
  danger:  "border-red-500/50 text-red-400 hover:border-red-500",
  muted:   "border-border/60 text-muted-foreground/50 hover:text-muted-foreground hover:border-border",
};

interface Props {
  onAction: (id: string) => void;
  busy: boolean;
  relayLocked?: boolean;
}

export function QuickBar({ onAction, busy, relayLocked = true }: Props) {
  const handleKey = useCallback((e: KeyboardEvent) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const key = e.key.toUpperCase();
    const action = ACTIONS.find(a => a.key === key);
    if (!action) return;
    if (action.id === "start_relay" && relayLocked) return;
    e.preventDefault();
    onAction(action.id);
  }, [onAction, relayLocked]);

  useEffect(() => {
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [handleKey]);

  return (
    <div className="flex flex-col gap-1">
      <div className="font-mono text-[9px] text-muted-foreground/40 uppercase tracking-wider mb-1">
        Quick Actions <span className="text-muted-foreground/20 ml-1">keyboard shortcuts active</span>
      </div>
      <div className="grid grid-cols-3 gap-1">
        {ACTIONS.map(({ id, key, label, icon: Icon, variant }) => {
          const isRelayOn = id === "start_relay";
          const disabled = busy || (isRelayOn && relayLocked);
          return (
            <button
              key={id}
              onClick={() => onAction(id)}
              disabled={disabled}
              title={`[${key}] ${label}`}
              className={`flex flex-col items-center gap-1 px-2 py-2 border font-mono text-[8px]
                transition-colors ${VARIANT_CLASS[variant]}
                ${disabled ? "opacity-30 pointer-events-none" : ""}`}
            >
              <div className="flex items-center gap-1">
                <span className="text-[7px] font-bold text-muted-foreground/40">[{key}]</span>
                <Icon size={10} strokeWidth={1.5} />
              </div>
              <span className="leading-tight text-center">{label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
