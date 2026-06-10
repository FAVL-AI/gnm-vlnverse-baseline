"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { MatrixRain } from "@/components/MatrixRain";

export default function LandingPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [entering, setEntering] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setReady(true), 400);
    return () => clearTimeout(t);
  }, []);

  function enter() {
    setEntering(true);
    setTimeout(() => router.push("/dashboard"), 500);
  }

  return (
    <main
      className="relative overflow-hidden bg-black flex flex-col items-center justify-center"
      style={{ minHeight: "100dvh" }}
    >
      <MatrixRain />

      {/* Vignette */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 80% 60% at 50% 50%, transparent 0%, rgba(0,0,0,0.75) 100%)",
        }}
      />

      {/* Content */}
      <div
        className="relative z-10 flex flex-col items-center gap-8"
        style={{
          opacity: ready && !entering ? 1 : 0,
          transform: entering ? "scale(0.96)" : "scale(1)",
          transition: "opacity 0.5s, transform 0.5s",
        }}
      >
        <div className="flex flex-col items-center gap-3 select-none">
          <span
            className="text-white font-mono font-bold uppercase"
            style={{ fontSize: "clamp(1.5rem, 4vw, 2.5rem)", letterSpacing: "0.3em" }}
          >
            FLEETSAFE
          </span>
          <div
            className="font-mono text-white/40 uppercase"
            style={{ fontSize: "clamp(0.55rem, 1.5vw, 0.75rem)", letterSpacing: "0.5em" }}
          >
            command&nbsp;&nbsp;center
          </div>
        </div>

        <div className="w-px h-10 bg-white/20" />

        <p
          className="font-mono text-white/50 text-center max-w-sm leading-relaxed"
          style={{ fontSize: "clamp(0.65rem, 1.5vw, 0.8rem)", letterSpacing: "0.05em" }}
        >
          Benchmark orchestration for embodied AI.
          <br />
          Isaac · MuJoCo · ROS2 · Real robot.
        </p>

        <button
          onClick={enter}
          className="group relative font-mono text-xs uppercase text-white/70 border border-white/20 px-8 py-3 hover:border-white/60 hover:text-white transition-all duration-200 focus:outline-none focus:ring-1 focus:ring-white/30"
          style={{ letterSpacing: "0.3em" }}
        >
          <span className="relative z-10">Enter</span>
          <span className="absolute inset-0 bg-white/0 group-hover:bg-white/5 transition-colors duration-200" />
        </button>

        <div className="font-mono text-white/20" style={{ fontSize: "0.6rem", letterSpacing: "0.2em" }}>
          v0.1&nbsp;·&nbsp;FLEETSAFE-VISUALNAV-BENCHMARK
        </div>
      </div>
    </main>
  );
}
