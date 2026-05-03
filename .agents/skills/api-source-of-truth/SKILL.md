---
name: api-source-of-truth
description: Ensure API-facing work uses canonical external specs from paprika-tools and skylight-tools, refreshed on demand before implementation. Use when adding or changing Paprika/Skylight API functionality.
---

Use this skill whenever implementing, debugging, or extending Paprika/Skylight API integrations.

## Canonical Sources

- Paprika: https://github.com/aarons22/paprika-tools
- Skylight: https://github.com/aarons22/skylight-tools

These repos are the source of truth for API behavior.
Prefer `openapi.yaml`, README docs, and API reference material in those repos.

## Required Workflow

1. Refresh local spec snapshots before API-facing changes.

```bash
repo_root="$(git rev-parse --show-toplevel)"
"$repo_root/scripts/pull_external_api_specs.sh"
```

2. Review canonical docs from the refreshed snapshots first:
   - `openapi.yaml`
   - API reference and README guidance

3. Implement against that snapshot.

4. When behavior changes are introduced, record source commit SHAs in local notes (`API_REFERENCE.md`) so the implementation has a traceable spec baseline.

## Notes

- Treat local `API_REFERENCE.md` as project commentary/snapshot notes, not canonical truth.
- If you find missing or incorrect canonical docs, prefer updating the external source repos (or filing upstream issues/PRs), then document local impact.
