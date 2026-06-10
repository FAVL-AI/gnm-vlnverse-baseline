"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Terminal,
  FolderOpen,
  FlaskConical,
  Play,
  Zap,
  MapPin,
  Shield,
  ListTodo,
  Video,
  Radio,
  Gamepad2,
  BookOpenCheck,
  Clock,
  ScanSearch,
  GraduationCap,
  Cpu,
  FileText,
  ShieldCheck,
  BookOpen,
  HelpCircle,
  Settings2,
  ChevronLeft,
  ChevronRight,
  BarChart3,
  MonitorPlay,
  Database,
  Globe,
} from "lucide-react";
import { useEffect, useState } from "react";

// liveOnly: hidden on public Vercel deployment (NEXT_PUBLIC_DEPLOYMENT_MODE=public_readonly)
// These pages require SSH / ROS2 / FastAPI backend running locally.
const NAV = [
  { href: "/project",                    icon: Globe,           label: "Project",         liveOnly: false },
  { href: "/dashboard",                 icon: LayoutDashboard, label: "Overview",        liveOnly: false },
  { href: "/dashboard/experiments",      icon: FlaskConical,    label: "Experiments",     liveOnly: false },
  { href: "/dashboard/benchmark-results",icon: BarChart3,      label: "Benchmark",       liveOnly: false },
  { href: "/dashboard/demo",             icon: MonitorPlay,    label: "Live Demo",        liveOnly: true  },
  { href: "/dashboard/evidence",         icon: BookOpenCheck,  label: "Evidence",        liveOnly: false },
  { href: "/dashboard/publication",      icon: FileText,       label: "Publication",     liveOnly: false },
  { href: "/dashboard/reproducibility", icon: ShieldCheck,     label: "Reproducibility", liveOnly: false },
  { href: "/dashboard/replay",          icon: Play,            label: "Replay",          liveOnly: false },
  { href: "/dashboard/timeline",        icon: Clock,           label: "Timeline",        liveOnly: false },
  { href: "/dashboard/artifacts",       icon: FolderOpen,      label: "Artifacts",       liveOnly: false },
  { href: "/dashboard/ground-truth",    icon: ScanSearch,      label: "Ground Truth",    liveOnly: false },
  { href: "/dashboard/training",        icon: GraduationCap,   label: "Training",        liveOnly: false },
  { href: "/dashboard/digital-twin",    icon: Cpu,             label: "Digital Twin",    liveOnly: false },
  { href: "/dashboard/vln-hub",         icon: Database,        label: "VLN Hub",          liveOnly: false },
  // ── live-only: hidden on public deployment ────────────────────────────────
  { href: "/dashboard/commissioning",   icon: Radio,           label: "Commissioning",   liveOnly: true  },
  { href: "/dashboard/robot-control",   icon: Gamepad2,        label: "Robot Control",   liveOnly: true  },
  { href: "/dashboard/fleet",           icon: MapPin,          label: "Fleet Map",       liveOnly: true  },
  { href: "/dashboard/safety",          icon: Shield,          label: "Safety",          liveOnly: true  },
  { href: "/dashboard/missions",        icon: ListTodo,        label: "Missions",        liveOnly: true  },
  { href: "/dashboard/sessions",        icon: Video,           label: "Sessions",        liveOnly: true  },
  { href: "/dashboard/launcher",        icon: Terminal,        label: "Launcher",        liveOnly: true  },
  { href: "/dashboard/isaac",           icon: Zap,             label: "Isaac Sim",       liveOnly: true  },
];

const UTILITY_NAV = [
  { href: "/dashboard/docs",     icon: BookOpen,   label: "Docs"     },
  { href: "/dashboard/help",     icon: HelpCircle, label: "Help"     },
  { href: "/dashboard/settings", icon: Settings2,  label: "Settings" },
];

const IS_READONLY = process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "public_readonly";

export function CommandRail() {
  const path = usePathname();
  const [collapsed, setCollapsed] = useState(true);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("fs_sidebar_collapsed");
    if (stored !== null) {
      setCollapsed(stored === "true");
    }
    setMounted(true);
  }, []);

  function toggleCollapsed() {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("fs_sidebar_collapsed", String(next));
  }

  const visibleNav = IS_READONLY ? NAV.filter(n => !n.liveOnly) : NAV;

  function NavItem({ href, icon: Icon, label }: { href: string; icon: React.ElementType; label: string }) {
    const active = path === href || (href !== "/dashboard" && path.startsWith(href));
    return (
      <Link
        href={href}
        title={collapsed ? label : undefined}
        className={`flex items-center gap-2 rounded-sm transition-colors ${
          collapsed ? "w-10 h-10 justify-center" : "h-9 px-2"
        } ${
          active
            ? "bg-foreground text-background"
            : "text-foreground/75 hover:text-foreground hover:bg-accent"
        }`}
      >
        <Icon size={16} strokeWidth={1.5} className="shrink-0" />
        <span
          className={`font-mono text-[11px] tracking-wide whitespace-nowrap transition-all duration-200 ${
            collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
          }`}
        >
          {label}
        </span>
      </Link>
    );
  }

  return (
    <aside
      className={`relative z-20 flex flex-col shrink-0 border-r border-border bg-card py-4 gap-1 transition-all duration-200 ease-in-out ${
        collapsed ? "w-14 items-center" : "w-56 items-stretch px-2"
      }`}
      suppressHydrationWarning
    >
      {/* Brand dot */}
      <div
        className={`flex items-center justify-center mb-4 ${
          collapsed ? "w-7 h-7 rounded-sm border border-border" : "h-7 px-1"
        }`}
      >
        <span className="font-mono text-[8px] font-bold tracking-wider text-foreground/70 shrink-0">
          FS
        </span>
        <span
          className={`font-mono text-[10px] font-bold tracking-widest text-foreground/50 ml-2 whitespace-nowrap transition-all duration-200 ${
            collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
          }`}
        >
          FleetSafe
        </span>
      </div>

      {/* Main nav */}
      <div className={`flex flex-col gap-0.5 flex-1 ${collapsed ? "items-center w-full" : ""}`}>
        {mounted && visibleNav.map(({ href, icon, label }) => (
          <NavItem key={href} href={href} icon={icon} label={label} />
        ))}
      </div>

      {/* Divider above utility nav */}
      <div className={`my-1 border-t border-border ${collapsed ? "w-8" : "w-full"}`} />

      {/* Utility nav: Docs / Help / Settings */}
      <div className={`flex flex-col gap-0.5 ${collapsed ? "items-center w-full" : ""}`}>
        {UTILITY_NAV.map(({ href, icon, label }) => (
          <NavItem key={href} href={href} icon={icon} label={label} />
        ))}
      </div>

      {/* Collapse toggle */}
      <button
        onClick={toggleCollapsed}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        className={`flex items-center justify-center mt-2 rounded-sm h-8 transition-colors text-foreground/50 hover:text-foreground hover:bg-accent ${
          collapsed ? "w-10" : "w-full"
        }`}
      >
        {collapsed ? (
          <ChevronRight size={14} strokeWidth={1.5} />
        ) : (
          <ChevronLeft size={14} strokeWidth={1.5} />
        )}
      </button>
    </aside>
  );
}
