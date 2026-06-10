"use client";

import { useCallback, useState } from "react";
import { useFleet } from "@/hooks/useFleet";
import { FleetMap } from "@/components/fleet/FleetMap";
import { RobotCard } from "@/components/fleet/RobotCard";
import { fleetApi, sessionApi, type RobotSnapshot } from "@/lib/api";
import { AlertTriangle, Circle, Video, VideoOff } from "lucide-react";

export default function FleetPage() {
  const fleet = useFleet();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeSessions, setActiveSessions] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const robots: RobotSnapshot[] = fleet?.robots ?? [];
  const estopped: string[] = fleet?.estopped ?? [];

  const handleEstop = useCallback(async (robot_id: string) => {
    try { await fleetApi.estop(robot_id); } catch { /* ignore */ }
  }, []);

  const handleClearEstop = useCallback(async (robot_id: string) => {
    try { await fleetApi.clearEstop(robot_id); } catch { /* ignore */ }
  }, []);

  const handleEstopAll = useCallback(async () => {
    setBusy(true);
    try { await fleetApi.estopAll(); } catch { /* ignore */ }
    finally { setBusy(false); }
  }, []);

  const toggleRecording = useCallback(async (robot_id: string) => {
    const sid = activeSessions[robot_id];
    if (sid) {
      try { await sessionApi.stop(sid); } catch { /* ignore */ }
      setActiveSessions(p => { const n = { ...p }; delete n[robot_id]; return n; });
    } else {
      try {
        const s = await sessionApi.start(robot_id);
        setActiveSessions(p => ({ ...p, [robot_id]: s.session_id }));
      } catch { /* ignore */ }
    }
  }, [activeSessions]);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Main: map */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center gap-3 px-4 py-2 border-b border-border shrink-0">
          <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
            Fleet Map
          </span>
          <span className="font-mono text-[9px] text-muted-foreground">
            {robots.filter(r => r.status !== "offline").length}/{robots.length} online
          </span>
          {estopped.length > 0 && (
            <span className="font-mono text-[9px] text-red-400 animate-pulse">
              {estopped.length} E-STOP
            </span>
          )}
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={handleEstopAll}
              disabled={busy}
              className="font-mono text-[9px] px-3 py-1.5 border border-red-500/40 text-red-400 hover:border-red-500 hover:text-red-300 transition-colors flex items-center gap-1.5 disabled:opacity-30"
            >
              <AlertTriangle size={10} />
              ALL E-STOP
            </button>
          </div>
        </div>

        {/* Map */}
        <div className="flex-1 overflow-auto p-4">
          {fleet ? (
            <FleetMap
              robots={robots}
              estopped={estopped}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          ) : (
            <div className="font-mono text-[10px] text-muted-foreground/30 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/20 animate-pulse" />
              Connecting to fleet…
            </div>
          )}
        </div>
      </div>

      {/* Sidebar: robot cards */}
      <aside className="w-52 shrink-0 border-l border-border flex flex-col overflow-hidden">
        <div className="px-3 py-2 border-b border-border font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          Robots
        </div>
        <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-2">
          {robots.map(r => (
            <div key={r.robot_id} className="flex flex-col gap-1">
              <RobotCard
                robot={r}
                estopped={estopped.includes(r.robot_id)}
                selected={selectedId === r.robot_id}
                onClick={() => setSelectedId(r.robot_id)}
                onEstop={() => handleEstop(r.robot_id)}
                onClearEstop={() => handleClearEstop(r.robot_id)}
              />
              {/* Recording toggle */}
              <button
                onClick={() => toggleRecording(r.robot_id)}
                className={`w-full font-mono text-[8px] px-2 py-1 border transition-colors flex items-center gap-1.5 justify-center
                  ${activeSessions[r.robot_id]
                    ? "border-red-500/40 text-red-400 hover:border-red-500"
                    : "border-border text-muted-foreground/40 hover:border-foreground/30 hover:text-muted-foreground"}`}
              >
                {activeSessions[r.robot_id]
                  ? <><VideoOff size={9} /> Stop Recording</>
                  : <><Video size={9} /> Record Session</>}
              </button>
            </div>
          ))}
          {!fleet && (
            <div className="text-[9px] text-muted-foreground/30 font-mono text-center mt-4">
              Connecting…
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
