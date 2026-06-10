SHELL := /bin/bash

# GNM-VLNVerse Baseline — Makefile
#
# ── GNM/VLNVerse targets ──────────────────────────────────────────────────────
#   make prove-dataset      — Validate dataset (238 train, 15 val)
#   make list-scenes        — List four Kujiale scenes with counts
#   make export-dashboard   — Export live START|CURRENT|GOAL dashboard PNGs
#   make testdrive-dryrun   — Print manual test-drive controls and schema
#   make test               — Run all tests/gnm tests
#   make source-clean-check — Confirm no binary/generated files tracked

PYTHON    := python3
REPO_ROOT := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

# ── GNM/VLNVerse targets ──────────────────────────────────────────────────────
.PHONY: prove-dataset list-scenes export-dashboard testdrive-dryrun test source-clean-check

prove-dataset:
	$(PYTHON) scripts/gnm/replay_gnm_demo.py --prove-dataset

list-scenes:
	$(PYTHON) scripts/gnm/replay_gnm_demo.py --list-scenes

export-dashboard:
	$(PYTHON) scripts/gnm/replay_gnm_demo.py --export-live-dashboard

testdrive-dryrun:
	$(PYTHON) scripts/gnm/manual_testdrive.py --dry-run
	$(PYTHON) scripts/gnm/replay_manual_testdrive.py --dry-run
	$(PYTHON) scripts/gnm/convert_manual_testdrive_to_gnm.py --dry-run

test:
	$(PYTHON) -m pytest tests/gnm -q

source-clean-check:
	@git ls-files | grep -E '(^simulations/|^topomaps/|^recordings/|^results/figures/|^results/bo_reviewer_packet/live_dashboard/|^results/bo_reviewer_packet/05_gnm_input_output_triplet\.png|^evidence/|^data/gnm_from_hdf5/|^data/gnm_hospital_dataset/|^data/isaac_vint_proof/|^data/training_episodes_with_images/|datasets/custom_vln_office/.*/rgb/|^datasets/vlntube/train|^datasets/vlntube/val|command-center/frontend/public/(evidence|figures|live|icons)/|command-center/recordings/|\.jpg$$|\.jpeg$$|\.png$$|\.mp4$$|\.pt$$|\.pth$$|\.ckpt$$)' \
	&& echo "WARNING: binary/generated files tracked" || echo "OK: repo is source-code clean"

# ── Legacy scripts (retained from wider workspace) ────────────────────────────
# ── Benchmark scripts ─────────────────────────────────────────────────────────
BENCH_SCRIPT  := scripts/benchmarks/benchmark.py
TABLE_SCRIPT  := scripts/benchmarks/generate_results_table.py
GAZEBO_BENCH  := scripts/benchmarks/m3pro_gazebo_benchmark.py
AUDIT_DASH    := scripts/benchmarks/m3pro_nav_audit_dashboard.py
ROS2_CONV     := scripts/visualnav/ros2_to_vnt_converter.py
MATRIX        := scripts/visualnav/run_evaluation_matrix.py
UNIFIED_BENCH := scripts/benchmarks/unified_benchmark.py

# ── Isaac Sim scripts ─────────────────────────────────────────────────────────
LOAD_NVIDIA   := scripts/isaaclab/load_nvidia_assets.py
EXPORT_VINT   := scripts/isaaclab/export_vint_dataset.py

# ── Gazebo world setup ────────────────────────────────────────────────────────
SETUP_AWS     := scripts/ros2_gazebo/setup_aws_worlds.sh

# ── Result directories ────────────────────────────────────────────────────────
RESULTS_DIR      := results
BENCH_OUT        := $(RESULTS_DIR)/benchmark_latest
GAZEBO_OUT       := $(RESULTS_DIR)/gazebo_latest
AUDIT_OUT        := $(RESULTS_DIR)/audit_latest
BENCH_FINAL      := $(RESULTS_DIR)/benchmark_final
UNIFIED_OUT      := $(RESULTS_DIR)/unified_benchmark
ISAAC_ASSETS_OUT := IsaacLabAssets

# ── Bag files (configure for your machine) ────────────────────────────────────
BAG_DIR          := recordings
DATASET_OUT      := data/gnm_hospital_dataset
DATASET_NAME     := fleetsafe
ISAAC_DATASET    := data/isaac_vint_dataset

# ── Isaac Sim environment (override per machine) ──────────────────────────────
ISAAC_ENV      := hospital
ISAAC_USD      := $(ISAAC_ASSETS_OUT)/$(ISAAC_ENV)_photorealistic.usd
ISAAC_CONDA    := isaac
# Set ISAAC_HEADLESS=0 to open the Isaac Kit GUI; default headless for CI/server
ISAAC_HEADLESS := 1

.PHONY: all figures verify update paper bundle pub check finalize clean \
        benchmark benchmark-paper benchmark-results benchmark-gazebo benchmark-ros2 \
        audit convert-bag results-table matrix \
        benchmark-unified \
        isaac-load-assets isaac-export-vint isaac-load-validate \
        gazebo-setup-aws m3pro-gazebo \
        clean-results clean-isaac \
        robot-check robot-install robot-install-jetson-deps robot-bundle robot-status robot-start robot-stop-motion \
        robot-discover-yahboom robot-diagnose-yahboom robot-start-yahboom robot-status-yahboom robot-live-preflight \
        vln-live-preflight vln-full-preflight vln-live-motion-proof \
        formal-check formal-report no-blackbox-audit \
        certify-latest-real-bag verify-latest-real-cert formal-real-report \
        vln-audit vln-demo-dry vln-demo-text vln-demo-voice-mock vln-demo-live \
        vln-tests vln-check vln-send vln-record vln-formal-report vln-report \
        vln-robot vln-robot-live \
        vln-desktop vln-desktop-radius vln-desktop-live \
        vln-watch-parsed vln-watch-nominal vln-watch-cert \
        vln-check-stack vln-lidar-inspect vln-evidence-latest vln-camera-check \
        vln-clear-estop vln-demo-voice-proof \
        robot-voice-discover voice-start-robot robot-sync-repo

all: verify figures

## ── Benchmark ────────────────────────────────────────────────────────────────

benchmark:
	@echo "[FleetSafe] Running benchmark (mock, 10 seeds)..."
	$(PYTHON) $(BENCH_SCRIPT) \
	    --models gnm vint \
	    --seeds 10 \
	    --max-steps 120 \
	    --output $(BENCH_OUT)
	@echo "[FleetSafe] Done → $(BENCH_OUT)/"

benchmark-paper:
	@echo "[FleetSafe] Running benchmark (paper mode, 50 seeds, all models)..."
	$(PYTHON) $(BENCH_SCRIPT) \
	    --paper \
	    --output $(BENCH_OUT)_paper
	@echo "[FleetSafe] Done → $(BENCH_OUT)_paper/"

benchmark-results:
	@echo "[FleetSafe] Generating authoritative results table..."
	$(PYTHON) $(TABLE_SCRIPT) \
	    --real-results $(RESULTS_DIR)/may29_evaluation_full.json \
	    --output $(BENCH_FINAL)
	@echo "[FleetSafe] Table → $(BENCH_FINAL)/benchmark_table_paper.tex"

results-table: benchmark-results

## ── Gazebo / M3Pro Benchmark ─────────────────────────────────────────────────

benchmark-gazebo:
	@echo "[FleetSafe] Running M3Pro Gazebo benchmark (mock mode)..."
	$(PYTHON) $(GAZEBO_BENCH) \
	    --worlds hospital warehouse hunav_cafe \
	    --models gnm vint \
	    --fleetsafe \
	    --num-episodes 20 \
	    --output-dir $(GAZEBO_OUT)
	@echo "[FleetSafe] Done → $(GAZEBO_OUT)/"

