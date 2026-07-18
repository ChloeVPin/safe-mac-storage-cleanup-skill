#!/usr/bin/env python3
"""Validated cleanup for paths from a prior storage audit.

Never runs without an audit JSON + explicit approved paths.
Prefers Trash. Permanent delete requires --mode permanent.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from utils import (  # noqa: E402
    assert_safe_for_cleanup,
    dir_size_bytes,
    human_bytes,
    move_to_trash,
    permanent_delete,
    read_json,
    setup_logger,
    utc_now_iso,
    write_json,
)

logger = setup_logger("safe_cleanup")


def load_audit_paths(audit_json: Path) -> Dict[str, Any]:
    data = read_json(audit_json)
    if not isinstance(data, dict) or "findings" not in data:
        raise ValueError("Invalid audit JSON: missing findings")
    return data


def parse_approved(raw: str) -> List[str]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts


def cleanup(
    audit: Dict[str, Any],
    approved_paths: Sequence[str],
    mode: str = "trash",
    dry_run: bool = True,
) -> Dict[str, Any]:
    if mode not in ("trash", "permanent"):
        raise ValueError("mode must be 'trash' or 'permanent'")

    audit_path_set = [f["path"] for f in audit.get("findings", [])]
    results: List[Dict[str, Any]] = []
    total_reclaimed = 0

    for raw in approved_paths:
        path = Path(raw).expanduser()
        entry: Dict[str, Any] = {
            "path": str(path),
            "mode": mode,
            "dry_run": dry_run,
            "ok": False,
            "error": None,
            "size_bytes": 0,
        }
        try:
            assert_safe_for_cleanup(path, audit_paths=audit_path_set)
            if not path.exists():
                raise FileNotFoundError(f"Path does not exist: {path}")
            size = dir_size_bytes(path)
            entry["size_bytes"] = size
            entry["size_human"] = human_bytes(size)

            if dry_run:
                entry["ok"] = True
                entry["action"] = f"would_{mode}"
            else:
                if mode == "trash":
                    move_to_trash(path)
                else:
                    permanent_delete(path)
                entry["ok"] = True
                entry["action"] = mode
                total_reclaimed += size
        except Exception as e:
            entry["error"] = str(e)
            logger.error("%s", e)

        results.append(entry)

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
    p = argparse.ArgumentParser(description="Validated safe cleanup (audit-gated)")
    p.add_argument("--audit-json", required=True, help="Path to audit JSON from storage_audit.py")
    p.add_argument(
        "--approved-paths",
        required=True,
        help="Comma-separated absolute paths the user approved",
    )
    p.add_argument(
        "--mode",
        choices=["trash", "permanent"],
        default="trash",
        help="trash (default) or permanent",
    )
    p.add_argument(
        "--dry-run",
        default="true",
        choices=["true", "false"],
        help="If true (default), only simulate",
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

    if args.mode == "permanent" and not dry_run:
        logger.warning("PERMANENT delete requested — paths will not go to Trash")

    report = cleanup(audit, approved, mode=args.mode, dry_run=dry_run)

    if args.log_json:
        write_json(Path(args.log_json), report)

    print("=== safe_cleanup summary ===")
    print(f"mode={report['mode']} dry_run={report['dry_run']} sandbox={report['sandbox']}")
    print(f"success={report['success_count']} failed={report['failed_count']}")
    if dry_run:
        print(f"would_reclaim={report['would_reclaim_human']}")
    else:
        print(f"reclaimed={report['reclaimed_human']}")
    for r in report["results"]:
        status = "OK" if r["ok"] else "FAIL"
        err = f" — {r['error']}" if r.get("error") else ""
        print(f"  [{status}] {r.get('size_human', '?')}  {r['path']}{err}")

    return 0 if report["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
