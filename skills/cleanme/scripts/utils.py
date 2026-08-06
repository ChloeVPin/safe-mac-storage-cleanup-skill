#!/usr/bin/env python3
"""Shared helpers for safe macOS storage audit/cleanup.

All paths resolve under os.environ["HOME"] so tests can use a fake home.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence

# --- Path roots (HOME-aware) -------------------------------------------------

def home() -> Path:
    return Path(os.path.expanduser("~")).resolve()


def library() -> Path:
    return home() / "Library"


# --- Size / formatting -------------------------------------------------------

def human_bytes(n: int) -> str:
    if n < 0:
        n = 0
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for u in units:
        if size < 1024.0 or u == units[-1]:
            if u == "B":
                return f"{int(size)} {u}"
            return f"{size:.1f} {u}"
        size /= 1024.0
    return f"{n} B"


def dir_size_bytes(path: Path, max_depth: int = 8, max_walk_seconds: float = 30.0) -> int:
    """Best-effort recursive size. Skips permission errors and times out after max_walk_seconds."""
    if not path.exists():
        return 0
    if path.is_file() or path.is_symlink():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    start = datetime.now(timezone.utc)
    file_count = 0
    try:
        for root, dirs, files in os.walk(path, followlinks=False):
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            if elapsed > max_walk_seconds:
                logger.warning("dir_size_bytes timed out after %.1fs walking %s", elapsed, path)
                break
            depth = Path(root).relative_to(path).parts
            if len(depth) >= max_depth:
                dirs.clear()
            for name in files:
                file_count += 1
                if file_count % 1000 == 0:
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
                    if elapsed > max_walk_seconds:
                        logger.warning("dir_size_bytes timed out after %.1fs and %d files in %s", elapsed, file_count, path)
                        break
                fp = Path(root) / name
                try:
                    if fp.is_symlink():
                        continue
                    total += fp.stat().st_size
                except OSError:
                    continue
    except OSError:
        pass
    return total


# --- Safety model ------------------------------------------------------------

# Exact prefixes (under HOME) that may be scanned / cleaned.
# Paths are matched as resolved absolute paths starting with these roots.
SAFE_PREFIX_REL = [
    "Library/Caches",
    "Library/Logs",
    "Library/Developer/Xcode/DerivedData",
    "Library/Developer/CoreSimulator/Caches",
    "Library/Developer/Xcode/iOS DeviceSupport",
    ".npm/_cacache",
    ".npm/_logs",
    ".cache",
    ".cargo/registry/cache",
    ".cargo/git/db",
    "go/pkg/mod/cache",
    ".Trash",
    # package managers often under Library
    "Library/Caches/Homebrew",
    "Library/Caches/pip",
    "Library/Caches/Yarn",
    "Library/Caches/CocoaPods",
    "Library/Caches/com.apple.dt.Xcode",
    # additional package managers
    ".conda/pkgs",
    ".rbenv/versions",
    ".phpbrew",
]

# Absolute roots that are also safe (system temp)
SAFE_ABS_PREFIXES = [
    "/tmp",
    "/private/tmp",
    "/var/folders",  # macOS user temp; still validated carefully
]

# Hard deny: never scan or clean these (relative to HOME)
DENY_PREFIX_REL = [
    "Documents",
    "Desktop",
    "Pictures",
    "Music",
    "Movies",
    "Public",
    "Downloads",  # high-caution only; excluded from automated clean
    "Library/Mail",
    "Library/Keychains",
    "Library/Messages",
    "Library/Photos",
    "Library/Containers",
    "Library/Group Containers",
    "Library/Mobile Documents",
    "Library/Application Support",  # often real user data
    "Library/Preferences",
    ".ssh",
    ".gnupg",
    ".aws",
    ".config",
]

DENY_ABS_PREFIXES = [
    "/System",
    "/usr",
    "/bin",
    "/sbin",
    "/etc",
    "/Applications",
    "/Library",  # system Library, not ~/Library
]


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def deny_reasons(path: Path) -> List[str]:
    """Return human reasons this path is forbidden (empty = not denied by hard rules)."""
    reasons: List[str] = []
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return ["unresolvable path"]

    s = str(resolved)
    h = home()

    for d in DENY_ABS_PREFIXES:
        if s == d or s.startswith(d + os.sep):
            # Allow /tmp etc handled separately; /Library is system
            if d == "/Library" and _is_under(resolved, library()):
                continue
            reasons.append(f"system/deny absolute prefix: {d}")

    if _is_under(resolved, h):
        try:
            rel = str(resolved.relative_to(h))
        except ValueError:
            rel = ""
        for d in DENY_PREFIX_REL:
            if rel == d or rel.startswith(d + os.sep):
                reasons.append(f"user-data deny prefix: ~/{d}")

    # Never allow path traversal outside known roots for cleanup of HOME-relative claims
    if ".." in path.parts:
        reasons.append("path contains ..")

    return reasons


def is_whitelisted(path: Path) -> bool:
    """True if path is under a safe prefix and not hard-denied."""
    if deny_reasons(path):
        return False
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False

    s = str(resolved)
    h = home()

    for abs_p in SAFE_ABS_PREFIXES:
        if s == abs_p or s.startswith(abs_p.rstrip("/") + os.sep) or s.startswith(abs_p + os.sep):
            # /var/folders is broad; require it to look like a temp cache path
            if abs_p == "/var/folders":
                # Only allow specific known-safe patterns under /var/folders
                # These are macOS user temp/cache directories
                if "/T/" in s and ("/Library/Caches/" in s or "/Caches/" in s):
                    return True
                if "/C/" in s and ("/Library/Caches/" in s or "/Caches/" in s):
                    return True
                return False
            return True

    if not _is_under(resolved, h):
        return False

    rel = str(resolved.relative_to(h))
    for pref in SAFE_PREFIX_REL:
        if rel == pref or rel.startswith(pref + os.sep):
            return True
    # Check user-configured extra prefixes
    for pref in get_extra_whitelist_prefixes():
        if rel == pref or rel.startswith(pref + os.sep):
            return True
    return False


def assert_safe_for_cleanup(path: Path, audit_paths: Optional[Sequence[str]] = None) -> None:
    """Raise ValueError if path must not be cleaned."""
    if path.is_symlink():
        raise ValueError(f"Refusing symlink: {path}")
    reasons = deny_reasons(path)
    if reasons:
        raise ValueError(f"Refusing path (deny list): {path} - {'; '.join(reasons)}")
    if not is_whitelisted(path):
        raise ValueError(f"Refusing path (not on whitelist): {path}")
    if audit_paths is not None:
        resolved = str(path.expanduser().resolve())
        allowed = {str(Path(p).expanduser().resolve()) for p in audit_paths}
        if resolved not in allowed:
            raise ValueError(
                f"Refusing path not present in audit report: {path}"
            )


def check_python3() -> None:
    """Verify python3 is available and meets minimum version."""
    if sys.version_info < (3, 8):
        print("ERROR: python3 >= 3.8 is required. Please install it from python.org or brew.", file=sys.stderr)
        sys.exit(1)


# --- Logging -----------------------------------------------------------------

def setup_logger(name: str = "cleanme", log_file: Optional[Path] = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


# --- Trash / delete ----------------------------------------------------------

def move_to_trash(path: Path) -> None:
    """Move to Trash via Finder (macOS) or ~/.Trash fallback / sandbox trash."""
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(str(path))
    if path.is_symlink():
        raise ValueError(f"Refusing symlink: {path}")

    # Prefer macOS Finder trash when available and not in sandbox (real home)
    if sys.platform == "darwin" and os.environ.get("MAC_STORAGE_SANDBOX") != "1":
        script = f'tell application "Finder" to delete POSIX file "{path}"'
        try:
            subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                text=True,
            )
            if path.exists():
                raise RuntimeError(f"Finder reported success but path still exists: {path}")
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    trash_dir = home() / ".Trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    dest = trash_dir / path.name
    if dest.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        dest = trash_dir / f"{path.name}.{stamp}"
    try:
        shutil.move(str(path), str(dest))
    except PermissionError as e:
        raise PermissionError(f"Permission denied moving to Trash: {path} ({e})")
    if path.exists():
        raise RuntimeError(f"Trash operation completed but source still exists: {path}")


def permanent_delete(path: Path) -> None:
    path = path.expanduser().resolve()
    if path.is_symlink():
        raise ValueError(f"Refusing symlink: {path}")
    if path.is_dir() and not path.is_symlink():
        try:
            shutil.rmtree(path)
        except PermissionError as e:
            raise PermissionError(f"Permission denied permanently deleting: {path} ({e})")
    else:
        try:
            path.unlink()
        except PermissionError as e:
            raise PermissionError(f"Permission denied permanently deleting: {path} ({e})")


def soft_permanent_delete(path: Path, quarantine_dir: Optional[Path] = None) -> Path:
    """Move to quarantine directory before permanent deletion."""
    path = path.expanduser().resolve()
    if path.is_symlink():
        raise ValueError(f"Refusing symlink: {path}")
    if quarantine_dir is None:
        quarantine_dir = home() / ".Trash" / "cleanme-quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    dest = quarantine_dir / path.name
    if dest.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        dest = quarantine_dir / f"{path.name}.{stamp}"
    try:
        shutil.move(str(path), str(dest))
    except OSError as e:
        # Cross-filesystem move fallback: copy then delete
        if path.is_dir() and not path.is_symlink():
            shutil.copytree(str(path), str(dest))
            shutil.rmtree(str(path))
        else:
            shutil.copy2(str(path), str(dest))
            path.unlink()
    return dest


def disk_free_bytes(mount: str = "/") -> Optional[int]:
    try:
        usage = shutil.disk_usage(mount)
        return usage.free
    except OSError:
        return None


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_cleanme_config() -> Dict[str, Any]:
    """Load optional cleanme.json config file for user-extended whitelist."""
    config_path = home() / ".cleanme.json"
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def get_extra_whitelist_prefixes() -> List[str]:
    """Return additional safe prefixes from cleanme.json config."""
    config = load_cleanme_config()
    prefixes = config.get("extra_whitelist_prefixes", [])
    if not isinstance(prefixes, list):
        return []
    return [str(p) for p in prefixes if isinstance(p, str)]
