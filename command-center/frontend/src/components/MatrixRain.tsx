"use client";

import { useEffect, useRef } from "react";

const CHARS =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθ" +
  "fleetsafe visualnav gnm vint nomad mujoco isaaclab spl collision zone ";

export function MatrixRain({ className = "" }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const FONT_SIZE = 13;
    let cols = 0;
    let drops: number[] = [];

    function resize() {
      canvas!.width  = window.innerWidth;
      canvas!.height = window.innerHeight;
      cols  = Math.floor(canvas!.width / FONT_SIZE);
      drops = Array.from({ length: cols }, () => Math.random() * -50);
    }
    resize();
    window.addEventListener("resize", resize);

    let raf: number;

    function draw() {
      if (!ctx || !canvas) return;

      // Dark translucent fade — creates the trailing tail
      ctx.fillStyle = "rgba(0, 0, 0, 0.05)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.font = `${FONT_SIZE}px monospace`;

      for (let i = 0; i < cols; i++) {
        const char = CHARS[Math.floor(Math.random() * CHARS.length)];
        const y = drops[i] * FONT_SIZE;

        // Lead character — bright white
        ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
        ctx.fillText(char, i * FONT_SIZE, y);

        // Body — dim white at varying opacity
        const prevChar = CHARS[Math.floor(Math.random() * CHARS.length)];
        ctx.fillStyle = `rgba(200, 200, 200, ${0.08 + Math.random() * 0.12})`;
        ctx.fillText(prevChar, i * FONT_SIZE, y - FONT_SIZE);

        if (y > canvas.height && Math.random() > 0.975) {
          drops[i] = 0;
        }
        drops[i] += 0.5;
      }

      raf = requestAnimationFrame(draw);
    }

    draw();
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 ${className}`}
      style={{ pointerEvents: "none" }}
    />
  );
}
