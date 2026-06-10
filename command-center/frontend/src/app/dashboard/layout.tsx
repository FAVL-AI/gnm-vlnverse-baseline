import { CommandRail }   from "@/components/CommandRail";
import { StatusBar }      from "@/components/StatusBar";
import { ReadonlyBanner } from "@/components/ReadonlyBanner";

export const metadata = { title: "FleetSafe Command Center" };

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <ReadonlyBanner />
      <StatusBar />
      <div className="flex flex-1 overflow-hidden">
        <CommandRail />
        <div className="flex-1 flex flex-col overflow-hidden">
          <main className="flex-1 overflow-auto bg-background">
            {children}
          </main>
          <footer className="shrink-0 border-t border-border bg-card px-4 py-1.5 flex items-center justify-end">
            <span className="font-mono text-[10px] text-foreground/40 tracking-wide">
              &copy; {new Date().getFullYear()} Frank Van Laarhoven. All rights reserved.
            </span>
          </footer>
        </div>
      </div>
    </div>
  );
}
