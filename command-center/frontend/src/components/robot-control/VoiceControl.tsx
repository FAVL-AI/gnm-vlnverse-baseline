"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Mic, MicOff } from "lucide-react";

// Web Speech API type shim
declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognition;
    webkitSpeechRecognition?: new () => SpeechRecognition;
  }
  interface SpeechRecognition extends EventTarget {
    continuous: boolean;
    interimResults: boolean;
    lang: string;
    start(): void;
    stop(): void;
    onresult: ((e: SpeechRecognitionEvent) => void) | null;
    onerror: ((e: Event) => void) | null;
    onend: (() => void) | null;
  }
  interface SpeechRecognitionEvent extends Event {
    results: SpeechRecognitionResultList;
    resultIndex: number;
  }
  interface SpeechRecognitionResultList {
    readonly length: number;
    item(index: number): SpeechRecognitionResult;
    [index: number]: SpeechRecognitionResult;
  }
  interface SpeechRecognitionResult {
    readonly isFinal: boolean;
    [index: number]: SpeechRecognitionAlternative;
  }
  interface SpeechRecognitionAlternative {
    readonly transcript: string;
    readonly confidence: number;
  }
}

const WAKE = "neo";

interface Props {
  voiceMap: Record<string, string>;
  onCommand: (opId: string, phrase: string) => void;
}

export function VoiceControl({ voiceMap, onCommand }: Props) {
  const [active, setActive] = useState(false);
  const [lastPhrase, setLastPhrase] = useState<string | null>(null);
  const [supported, setSupported] = useState(true);
  const recRef = useRef<SpeechRecognition | null>(null);

  const handleResult = useCallback((transcript: string) => {
    const phrase = transcript.toLowerCase().trim();
    if (!phrase.startsWith(WAKE)) return;
    setLastPhrase(phrase);
    const op = voiceMap[phrase];
    if (op) onCommand(op, phrase);
  }, [voiceMap, onCommand]);

  useEffect(() => {
    const SR = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!SR) { setSupported(false); return; }

    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = false;
    rec.lang = "en-US";
    rec.onresult = (e: SpeechRecognitionEvent) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) handleResult(e.results[i][0].transcript);
      }
    };
    rec.onerror = () => { setActive(false); };
    rec.onend = () => { setActive(false); };
    recRef.current = rec;
    return () => { rec.stop(); };
  }, [handleResult]);

  function toggle() {
    if (!recRef.current) return;
    if (active) {
      recRef.current.stop();
      setActive(false);
    } else {
      recRef.current.start();
      setActive(true);
    }
  }

  if (!supported) {
    return (
      <div className="font-mono text-[8px] text-muted-foreground/30">
        Voice not supported in this browser.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={toggle}
        className={`flex items-center gap-2 px-3 py-2 border font-mono text-[9px] transition-colors
          ${active
            ? "border-red-500/60 text-red-400 animate-pulse"
            : "border-border text-muted-foreground/40 hover:text-muted-foreground hover:border-border/80"}`}
      >
        {active ? <><Mic size={10} /> Listening… say "Neo …"</> : <><MicOff size={10} /> Enable Voice</>}
      </button>
      {lastPhrase && (
        <div className="font-mono text-[8px] text-muted-foreground/40 truncate">
          Last: <span className="text-foreground/50">{lastPhrase}</span>
        </div>
      )}
      <div className="font-mono text-[7px] text-muted-foreground/20 flex flex-col gap-0.5">
        {Object.entries(voiceMap).map(([phrase, op]) => (
          <div key={phrase} className="flex gap-2">
            <span className="text-muted-foreground/30 shrink-0">&quot;{phrase}&quot;</span>
            <span className="text-muted-foreground/20">→ {op}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
