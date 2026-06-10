"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

export type WebRTCState = "idle" | "connecting" | "connected" | "failed";

export function useWebRTC(
  streamId: string | null,
  videoRef: React.RefObject<HTMLVideoElement | null>,
) {
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const [state, setState] = useState<WebRTCState>("idle");

  useEffect(() => {
    if (!streamId) {
      setState("idle");
      return;
    }

    setState("connecting");
    let alive = true;

    async function connect() {
      try {
        const pc = new RTCPeerConnection({
          iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
        });
        pcRef.current = pc;

        pc.ontrack = (e) => {
          if (videoRef.current && e.streams[0]) {
            videoRef.current.srcObject = e.streams[0];
          }
        };

        pc.onconnectionstatechange = () => {
          if (!alive) return;
          if (pc.connectionState === "connected") setState("connected");
          if (pc.connectionState === "failed") setState("failed");
        };

        // Add a receive-only transceiver
        pc.addTransceiver("video", { direction: "recvonly" });

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        // Wait for ICE gathering
        await new Promise<void>((resolve) => {
          if (pc.iceGatheringState === "complete") { resolve(); return; }
          pc.onicegatheringstatechange = () => {
            if (pc.iceGatheringState === "complete") resolve();
          };
          setTimeout(resolve, 2000); // 2s max
        });

        const res = await fetch(
          (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api/webrtc/offer",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              stream_id: streamId,
              sdp:  pc.localDescription!.sdp,
              type: pc.localDescription!.type,
            }),
          },
        );

        if (!res.ok) throw new Error(`SDP offer failed: ${res.status}`);
        const answer = await res.json();
        await pc.setRemoteDescription(answer);
      } catch (err) {
        if (alive) setState("failed");
      }
    }

    connect();
    return () => {
      alive = false;
      pcRef.current?.close();
      pcRef.current = null;
    };
  }, [streamId]); // eslint-disable-line react-hooks/exhaustive-deps

  return state;
}
