#!/usr/bin/env python3
"""Read-only macOS storage audit. Never deletes or modifies files.

Respects HOME (and MAC_STORAGE_SANDBOX) so tests can use a fake home.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow running as script from any cwd
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from utils import (  # noqa: E402
    check_python3,
    dir_size_bytes,
    home,
    human_bytes,
    is_whitelisted,
    library,
    setup_logger,
    utc_now_iso,
    write_json,
)

logger = setup_logger("storage_audit")

# Scan targets: (relative_to_home or absolute, category, risk, label)
# risk: low | medium
SCAN_TARGETS = [
    ("Library/Caches", "caches", "low", "User Library Caches"),
    ("Library/Logs", "logs", "low", "User Library Logs"),
    ("Library/Developer/Xcode/DerivedData", "developer", "low", "Xcode DerivedData"),
    ("Library/Developer/CoreSimulator/Caches", "developer", "low", "CoreSimulator Caches"),
    (".npm/_cacache", "package_cache", "low", "npm cache"),
    (".cache", "caches", "low", "User ~/.cache"),
    (".Trash", "trash", "low", "Trash"),
    ("Library/Caches/Homebrew", "package_cache", "low", "Homebrew cache"),
    ("Library/Caches/pip", "package_cache", "low", "pip cache"),
    ("Library/Caches/Yarn", "package_cache", "low", "Yarn cache"),
    ("Library/Caches/CocoaPods", "package_cache", "low", "CocoaPods cache"),
    (".conda/pkgs", "package_cache", "low", "conda packages"),
    (".rbenv/versions", "package_manager", "low", "rbenv Ruby versions"),
    (".phpbrew", "package_manager", "low", "phpbrew PHP versions"),
]

ABS_SCAN = [
    ("/tmp", "temp", "low", "System /tmp"),
    ("/private/tmp", "temp", "low", "System /private/tmp"),
]


def _resolve_target(spec: str) -> Path:
    if spec.startswith("/"):
        return Path(spec)
    return home() / spec


def _list_children(root: Path, min_size: int) -> List[Dict[str, Any]]:
    """List direct children of root with sizes (or root itself if file)."""
    items: List[Dict[str, Any]] = []
    if not root.exists():
        return items
    if root.is_file():
        try:
            sz = root.stat().st_size
        except OSError:
            return items
        if sz >= min_size:
            items.append({"path": str(root.resolve()), "size_bytes": sz})
        return items

    try:
        children = list(root.iterdir())
    except OSError as e:
        logger.warning("Cannot list %s: %s", root, e)
        return items

    for child in children:
        try:
            if child.is_symlink():
                continue
            sz = dir_size_bytes(child)
            if sz >= min_size:
                items.append({"path": str(child.resolve()), "size_bytes": sz})
        except OSError:
            continue
    return items


def audit(
    min_size_mb: float = 1.0,
    categories: Optional[List[str]] = None,
    include_abs_tmp: bool = True,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    min_size = int(min_size_mb * 1024 * 1024)
    cat_filter = set(categories) if categories else None
    findings: List[Dict[str, Any]] = []

    targets = list(SCAN_TARGETS)
    if include_abs_tmp and os.environ.get("MAC_STORAGE_SANDBOX") != "1":
        targets_abs = ABS_SCAN
    else:
        # In sandbox, scan fake home tmp only
        targets_abs = []
        sandbox_tmp = home() / "tmp"
        if sandbox_tmp.exists():
            targets.append(("tmp", "temp", "low", "Sandbox tmp"))

    for rel, category, risk, label in targets:
        if cat_filter and category not in cat_filter:
            continue
        root = _resolve_target(rel)
        if not root.exists():
            continue
        if not is_whitelisted(root):
            logger.warning("Skipping non-whitelisted target %s", root)
            continue

        for child in _list_children(root, min_size):
            p = Path(child["path"])
            if not is_whitelisted(p):
                logger.warning("Skipping non-whitelisted child %s", p)
                continue
            try:
                stat = p.stat()
                inode = (stat.st_dev, stat.st_ino)
            except OSError:
                inode = None
            findings.append(
                {
                    "path": child["path"],
                    "size_bytes": child["size_bytes"],
                    "size_human": human_bytes(child["size_bytes"]),
                    "category": category,
                    "risk": risk,
                    "label": label,
                    "recommended_action": "trash" if risk == "low" else "review",
                    "inode": inode,
                }
            )

    for abs_path, category, risk, label in targets_abs:
        if cat_filter and category not in cat_filter:
            continue
        root = Path(abs_path)
        if not root.exists():
            continue
        for child in _list_children(root, min_size):
            p = Path(child["path"])
            if not is_whitelisted(p):
                continue
            try:
                stat = p.stat()
                inode = (stat.st_dev, stat.st_ino)
            except OSError:
                inode = None
            # Avoid scanning huge unrelated /tmp noise: only age-agnostic but size-gated
            findings.append(
                {
                    "path": child["path"],
                    "size_bytes": child["size_bytes"],
                    "size_human": human_bytes(child["size_bytes"]),
                    "category": category,
                    "risk": risk,
                    "label": label,
                    "recommended_action": "trash",
                    "inode": inode,
                }
            )

    findings.sort(key=lambda x: x["size_bytes"], reverse=True)
    total = sum(f["size_bytes"] for f in findings)
    low = sum(f["size_bytes"] for f in findings if f["risk"] == "low")

    report = {
        "generated_at": utc_now_iso(),
        "home": str(home()),
        "sandbox": os.environ.get("MAC_STORAGE_SANDBOX") == "1",
        "min_size_mb": min_size_mb,
        "session_id": session_id,
        "summary": {
            "item_count": len(findings),
            "total_bytes": total,
            "total_human": human_bytes(total),
            "low_risk_bytes": low,
            "low_risk_human": human_bytes(low),
        },
        "findings": findings,
    }
    return report


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# macOS Storage Audit (read-only)",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Home: `{report['home']}`",
        f"- Sandbox: `{report['sandbox']}`",
        f"- Min size: `{report['min_size_mb']} MB`",
        f"- Items: **{report['summary']['item_count']}**",
        f"- Total reclaimable (listed): **{report['summary']['total_human']}**",
        f"- Low-risk subset: **{report['summary']['low_risk_human']}**",
        "",
        "## Ranked findings",
        "",
        "| # | Size | Risk | Category | Recommended | Path |",
        "|---|------|------|----------|-------------|------|",
    ]
    for i, f in enumerate(report["findings"], 1):
        lines.append(
            f"| {i} | {f['size_human']} | {f['risk']} | {f['category']} | "
            f"{f['recommended_action']} | `{f['path']}` |"
        )
    if not report["findings"]:
        lines.append("| - | - | - | - | - | _(none above min size)_ |")
    lines.extend(
        [
            "",
            "## Next steps",
            "",
            "1. Review paths carefully.",
            "2. Approve specific paths in chat.",
            "3. Run `safe_cleanup.py` with `--approved-paths` (prefer `--mode trash`).",
            "",
            "**Nothing has been deleted or moved.**",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    check_python3()
    p = argparse.ArgumentParser(description="Read-only safe storage audit")
    p.add_argument(
        "--output",
        required=True,
        help="Output path prefix (writes .json and .md)",
    )
    p.add_argument("--min-size-mb", type=float, default=1.0)
    p.add_argument(
        "--category",
        nargs="*",
        default=None,
        help="Optional category filter: caches logs developer package_cache trash temp",
    )
    p.add_argument(
        "--no-system-tmp",
        action="store_true",
        help="Skip /tmp and /private/tmp",
    )
    p.add_argument(
        "--session-id",
        default=None,
        help="Optional session ID to embed in the audit report for replay protection",
    )
    args = p.parse_args(argv)

    report = audit(
        min_size_mb=args.min_size_mb,
        categories=args.category,
        include_abs_tmp=not args.no_system_tmp,
        session_id=args.session_id,
    )

    out = Path(args.output)
    # if output is a directory-like prefix without suffix, use as prefix
    json_path = out if out.suffix == ".json" else Path(str(out) + ".json")
    md_path = json_path.with_suffix(".md")

    write_json(json_path, report)
    md_path.write_text(render_markdown(report), encoding="utf-8")

    logger.info("Wrote %s (%d findings, %s)", json_path, report["summary"]["item_count"], report["summary"]["total_human"])
    logger.info("Wrote %s", md_path)
    print(md_path.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
