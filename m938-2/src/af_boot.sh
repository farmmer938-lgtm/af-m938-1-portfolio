#!/usr/bin/env bash
# Bring AF's unattended m938-2 services back after a container restart.
# A restart wipes the container rootfs (apt/pip pkgs, processes) but keeps /workspace.
# Kept for compatibility; the real work lives in af_up.sh (identity-checked, idempotent).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
exec bash "$HERE/af_up.sh"
