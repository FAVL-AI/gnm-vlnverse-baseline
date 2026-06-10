"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEPLOYMENT_MODE = process.env.NEXT_PUBLIC_DEPLOYMENT_MODE ?? "live";

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-foreground/60 uppercase tracking-wider text-[9px] font-mono mb-3">
      {children}
    </p>
  );
}

function Section({ children }: { children: React.ReactNode }) {
  return (
    <div className="border border-border p-5 space-y-3">
      {children}
    </div>
  );
}

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const [displayName, setDisplayName] = useState("");
  const [saved, setSaved] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const name = localStorage.getItem("fs_display_name") ?? "";
    setDisplayName(name);
    const collapsed = localStorage.getItem("fs_sidebar_collapsed");
    setSidebarCollapsed(collapsed === null ? true : collapsed === "true");
    setMounted(true);
  }, []);

  function handleSave() {
    localStorage.setItem("fs_display_name", displayName);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  function handleSidebarToggle() {
    const next = !sidebarCollapsed;
    setSidebarCollapsed(next);
    localStorage.setItem("fs_sidebar_collapsed", String(next));
  }

  const themes = [
    { value: "light",  label: "Light"  },
    { value: "dark",   label: "Dark"   },
    { value: "system", label: "System" },
  ] as const;

  if (!mounted) return null;

  return (
    <div className="max-w-2xl mx-auto px-6 py-10 space-y-6">
      <h1 className="font-mono text-sm font-semibold text-foreground tracking-wide uppercase">
        Settings
      </h1>

      {/* Profile */}
      <div className="space-y-2">
        <SectionHeader>Profile</SectionHeader>
        <Section>
          <label className="block font-mono text-[11px] text-foreground/60 mb-1">
            Display name
          </label>
          <div className="flex items-center gap-3">
            <input
              type="text"
              value={displayName}
              onChange={e => setDisplayName(e.target.value)}
              placeholder="Operator"
              className="flex-1 bg-background border border-border text-foreground font-mono text-[12px] px-3 py-1.5 focus:outline-none focus:border-foreground/30 transition-colors"
            />
            <button
              onClick={handleSave}
              className={`font-mono text-[11px] px-4 py-1.5 border transition-colors ${
                saved
                  ? "border-green-500 text-green-500 shadow-[0_0_8px_rgba(34,197,94,0.3)]"
                  : "border-border text-foreground/70 hover:text-foreground hover:border-foreground/30"
              }`}
            >
              {saved ? "Saved" : "Save"}
            </button>
          </div>
          <p className="font-mono text-[10px] text-foreground/40">
            Shown in the status bar. Defaults to "Operator" if empty.
          </p>
        </Section>
      </div>

      {/* Appearance */}
      <div className="space-y-2">
        <SectionHeader>Appearance</SectionHeader>
        <Section>
          <p className="font-mono text-[11px] text-foreground/60 mb-2">Theme</p>
          <div className="flex gap-2">
            {themes.map(({ value, label }) => (
              <button
                key={value}
                onClick={() => setTheme(value)}
                suppressHydrationWarning
                className={`font-mono text-[11px] px-4 py-1.5 border transition-colors ${
                  theme === value
                    ? "border-foreground text-foreground bg-foreground/5"
                    : "border-border text-foreground/50 hover:text-foreground hover:border-foreground/30"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </Section>
      </div>

      {/* API */}
      <div className="space-y-2">
        <SectionHeader>API</SectionHeader>
        <Section>
          <p className="font-mono text-[11px] text-foreground/60 mb-1">
            Backend API endpoint — set via{" "}
            <code className="text-foreground/80">NEXT_PUBLIC_API_URL</code> env var
          </p>
          <code className="block font-mono text-[12px] text-foreground/90 bg-muted px-3 py-2">
            {API_URL}
          </code>
        </Section>
      </div>

      {/* Sidebar */}
      <div className="space-y-2">
        <SectionHeader>Sidebar</SectionHeader>
        <Section>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-mono text-[12px] text-foreground">Start collapsed</p>
              <p className="font-mono text-[10px] text-foreground/40 mt-0.5">
                Stored in localStorage as <code>fs_sidebar_collapsed</code>
              </p>
            </div>
            <button
              onClick={handleSidebarToggle}
              className={`relative w-10 h-5 rounded-full transition-colors ${
                sidebarCollapsed ? "bg-foreground/20" : "bg-foreground"
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-background transition-transform ${
                  sidebarCollapsed ? "translate-x-0" : "translate-x-5"
                }`}
              />
            </button>
          </div>
        </Section>
      </div>

      {/* Deployment */}
      <div className="space-y-2">
        <SectionHeader>Deployment</SectionHeader>
        <Section>
          <p className="font-mono text-[11px] text-foreground/60 mb-1">
            Deployment mode — set via{" "}
            <code className="text-foreground/80">NEXT_PUBLIC_DEPLOYMENT_MODE</code>
          </p>
          <code className="block font-mono text-[12px] text-foreground/90 bg-muted px-3 py-2">
            {DEPLOYMENT_MODE}
          </code>
          <p className="font-mono text-[10px] text-foreground/40">
            {DEPLOYMENT_MODE === "public_readonly"
              ? "Robot Control and Commissioning pages are hidden in this mode."
              : "All pages are visible. Backend must be running locally."}
          </p>
        </Section>
      </div>
    </div>
  );
}
