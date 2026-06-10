"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Maximize2, Minimize2, Camera, Circle } from "lucide-react";
import { api } from "@/lib/api";
import { useTelemetry } from "@/hooks/useTelemetry";
import { useWebRTC } from "@/hooks/useWebRTC";

type StreamInfo = {
  id: string;
  label: string;
  icon: string;
  type: "foxglove" | "webrtc" | "mjpeg";
  status: string;
  foxglove_ws: string | null;
  webrtc_offer_url: string | null;
  mjpeg_url: string | null;
  has_launcher: boolean;
};

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STATUS_DOT: Record<string, string> = {
  connected:    "bg-green-500",
  available:    "bg-green-500/60",
  disconnected: "bg-red-400/60",
  unknown:      "bg-muted-foreground/30",
};

// ── Foxglove iframe ───────────────────────────────────────────────────────────

function FoxgloveEmbed({ wsUrl, label }: { wsUrl: string; label: string }) {
  const src = `https://studio.foxglove.dev/?ds=foxglove-websocket&ds.url=${encodeURIComponent(wsUrl)}`;
  return (
    <div className="relative w-full h-full flex flex-col">
      <div className="absolute top-2 left-2 z-10 font-mono text-[9px] text-white/40 pointer-events-none">
        {label} · Foxglove
      </div>
      <iframe
        src={src}
        className="flex-1 w-full border-0"
        allow="clipboard-read; clipboard-write"
        sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
        title={`Foxglove — ${label}`}
      />
    </div>
  );
}

// ── WebRTC player ─────────────────────────────────────────────────────────────

function WebRTCPlayer({ streamId, label }: { streamId: string; label: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const state = useWebRTC(streamId, videoRef);

  return (
    <div className="relative w-full h-full bg-black flex items-center justify-center">
      <video
        ref={videoRef}
        className="w-full h-full object-contain"
        autoPlay
        muted
        playsInline
      />
      {state !== "connected" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 font-mono text-xs text-white/30">
          <div className="w-4 h-4 border-2 border-white/20 border-t-white/60 rounded-full animate-spin" />
          <span>
            {state === "connecting" ? "Negotiating WebRTC…" :
             state === "failed"     ? "WebRTC failed — check Isaac is running" :
             `${label} · WebRTC`}
          </span>
        </div>
      )}
    </div>
  );
}

// ── MJPEG player ──────────────────────────────────────────────────────────────

function MjpegPlayer({ streamId, mjpegUrl, label }: { streamId: string; mjpegUrl: string; label: string }) {
  const fullUrl = mjpegUrl.startsWith("http") ? mjpegUrl : `${BASE}${mjpegUrl}`;
  return (
    <div className="relative w-full h-full bg-black flex items-center justify-center">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={fullUrl}
        className="w-full h-full object-contain"
        alt={`${label} MJPEG stream`}
        crossOrigin="anonymous"
      />
      <div className="absolute top-2 right-2 font-mono text-[9px] text-white/30 pointer-events-none">
        {label} · MJPEG
      </div>
    </div>
  );
}

// ── Disconnected placeholder ──────────────────────────────────────────────────

function DisconnectedView({
  stream,
  onLaunch,
  launching,
}: {
  stream: StreamInfo;
  onLaunch: () => void;
  launching: boolean;
}) {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center gap-4 text-muted-foreground/40 font-mono">
      <div className="text-3xl">{stream.icon}</div>
      <div className="text-xs tracking-wider">{stream.label} · not connected</div>
      {stream.type === "foxglove" && (
        <div className="flex flex-col items-center gap-3 text-[10px]">
          <div className="text-center leading-relaxed opacity-60">
            Foxglove bridge is not running.<br />
            {stream.foxglove_ws && <span>Listening on: {stream.foxglove_ws}</span>}
          </div>
          {stream.has_launcher && (
            <button
              onClick={onLaunch}
              disabled={launching}
              className="border border-border px-4 py-2 hover:border-foreground/40 hover:text-foreground transition-colors disabled:opacity-40 text-xs tracking-widest uppercase"
            >
              {launching ? "Launching…" : "Launch Foxglove Bridge"}
            </button>
          )}
        </div>
      )}
      {stream.type === "webrtc" && (
        <div className="text-[10px] text-center leading-relaxed opacity-60">
          Isaac Sim is not running or WebRTC extension is disabled.<br />
          Start Isaac with <code className="bg-muted px-1">--enable-extension omni.kit.livestream.webrtc</code>
        </div>
      )}
    </div>
  );
}

// ── Zone overlay ──────────────────────────────────────────────────────────────