benchmark-ros2:
	@echo "[FleetSafe] Running M3Pro benchmark with real Gazebo (ROS2 mode)..."
	@echo "  Requires: source /opt/ros/humble/setup.bash && source ~/m3pro_sim_ws/install/setup.bash"
	$(PYTHON) $(GAZEBO_BENCH) \
	    --mode ros2 \
	    --worlds hospital \
	    --models gnm vint \
	    --fleetsafe \
	    --num-episodes 20 \
	    --gnm-ckpt third_party/visualnav-transformer/model_weights/gnm/gnm.pth \
	    --vint-ckpt third_party/visualnav-transformer/model_weights/vint/vint.pth \
	    --output-dir $(GAZEBO_OUT)_ros2

## ── Evaluation matrix (quick 4-condition comparison) ────────────────────────

matrix:
	@echo "[FleetSafe] Running 4-condition evaluation matrix..."
	$(PYTHON) $(MATRIX) \
	    --models gnm vint \
	    --episodes 10 \
	    --scenes hospital_corridor cluttered_navigation \
	    --max-steps 80 \
	    --output $(RESULTS_DIR)/matrix_latest.json
	@echo "[FleetSafe] Results → $(RESULTS_DIR)/matrix_latest.json"

## ── Navigation audit dashboard ───────────────────────────────────────────────

audit:
	@echo "[FleetSafe] Running navigation audit dashboard..."
	$(PYTHON) $(AUDIT_DASH) \
	    --input-dir $(RESULTS_DIR) \
	    --extra-json $(RESULTS_DIR)/may29_evaluation_full.json \
	    --output-dir $(AUDIT_OUT) \
	    --latex
	@echo "[FleetSafe] Dashboard → $(AUDIT_OUT)/"
	@echo "  CSV : $(AUDIT_OUT)/nav_audit_summary.csv"
	@echo "  LaTeX: $(AUDIT_OUT)/nav_audit_table.tex"

## ── ROS2 bag → GNM format converter ─────────────────────────────────────────

