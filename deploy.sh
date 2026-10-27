#!/usr/bin/env bash
# ==============================================================================
# NexChecker Root Universal Launcher
# Forwards to deploy/universal.sh with full argument passthrough
# Usage: ./deploy.sh [OPTIONS]
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/deploy/universal.sh" "$@"
