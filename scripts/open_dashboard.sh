#!/usr/bin/env bash
# scripts/open_dashboard.sh
# ─────────────────────────────────────────────────────────────────────────────
# Open a URL in the user's default browser — browser-agnostic.
#
# Usage:
#   bash scripts/open_dashboard.sh
#   bash scripts/open_dashboard.sh http://localhost:3000/dashboard/demo
# ─────────────────────────────────────────────────────────────────────────────

URL="${1:-http://localhost:3000/dashboard/demo}"

open_dashboard() {
    local url="$1"

    echo "Opening Dashboard: $url"

    # No GUI available (SSH session, headless server)
    if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
        echo "No GUI display detected (DISPLAY/WAYLAND_DISPLAY not set)."
        echo "Open this URL manually in your browser:"
        echo "  $url"
        return 0
    fi

    # Honour $BROWSER env var if set and executable
    if [ -n "${BROWSER:-}" ] && command -v "$BROWSER" >/dev/null 2>&1; then
        nohup "$BROWSER" "$url" >/dev/null 2>&1 &
        return 0
    fi

    # xdg-open — delegates to the desktop environment's default handler
    if command -v xdg-open >/dev/null 2>&1; then
        nohup xdg-open "$url" >/dev/null 2>&1 &
        return 0
    fi

    # sensible-browser — Debian/Ubuntu helper
    if command -v sensible-browser >/dev/null 2>&1; then
        nohup sensible-browser "$url" >/dev/null 2>&1 &
        return 0
    fi

    # gio — GNOME fallback
    if command -v gio >/dev/null 2>&1; then
        nohup gio open "$url" >/dev/null 2>&1 &
        return 0
    fi

    # Direct browser fallbacks in preference order
    for browser in google-chrome chrome chromium-browser chromium brave-browser microsoft-edge firefox; do
        if command -v "$browser" >/dev/null 2>&1; then
            nohup "$browser" "$url" >/dev/null 2>&1 &
            return 0
        fi
    done

    echo "Could not detect a browser to open automatically."
    echo "Open this URL manually:"
    echo "  $url"
}

open_dashboard "$URL"
