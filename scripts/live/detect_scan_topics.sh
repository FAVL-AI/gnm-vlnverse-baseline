#!/usr/bin/env bash
# detect_scan_topics.sh — Detect which LiDAR and odometry topics the Yahboom stack publishes
# and verifies that each candidate topic is actually delivering messages (not just in the graph).
#
# Queries ros2 topic list on the configured ROS_DOMAIN_ID and outputs shell
# variable assignments that can be sourced by the calling script:
#
#   FLEETSAFE_SCAN_TOPICS=/scan0,/scan1    preferred — M3Pro dual-LiDAR layout
#   FLEETSAFE_SCAN_TOPICS=/scan,/scan_multi  alternate firmware layout
#   FLEETSAFE_SCAN_TOPICS=/scan0           single-scanner fallback
#   FLEETSAFE_ODOM_TOPIC=/odom_raw         preferred
#   FLEETSAFE_ODOM_TOPIC=/odom             fallback
#
# Data quality: a topic passes only when it appears in ros2 topic list AND
# at least one message can be read within a 3 s window.  Graph-only topics
# (publisher count ≥ 1 but no messages) are treated as not publishing.
#
# Usage (source into caller):
#   source <(bash scripts/live/detect_scan_topics.sh)
#   # FLEETSAFE_SCAN_TOPICS and FLEETSAFE_ODOM_TOPIC are now exported
#
# Usage (check only — silent on success):
#   bash scripts/live/detect_scan_topics.sh > /dev/null && echo "scan topics found"
#
# Exit codes:
#   0  usable scan topics with real data found
#   1  no scan topics with real data (Jetson stack not running / LiDAR no data)
set -eo pipefail

if ! command -v ros2 &>/dev/null; then
    set +u
    # shellcheck source=/dev/null
    source /opt/ros/humble/setup.bash 2>/dev/null || {
        # ROS2 not available — output defaults and exit without error
        echo "FLEETSAFE_SCAN_TOPICS=/scan0,/scan1"
        echo "FLEETSAFE_ODOM_TOPIC=/odom_raw"
        exit 0
    }
    set -u
fi

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

# Query the live topic list (6 s timeout to handle DDS discovery delay)
TOPICS=$(timeout 6 ros2 topic list 2>/dev/null || true)

if [[ -z "$TOPICS" ]]; then
    # No topics — Jetson stack not running; output defaults so callers can proceed
    echo "FLEETSAFE_SCAN_TOPICS=/scan0,/scan1"
    echo "FLEETSAFE_ODOM_TOPIC=/odom_raw"
    exit 1
fi

# ── Helpers ────────────────────────────────────────────────────────────────────
# _in_graph: topic appears in ros2 topic list
_in_graph() { echo "$TOPICS" | grep -qx "$1"; }

# _has_data: topic is in graph AND a message arrives within 3 s.
# Uses --once with best_effort QoS (LaserScan is typically best_effort).
# Falls back to reliable QoS if first attempt returns nothing.
_has_data() {
    local t="$1"
    _in_graph "$t" || return 1
    # Try best_effort first (LiDAR, IMU are typically best_effort)
    if timeout 3 ros2 topic echo --once \
            --qos-reliability best_effort \
            --qos-durability volatile \
            "$t" 2>/dev/null | grep -q .; then
        return 0
    fi
    # Fallback: reliable QoS (some drivers publish reliable)
    if timeout 3 ros2 topic echo --once "$t" 2>/dev/null | grep -q .; then
        return 0
    fi
    return 1
}

# ── Detect scan topic layout ───────────────────────────────────────────────────
# Priority: prefer topics that have real data.  Fall back to graph-only if none
# have data (e.g. LiDAR connected but merger waiting on upstream).
SCAN_TOPICS=""
SCAN_HAS_DATA=0

_try_scan_layout() {
    local layout="$1"; shift
    local all_in_graph=1 any_has_data=0
    local t
    for t in "$@"; do
        _in_graph "$t" || { all_in_graph=0; break; }
    done
    [[ $all_in_graph -eq 0 ]] && return 1
    for t in "$@"; do
        _has_data "$t" && any_has_data=1
    done
    SCAN_TOPICS="$layout"
    SCAN_HAS_DATA=$any_has_data
    return 0
}

# Try layouts in priority order; prefer the one with real data
if _try_scan_layout "/scan0,/scan1" /scan0 /scan1; then
    :  # found
elif _try_scan_layout "/scan,/scan_multi" /scan /scan_multi; then
    :
elif _try_scan_layout "/scan0" /scan0; then
    :
elif _in_graph /scan; then
    SCAN_TOPICS="/scan"
    _has_data /scan && SCAN_HAS_DATA=1 || SCAN_HAS_DATA=0
fi

# ── Detect odometry topic ──────────────────────────────────────────────────────
ODOM_TOPIC="/odom_raw"
if ! _in_graph /odom_raw && _in_graph /odom; then
    ODOM_TOPIC="/odom"
fi

# ── Output ─────────────────────────────────────────────────────────────────────
if [[ -n "$SCAN_TOPICS" ]]; then
    echo "FLEETSAFE_SCAN_TOPICS=${SCAN_TOPICS}"
    echo "FLEETSAFE_ODOM_TOPIC=${ODOM_TOPIC}"
    [[ $SCAN_HAS_DATA -eq 1 ]] && exit 0 || exit 1
else
    # No scan topics found — output defaults and signal failure
    echo "FLEETSAFE_SCAN_TOPICS=/scan0,/scan1"
    echo "FLEETSAFE_ODOM_TOPIC=${ODOM_TOPIC}"
    exit 1
fi
