#!/usr/bin/env bash
set -euo pipefail

# Refresh local snapshots of canonical Paprika/Skylight API specs and print pinned SHAs.

REPO_ROOT="$(git rev-parse --show-toplevel)"
CACHE_ROOT="${WHISK_EXTERNAL_API_CACHE_DIR:-$REPO_ROOT/.cache/external-api-specs}"

PAPRIKA_URL="https://github.com/aarons22/paprika-tools"
SKYLIGHT_URL="https://github.com/aarons22/skylight-tools"

refresh_repo() {
  local name="$1"
  local url="$2"
  local dir="$CACHE_ROOT/$name"

  if [[ -d "$dir/.git" ]]; then
    git -C "$dir" fetch origin main --prune
  else
    git clone "$url" "$dir"
    git -C "$dir" fetch origin main --prune
  fi

  git -C "$dir" checkout -q main
  git -C "$dir" pull --ff-only origin main
}

mkdir -p "$CACHE_ROOT"

refresh_repo "paprika-tools" "$PAPRIKA_URL"
refresh_repo "skylight-tools" "$SKYLIGHT_URL"

paprika_sha="$(git -C "$CACHE_ROOT/paprika-tools" rev-parse HEAD)"
skylight_sha="$(git -C "$CACHE_ROOT/skylight-tools" rev-parse HEAD)"

cat <<OUT
External API specs refreshed.
Cache directory: $CACHE_ROOT
Paprika repo: $CACHE_ROOT/paprika-tools
Paprika SHA:  $paprika_sha
Skylight repo: $CACHE_ROOT/skylight-tools
Skylight SHA:  $skylight_sha
OUT
