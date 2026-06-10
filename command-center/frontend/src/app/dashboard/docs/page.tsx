const TOC = [
  { id: "overview",        label: "Overview"         },
  { id: "sections",        label: "Dashboard"        },
  { id: "benchmarks",      label: "Benchmarks"       },
  { id: "robot-controls",  label: "Robot Controls"   },
  { id: "evidence",        label: "Evidence"         },
  { id: "api",             label: "API"              },
  { id: "cli",             label: "CLI Reference"    },
];

const DASHBOARD_ROWS = [
  ["Overview",        "Run summaries and KPIs",                           "No"],
  ["Experiments",     "Full backbone × safety matrix",                    "No"],
  ["Evidence",        "Append-only ledger with SHA256 artifacts",         "No"],
  ["Publication",     "Bundle export and readiness score",                "No"],
  ["Replay",          "Per-episode trajectory and action replay",         "No"],
  ["Robot Control",   "SSH relay, e-stop, watchdog, preflight",           "Yes (local backend)"],
  ["Commissioning",   "Robot FSM — DISARMED → RELAY_ENABLED",            "Yes (local backend)"],
];

const ENV_ROWS = [
  ["FLEETSAFE_ROBOT_SSH",      "SSH target",              "jetson@100.91.232.55"],
  ["FLEETSAFE_ROBOT_DRY_RUN",  "Dry-run mode",            "true"],
  ["FLEETSAFE_ROBOT_PASSWORD", "sshpass fallback",        "(never commit)"],
  ["NEXT_PUBLIC_API_URL",      "Backend URL",             "http://localhost:8000"],
  ["NEXT_PUBLIC_DEPLOYMENT_MODE", "public_readonly or live", "—"],
];