convert-bag:
	@echo "[FleetSafe] Converting ROS2 bags → GNM training format..."
	@[ -d "$(BAG_DIR)" ] || (echo "ERROR: BAG_DIR=$(BAG_DIR) not found. Set BAG_DIR=<path>." && exit 1)
	$(PYTHON) $(ROS2_CONV) \
	    --bag $(BAG_DIR)/*.db3 \
	    --output $(DATASET_OUT) \
	    --dataset-name $(DATASET_NAME) \
	    --resample-dt 0.1 \
	    --split-distance 15.0 \
	    --eval-fraction 0.1
	@echo "[FleetSafe] Dataset → $(DATASET_OUT)/"
	@echo "  Fine-tune: cd third_party/visualnav-transformer/train && python train.py \\"
	@echo "             --config vint_train/config/gnm.yaml \\"
	@echo "             --data-folder $(REPO_ROOT)/$(DATASET_OUT)"

## ── FleetSafe-VLN benchmark ─────────────────────────────────────────────────

benchmark-smoke-vln:
	@echo "[FleetSafe-VLN] Running benchmark smoke test (mock platform, no GPU)..."
	bash scripts/run_benchmark_smoke_test.sh

datagen-smoke:
	@echo "[FleetSafe-VLN] Running DataForge smoke test..."
	bash scripts/run_safe_datagen_smoke_test.sh

gnm-collect:
	@echo "[FleetSafe-VLN] Starting GNM data collection..."
	bash scripts/gnm/collect_gnm_data.sh $(if $(SCENE),--scene $(SCENE),) $(if $(ROBOT),--robot $(ROBOT),)

gnm-train:
	@echo "[FleetSafe-VLN] Fine-tuning GNM on FleetSafe data..."
	bash scripts/gnm/train_gnm.sh $(if $(DATA),--data $(DATA),) $(if $(EPOCHS),--epochs $(EPOCHS),)

gnm-eval:
	@echo "[FleetSafe-VLN] Running GNM evaluation matrix..."
	bash scripts/gnm/eval_gnm.sh $(if $(PLATFORM),--platform $(PLATFORM),)

gnm-setup:
	@echo "[FleetSafe-VLN] Setting up GNM dependencies..."
	bash scripts/visualnav/setup_visualnav.sh

## ── Figures ──────────────────────────────────────────────────────────────────

figures:
	@echo "[FleetSafe] Generating publication figures..."
	$(PYTHON) $(FIG_SCRIPT) --out $(FIG_OUT) --png $(FIG_PNG)
	@echo "[FleetSafe] Done — $(FIG_OUT) and $(FIG_PNG)"

## ── PROVEN gate ──────────────────────────────────────────────────────────────

verify:
	@echo "[FleetSafe] Running PROVEN gate verifier..."
	$(PYTHON) $(VERIFY) --verbose
	@echo ""

## ── Paper auto-update ────────────────────────────────────────────────────────

update:
	@echo "[FleetSafe] Auto-patching paper with latest Isaac results..."
	$(PYTHON) $(UPDATE)
	@echo "[FleetSafe] Paper update done."

## ── LaTeX paper ──────────────────────────────────────────────────────────────

paper:
	@which pdflatex > /dev/null 2>&1 || (echo "ERROR: pdflatex not found. Install texlive-full." && exit 1)
	@echo "[FleetSafe] Compiling LaTeX paper..."
	cd $(PAPER_DIR) && pdflatex fleetsafe_paper.tex && bibtex fleetsafe_paper && pdflatex fleetsafe_paper.tex && pdflatex fleetsafe_paper.tex
	@echo "[FleetSafe] Paper PDF: $(PAPER_DIR)fleetsafe_paper.pdf"

## ── Bundle ───────────────────────────────────────────────────────────────────

bundle:
	@echo "[FleetSafe] Exporting publication bundle..."
	$(PYTHON) $(BUNDLE)
	@echo "[FleetSafe] Bundle complete."

## ── Full pipeline ────────────────────────────────────────────────────────────

pub: benchmark-results audit verify update figures bundle
	@echo "[FleetSafe] Publication pipeline complete."
	@echo "  Results table : $(BENCH_FINAL)/benchmark_table_paper.tex"
	@echo "  Audit CSV     : $(AUDIT_OUT)/nav_audit_summary.csv"
	@echo "  Figures       : $(FIG_OUT)"
	@echo "  Next: git add figures/ paper/ results/benchmark_final/ results/audit_latest/ && git commit"
	@echo "  Then: git push origin main"

## ── Finalize ─────────────────────────────────────────────────────────────────

finalize: update figures verify
	@echo "[FleetSafe] Finalization complete. Run Isaac PROVEN when all combos done."
	@echo "  1. Check: python scripts/publication/verify_proven_gate.py --verbose"
	@echo "  2. Stage:  git add figures/ paper/ command-center/frontend/public/figures/"
	@echo "  3. Commit: git commit -m 'evidence: Isaac PROVEN — all 3 models GNM/ViNT/NoMaD complete'"
	@echo "  4. Push:   git push origin main"

## ── CI check ─────────────────────────────────────────────────────────────────

check: figures
	@echo "[FleetSafe] Running TypeScript type check..."
	cd command-center/frontend && npx tsc --noEmit
	@echo "[FleetSafe] All checks passed."

## ── Formal Safety Evaluation ─────────────────────────────────────────────────

# Sample certificate file used by formal-check and formal-report
FORMAL_SAMPLE := /tmp/fleetsafe_sample_certs.jsonl
FORMAL_REPORT := results/formal_eval_report.md

formal-check:
	@echo "[FleetSafe] Generating sample safety certificates..."
	python3 scripts/evaluation/generate_sample_certificates.py \
	    --output $(FORMAL_SAMPLE) --n 30
	@echo "[FleetSafe] Running certificate verifier..."
	python3 scripts/evaluation/verify_cbf_certificates.py \
	    --input $(FORMAL_SAMPLE) --d-safe 0.5 --h-tol 0.02 --latency-ms 100
	@echo "[FleetSafe] Running tests..."
	python3 -m pytest tests/test_cbf_math_contract.py tests/test_safety_certificate_schema.py -v
	@echo "[FleetSafe] formal-check PASSED"

formal-report:
	@echo "[FleetSafe] Generating formal evaluation report..."
	@[ -f "$(FORMAL_SAMPLE)" ] || $(MAKE) --no-print-directory formal-check
	python3 scripts/evaluation/generate_formal_eval_report.py \
	    --input $(FORMAL_SAMPLE) \
	    --output $(FORMAL_REPORT) \
	    --d-safe 0.5 --h-tol 0.02 --latency-ms 100
	@echo "[FleetSafe] Report → $(FORMAL_REPORT)"

no-blackbox-audit:
	@echo "[FleetSafe] Auditing run directories for explainability..."
	@if [ -d "results" ] && ls results/*/certificates.jsonl 2>/dev/null | head -1 | grep -q .; then \
	    for d in results/*/; do \
	        if [ -f "$$d/certificates.jsonl" ]; then \
	            python3 scripts/evaluation/audit_no_blackbox_logs.py --run-dir "$$d"; \
	        fi; \
	    done; \
	elif [ -d "results" ]; then \
	    echo "  No certificate files found in results/. Running guidance audit..."; \
	    python3 scripts/evaluation/audit_no_blackbox_logs.py --run-dir results/; \
	else \
	    echo "  No results/ directory. Run a FleetSafe experiment first, then:"; \
	    echo "    make no-blackbox-audit"; \
	fi

## ── Real Robot Certificate Pipeline ─────────────────────────────────────────

# Paths for real-robot posthoc certification
REAL_BAG_DIR  := data/real_robot_bags
REAL_CERT_DIR := results/certificates
REAL_CERT_OUT := $(REAL_CERT_DIR)/latest_real_robot.jsonl
REAL_REPORT   := results/formal_real_report.md

certify-latest-real-bag:
	@echo "[FleetSafe] Finding latest M3Pro bag..."
	@LATEST=$$(ls -td $(REAL_BAG_DIR)/m3pro_full_motion_* 2>/dev/null | head -1); \
	if [ -z "$$LATEST" ]; then \
	    echo "ERROR: No m3pro_full_motion_* bags found in $(REAL_BAG_DIR)/"; \
	    echo "       Run: make record-real  (or bash scripts/live/record_real_robot_bag.sh)"; \
	    exit 1; \
	fi; \
	echo "[FleetSafe] Certifying $$LATEST"; \
	mkdir -p $(REAL_CERT_DIR); \
	python3 scripts/evaluation/certify_rosbag_run.py \
	    --bag "$$LATEST" \
	    --output $(REAL_CERT_OUT) \
	    --d-safe 0.5 \
	    --verbose
	@echo "[FleetSafe] Certificates → $(REAL_CERT_OUT)"

verify-latest-real-cert:
	@echo "[FleetSafe] Verifying posthoc certificates..."
	@[ -f "$(REAL_CERT_OUT)" ] || (echo "ERROR: $(REAL_CERT_OUT) not found. Run: make certify-latest-real-bag" && exit 1)
	python3 scripts/evaluation/verify_cbf_certificates.py \
	    --input $(REAL_CERT_OUT) \
	    --d-safe 0.5 \
	    --h-tol 0.02 \
	    --latency-ms 9999 \
	    --allow-violations 0
	@echo "[FleetSafe] Verification complete."

formal-real-report: certify-latest-real-bag verify-latest-real-cert
	@echo "[FleetSafe] Generating formal real-robot report..."
	python3 scripts/evaluation/generate_formal_eval_report.py \
	    --input $(REAL_CERT_OUT) \
	    --output $(REAL_REPORT) \
	    --d-safe 0.5 --h-tol 0.02 --latency-ms 9999
	@echo "[FleetSafe] Report → $(REAL_REPORT)"

## ── Real Robot ───────────────────────────────────────────────────────────────

robot-check:
	@bash scripts/robot/check_robot_connection.sh

robot-install:
	@bash scripts/robot/install_robot_tools.sh

robot-install-jetson-deps:
	@echo "[FleetSafe] Installing runtime deps on Jetson (requires sudo on Jetson)..."
	@source config/fleetsafe_real_robot.env && \
	 ROBOT="" && \
	 for _h in "fleetsafe-jetson" "$${ROBOT_USER}@$${ROBOT_HOTSPOT_IP}" "$${ROBOT_USER}@$${ROBOT_TAILSCALE_IP}"; do \
	   if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o LogLevel=ERROR "$$_h" "exit 0" 2>/dev/null; then \
	     ROBOT="$$_h"; break; \
	   fi; \
	 done && \
	 [ -n "$$ROBOT" ] || (echo "[FAIL] Jetson unreachable" && exit 1) && \
	 echo "  Jetson: $$ROBOT" && \
	 ssh -o StrictHostKeyChecking=no -t "$$ROBOT" \
	   "for f in /etc/apt/sources.list.d/*cudnn*local*tegra* /etc/apt/sources.list.d/*cudnn*local*; do [ -f \"\$$f\" ] && sudo mv \"\$$f\" \"\$${f}.disabled\" && echo \"disabled broken apt source: \$$f\" || true; done; sudo apt-get update -qq && sudo apt-get install -y tmux ros-humble-micro-ros-agent && echo '[OK] tmux and micro-ros-agent installed'"

robot-bundle:
	@bash scripts/robot/make_robot_tools_bundle.sh

robot-status:
	@source config/fleetsafe_real_robot.env && \
	 for ip in "$$ROBOT_HOTSPOT_IP" "$$ROBOT_TAILSCALE_IP"; do \
	   if ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
	         "$$ROBOT_USER@$$ip" \
	         "bash ~/fleetsafe_robot_tools/status_robot_stack.sh" 2>/dev/null; then \
	     break; \
	   fi; \
	 done || (echo "Robot unreachable — run: make robot-check")

robot-start:
	@echo "[FleetSafe] Starting Jetson robot stack via SSH..."
	@source config/fleetsafe_real_robot.env && \
	 for ip in "$$ROBOT_HOTSPOT_IP" "$$ROBOT_TAILSCALE_IP"; do \
	   if ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=8 \
	         "$$ROBOT_USER@$$ip" \
	         "bash ~/fleetsafe_robot_tools/start_robot_stack.sh" 2>/dev/null; then \
	     echo "[FleetSafe] Robot stack started on $$ip."; \
	     break; \
	   fi; \
	 done || (echo "[FleetSafe] Robot unreachable — run: make robot-install first, then make robot-start")

robot-discover-yahboom:
	@echo "[FleetSafe] Discovering Yahboom stack state on Jetson..."
	bash scripts/robot/discover_yahboom_stack.sh

robot-diagnose-yahboom:
	@echo "[FleetSafe] Running deep Yahboom stack diagnostic on Jetson..."
	bash scripts/robot/diagnose_yahboom_live_stack.sh

robot-start-yahboom:
	@echo "[FleetSafe] Starting Yahboom M3Pro full stack on Jetson..."
	bash scripts/robot/start_yahboom_stack.sh

robot-status-yahboom:
	@echo "[FleetSafe] Checking Yahboom stack status on Jetson..."
	bash scripts/robot/status_yahboom_stack.sh

robot-live-preflight:
	@echo "[FleetSafe-VLN] Running live-motion sensor preflight (no controller required)..."
	SAFETY_RADIUS=$(VLN_PREFLIGHT_RADIUS) bash scripts/live/preflight_live_motion.sh

robot-stop-motion:
	@echo "[FleetSafe] Publishing zero /cmd_vel (safety stop) on domain $${ROS_DOMAIN_ID:-30}..."
	@source /opt/ros/humble/setup.bash 2>/dev/null || true; \
	 export ROS_DOMAIN_ID=$${ROS_DOMAIN_ID:-30}; \
	 export ROS_LOCALHOST_ONLY=0; \
	 for i in 1 2 3; do \
	   ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
	       '{"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}' \
	       2>/dev/null || true; \
	   sleep 0.2; \
	 done; \
	 echo "  [OK] Zero velocity published to /cmd_vel (3 times)."

VLN_PREFLIGHT_RADIUS ?= $(VLN_SAFETY_RADIUS)

# Sensor-only gate: verifies /YB_Node, scan0/scan1/odom_raw publishers + data,
# /cmd_vel subscriber, and LiDAR clearance.  Does NOT require the VLN controller
# to be running.  Called automatically by run_vln_desktop.sh --enable-motion.
vln-live-preflight:
	@echo "[FleetSafe-VLN] Running live-motion sensor preflight..."
	SAFETY_RADIUS=$(VLN_PREFLIGHT_RADIUS) bash scripts/live/preflight_live_motion.sh

# Full 9-check preflight (requires VLN controller running + dry-run instruction).
vln-full-preflight:
	@echo "[FleetSafe-VLN] Running full preflight (9 checks, controller required)..."
	SAFETY_RADIUS=$(VLN_PREFLIGHT_RADIUS) bash scripts/live/vln_live_preflight.sh

VLN_PROOF_TEXT  ?= move forward very slowly
VLN_PROOF_RADIUS ?= $(VLN_SAFETY_RADIUS)

vln-live-motion-proof:
	@[ "$${CONFIRM_ENABLE_MOTION:-}" = "YES" ] || \
	    (echo "[FleetSafe] ERROR: set CONFIRM_ENABLE_MOTION=YES to run live motion proof." && exit 1)
	@echo "[FleetSafe-VLN] Live motion proof (MOTION ENABLED)..."
	@source /opt/ros/humble/setup.bash 2>/dev/null || true; \
	 export ROS_DOMAIN_ID=$${ROS_DOMAIN_ID:-30}; \
	 export ROS_LOCALHOST_ONLY=0; \
	 echo "── Step 1: kill stale controller ───────────────────────────────────"; \
	 STALE=$$(pgrep -f "run_vln_m3pro.py" || true); \
	 if [ -n "$$STALE" ]; then \
	   echo "  Killing stale PID(s): $$STALE"; \
	   kill $$STALE 2>/dev/null || true; sleep 2; \
	 else echo "  No stale controller."; fi; \
	 echo ""; \
	 echo "── Step 2: start controller (LIVE MOTION) ──────────────────────────"; \
	 CONFIRM_ENABLE_MOTION=YES bash scripts/live/run_vln_desktop.sh \
	     --enable-motion --safety-radius $(VLN_PROOF_RADIUS) --backbone auto & \
	 CTRL_PID=$$!; echo "  Controller PID: $$CTRL_PID"; \
	 echo "  Waiting for controller to subscribe (up to 25 s)..."; \
	 READY=0; \
	 for i in $$(seq 1 25); do \
	   SUB_CT=$$(timeout 3 ros2 topic info /fleetsafe/instruction_text 2>/dev/null \
	              | grep -oP '(?<=Subscription count: )\d+' || echo 0); \
	   if [ "$${SUB_CT:-0}" -ge 1 ]; then \
	     echo "  Controller ready after $${i} s."; READY=1; break; \
	   fi; sleep 1; \
	 done; \
	 [ "$$READY" -eq 1 ] || { echo "  [FAIL] Controller did not start in 25 s."; kill $$CTRL_PID 2>/dev/null; exit 1; }; \
	 echo ""; \
	 echo "── Step 3: clear e-stop ────────────────────────────────────────────"; \
	 ros2 topic pub --once /fleetsafe/estop_clear std_msgs/msg/String \
	     "{data: 'clear'}" 2>/dev/null || true; sleep 1; \
	 echo ""; \
	 echo "── Step 4: send instruction ─────────────────────────────────────────"; \
	 echo "  '$(VLN_PROOF_TEXT)'"; \
	 ros2 topic pub --once /fleetsafe/instruction_text std_msgs/msg/String \
	     "{data: '$(VLN_PROOF_TEXT)'}" 2>&1 || true; \
	 sleep 3; \
	 echo ""; \
	 echo "── Step 5: safety stop ──────────────────────────────────────────────"; \
	 ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
	     '{"linear":{"x":0.0},"angular":{"z":0.0}}' 2>/dev/null || true; \
	 echo "  Zero velocity published."; \
	 echo ""; \
	 echo "── Step 6: stop controller ──────────────────────────────────────────"; \
	 kill $$CTRL_PID 2>/dev/null || true; sleep 1; \
	 echo ""; \
	 echo "── Step 7: read and assert latest certificate ───────────────────────"; \
	 LATEST_CERT=$$(ls -t results/certificates/*/vln_certificates_m3pro.jsonl 2>/dev/null | head -1); \
	 LATEST_TRACE=$$(ls -t results/vln_runs/*/vln_trace_m3pro.jsonl 2>/dev/null | head -1); \
	 [ -n "$$LATEST_CERT" ] && [ -s "$$LATEST_CERT" ] || \
	     { echo "  [FAIL] No certificate found."; exit 1; }; \
	 LAST_JSON=$$(tail -n 1 "$$LATEST_CERT"); \
	 echo "$$LAST_JSON" | /usr/bin/python3 -m json.tool 2>/dev/null || echo "$$LAST_JSON"; \
	 echo ""; \
	 /usr/bin/python3 -c " \
import sys, json, os; \
cert_path=sys.argv[1]; trace_path=sys.argv[2]; last_json=sys.argv[3]; \
errors=[]; \
if not os.path.isfile(cert_path) or os.path.getsize(cert_path)==0: errors.append('cert file empty: '+cert_path); \
if trace_path and (not os.path.isfile(trace_path) or os.path.getsize(trace_path)==0): errors.append('trace file empty: '+trace_path); \
d=json.loads(last_json); \
src=d.get('source',''); \
[errors.append('source='+repr(src)+' expected text/voice') for _ in [0] if src not in ('text','voice')]; \
safe=d.get('safe'); decision=d.get('decision',''); reason=d.get('reason',''); qp=d.get('qp_status',''); estop=d.get('estop_latched',False); \
[errors.append('safe field missing') for _ in [0] if safe is None]; \
if safe is False: \
  print('[INFO] safe=False: decision='+decision+' reason='+reason); \
  [print('[INFO] CBF e-stop: obstacle within safety_radius. Make vln-clear-estop then retry.') for _ in [0] if qp=='cbf_infeasible']; \
  [print('[INFO] E-stop latched. Run: make vln-clear-estop') for _ in [0] if estop]; \
  [errors.append('safe=False but decision empty') for _ in [0] if not decision]; \
required=['timestamp','source','safe','qp_status','h_min','min_dist_m','scan_audit','u_nominal','u_safe','camera_seen','camera_frame_id','camera_last_age_ms','estop_latched','decision']; \
[errors.append('missing cert field: '+k) for k in required if k not in d]; \
[ print('[FAIL] '+e) for e in errors ]; \
sys.exit(1) if errors else print('[PASS] source='+src+'  safe='+str(safe)+'  decision='+decision+'  qp='+qp) \
" "$$LATEST_CERT" "$${LATEST_TRACE:-}" "$$LAST_JSON" || exit 1; \
	 echo ""; \
	 echo "════════════════════════════════════════════════════════════════"; \
	 echo "  Live Motion Proof COMPLETE."; \
	 echo "  Cert : $$LATEST_CERT"; \
	 echo "  Trace: $$LATEST_TRACE"; \
	 echo "════════════════════════════════════════════════════════════════"

## ── VLN — Voice/Text/Image-grounded Visual-Language Navigation ───────────────

VLN_CERT_DIR := results/certificates
VLN_TRACE_DIR := results/vln_runs
VLN_TEXT ?= go to the nurse station and avoid people

vln-audit:
	@echo "[FleetSafe-VLN] Auditing current VLN stack..."
	python3 scripts/vln/audit_current_vln_stack.py
	@echo "[FleetSafe-VLN] Done → results/vln/current_stack_audit.md"

vln-check:
	@echo "[FleetSafe-VLN] Checking VLN prerequisites..."
	@python3 -c "from fleet_safe_vla.vln import VLNInstruction, InstructionGrounder, BackboneRouter; print('  ✅ VLN package importable')"
	@python3 -m py_compile scripts/vln/run_vln_instruction_demo.py && echo "  ✅ demo script compiles"
	@bash -n scripts/robot/check_voice_module.sh && echo "  ✅ check_voice_module.sh valid"
	@bash -n scripts/live/send_vln_text_instruction.sh || true
	@echo "[FleetSafe-VLN] vln-check PASSED"

vln-demo-dry:
	@echo "[FleetSafe-VLN] Dry-run demo: $(VLN_TEXT)"
	@mkdir -p $(VLN_CERT_DIR) $(VLN_TRACE_DIR)
	python3 scripts/vln/run_vln_instruction_demo.py \
	    --text "$(VLN_TEXT)" \
	    --backbone mock \
	    --dry-run \
	    --certificate-out $(VLN_CERT_DIR)/vln_dryrun.jsonl
	@echo "[FleetSafe-VLN] Trace → $(VLN_CERT_DIR)/vln_dryrun_trace.jsonl"

vln-demo-text:
	@echo "[FleetSafe-VLN] Text instruction demo (stdin mode)..."
	python3 scripts/vln/run_vln_instruction_demo.py \
	    --source stdin \
	    --backbone auto \
	    --dry-run \
	    --certificate-out $(VLN_CERT_DIR)/vln_text_demo.jsonl

vln-demo-voice-mock:
	@echo "[FleetSafe-VLN] Voice-mock demo (pre-canned transcript)..."
	python3 scripts/vln/run_vln_instruction_demo.py \
	    --text "go forward slowly through the corridor and avoid people" \
	    --source voice \
	    --backbone gnm \
	    --dry-run \
	    --certificate-out $(VLN_CERT_DIR)/vln_voice_mock.jsonl

vln-demo-live:
	@echo "[FleetSafe-VLN] LIVE MOTION demo — requires safety preflight PASS"
	@echo "WARNING: This will send /cmd_vel to the real robot if connected."
	@echo "Press Ctrl+C within 5s to abort."
	@sleep 5
	bash scripts/live/start_vln_stack.sh --enable-motion

vln-send:
	@[ -n "$(TEXT)" ] || (echo "Usage: make vln-send TEXT=\"your instruction\"" && exit 1)
	@source /opt/ros/humble/setup.bash 2>/dev/null || true; \
	 export ROS_DOMAIN_ID=30; export ROS_LOCALHOST_ONLY=0; \
	 bash scripts/live/send_vln_instruction.sh $(TEXT)

vln-record:
	@echo "[FleetSafe-VLN] Recording VLN bag (all topics + instruction topics)..."
	@source /opt/ros/humble/setup.bash 2>/dev/null || true
	@source config/fleetsafe_vln.env && \
	 STAMP=$$(date +%Y%m%d_%H%M%S) && \
	 OUT="data/real_robot_bags/vln_run_$${STAMP}" && \
	 mkdir -p "$$OUT" && \
	 ros2 bag record \
	   /camera/color/image_raw \
	   /camera/depth/image_raw \
	   /odom_raw /imu/data_raw /scan0 /scan1 /cmd_vel \
	   /fleetsafe/instruction_text \
	   /fleetsafe/instruction_voice \
	   /fleetsafe/vln/parsed_instruction \
	   /fleetsafe/vln/subgoal \
	   /fleetsafe/cmd_vel_nominal \
	   -o "$$OUT" || echo "ROS2 not available — ensure: source /opt/ros/humble/setup.bash"

vln-tests:
	@echo "[FleetSafe-VLN] Running VLN test suite..."
	python3 -m pytest tests/test_vln_instruction_schema.py \
	                  tests/test_vln_grounding.py \
	                  tests/test_vln_backbone_router.py \
	                  tests/test_vln_demo_trace.py -v
	@echo "[FleetSafe-VLN] VLN tests PASSED"

vln-formal-report: vln-demo-dry
	@echo "[FleetSafe-VLN] Generating formal VLN report..."
	python3 scripts/evaluation/generate_formal_eval_report.py \
	    --input $(VLN_CERT_DIR)/vln_dryrun.jsonl \
	    --output results/vln_formal_report.md \
	    --d-safe 0.5 --h-tol 0.02 --latency-ms 100
	@echo "[FleetSafe-VLN] Report → results/vln_formal_report.md"

vln-report: vln-formal-report vln-audit
	@echo "[FleetSafe-VLN] Full VLN report generated."

vln-robot:
	@echo "[FleetSafe-VLN] Starting VLN controller on M3Pro (DRY-RUN)..."
	@source /opt/ros/humble/setup.bash 2>/dev/null || true
	python3 scripts/real_robot/run_vln_m3pro.py \
	    --backbone auto \
	    --safety-radius 0.50 \
	    --trace-dir $(VLN_TRACE_DIR) \
	    --cert-dir $(VLN_CERT_DIR)

vln-robot-live:
	@echo "[FleetSafe-VLN] LIVE MOTION — M3Pro VLN controller with real /cmd_vel"
	@echo "WARNING: Robot will move. Ensure area is clear. Press Ctrl+C to abort."
	@sleep 3
	@source /opt/ros/humble/setup.bash 2>/dev/null || true
	python3 scripts/real_robot/run_vln_m3pro.py \
	    --enable-motion \
	    --backbone auto \
	    --safety-radius 0.50 \
	    --trace-dir $(VLN_TRACE_DIR) \
	    --cert-dir $(VLN_CERT_DIR)

## ── RTX Desktop VLN workflow ─────────────────────────────────────────────────
# VLN controller runs on the RTX desktop; Jetson exposes sensor topics via DDS.

VLN_SAFETY_RADIUS ?= 0.30
VLN_BACKBONE      ?= auto

vln-desktop:
	@echo "[FleetSafe-VLN] Starting VLN controller on RTX desktop (DRY-RUN)..."
	bash scripts/live/run_vln_desktop.sh \
	    --safety-radius $(VLN_SAFETY_RADIUS) \
	    --backbone $(VLN_BACKBONE)

vln-desktop-radius:
	@[ -n "$(RADIUS)" ] || (echo "Usage: make vln-desktop-radius RADIUS=0.20" && exit 1)
	@echo "[FleetSafe-VLN] Starting VLN controller (DRY-RUN, radius=$(RADIUS))..."
	bash scripts/live/run_vln_desktop.sh \
	    --safety-radius $(RADIUS) \
	    --backbone $(VLN_BACKBONE)

vln-desktop-live:
	@echo "[FleetSafe-VLN] Starting VLN controller with REAL MOTION..."
	CONFIRM_ENABLE_MOTION=YES bash scripts/live/run_vln_desktop.sh \
	    --enable-motion \
	    --safety-radius $(VLN_SAFETY_RADIUS) \
	    --backbone $(VLN_BACKBONE)

vln-watch-parsed:
	bash scripts/live/watch_vln_outputs.sh parsed

vln-watch-nominal:
	bash scripts/live/watch_vln_outputs.sh nominal

vln-watch-cert:
	bash scripts/live/watch_vln_outputs.sh certificate

vln-check-stack:
	SAFETY_RADIUS=$${SAFETY_RADIUS:-$(VLN_SAFETY_RADIUS)} bash scripts/live/check_vln_stack.sh

vln-lidar-inspect:
	@echo "[FleetSafe-VLN] Inspecting live LiDAR raw vs effective clearance..."
	@set +u; \
	 source <(bash scripts/live/detect_scan_topics.sh 2>/dev/null) || true; \
	 SCAN_TOPICS="$${FLEETSAFE_SCAN_TOPICS:-/scan0,/scan1}"; \
	 TOPICS_ARGS=$$(echo "$$SCAN_TOPICS" | tr ',' ' '); \
	 /usr/bin/python3 scripts/live/inspect_lidar_clearance.py \
	     --safety-radius $(VLN_SAFETY_RADIUS) --topics $$TOPICS_ARGS

vln-camera-check:
	@echo "[FleetSafe-VLN] Camera check (/camera/color/image_raw)..."
	@source /opt/ros/humble/setup.bash 2>/dev/null || true; \
	 export ROS_DOMAIN_ID=$${ROS_DOMAIN_ID:-30}; \
	 TOPICS=$$(timeout 5 ros2 topic list 2>/dev/null || true); \
	 if echo "$$TOPICS" | grep -qx "/camera/color/image_raw"; then \
	   echo "  [OK]   /camera/color/image_raw exists on domain $$ROS_DOMAIN_ID"; \
	   echo "         Measuring Hz (5 s window)..."; \
	   HZ=$$(timeout 8 ros2 topic hz --window 20 /camera/color/image_raw 2>/dev/null \
	          | grep "average rate" | tail -1 | awk '{print $$3}' || echo "?"); \
	   if [ -n "$$HZ" ] && [ "$$HZ" != "?" ]; then \
	     echo "  [OK]   Hz: $$HZ"; \
	   else \
	     echo "  [WARN] Could not measure Hz — camera not publishing?"; \
	   fi; \
	 else \
	   echo "  [FAIL] /camera/color/image_raw not found"; \
	   echo "         → Check USB cable, Orbbec driver, and that the Jetson stack is running"; \
	 fi; \
	 LATEST_CERT=$$(ls -t results/certificates/*/vln_certificates_m3pro.jsonl 2>/dev/null | head -1); \
	 if [ -n "$$LATEST_CERT" ] && [ -s "$$LATEST_CERT" ]; then \
	   echo ""; \
	   echo "  Latest certificate:  $$LATEST_CERT"; \
	   LAST=$$(tail -n 1 "$$LATEST_CERT"); \
	   CAM_SEEN=$$(echo "$$LAST" | /usr/bin/python3 -c \
	     "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('camera_seen','?'))"); \
	   CAM_AGE=$$(echo "$$LAST" | /usr/bin/python3 -c \
	     "import sys,json; d=json.loads(sys.stdin.read()); v=d.get('camera_last_age_ms'); print(f'{v:.0f} ms' if v is not None else 'N/A')"); \
	   echo "  camera_seen        : $$CAM_SEEN"; \
	   echo "  camera_last_age_ms : $$CAM_AGE"; \
	   echo "  NOTE: camera_seen in the certificate is the authoritative controller-level"; \
	   echo "        proof that frames reached the VLN pipeline. Topic Hz is advisory only."; \
	   if [ "$$CAM_SEEN" = "True" ]; then \
	     echo "  [OK]   Camera frames reaching the VLN controller (certificate confirmed)"; \
	   else \
	     echo "  [WARN] camera_seen=False in last cert — QoS mismatch or stale frame (>2 s)"; \
	     echo "         Topic Hz check may show data but controller-side subscription may differ."; \
	   fi; \
	 else \
	   echo "  No certificate found — send an instruction first (make vln-send TEXT='test')"; \
	 fi

