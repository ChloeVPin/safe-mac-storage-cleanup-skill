#!/usr/bin/env python3
"""Validated cleanup for paths from a prior storage audit.

Never runs without an audit JSON + explicit approved paths.
Prefers Trash. Permanent delete requires --mode permanent.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from utils import (  # noqa: E402
    assert_safe_for_cleanup,
    check_python3,
    dir_size_bytes,
    human_bytes,
    move_to_trash,
    permanent_delete,
    read_json,
    setup_logger,
    utc_now_iso,
    write_json,
)

logger = setup_logger("cleanme")


def load_audit_paths(audit_json: Path) -> Dict[str, Any]:
    data = read_json(audit_json)
    if not isinstance(data, dict) or "findings" not in data:
        raise ValueError("Invalid audit JSON: missing findings")
    generated_at = data.get("generated_at")
    if generated_at:
        try:
            audit_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age_hours = (now - audit_time).total_seconds() / 3600
            if age_hours > 24:
                logger.warning("Audit JSON is %.1f hours old (max 24h recommended)", age_hours)
        except (ValueError, TypeError):
            pass
    return data


def parse_approved(raw: str) -> List[str]:
    if not raw.strip():
        return []
    parts = [p.strip().strip('"').strip("'") for p in raw.replace("\n", ",").split(",") if p.strip()]
    return parts


def cleanup(
    audit: Dict[str, Any],
    approved_paths: Sequence[str],
    mode: str = "trash",
    dry_run: bool = True,
    interactive: bool = False,
    progress: bool = False,
) -> Dict[str, Any]:
    if mode not in ("trash", "permanent", "soft-permanent"):
        raise ValueError("mode must be 'trash', 'permanent', or 'soft-permanent'")

    audit_path_set = [f["path"] for f in audit.get("findings", [])]
    audit_inode_map = {}
    audit_by_path = {}
    for f in audit.get("findings", []):
        if f.get("inode"):
            audit_inode_map[f["path"]] = tuple(f["inode"])
        audit_by_path[f["path"]] = f
    results: List[Dict[str, Any]] = []
    total_reclaimed = 0
    total_approved = len(approved_paths)

    for idx, raw in enumerate(approved_paths, 1):
        path = Path(raw).expanduser()
        entry: Dict[str, Any] = {
            "path": str(path),
            "mode": mode,
            "dry_run": dry_run,
            "ok": False,
            "error": None,
            "size_bytes": 0,
        }
        if progress:
            print(f"[{idx}/{total_approved}] Processing {path}...")
        try:
            assert_safe_for_cleanup(path, audit_paths=audit_path_set)
            if not path.exists():
                raise FileNotFoundError(f"Path does not exist: {path}")
            current_inode = None
            try:
                stat = path.stat()
                current_inode = (stat.st_dev, stat.st_ino)
            except OSError:
                pass
            resolved_path = str(path.resolve())
            if resolved_path in audit_inode_map:
                expected_inode = audit_inode_map[resolved_path]
                if current_inode and expected_inode and current_inode != expected_inode:
                    raise ValueError(
                        f"Path inode changed since audit (expected {expected_inode}, got {current_inode}): {path}"
                    )
            size = dir_size_bytes(path)
            entry["size_bytes"] = size
            entry["size_human"] = human_bytes(size)
            audit_entry = audit_by_path.get(resolved_path)
            if audit_entry and audit_entry.get("size_bytes"):
                expected_size = audit_entry["size_bytes"]
                if expected_size > 0 and abs(size - expected_size) / expected_size > 0.5:
                    logger.warning(
                        "Size changed for %s: audit=%s current=%s",
                        path, human_bytes(expected_size), human_bytes(size)
                    )

            if dry_run:
                entry["ok"] = True
                entry["action"] = f"would_{mode}"
            else:
                if interactive:
                    resp = input(f"[{idx}/{total_approved}] Delete {path} ({entry.get('size_human', '?')})? [y/N] ").strip().lower()
                    if resp != "y":
                        entry["error"] = "User declined interactive confirmation"
                        logger.warning("User declined deletion of %s", path)
                        results.append(entry)
                        continue
                if mode == "trash":
                    move_to_trash(path)
                elif mode == "soft-permanent":
                    dest = soft_permanent_delete(path)
                    entry["quarantine_path"] = str(dest)
                    # Now permanently delete from quarantine
                    permanent_delete(Path(dest))
                else:
                    permanent_delete(path)
                entry["ok"] = True
                entry["action"] = mode
                total_reclaimed += size
        except Exception as e:
            entry["error"] = str(e)
            logger.error("%s", e)

        results.append(entry)
        if not dry_run and entry["ok"]:
            print(f"[{idx}/{total_approved}] {entry['action']} {entry['path']} ({entry.get('size_human', '?')})")

    if dry_run:
        total_reclaimed = sum(r["size_bytes"] for r in results if r["ok"])

    return {
        "generated_at": utc_now_iso(),
        "mode": mode,
        "dry_run": dry_run,
        "sandbox": os.environ.get("MAC_STORAGE_SANDBOX") == "1",
        "approved_count": len(approved_paths),
        "success_count": sum(1 for r in results if r["ok"]),
        "failed_count": sum(1 for r in results if not r["ok"]),
        "reclaimed_bytes": total_reclaimed if not dry_run else 0,
        "reclaimed_human": human_bytes(total_reclaimed if not dry_run else 0),
        "would_reclaim_bytes": sum(r["size_bytes"] for r in results if r["ok"]),
        "would_reclaim_human": human_bytes(sum(r["size_bytes"] for r in results if r["ok"])),
        "results": results,
    }


def main(argv: Optional[List[str]] = None) -> int:
    check_python3()
    p = argparse.ArgumentParser(description="Validated safe cleanup (audit-gated)")
    p.add_argument("--audit-json", required=True, help="Path to audit JSON from storage_audit.py")
    p.add_argument(
        "--approved-paths",
        required=True,
        help="Comma-separated absolute paths the user approved",
    )
    p.add_argument(
        "--mode",
        choices=["trash", "permanent", "soft-permanent"],
        default="trash",
        help="trash (default), permanent, or soft-permanent (quarantine then delete)",
    )
    p.add_argument(
        "--confirm-permanent",
        action="store_true",
        help="Required when --mode permanent or --mode soft-permanent: confirms irreversible deletion",
    )
    p.add_argument(
        "--session-id",
        default=None,
        help="Expected session ID from the audit report (replay protection)",
    )
    p.add_argument(
        "--dry-run",
        default="true",
        choices=["true", "false"],
        help="If true (default), only simulate",
    )
    p.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for confirmation before each deletion",
    )
    p.add_argument(
        "--progress",
        action="store_true",
        help="Show progress indication for large cleanups",
    )
    p.add_argument(
        "--log-json",
        default=None,
        help="Optional path to write cleanup result JSON",
    )
    args = p.parse_args(argv)

    dry_run = args.dry_run.lower() == "true"
    audit = load_audit_paths(Path(args.audit_json))
    approved = parse_approved(args.approved_paths)

    if not approved:
        logger.error("No approved paths provided")
        return 2

    if args.session_id and audit.get("session_id") and args.session_id != audit["session_id"]:
        logger.error("Session ID mismatch: expected %s, got %s", args.session_id, audit.get("session_id"))
        return 2

    if args.mode in ("permanent", "soft-permanent") and not dry_run and not args.confirm_permanent:
        logger.error("%s delete requires --confirm-permanent flag", args.mode)
        return 2

    if args.mode in ("permanent", "soft-permanent") and not dry_run:
        logger.warning("%s delete requested - files will not go to Trash", args.mode)

    report = cleanup(audit, approved, mode=args.mode, dry_run=dry_run, interactive=args.interactive, progress=args.progress)

    if args.log_json:
        write_json(Path(args.log_json), report)

    print("=== cleanme cleanup summary ===")
    print(f"mode={report['mode']} dry_run={report['dry_run']} sandbox={report['sandbox']}")
    print(f"success={report['success_count']} failed={report['failed_count']}")
    if dry_run:
        print(f"would_reclaim={report['would_reclaim_human']}")
    else:
        print(f"reclaimed={report['reclaimed_human']}")
    print()
    print("| Status | Size | Path | Action | Error |")
    print("|--------|------|------|--------|-------|")
    for r in report["results"]:
        status = "OK" if r["ok"] else "FAIL"
        size = r.get("size_human", "?")
        action = r.get("action", "?")
        err = r.get("error", "")
        safe_path = str(r["path"]).replace("|", "\\|")
        print(f"| {status} | {size} | {safe_path} | {action} | {err} |")

    return 0 if report["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
