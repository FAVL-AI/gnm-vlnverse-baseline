#!/usr/bin/env bash
# setup_aws_worlds.sh — Install AWS Robomaker photorealistic Gazebo worlds.
#
# Clones and builds the AWS Robomaker Hospital and Small Warehouse worlds
# into a ROS2 workspace so they can be used with `ros2 launch` and with
# the FleetSafe benchmark runner (make benchmark-gazebo).
#
# Worlds:
#   Hospital  : github.com/aws-robotics/aws-robomaker-hospital-world
#   Warehouse : github.com/aws-robotics/aws-robomaker-small-warehouse-world
#
# Usage:
#   bash scripts/ros2_gazebo/setup_aws_worlds.sh
#   bash scripts/ros2_gazebo/setup_aws_worlds.sh --ws ~/m3pro_sim_ws --worlds hospital
#   bash scripts/ros2_gazebo/setup_aws_worlds.sh --ws ~/aws_worlds_ws --worlds hospital warehouse

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROS_DISTRO="${ROS_DISTRO:-humble}"

# ── Defaults ──────────────────────────────────────────────────────────────────

WS_DIR="$HOME/m3pro_sim_ws"
WORLDS_TO_INSTALL=("hospital" "warehouse")

# ── Arg parse ─────────────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ws)        WS_DIR="$2";   shift 2 ;;
        --worlds)    shift; WORLDS_TO_INSTALL=(); while [[ $# -gt 0 && "$1" != --* ]]; do WORLDS_TO_INSTALL+=("$1"); shift; done ;;
        -h|--help)
            echo "Usage: $0 [--ws DIR] [--worlds hospital warehouse]"
            exit 0 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# ── Print banner ──────────────────────────────────────────────────────────────

echo ""
echo "=================================================================="
echo "  FleetSafe — AWS Robomaker Gazebo World Setup"
echo "=================================================================="
echo "  Workspace  : $WS_DIR"
echo "  Worlds     : ${WORLDS_TO_INSTALL[*]}"
echo "  ROS2 distro: $ROS_DISTRO"
echo ""

# ── Check prerequisites ───────────────────────────────────────────────────────

if ! command -v ros2 &>/dev/null; then
    echo "ERROR: ROS2 not found. Source /opt/ros/$ROS_DISTRO/setup.bash first."
    exit 1
fi

if ! command -v gz &>/dev/null; then
    echo "[WARN] Gazebo Harmonic not installed. Installing ros-gz packages …"
    sudo apt-get install -y \
        ros-${ROS_DISTRO}-ros-gz \
        ros-${ROS_DISTRO}-ros-gz-bridge \
        ros-${ROS_DISTRO}-ros-gz-sim \
        ros-${ROS_DISTRO}-xacro \
        2>/dev/null || echo "[WARN] Some packages may not have installed — continuing."
fi

# ── Create workspace ──────────────────────────────────────────────────────────

mkdir -p "$WS_DIR/src"
cd "$WS_DIR"

# ── Clone AWS Robomaker worlds ────────────────────────────────────────────────

declare -A REPOS=(
    ["hospital"]="https://github.com/aws-robotics/aws-robomaker-hospital-world.git"
    ["warehouse"]="https://github.com/aws-robotics/aws-robomaker-small-warehouse-world.git"
)

declare -A WORLD_LAUNCH=(
    ["hospital"]="aws_robomaker_hospital_world view_hospital.launch.py"
    ["warehouse"]="aws_robomaker_small_warehouse_world view_small_warehouse.launch.py"
)

declare -A WORLD_SDF=(
    ["hospital"]="worlds/hospital.world"
    ["warehouse"]="worlds/small_warehouse.world"
)

for world in "${WORLDS_TO_INSTALL[@]}"; do
    repo="${REPOS[$world]:-}"
    if [[ -z "$repo" ]]; then
        echo "[WARN] Unknown world: $world (skip)"
        continue
    fi

    dest_dir="$WS_DIR/src/$(basename "$repo" .git)"

    if [[ -d "$dest_dir" ]]; then
        echo "  [SKIP] $world already at $dest_dir"
        echo "         Run 'git -C $dest_dir pull' to update."
    else
        echo "  Cloning $world → $dest_dir"
        git clone --depth 1 "$repo" "$dest_dir"
        echo "  ✓ $world cloned"
    fi
done

# ── Install dependencies via rosdep ──────────────────────────────────────────

echo ""
echo "  Installing ROS2 dependencies …"
set +u
source "/opt/ros/${ROS_DISTRO}/setup.bash"
set -u
rosdep update --rosdistro "$ROS_DISTRO" 2>/dev/null || true
rosdep install --from-paths src --ignore-src -r -y \
    --rosdistro "$ROS_DISTRO" 2>/dev/null \
    || echo "  [WARN] rosdep install had errors — some deps may be missing"

# ── Build ─────────────────────────────────────────────────────────────────────

echo ""
echo "  Marking AWS RoboMaker worlds as Gazebo assets (not ROS2 packages) …"
# These repos are ROS1/catkin only — colcon cannot build them.
# COLCON_IGNORE tells colcon to skip the directory while keeping the SDF/world
# files accessible for Gazebo via GAZEBO_MODEL_PATH.
for _aws_pkg in \
    "$WS_DIR/src/aws-robomaker-hospital-world" \
    "$WS_DIR/src/aws-robomaker-small-warehouse-world"; do
    if [[ -d "$_aws_pkg" ]]; then
        touch "$_aws_pkg/COLCON_IGNORE"
        echo "  [ASSET] $(basename "$_aws_pkg") → world files only (COLCON_IGNORE placed)"
    fi
done

echo ""
echo "  Building workspace …"
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release \
    2>&1 | tail -30

if [[ ! -f "$WS_DIR/install/setup.bash" ]]; then
    echo "ERROR: colcon build failed — install/setup.bash not found."
    exit 1
fi
echo "  ✓ Build complete"

# ── Set GAZEBO_MODEL_PATH ─────────────────────────────────────────────────────

echo ""
echo "  Setting up model paths …"
MODEL_PATH_LINES=()
for world in "${WORLDS_TO_INSTALL[@]}"; do
    dest_dir="$WS_DIR/src/$(basename "${REPOS[$world]:-}" .git)"
    if [[ -d "$dest_dir/models" ]]; then
        MODEL_PATH_LINES+=("export GAZEBO_MODEL_PATH=\$GAZEBO_MODEL_PATH:$dest_dir/models")
    fi
done

SETUP_FILE="$WS_DIR/setup_aws_worlds.bash"
cat > "$SETUP_FILE" << SETUP_EOF
# Auto-generated by setup_aws_worlds.sh
source /opt/ros/${ROS_DISTRO}/setup.bash
source ${WS_DIR}/install/setup.bash
$(printf '%s\n' "${MODEL_PATH_LINES[@]}")
SETUP_EOF
echo "  Setup file: $SETUP_FILE"
echo "  Source it:  source $SETUP_FILE"

# ── Validate M3Pro Gazebo launch is available ─────────────────────────────────

FLEET_SAFE_WS="$REPO_ROOT/ros2_ws"
if [[ -f "$FLEET_SAFE_WS/src/fleet_safe_bringup/launch/m3pro_gazebo.launch.py" ]]; then
    echo ""
    echo "  ✓ fleet_safe_bringup/launch/m3pro_gazebo.launch.py found"
fi

# ── Print launch instructions ─────────────────────────────────────────────────

echo ""
echo "=================================================================="
echo "  Setup complete! Launch commands:"
echo ""
echo "  Source workspace:"
echo "    source $SETUP_FILE"
echo ""

for world in "${WORLDS_TO_INSTALL[@]}"; do
    pkg_launch="${WORLD_LAUNCH[$world]:-}"
    if [[ -n "$pkg_launch" ]]; then
        pkg=$(echo "$pkg_launch" | awk '{print $1}')
        lf=$(echo "$pkg_launch"  | awk '{print $2}')
        echo "  Launch $world world:"
        echo "    ros2 launch $pkg $lf"
        echo ""
    fi
done

echo "  Launch M3Pro in hospital world:"
echo "    source $REPO_ROOT/ros2_ws/install/setup.bash"
echo "    ros2 launch fleet_safe_bringup m3pro_gazebo.launch.py world:=hospital_corridor"
echo ""
echo "  Run FleetSafe Gazebo benchmark:"
echo "    cd $REPO_ROOT"
echo "    make benchmark-gazebo"
echo ""
echo "  Record training bag:"
echo "    ros2 bag record /camera/image_raw /odom /cmd_vel -o recordings/hospital_aws_01"
echo ""
echo "  Convert bag → ViNT format:"
echo "    python scripts/visualnav/ros2_to_vnt_converter.py \\"
echo "        --bag recordings/hospital_aws_01 \\"
echo "        --output data/gazebo_hospital_vint \\"
echo "        --dataset-name gazebo_hospital"
echo ""
echo "=================================================================="
