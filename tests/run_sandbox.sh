#!/usr/bin/env bash
# Controlled sandbox test — NEVER touches the real user home.
# Creates a fake HOME under /tmp, seeds caches + forbidden dirs, runs audit/cleanup.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/skill/scripts"
SANDBOX_ROOT="$(mktemp -d /tmp/mac-storage-sandbox.XXXXXX)"
FAKE_HOME="$SANDBOX_ROOT/home"
AUDIT_PREFIX="$SANDBOX_ROOT/audit"
export HOME="$FAKE_HOME"
export MAC_STORAGE_SANDBOX=1
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

PASS=0
FAIL=0
pass() { echo "  PASS  $*"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL  $*"; FAIL=$((FAIL + 1)); }

cleanup_sandbox() {
  rm -rf "$SANDBOX_ROOT"
}
trap cleanup_sandbox EXIT

echo "=== Sandbox root: $SANDBOX_ROOT ==="
echo "=== Fake HOME:    $FAKE_HOME ==="
echo

# --- Seed fixture tree -------------------------------------------------------
mkdir -p \
  "$FAKE_HOME/Library/Caches/BigAppCache" \
  "$FAKE_HOME/Library/Caches/SmallCache" \
  "$FAKE_HOME/Library/Logs" \
  "$FAKE_HOME/Library/Developer/Xcode/DerivedData/MyApp-abc" \
  "$FAKE_HOME/.npm/_cacache/content-v2" \
  "$FAKE_HOME/.Trash" \
  "$FAKE_HOME/Documents/SecretProject" \
  "$FAKE_HOME/Desktop" \
  "$FAKE_HOME/Pictures" \
  "$FAKE_HOME/Library/Mail" \
  "$FAKE_HOME/Library/Keychains" \
  "$FAKE_HOME/Library/Application Support/ImportantApp"

# ~6 MB cache (above 1 MB min)
dd if=/dev/urandom of="$FAKE_HOME/Library/Caches/BigAppCache/blob.bin" bs=1024 count=6000 status=none
# small cache under threshold
echo "tiny" > "$FAKE_HOME/Library/Caches/SmallCache/x.txt"
# logs ~2 MB
dd if=/dev/urandom of="$FAKE_HOME/Library/Logs/app.log" bs=1024 count=2048 status=none
# derived data ~3 MB
dd if=/dev/urandom of="$FAKE_HOME/Library/Developer/Xcode/DerivedData/MyApp-abc/build.o" bs=1024 count=3072 status=none
# npm cache ~2 MB
dd if=/dev/urandom of="$FAKE_HOME/.npm/_cacache/content-v2/pack.tgz" bs=1024 count=2048 status=none

# FORBIDDEN — must never appear as cleanable targets that get deleted by accident
echo "DO NOT DELETE — real documents" > "$FAKE_HOME/Documents/SecretProject/thesis.txt"
echo "private desktop note" > "$FAKE_HOME/Desktop/notes.txt"
echo "photo library stub" > "$FAKE_HOME/Pictures/vacation.jpg"
echo "mail store" > "$FAKE_HOME/Library/Mail/mailbox.db"
echo "keychain stub" > "$FAKE_HOME/Library/Keychains/login.keychain-db"
echo "app data" > "$FAKE_HOME/Library/Application Support/ImportantApp/data.db"

DOC_HASH_BEFORE=$(shasum -a 256 "$FAKE_HOME/Documents/SecretProject/thesis.txt" | awk '{print $1}')
DESK_HASH_BEFORE=$(shasum -a 256 "$FAKE_HOME/Desktop/notes.txt" | awk '{print $1}')
MAIL_HASH_BEFORE=$(shasum -a 256 "$FAKE_HOME/Library/Mail/mailbox.db" | awk '{print $1}')
KEY_HASH_BEFORE=$(shasum -a 256 "$FAKE_HOME/Library/Keychains/login.keychain-db" | awk '{print $1}')
APP_HASH_BEFORE=$(shasum -a 256 "$FAKE_HOME/Library/Application Support/ImportantApp/data.db" | awk '{print $1}')

echo "--- 1) Syntax check scripts ---"
python3 -m py_compile "$SCRIPTS/utils.py" "$SCRIPTS/storage_audit.py" "$SCRIPTS/safe_cleanup.py"
pass "python syntax"

echo "--- 2) Read-only audit ---"
python3 "$SCRIPTS/storage_audit.py" \
  --output "$AUDIT_PREFIX" \
  --min-size-mb 1 \
  --no-system-tmp > "$SANDBOX_ROOT/audit_stdout.txt"

test -f "$AUDIT_PREFIX.json" && pass "audit JSON written" || fail "audit JSON missing"
test -f "$AUDIT_PREFIX.md" && pass "audit MD written" || fail "audit MD missing"

python3 - <<'PY' "$AUDIT_PREFIX.json" "$FAKE_HOME"
import json, sys
from pathlib import Path
report = json.loads(Path(sys.argv[1]).read_text())
home = Path(sys.argv[2]).resolve()
findings = report["findings"]
paths = [f["path"] for f in findings]
print(f"  findings={len(findings)} total={report['summary']['total_human']}")

deny_markers = ["Documents", "Desktop", "Pictures", "Library/Mail", "Keychains", "Application Support"]
bad = []
for p in paths:
    rel = str(Path(p))
    for m in deny_markers:
        if f"/{m}/" in rel or rel.endswith(f"/{m}") or f"/{m}" in rel.split(str(home))[-1]:
            # more precise:
            pass
    try:
        r = Path(p).resolve().relative_to(home)
        s = str(r)
        for m in ["Documents", "Desktop", "Pictures", "Library/Mail", "Library/Keychains", "Library/Application Support"]:
            if s == m or s.startswith(m + "/"):
                bad.append(p)
    except Exception as e:
        bad.append(f"{p} ({e})")

if bad:
    print("  DENY LIST LEAK:", bad)
    sys.exit(1)
if not any("BigAppCache" in p for p in paths):
    print("  expected BigAppCache in findings")
    sys.exit(1)
if any("SmallCache" in p for p in paths):
    print("  SmallCache should be under min-size")
    sys.exit(1)
if report.get("home") != str(home):
    print("  home mismatch", report.get("home"), home)
    sys.exit(1)
if not report.get("sandbox"):
    print("  sandbox flag false")
    sys.exit(1)
print("  OK audit contents")
PY
pass "audit only lists safe, large fixtures"

echo "--- 3) Refuse forbidden path even if forced ---"
set +e
python3 "$SCRIPTS/safe_cleanup.py" \
  --audit-json "$AUDIT_PREFIX.json" \
  --approved-paths "$FAKE_HOME/Documents/SecretProject" \
  --mode trash \
  --dry-run false \
  --log-json "$SANDBOX_ROOT/refuse_docs.json" > "$SANDBOX_ROOT/refuse_docs.out" 2>&1
RC=$?
set -e
if grep -q "Refusing path" "$SANDBOX_ROOT/refuse_docs.out" || grep -q "FAIL" "$SANDBOX_ROOT/refuse_docs.out"; then
  pass "cleanup refused Documents"
else
  fail "cleanup did not refuse Documents (rc=$RC)"
  cat "$SANDBOX_ROOT/refuse_docs.out"
fi
test -f "$FAKE_HOME/Documents/SecretProject/thesis.txt" && pass "Documents still intact" || fail "Documents were deleted!"

echo "--- 4) Refuse path not in audit ---"
# Create a new cache not in audit
mkdir -p "$FAKE_HOME/Library/Caches/NotInAudit"
dd if=/dev/urandom of="$FAKE_HOME/Library/Caches/NotInAudit/x.bin" bs=1024 count=1500 status=none
set +e
python3 "$SCRIPTS/safe_cleanup.py" \
  --audit-json "$AUDIT_PREFIX.json" \
  --approved-paths "$FAKE_HOME/Library/Caches/NotInAudit" \
  --mode trash \
  --dry-run false > "$SANDBOX_ROOT/refuse_audit.out" 2>&1
set -e
if grep -qi "not present in audit\|Refusing" "$SANDBOX_ROOT/refuse_audit.out"; then
  pass "cleanup refused non-audit path"
else
  fail "should refuse path missing from audit"
  cat "$SANDBOX_ROOT/refuse_audit.out"
fi
test -d "$FAKE_HOME/Library/Caches/NotInAudit" && pass "NotInAudit still present" || fail "NotInAudit removed without audit"

echo "--- 5) Dry-run approved cache ---"
BIG="$FAKE_HOME/Library/Caches/BigAppCache"
python3 "$SCRIPTS/safe_cleanup.py" \
  --audit-json "$AUDIT_PREFIX.json" \
  --approved-paths "$BIG" \
  --mode trash \
  --dry-run true \
  --log-json "$SANDBOX_ROOT/dryrun.json" > "$SANDBOX_ROOT/dryrun.out"
test -d "$BIG" && pass "dry-run left cache in place" || fail "dry-run deleted cache"
grep -q "would_reclaim" "$SANDBOX_ROOT/dryrun.out" && pass "dry-run reported would_reclaim" || fail "dry-run summary missing"

echo "--- 6) Real trash of approved cache (sandbox Trash) ---"
python3 "$SCRIPTS/safe_cleanup.py" \
  --audit-json "$AUDIT_PREFIX.json" \
  --approved-paths "$BIG" \
  --mode trash \
  --dry-run false \
  --log-json "$SANDBOX_ROOT/cleanup.json" > "$SANDBOX_ROOT/cleanup.out"
if [[ ! -d "$BIG" ]]; then
  pass "BigAppCache removed from Caches"
else
  fail "BigAppCache still in Caches"
fi
if ls "$FAKE_HOME/.Trash"/BigAppCache* >/dev/null 2>&1; then
  pass "BigAppCache landed in sandbox .Trash"
else
  fail "BigAppCache not in .Trash"
fi

echo "--- 7) Forbidden data integrity ---"
DOC_HASH_AFTER=$(shasum -a 256 "$FAKE_HOME/Documents/SecretProject/thesis.txt" | awk '{print $1}')
DESK_HASH_AFTER=$(shasum -a 256 "$FAKE_HOME/Desktop/notes.txt" | awk '{print $1}')
MAIL_HASH_AFTER=$(shasum -a 256 "$FAKE_HOME/Library/Mail/mailbox.db" | awk '{print $1}')
KEY_HASH_AFTER=$(shasum -a 256 "$FAKE_HOME/Library/Keychains/login.keychain-db" | awk '{print $1}')
APP_HASH_AFTER=$(shasum -a 256 "$FAKE_HOME/Library/Application Support/ImportantApp/data.db" | awk '{print $1}')

[[ "$DOC_HASH_BEFORE" == "$DOC_HASH_AFTER" ]] && pass "Documents hash unchanged" || fail "Documents mutated"
[[ "$DESK_HASH_BEFORE" == "$DESK_HASH_AFTER" ]] && pass "Desktop hash unchanged" || fail "Desktop mutated"
[[ "$MAIL_HASH_BEFORE" == "$MAIL_HASH_AFTER" ]] && pass "Mail hash unchanged" || fail "Mail mutated"
[[ "$KEY_HASH_BEFORE" == "$KEY_HASH_AFTER" ]] && pass "Keychains hash unchanged" || fail "Keychains mutated"
[[ "$APP_HASH_BEFORE" == "$APP_HASH_AFTER" ]] && pass "Application Support hash unchanged" || fail "Application Support mutated"

echo "--- 8) Simulated agent workflow ---"
# Agent: load skill, audit, present findings, get approval, dry-run, execute
python3 - <<'PY' "$SCRIPTS" "$AUDIT_PREFIX.json" "$FAKE_HOME"
"""Minimal agent loop simulation (not LLM) — exercises the same calls an agent would make."""
import json, subprocess, sys
from pathlib import Path

scripts, audit_json, home = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
report = json.loads(audit_json.read_text())
# Agent selects only low-risk log path still present
candidates = [f for f in report["findings"] if f["risk"] == "low" and "Logs" in f["path"] and Path(f["path"]).exists()]
assert candidates, "no log candidates for agent sim"
target = candidates[0]["path"]
print(f"  agent approved: {target}")

# dry-run
r = subprocess.run(
    [sys.executable, str(scripts / "safe_cleanup.py"),
     "--audit-json", str(audit_json),
     "--approved-paths", target,
     "--mode", "trash", "--dry-run", "true"],
    capture_output=True, text=True,
)
assert r.returncode == 0, r.stderr + r.stdout
assert Path(target).exists(), "dry-run must not delete"
# execute
r = subprocess.run(
    [sys.executable, str(scripts / "safe_cleanup.py"),
     "--audit-json", str(audit_json),
     "--approved-paths", target,
     "--mode", "trash", "--dry-run", "false"],
    capture_output=True, text=True,
)
assert r.returncode == 0, r.stderr + r.stdout
assert not Path(target).exists(), "execute should trash log"
assert any(Path(home / ".Trash").glob("app.log*")), "log should be in trash"
print("  agent workflow OK")
PY
pass "simulated agent audit→approve→dry-run→trash"

echo
echo "=== RESULTS: $PASS passed, $FAIL failed ==="
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
echo "Sandbox only used: $SANDBOX_ROOT (deleted on exit)"
echo "Real HOME was never set as target. Real user files were not scanned."
exit 0