vln-evidence-latest:
	@LATEST_TRACE=$$(ls -t results/vln_runs/*/vln_trace_m3pro.jsonl 2>/dev/null | head -1); \
	 LATEST_CERT=$$(ls -t results/certificates/*/vln_certificates_m3pro.jsonl 2>/dev/null | head -1); \
	 echo "── VLN Evidence: latest files ──────────────────────────────────────"; \
	 if [ -n "$$LATEST_TRACE" ]; then \
	   echo "  Trace : $$LATEST_TRACE"; \
	   echo "  Size  : $$(wc -c < $$LATEST_TRACE) bytes   Lines: $$(wc -l < $$LATEST_TRACE)"; \
	   echo "  Last 3 rows (qp_status / decision):"; \
	   tail -n 3 "$$LATEST_TRACE" | /usr/bin/python3 -c \
	     "import sys,json; [print('    qp='+d.get('qp_status','?')+' stop='+str(d.get('stop_reason','?'))) for l in sys.stdin for d in [json.loads(l)]]" 2>/dev/null \
	     || tail -n 3 "$$LATEST_TRACE"; \
	 else \
	   echo "  Trace : (none found in results/vln_runs/)"; \
	 fi; \
	 if [ -n "$$LATEST_CERT" ]; then \
	   echo "  Cert  : $$LATEST_CERT"; \
	   echo "  Size  : $$(wc -c < $$LATEST_CERT) bytes   Lines: $$(wc -l < $$LATEST_CERT)"; \
	   echo "  Last 3 rows (decision / safe):"; \
	   tail -n 3 "$$LATEST_CERT" | /usr/bin/python3 -c \
	     "import sys,json; [print('    decision='+d.get('decision','?')+' safe='+str(d.get('safe','?'))) for l in sys.stdin for d in [json.loads(l)]]" 2>/dev/null \
	     || tail -n 3 "$$LATEST_CERT"; \
	 else \
	   echo "  Cert  : (none found in results/certificates/)"; \
	 fi

