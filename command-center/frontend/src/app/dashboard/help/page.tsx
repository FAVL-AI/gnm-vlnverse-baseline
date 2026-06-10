"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

const FAQ = [
  {
    q: "What is dry-run mode?",
    a: "When FLEETSAFE_ROBOT_DRY_RUN=true (default), all SSH commands are logged but not executed on the robot. Switch to false only when physically present at the robot.",
  },
  {
    q: "Why is my relay guard failing?",
    a: "The relay guard requires: /cmd_vel publisher count = 0, /cmd_vel_raw subscriber = fleetsafe_perception, /cmd_vel_safe publisher = fleetsafe_perception. Run the preflight check on Robot Control to see which condition is failing.",
  },
  {
    q: "What is the publication readiness score?",
    a: "A weighted score across 7 evidence claims. PROVEN=1.0, RECORDED=0.7, PRELIMINARY=0.5, RECORDED_ONLY=0.3. Target is 80% for submission.",
  },
  {
    q: "How do I access the public dashboard without the backend?",
    a: "The Vercel deployment shows Experiments, Evidence, Publication, and Reproducibility pages without a running backend. Robot Control and Commissioning are hidden in public_readonly mode.",
  },
  {
    q: "What is sshpass and when is it used?",
    a: "sshpass provides password authentication when SSH key auth is not configured. Set FLEETSAFE_ROBOT_PASSWORD in your local environment. The password is passed via the SSHPASS env var — never via CLI argv or audit logs.",
  },
];

const PROBLEMS = [
  {
    problem: "API Offline",
    solution: "Check that ./command-center/start.sh is running. The backend runs on port 8000 by default. Verify with: curl http://localhost:8000/api/health",
  },
  {
    problem: "SSH connection refused",
    solution: "Ensure the Jetson is powered on and connected to the same network/VPN (Tailscale). Test with: ssh jetson@100.91.232.55 echo OK. If key auth fails, set FLEETSAFE_ROBOT_PASSWORD and ensure sshpass is installed.",
  },
  {
    problem: "Relay guard FAIL: publisher count > 0",
    solution: "Another node is publishing on /cmd_vel. Run the Safe Motion Preflight on the Robot Control page. Use 'kill source' next to any BLOCKED publisher.",
  },
  {
    problem: "WandB shows MISSING",
    solution: "Set WANDB_API_KEY and ensure entity=f-a-v-l project=fleet-safe-vla. Run: python scripts/integrations/sync_wandb_hf_metadata.py",
  },
  {
    problem: "HuggingFace shows NOT_RUN",
    solution: "Set HF_TOKEN and HF_REPO_ID=FAVL/fleetsafe-hospitalnav. Run: python scripts/integrations/sync_wandb_hf_metadata.py",
  },
  {
    problem: "ViNT / NoMaD import errors",
    solution: "Install: pip install efficientnet_pytorch warmup-scheduler 'diffusers>=0.20.0' einops. For diffusion_policy: clone and install from GitHub (not on PyPI).",
  },
  {
    problem: "Publication readiness stuck below 80%",
    solution: "Check claim_validation_report.json in the latest publication bundle. Run the full backbone matrix (run_publication_smoke_matrix.py) and delay injection (run_delay_injection_matrix.py) to advance PRELIMINARY claims to PROVEN.",
  },
];

type Tab = "faq" | "troubleshooting";

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-border">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left group"
      >
        <span className="font-mono text-[12px] text-foreground group-hover:text-foreground/80 transition-colors">
          {q}
        </span>
        <ChevronDown
          size={14}
          strokeWidth={1.5}
          className={`shrink-0 text-foreground/40 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-border">
          <p className="font-mono text-[11px] text-foreground/70 leading-relaxed mt-3">{a}</p>
        </div>
      )}
    </div>
  );
}

export default function HelpPage() {
  const [tab, setTab] = useState<Tab>("faq");

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <h1 className="font-mono text-sm font-semibold text-foreground tracking-wide uppercase mb-6">
        Help & Troubleshooting
      </h1>

      {/* Tabs */}
      <div className="flex border-b border-border mb-8">
        {(["faq", "troubleshooting"] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`font-mono text-[10px] uppercase tracking-wider px-4 py-2 border-b-2 transition-colors ${
              tab === t
                ? "border-foreground text-foreground"
                : "border-transparent text-foreground/50 hover:text-foreground/75"
            }`}
          >
            {t === "faq" ? "FAQ" : "Troubleshooting"}
          </button>
        ))}
      </div>

      {/* FAQ */}
      {tab === "faq" && (
        <div className="space-y-2">
          {FAQ.map((item, i) => (
            <FaqItem key={i} q={item.q} a={item.a} />
          ))}
        </div>
      )}

      {/* Troubleshooting */}
      {tab === "troubleshooting" && (
        <div className="space-y-3">
          {PROBLEMS.map(({ problem, solution }, i) => (
            <div key={i} className="border border-border p-4">
              <p className="text-foreground font-semibold text-[12px] font-mono">{problem}</p>
              <p className="text-foreground/75 text-[11px] mt-1 font-mono leading-relaxed">
                {solution}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
