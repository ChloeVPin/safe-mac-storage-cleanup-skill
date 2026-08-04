---
name: cleanme
description: >
  Safety-first macOS storage cleanup for AI agents. Read-only audit first,
  strict whitelists, explicit per-path approval, Trash by default.
  Use when the user mentions full disk, free space, storage cleanup, or
  reclaiming disk on macOS.
---

# cleanme

## Core rules (never violate)

1. **Never** delete, move, or modify files without **explicit user approval** of specific paths from the current audit.
2. **Whitelist only.** Operate only on caches, logs, package caches, developer artifacts, Trash, and temps. Never touch Documents, Desktop, Pictures, Photos, Keychains, Mail, iCloud, Application Support user data, or system roots.
3. **Read-only audit first** every session via `scripts/storage_audit.py`.
4. **Validated cleanup only** via `scripts/safe_cleanup.py`. Prefer `--mode trash`. Default `--dry-run true` until the user says to proceed.
5. **No raw `rm` / `rm -rf`.** No sudo unless the user explicitly demands and justifies it.
6. Broad phrases like "clean everything" only apply to **already-listed low-risk** items from the **current** audit.

## Scripts

Resolve `SKILL_ROOT` to this skill directory (folder containing this `SKILL.md`).

```bash
# Audit (read-only)
python3 "$SKILL_ROOT/scripts/storage_audit.py" \
  --output "/tmp/cleanme-audit-$(date +%Y%m%d-%H%M)" \
  --min-size-mb 100

# Cleanup (after explicit path approval)
python3 "$SKILL_ROOT/scripts/safe_cleanup.py" \
  --audit-json "/tmp/cleanme-audit-….json" \
  --approved-paths "/exact/path1,/exact/path2" \
  --mode trash \
  --dry-run true
```

Set `--dry-run false` only after the user confirms the dry-run summary.

## Workflow

1. Confirm intent.
2. Run a fresh audit.
3. Present a ranked table (path, size, category, risk, action).
4. Ask for explicit approval of exact paths.
5. Dry-run cleanup, show summary, get final yes.
6. Execute with `--dry-run false`.
7. Report reclaim and suggest emptying Trash in Finder if they want permanent free space.

## Agent presentation guide

- Format the audit as a Markdown table with columns: #, Size, Risk, Category, Recommended, Path.
- If the user says "clean everything", apply it only to low-risk items from the current audit. Do not extend to medium-risk or unlisted paths.
- If the user approves zero paths, report "No paths approved. Cleanup skipped." Do not treat this as an error.
- For dry-run, show the same table format with a "would_trash" or "would_permanent" action column.
- After execution, report reclaimed space and remind the user that Trash still occupies space until emptied.

## Error handling

- If `python3` is missing, tell the user to install it from python.org or Homebrew.
- If a path is refused, explain why (deny list, not whitelisted, not in audit, symlink, or inode mismatch).
- If cleanup fails partway, report which paths succeeded and which failed, then stop. Do not retry automatically.
- If the audit finds no items above the size threshold, tell the user and suggest lowering `--min-size-mb`.

## Sandbox / tests

Scripts honor `HOME` and `MAC_STORAGE_SANDBOX=1` (uses `~/.Trash` move instead of Finder). See `tests/run_sandbox.sh` in the repo.

## Recovery

If a cleanup moves files to Trash, inform the user they can restore from Finder Trash until it is emptied. If `--mode permanent` was used, the files are irreversibly deleted. Never use permanent mode without explicit user confirmation.