function ZoneOverlay({ enabled }: { enabled: boolean }) {
  const t = useTelemetry();
  if (!enabled || !t) return null;

  const zoneColour = {
    GREEN: "rgba(34,197,94,0.15)",
    AMBER: "rgba(245,158,11,0.15)",
    RED:   "rgba(239,68,68,0.2)",
  }[t.zone];

  return (
    <div
      className="absolute inset-0 pointer-events-none transition-colors duration-500"
      style={{ border: `2px solid ${zoneColour}`, background: "transparent" }}
    >
      {/* Corner brackets */}
      {[
        "top-0 left-0 border-t border-l",
        "top-0 right-0 border-t border-r",
        "bottom-0 left-0 border-b border-l",
        "bottom-0 right-0 border-b border-r",
      ].map((pos, i) => (
        <div
          key={i}
          className={`absolute w-6 h-6 ${pos}`}
          style={{ borderColor: zoneColour }}
        />
      ))}

      {/* Zone badge */}
      <div
        className="absolute top-3 left-1/2 -translate-x-1/2 font-mono text-[10px] px-2 py-0.5 tracking-widest uppercase"
        style={{ background: zoneColour, color: "white" }}
      >
        {t.zone}
      </div>
    </div>
  );
}

// ── Main ViewportPanel ────────────────────────────────────────────────────────

export function ViewportPanel({ className = "" }: { className?: string }) {
  const [streams, setStreams]         = useState<StreamInfo[]>([]);
  const [activeId, setActiveId]       = useState<string>("mujoco");
  const [fullscreen, setFullscreen]   = useState(false);
  const [overlay, setOverlay]         = useState(true);
  const [launching, setLaunching]     = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get<StreamInfo[]>("/api/streams")
      .then(ss => {
        setStreams(ss);
        // Auto-select first connected stream if available
        const connected = ss.find(s => s.status === "connected" || s.status === "available");
        if (connected) setActiveId(connected.id);
      })
      .catch(() => {});
    // Refresh every 8 seconds
    const id = setInterval(() => {
      api.get<StreamInfo[]>("/api/streams").then(setStreams).catch(() => {});
    }, 8000);
    return () => clearInterval(id);
  }, []);

  const active = streams.find(s => s.id === activeId) ?? null;
  const isConnected = active && (active.status === "connected" || active.status === "available");

  async function launchBridge(stream_id: string) {
    setLaunching(stream_id);
    try {
      await fetch(`${BASE}/api/streams/${stream_id}/launch`, { method: "POST" });
      setTimeout(() => {
        api.get<StreamInfo[]>("/api/streams").then(setStreams).catch(() => {});
      }, 3000);
    } finally {
      setLaunching(null);
    }
  }

  function screenshot() {
    // For MJPEG: open the snapshot URL in a new tab
    if (active?.mjpeg_url) {
      window.open(`${BASE}${active.mjpeg_url}?fps=1`, "_blank");
    }
  }

  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen();
      setFullscreen(true);
    } else {
      document.exitFullscreen();
      setFullscreen(false);
    }
  }

  useEffect(() => {
    const handler = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  return (
    <div ref={containerRef} className={`flex flex-col border border-border bg-black overflow-hidden ${className} ${fullscreen ? "fixed inset-0 z-50" : ""}`}>
      {/* Toolbar */}
      <div className="flex items-center gap-0 border-b border-border bg-card/80 backdrop-blur shrink-0 overflow-x-auto">
        {streams.map(s => (
          <button
            key={s.id}
            onClick={() => setActiveId(s.id)}
            className={`flex items-center gap-1.5 px-3 py-2 font-mono text-[10px] uppercase tracking-wide whitespace-nowrap transition-colors border-r border-border ${
              activeId === s.id
                ? "bg-foreground text-background"
                : "text-muted-foreground hover:text-foreground hover:bg-accent"
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[s.status] ?? "bg-muted-foreground/20"}`} />
            {s.label}
          </button>
        ))}

        <div className="ml-auto flex items-center gap-1 px-2">
          <button
            onClick={() => setOverlay(v => !v)}
            title="Toggle zone overlay"
            className={`p-1.5 rounded transition-colors ${overlay ? "text-foreground" : "text-muted-foreground/40"} hover:bg-accent`}
          >
            <Circle size={12} strokeWidth={1.5} />
          </button>
          <button
            onClick={screenshot}
            title="Screenshot"
            disabled={!active?.mjpeg_url}
            suppressHydrationWarning
            className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors disabled:opacity-30"
          >
            <Camera size={12} strokeWidth={1.5} />
          </button>
          <button
            onClick={toggleFullscreen}
            title="Fullscreen"
            className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            {fullscreen ? <Minimize2 size={12} strokeWidth={1.5} /> : <Maximize2 size={12} strokeWidth={1.5} />}
          </button>
        </div>
      </div>

      {/* Viewport */}
      <div className="relative flex-1 min-h-0">
        {!active ? (
          <div className="w-full h-full flex items-center justify-center font-mono text-xs text-muted-foreground/30">
            Loading streams…
          </div>
        ) : !isConnected ? (
          <DisconnectedView
            stream={active}
            onLaunch={() => launchBridge(active.id)}
            launching={launching === active.id}
          />
        ) : active.type === "foxglove" && active.foxglove_ws ? (
          <FoxgloveEmbed wsUrl={active.foxglove_ws} label={active.label} />
        ) : active.type === "webrtc" ? (
          <WebRTCPlayer streamId={active.id} label={active.label} />
        ) : active.type === "mjpeg" && active.mjpeg_url ? (
          <MjpegPlayer streamId={active.id} mjpegUrl={active.mjpeg_url} label={active.label} />
        ) : null}

        <ZoneOverlay enabled={overlay} />
      </div>
    </div>
  );
}