vln-clear-estop:
	@echo "[FleetSafe-VLN] Publishing /fleetsafe/estop_clear..."
	@source /opt/ros/humble/setup.bash 2>/dev/null || true; \
	 export ROS_DOMAIN_ID=$${ROS_DOMAIN_ID:-30}; \
	 export ROS_LOCALHOST_ONLY=0; \
	 ros2 topic pub --once /fleetsafe/estop_clear std_msgs/msg/String \
	     "{data: 'clear'}" 2>&1 && \
	 echo "  [OK]  E-stop clear signal sent to /fleetsafe/estop_clear." && \
	 echo "        Controller will log the clear attempt; if clearance < safety_radius the latch stays." || \
	 echo "  [FAIL] Could not publish — is ROS2 sourced and the DDS domain running?"

VLN_DEMO_VOICE_TEXT ?= move forward slowly

vln-demo-voice-proof:
	@echo "═══════════════════════════════════════════════════════════════════"
	@echo "  FleetSafe-VLN  |  Voice Proof Demo  (SAFETY_RADIUS=0.20)"
	@echo "═══════════════════════════════════════════════════════════════════"
	@source /opt/ros/humble/setup.bash 2>/dev/null || true; \
	 export ROS_DOMAIN_ID=$${ROS_DOMAIN_ID:-30}; \
	 export ROS_LOCALHOST_ONLY=0; \
	 echo ""; \
	 echo "── Step 1: stack health check ──────────────────────────────────────"; \
	 SAFETY_RADIUS=0.20 bash scripts/live/check_vln_stack.sh || true; \
	 echo ""; \
	 echo "── Step 2: clear e-stop ────────────────────────────────────────────"; \
	 ros2 topic pub --once /fleetsafe/estop_clear std_msgs/msg/String \
	     "{data: 'clear'}" 2>&1 || true; \
	 sleep 1; \
	 echo ""; \
	 echo "── Step 3: send voice instruction ──────────────────────────────────"; \
	 echo "  TEXT: $(VLN_DEMO_VOICE_TEXT)"; \
	 ros2 topic pub --once /fleetsafe/instruction_voice std_msgs/msg/String \
	     "{data: '$(VLN_DEMO_VOICE_TEXT)'}" 2>&1 || true; \
	 sleep 2; \
	 echo ""; \
	 echo "── Step 4: read latest certificate ─────────────────────────────────"; \
	 LATEST_CERT=$$(ls -t results/certificates/*/vln_certificates_m3pro.jsonl 2>/dev/null | head -1); \
	 if [ -z "$$LATEST_CERT" ] || [ ! -s "$$LATEST_CERT" ]; then \
	   echo "  [FAIL] No certificate found — is the VLN controller running? (make vln-desktop)"; \
	   exit 1; \
	 fi; \
	 LAST_JSON=$$(tail -n 1 "$$LATEST_CERT"); \
	 echo "$$LAST_JSON" | /usr/bin/python3 -m json.tool 2>/dev/null || echo "$$LAST_JSON"; \
	 echo ""; \
	 echo "── Step 5: assertions ──────────────────────────────────────────────"; \
	 /usr/bin/python3 -c " \
import sys, json; \
raw = sys.argv[1]; \
d = json.loads(raw); \
errors = []; \
if d.get('source') != 'voice': \
    errors.append('source=' + repr(d.get('source')) + ' (expected voice)'); \
if not d.get('camera_seen'): \
    errors.append('camera_seen=' + str(d.get('camera_seen')) + ' (expected True) — check camera QoS'); \
qp = d.get('qp_status', ''); safe = d.get('safe', False); \
ok_qp = qp in ('skipped', 'optimal', 'cbf_clipped') and safe; \
ok_dry = d.get('dry_run') and d.get('decision') == 'dry_run_zero'; \
if not ok_qp and not ok_dry: \
    errors.append('qp_status=' + repr(qp) + ' safe=' + str(safe) + ' dry_run=' + str(d.get('dry_run')) + ' (expected safe or dry-run path)'); \
if d.get('estop_latched'): \
    errors.append('estop_latched=True — run: make vln-clear-estop and retry'); \
if errors: \
    print('[FAIL] Assertion failures:'); \
    [print('  - ' + e) for e in errors]; \
    sys.exit(1); \
else: \
    print('[PASS] source=voice  camera_seen=True  safe=' + str(safe) + '  qp_status=' + qp); \
" "$$LAST_JSON" || exit 1; \
	 echo ""; \
	 echo "═══════════════════════════════════════════════════════════════════"; \
	 echo "  Voice proof PASSED."; \
	 echo "═══════════════════════════════════════════════════════════════════"

robot-sync-repo:
	bash scripts/robot/sync_repo_to_jetson.sh

robot-voice-discover:
	@echo "[FleetSafe-VLN] Running voice discovery on robot..."
	@source config/fleetsafe_real_robot.env && \
	 for ip in "$$ROBOT_HOTSPOT_IP" "$$ROBOT_TAILSCALE_IP"; do \
	   if ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
	         "$$ROBOT_USER@$$ip" \
	         "bash -s" < scripts/robot/discover_voice_resources.sh 2>/dev/null; then \
	     break; \
	   fi; \
	 done || (echo "Robot unreachable — run: make robot-check")

voice-start-robot:
	@echo "[FleetSafe-VLN] Starting voice listener on robot..."
	@source config/fleetsafe_real_robot.env && \
	 for ip in "$$ROBOT_HOTSPOT_IP" "$$ROBOT_TAILSCALE_IP"; do \
	   if ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
	         "$$ROBOT_USER@$$ip" \
	         "bash ~/fleetsafe_robot_tools/start_voice_listener.sh" 2>/dev/null; then \
	     break; \
	   fi; \
	 done || (echo "Robot unreachable — run: make robot-check")

## ── Clean ────────────────────────────────────────────────────────────────────

clean:
	@echo "[FleetSafe] Cleaning generated files..."
	rm -f $(FIG_OUT)*.pdf $(FIG_PNG)*.png
	rm -f $(PAPER_DIR)*.aux $(PAPER_DIR)*.bbl $(PAPER_DIR)*.blg $(PAPER_DIR)*.log $(PAPER_DIR)*.out
	@echo "[FleetSafe] Clean complete."

clean-results:
	@echo "[FleetSafe] Cleaning benchmark result directories..."
	rm -rf $(BENCH_OUT) $(GAZEBO_OUT) $(AUDIT_OUT) $(UNIFIED_OUT)
	@echo "[FleetSafe] Benchmark results cleaned (benchmark_final/ kept)."

clean-isaac:
	@echo "[FleetSafe] Cleaning Isaac Sim generated assets..."
	rm -rf $(ISAAC_ASSETS_OUT) $(ISAAC_DATASET)
	@echo "[FleetSafe] Isaac assets cleaned."

## ── Unified cross-simulator benchmark ───────────────────────────────────────

benchmark-unified:
	@echo "[FleetSafe] Running unified Isaac + Gazebo benchmark..."
	$(PYTHON) $(UNIFIED_BENCH) \
	    --simulators isaac gazebo \
	    --models gnm vint \
	    --worlds hospital \
	    --episodes 20 \
	    --seeds 10 \
	    --output $(UNIFIED_OUT)
	@echo "[FleetSafe] Results → $(UNIFIED_OUT)/"
	@echo "  LaTeX : $(UNIFIED_OUT)/cross_sim_table.tex"
	@echo "  Report: $(UNIFIED_OUT)/unified_report.md"

benchmark-unified-paper:
	@echo "[FleetSafe] Running paper-grade unified benchmark (50 episodes)..."
	$(PYTHON) $(UNIFIED_BENCH) \
	    --simulators isaac gazebo \
	    --models gnm vint nomad \
	    --worlds hospital warehouse \
	    --episodes 50 \
	    --seeds 20 \
	    --output $(UNIFIED_OUT)_paper
	@echo "[FleetSafe] Results → $(UNIFIED_OUT)_paper/"

## ── Isaac Sim: NVIDIA photorealistic asset loader ────────────────────────────

isaac-load-assets:
	@echo "[FleetSafe] Loading NVIDIA photorealistic assets ($(ISAAC_ENV))..."
	@echo "  Requires: conda activate $(ISAAC_CONDA)"
	@echo "  ISAAC_HEADLESS=$(ISAAC_HEADLESS)  (override: make isaac-load-assets ISAAC_HEADLESS=0)"
	@conda run -n $(ISAAC_CONDA) $(PYTHON) $(LOAD_NVIDIA) \
	    --env $(ISAAC_ENV) \
	    --out-dir $(ISAAC_ASSETS_OUT) \
	    $(if $(filter 1,$(ISAAC_HEADLESS)),--headless,)
	@echo "[FleetSafe] USD → $(ISAAC_USD)"

isaac-load-warehouse:
	@echo "[FleetSafe] Loading warehouse asset with clutter..."
	@conda run -n $(ISAAC_CONDA) $(PYTHON) $(LOAD_NVIDIA) \
	    --env warehouse \
	    --clutter medium \
	    --out-dir $(ISAAC_ASSETS_OUT) \
	    $(if $(filter 1,$(ISAAC_HEADLESS)),--headless,)
	@echo "[FleetSafe] USD → $(ISAAC_ASSETS_OUT)/warehouse_photorealistic.usd"

isaac-load-validate:
	@echo "[FleetSafe] Loading and validating hospital + warehouse..."
	@conda run -n $(ISAAC_CONDA) $(PYTHON) $(LOAD_NVIDIA) \
	    --env hospital warehouse \
	    --clutter medium \
	    --validate \
	    --rtx \
	    --out-dir $(ISAAC_ASSETS_OUT) \
	    $(if $(filter 1,$(ISAAC_HEADLESS)),--headless,)
	@echo "[FleetSafe] Validation report → $(ISAAC_ASSETS_OUT)/validation_report.json"

## ── Isaac Sim: Export synthetic ViNT dataset ─────────────────────────────────

isaac-export-vint:
	@echo "[FleetSafe] Exporting synthetic ViNT dataset from Isaac Sim..."
	@[ -f "$(ISAAC_USD)" ] || (echo "ERROR: $(ISAAC_USD) not found. Run: make isaac-load-assets" && exit 1)
	@conda run -n $(ISAAC_CONDA) $(PYTHON) $(EXPORT_VINT) \
	    --usd $(ISAAC_USD) \
	    --episodes 100 \
	    --steps 200 \
	    --out $(ISAAC_DATASET)
	@echo "[FleetSafe] Dataset → $(ISAAC_DATASET)/"
	@echo "  Fine-tune: cd third_party/visualnav-transformer/train && python train.py \\"
	@echo "             --config vint_train/config/gnm.yaml \\"
	@echo "             --data-folder $(REPO_ROOT)/$(ISAAC_DATASET)"

isaac-export-vint-paper:
	@echo "[FleetSafe] Exporting paper-grade ViNT dataset (500 episodes)..."
	@conda run -n $(ISAAC_CONDA) $(PYTHON) $(EXPORT_VINT) \
	    --usd $(ISAAC_USD) \
	    --episodes 500 \
	    --steps 200 \
	    --out $(ISAAC_DATASET)_paper
	@echo "[FleetSafe] Dataset → $(ISAAC_DATASET)_paper/"

## ── Gazebo: AWS Robomaker photorealistic worlds ──────────────────────────────

gazebo-setup-aws:
	@echo "[FleetSafe] Installing AWS Robomaker hospital + warehouse worlds..."
	bash $(SETUP_AWS) --worlds hospital warehouse
	@echo "[FleetSafe] Done. Source ~/m3pro_sim_ws/setup_aws_worlds.bash before launching."

gazebo-setup-hospital:
	@echo "[FleetSafe] Installing AWS Robomaker hospital world only..."
	bash $(SETUP_AWS) --worlds hospital

## ── Gazebo: Launch M3Pro ─────────────────────────────────────────────────────

m3pro-gazebo:
	@echo "[FleetSafe] Launching M3Pro in Gazebo Harmonic (hospital corridor)..."
	@echo "  Prereq: sudo apt install ros-humble-ros-gz ros-humble-xacro"
	@echo "  Prereq: source ros2_ws/install/setup.bash"
	source /opt/ros/humble/setup.bash && \
	source ros2_ws/install/setup.bash && \
	ros2 launch fleet_safe_bringup m3pro_gazebo.launch.py world:=hospital_corridor

m3pro-gazebo-build:
	@echo "[FleetSafe] Installing Gazebo packages and building ros2_ws..."
	sudo apt-get install -y ros-humble-ros-gz ros-humble-xacro
	source /opt/ros/humble/setup.bash && \
	cd ros2_ws && colcon build --symlink-install
	@echo "[FleetSafe] Done. Now run: make m3pro-gazebo"

## ── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "GNM-VLNVerse Baseline — Makefile targets"
	@echo ""
	@echo "  Benchmark:"
	@echo "    make benchmark         Quick benchmark (mock, ~5 min)"
	@echo "    make benchmark-paper   Full benchmark, 50 seeds (~50 min)"
	@echo "    make benchmark-results Generate results table from real checkpoints"
	@echo "    make benchmark-gazebo  M3Pro across hospital/warehouse/cafe (mock)"
	@echo "    make benchmark-ros2    M3Pro with real Gazebo (requires ROS2)"
	@echo "    make matrix            Quick 4-condition evaluation matrix"
	@echo ""
	@echo "  Data:"
	@echo "    make convert-bag       Convert ROS2 bags → GNM training format"
	@echo "                           (set BAG_DIR=<path> and DATASET_NAME=<name>)"
	@echo ""
	@echo "  Reporting:"
	@echo "    make audit             Navigation audit dashboard → CSV + LaTeX"
	@echo "    make results-table     Authoritative results table (real checkpoints)"
	@echo ""
	@echo "  Publication:"
	@echo "    make figures           Regenerate paper figures"
	@echo "    make verify            Run PROVEN gate verifier"
	@echo "    make paper             Compile LaTeX paper (requires pdflatex)"
	@echo "    make pub               Full pipeline: benchmark-results → audit → verify → figures → bundle"
	@echo "    make bundle            Export publication bundle"
	@echo ""
	@echo "  Cross-Simulator (Isaac + Gazebo):"
	@echo "    make benchmark-unified         Isaac vs Gazebo comparison (20 eps)"
	@echo "    make benchmark-unified-paper   Paper-grade (50 eps, all models)"
	@echo ""
	@echo "  Isaac Sim — NVIDIA Photorealistic Assets:"
	@echo "    make isaac-load-assets         Load hospital USD from Nucleus"
	@echo "    make isaac-load-warehouse      Load warehouse USD with clutter"
	@echo "    make isaac-load-validate       Load + validate + RTX checklist"
	@echo "    make isaac-export-vint         Export 100 synthetic ViNT trajectories"
	@echo "    make isaac-export-vint-paper   Export 500 synthetic ViNT trajectories"
	@echo ""
	@echo "  Gazebo — Photorealistic Worlds:"
	@echo "    make gazebo-setup-aws          Install AWS Robomaker hospital + warehouse"
	@echo "    make gazebo-setup-hospital     Install hospital world only"
	@echo "    make m3pro-gazebo              Launch M3Pro in hospital corridor (GUI)"
	@echo "    make m3pro-gazebo-build        apt install gz + colcon build ros2_ws"
	@echo ""
	@echo "  Formal Safety Evaluation:"
	@echo "    make formal-check      Tests + certificate verifier (no simulator needed)"
	@echo "    make formal-report     Generate markdown formal evaluation report"
	@echo "    make no-blackbox-audit Audit run dirs for explainability coverage"
	@echo ""
	@echo "  Real Robot (Yahboom M3Pro + Jetson Orin NX):"
	@echo "    make robot-check              Check hotspot + Tailscale SSH reachability"
	@echo "    make robot-install                Install helper scripts to robot over SSH"
	@echo "    make robot-install-jetson-deps    Install tmux + micro-ros-agent on Jetson (sudo)"
	@echo "    make robot-bundle             Build offline tarball (robot can be off)"
	@echo "    make robot-start              SSH to Jetson and start full robot stack"
	@echo "    make robot-status             SSH into robot and show stack status"
	@echo "    make robot-stop-motion        Publish zero /cmd_vel from desktop (safety stop)"
	@echo "    make robot-discover-yahboom   Discover Yahboom stack state: ROS env, processes, topics"
	@echo "    make robot-diagnose-yahboom   Deep diagnostic: serial, launch scoring, topic Hz, logs"
	@echo "    make robot-start-yahboom      Start M3Pro full stack on Jetson (tmux, auto serial)"
	@echo "    make robot-status-yahboom     Check Hz, publisher counts, VLN controller on desktop"
	@echo "    make robot-live-preflight     Sensor preflight gate (alias for vln-live-preflight)"
	@echo ""
	@echo "  VLN — RTX Desktop workflow (controller here, Jetson exposes topics):"
	@echo "    make vln-desktop                   Start VLN controller DRY-RUN (radius=0.30)"
	@echo "    make vln-desktop-radius RADIUS=0.20  DRY-RUN with custom safety radius"
	@echo "    make vln-desktop-live              LIVE MOTION (CONFIRM_ENABLE_MOTION=YES)"
	@echo "    make vln-send TEXT=\"...\"           Publish text instruction via ROS2"
	@echo "    make vln-watch-parsed              Echo /fleetsafe/vln/parsed_instruction"
	@echo "    make vln-watch-nominal             Echo /fleetsafe/cmd_vel_nominal"
	@echo "    make vln-watch-cert                Echo /fleetsafe/certificate"
	@echo "    make vln-check-stack               Verify Jetson topics + VLN subscriptions"
	@echo "    make vln-lidar-inspect             Inspect live LiDAR raw vs effective clearance"
	@echo "    make vln-evidence-latest           Print latest trace/cert paths, sizes, and tail"
	@echo "    make vln-camera-check              Check camera topic Hz and camera_seen in cert"
	@echo "    make vln-clear-estop               Publish /fleetsafe/estop_clear to reset latch"
	@echo "    make vln-demo-voice-proof          Full voice proof: stack check, clear, voice cmd, assert cert"
	@echo "    make vln-live-preflight            Sensor gate: /YB_Node, scan/odom publishers, LiDAR clearance"
	@echo "    make vln-full-preflight            Full 9-check preflight (requires controller running)"
	@echo "    make vln-live-motion-proof         End-to-end live motion test (CONFIRM_ENABLE_MOTION=YES)"
	@echo "    make robot-sync-repo               rsync repo to Jetson (runtime copy)"
	@echo ""
	@echo "  VLN — offline / simulation:"
	@echo "    make vln-robot         Start VLN controller on M3Pro (DRY-RUN)"
	@echo "    make vln-robot-live    Start VLN controller with real /cmd_vel"
	@echo "    make vln-demo-dry      One-shot dry-run demo (TEXT=... optional)"
	@echo "    make vln-demo-text     Interactive stdin VLN demo"
	@echo "    make vln-demo-voice-mock  Pre-canned voice transcript demo"
	@echo "    make vln-record        Record VLN bag (all topics + instruction topics)"
	@echo "    make vln-tests         Run all 72 VLN unit tests"
	@echo "    make vln-check         Fast VLN import + schema smoke test"
	@echo "    make vln-audit         Audit VLN stack (imports, files, ROS2 env)"
	@echo "    make vln-report        Full VLN evaluation report (demo + audit)"
	@echo "    make robot-voice-discover  Discover voice resources on robot (SSH)"
	@echo "    make voice-start-robot     Start voice listener on robot (SSH)"
	@echo ""
	@echo "  Maintenance:"
	@echo "    make clean             Clean figures and LaTeX build artifacts"
	@echo "    make clean-results     Clean benchmark result directories"
	@echo "    make clean-isaac       Clean IsaacLabAssets/ and isaac ViNT dataset"
	@echo "    make help              This message"
	@echo ""