export default function DocsPage() {
  return (
    <div className="flex gap-8 px-8 py-10 max-w-5xl mx-auto">
      {/* Sticky TOC */}
      <aside className="w-48 shrink-0">
        <div className="sticky top-10 space-y-0.5">
          <p className="font-mono text-[9px] uppercase tracking-wider text-foreground/40 mb-3">
            Contents
          </p>
          {TOC.map(({ id, label }) => (
            <a
              key={id}
              href={`#${id}`}
              className="block font-mono text-[11px] text-foreground/60 hover:text-foreground py-0.5 transition-colors"
            >
              {label}
            </a>
          ))}
        </div>
      </aside>

      {/* Content */}
      <div className="flex-1 max-w-3xl space-y-12">

        <section id="overview">
          <h2 className="font-mono text-sm font-semibold text-foreground mb-3">Overview</h2>
          <p className="text-foreground/80 text-[13px] leading-relaxed">
            FleetSafe Command Center is the operator interface for the
            FleetSafe-VisualNav-Benchmark. It connects the simulation pipeline,
            evidence tracking, and real-robot controls in one dashboard.
          </p>
          <p className="text-foreground/80 text-[13px] leading-relaxed mt-3">
            The benchmark evaluates visual navigation backbones (GNM, ViNT, NoMaD) under
            safety-critical conditions: communication delays, sensor degradation, and unexpected
            obstacles. All results are logged with SHA256-anchored evidence for reproducibility.
          </p>
        </section>

        <section id="sections">
          <h2 className="font-mono text-sm font-semibold text-foreground mb-3">Dashboard sections</h2>
          <div className="border border-border overflow-hidden">
            <table className="w-full text-[11px] font-mono">
              <thead>
                <tr className="border-b border-border bg-muted">
                  <th className="text-left px-3 py-2 text-foreground/60 font-normal">Section</th>
                  <th className="text-left px-3 py-2 text-foreground/60 font-normal">Description</th>
                  <th className="text-left px-3 py-2 text-foreground/60 font-normal">Live-only?</th>
                </tr>
              </thead>
              <tbody>
                {DASHBOARD_ROWS.map(([section, desc, live], i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    <td className="px-3 py-2 text-foreground/90">{section}</td>
                    <td className="px-3 py-2 text-foreground/70">{desc}</td>
                    <td className="px-3 py-2 text-foreground/50">{live}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section id="benchmarks">
          <h2 className="font-mono text-sm font-semibold text-foreground mb-3">Running benchmarks</h2>
          <p className="text-foreground/80 text-[13px] leading-relaxed mb-4">
            The benchmark suite is driven by Python scripts in <code className="font-mono text-[11px] bg-muted px-1 py-0.5">scripts/</code>.
            All runs log to WandB and write SHA256-anchored artifacts to the evidence ledger.
          </p>
          <div className="space-y-3">
            <div>
              <p className="font-mono text-[10px] text-foreground/50 mb-1">Smoke test</p>
              <pre className="bg-muted rounded p-3 font-mono text-[11px] text-foreground/90 overflow-x-auto">{`python scripts/visualnav/run_visualnav_benchmark.py \\
  --model gnm --seeds smoke --backend mock --fleetsafe both`}</pre>
            </div>
            <div>
              <p className="font-mono text-[10px] text-foreground/50 mb-1">Full backbone matrix</p>
              <pre className="bg-muted rounded p-3 font-mono text-[11px] text-foreground/90 overflow-x-auto">{`python scripts/benchmarks/run_publication_smoke_matrix.py`}</pre>
            </div>
            <div>
              <p className="font-mono text-[10px] text-foreground/50 mb-1">Delay injection</p>
              <pre className="bg-muted rounded p-3 font-mono text-[11px] text-foreground/90 overflow-x-auto">{`python scripts/benchmarks/run_delay_injection_matrix.py`}</pre>
            </div>
          </div>
        </section>

        <section id="robot-controls">
          <h2 className="font-mono text-sm font-semibold text-foreground mb-3">Robot Controls</h2>
          <p className="text-foreground/80 text-[13px] leading-relaxed mb-4">
            Safe motion requires a strict sequence to prevent uncontrolled movement.
            Always follow these steps when operating the physical robot.
          </p>
          <ol className="space-y-3 list-decimal list-inside text-[13px]">
            <li className="text-foreground/80 leading-relaxed">
              Start backend with{" "}
              <code className="font-mono text-[11px] bg-muted px-1 py-0.5">FLEETSAFE_ROBOT_DRY_RUN=false</code>
            </li>
            <li className="text-foreground/80 leading-relaxed">
              Run preflight check via the Robot Control page
            </li>
            <li className="text-foreground/80 leading-relaxed">
              All 4 conditions green → enable relay
            </li>
            <li className="text-foreground/80 leading-relaxed">
              Watchdog arms automatically — kills relay if blocked publisher detected on{" "}
              <code className="font-mono text-[11px] bg-muted px-1 py-0.5">/cmd_vel</code>
            </li>
          </ol>
        </section>

        <section id="evidence">
          <h2 className="font-mono text-sm font-semibold text-foreground mb-3">Evidence tracking</h2>
          <p className="text-foreground/80 text-[13px] leading-relaxed">
            The evidence ledger is an append-only log of claims backed by SHA256-hashed artifacts.
            Each claim has a status: <code className="font-mono text-[11px] bg-muted px-1 py-0.5">PROVEN</code>,{" "}
            <code className="font-mono text-[11px] bg-muted px-1 py-0.5">RECORDED</code>,{" "}
            <code className="font-mono text-[11px] bg-muted px-1 py-0.5">PRELIMINARY</code>, or{" "}
            <code className="font-mono text-[11px] bg-muted px-1 py-0.5">RECORDED_ONLY</code>.
          </p>
          <p className="text-foreground/80 text-[13px] leading-relaxed mt-3">
            Artifacts are uploaded to HuggingFace Hub (
            <code className="font-mono text-[11px] bg-muted px-1 py-0.5">FAVL/fleetsafe-hospitalnav</code>)
            via <code className="font-mono text-[11px] bg-muted px-1 py-0.5">scripts/integrations/sync_wandb_hf_metadata.py</code>.
            The publication readiness score is a weighted average across 7 evidence claims —
            target 80% for submission.
          </p>
        </section>

        <section id="api">
          <h2 className="font-mono text-sm font-semibold text-foreground mb-3">API</h2>
          <p className="text-foreground/80 text-[13px] leading-relaxed">
            The FastAPI backend runs on port 8000 by default.
            Set <code className="font-mono text-[11px] bg-muted px-1 py-0.5">NEXT_PUBLIC_API_URL</code> to
            override. Key endpoints:
          </p>
          <pre className="bg-muted rounded p-3 font-mono text-[11px] text-foreground/90 mt-3 overflow-x-auto">{`GET  /api/health                 # Backend liveness
GET  /api/evidence/ledger        # Full evidence ledger
GET  /api/runs                   # All benchmark runs
GET  /api/publication/bundle     # Latest publication bundle
POST /api/robot/preflight        # Run preflight check
POST /api/robot/relay/enable     # Enable motion relay
POST /api/robot/estop            # Emergency stop`}</pre>
        </section>

        <section id="cli">
          <h2 className="font-mono text-sm font-semibold text-foreground mb-3">CLI Reference</h2>
          <p className="text-foreground/80 text-[13px] leading-relaxed mb-4">
            Key environment variables for local operation:
          </p>
          <div className="border border-border overflow-hidden">
            <table className="w-full text-[11px] font-mono">
              <thead>
                <tr className="border-b border-border bg-muted">
                  <th className="text-left px-3 py-2 text-foreground/60 font-normal">Variable</th>
                  <th className="text-left px-3 py-2 text-foreground/60 font-normal">Purpose</th>
                  <th className="text-left px-3 py-2 text-foreground/60 font-normal">Default</th>
                </tr>
              </thead>
              <tbody>
                {ENV_ROWS.map(([varname, purpose, def_], i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    <td className="px-3 py-2 text-foreground/90">{varname}</td>
                    <td className="px-3 py-2 text-foreground/70">{purpose}</td>
                    <td className="px-3 py-2 text-foreground/50">{def_}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

      </div>
    </div>
  );
}
