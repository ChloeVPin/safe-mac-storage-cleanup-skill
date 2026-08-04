# CLEANME Gap Analysis Report

## Executive Summary

This report analyzes `safe-mac-storage-cleanup-skill` (to be renamed **CLEANME**) across safety, documentation, UX, script robustness, testing, installation, agent compatibility, and error handling. The skill has a solid safety-first foundation with whitelist enforcement and Trash-by-default behavior, but contains critical gaps in race condition handling, symlink safety, testing coverage, and documentation completeness.

**Recommendation**: Address P0 and P1 items before public release. The skill is usable today for technical users but requires hardening before broad agent deployment.

---

## Architecture Overview

The skill consists of three Python scripts orchestrated by an agent:

1. `storage_audit.py` - Read-only scanner that walks whitelisted directories, computes sizes, and emits JSON + Markdown reports.
2. `safe_cleanup.py` - Validates approved paths against the audit JSON and whitelist, then moves files to Trash or permanently deletes them.
3. `utils.py` - Shared helpers for path safety (`is_whitelisted`, `deny_reasons`, `assert_safe_for_cleanup`), size calculation, Trash operations, and JSON I/O.

Safety is enforced through:
- A hard deny list for protected directories (Documents, Desktop, Mail, Keychains, etc.)
- A whitelist of safe prefixes under `$HOME` plus absolute system temp paths
- Audit-gated cleanup: paths must appear in a prior audit JSON
- Default Trash mode with optional permanent delete

---

## Gap Analysis

### Safety

#### CRITICAL: TOCTOU Race Condition Between Audit and Cleanup
**Location**: `safe_cleanup.py:71-88`, `storage_audit.py:59-88`
**Description**: The audit records paths and sizes at a point in time. Between audit and cleanup, files can be modified, replaced with symlinks, or swapped for different content. `safe_cleanup.py` re-validates whitelist and existence but does not verify the file is the same inode or that its content/size matches the audit. A race condition could allow a protected file to be replaced with a cache file at the same path after audit, or a symlink to a protected directory to be approved.
**Proposed fix**: In `safe_cleanup.py`, after `assert_safe_for_cleanup`, verify the path is not a symlink (`path.is_symlink()` -> refuse). Optionally, record inode numbers during audit and verify they match during cleanup. Reject any path that is a symlink, even if its target is whitelisted.

#### HIGH: Symlink Following in Cleanup
**Location**: `utils.py:252-278` (`move_to_trash`), `utils.py:281-286` (`permanent_delete`)
**Description**: `move_to_trash` calls `path.resolve()` which follows symlinks. If a user approves a path that is a symlink pointing outside the whitelist (e.g., a symlink in `~/Library/Caches` pointing to `~/Documents`), the Trash operation will move the target document, not the symlink. The audit skips symlinks entirely, so this creates an inconsistency where the audit sees one thing and cleanup acts on another.
**Proposed fix**: In `assert_safe_for_cleanup`, add `if path.is_symlink(): raise ValueError("Refusing symlink")`. In `move_to_trash` and `permanent_delete`, refuse symlinks before resolving.

#### HIGH: Stale or Tampered Audit JSON
**Location**: `safe_cleanup.py:35-39`, `safe_cleanup.py:220-228`
**Description**: `safe_cleanup.py` trusts the audit JSON structure but does not validate its freshness or provenance. An old audit could approve paths that are no longer safe (e.g., a new protected directory created at the same path after the audit). There is no timestamp check or nonce.
**Proposed fix**: Add a `generated_at` timestamp check in `safe_cleanup.py` and reject audits older than a configurable threshold (e.g., 24 hours). Alternatively, require the agent to pass a nonce or session ID.

#### HIGH: Permanent Delete Has No Secondary Confirmation
**Location**: `safe_cleanup.py:149-150`, `utils.py:281-286`
**Description**: `--mode permanent --dry-run false` immediately calls `shutil.rmtree` or `unlink` with no interactive confirmation, no recycle bin, and no undo. The CLI warning is insufficient for irreversible destruction.
**Proposed fix**: Require an explicit `--confirm-permanent` flag for permanent mode, or implement a two-phase confirmation where the user must approve the specific list of paths twice. Consider adding a "soft permanent" mode that moves to a quarantine directory before deletion.

#### MEDIUM: `/var/folders` Whitelist Is Overly Broad
**Location**: `utils.py:99-103`, `utils.py:196-200`
**Description**: The whitelist includes `/var/folders` with a check for `/T/` or `/C/` in the path. This matches a huge swath of macOS temporary and cache data, including user-specific temp files that may contain sensitive data. While limited to temp paths, this is broader than necessary and could clean data the user did not expect to lose.
**Proposed fix**: Narrow the `/var/folders` whitelist to specific known-safe subdirectories (e.g., `/var/folders/*/T/*/Library/Caches/*`) or remove it entirely and rely on `~/Library/Caches` and `/tmp` coverage.

#### MEDIUM: No Verification After Trash Operation
**Location**: `utils.py:252-278`
**Description**: After `osascript` or `shutil.move` to Trash, the script does not verify the file was actually moved. If Finder returns success but the file remains (e.g., due to a bug or permission issue), the script reports success and the user believes the file is gone.
**Proposed fix**: After the Trash operation, verify `not path.exists()`. If the file still exists, raise an error and report failure.

#### MEDIUM: Network Volume and External Drive Handling
**Location**: `utils.py:45-70` (`dir_size_bytes`), `storage_audit.py:59-88`
**Description**: `os.walk` has no timeout and no exclusion for non-local filesystems. Scanning network volumes (AFP, SMB, NFS) or external drives could hang indefinitely or produce misleadingly large sizes.
**Proposed fix**: Add a filesystem type check (e.g., using `stat -f %Sd` or `df -T`) to skip non-local volumes. Add a timeout or max-depth enforcement for `dir_size_bytes`.

### Documentation

#### HIGH: README Is Incomplete and Outdated
**Location**: `README.md`
**Description**: The README lacks a troubleshooting section, does not explain what to do when the audit finds nothing, omits sandbox usage instructions for end users, and still references the old repo name `safe-mac-storage-cleanup-skill` in the anatomy section. It also does not document the new `cleanme` name.
**Proposed fix**: Add troubleshooting (missing python3, permission denied, no findings), update all references to `cleanme`, add a sandbox testing section for users, and document the expected agent workflow in more detail.

#### HIGH: SKILL.md Lacks Agent Guidance
**Location**: `skill/SKILL.md`
**Description**: SKILL.md tells the agent what to do but not how to present it. It does not specify:
- How to format the audit report for user readability
- How to handle ambiguous user approvals like "clean everything"
- What to do if cleanup fails partway through
- How to explain dry-run vs real execution to non-technical users
- How to handle the case where the user approves zero paths
**Proposed fix**: Add an "Agent Presentation Guide" section with example prompts, example report formatting, and decision trees for common user responses.

#### HIGH: `docs/example-report.md` Is Empty
**Location**: `docs/example-report.md`
**Description**: The file contains only `[full example]`. Agents and users have no reference for what the audit output looks like.
**Proposed fix**: Populate with a realistic example audit report showing the Markdown table, JSON structure, and summary statistics.

#### MEDIUM: No Troubleshooting Documentation
**Location**: Missing file or section
**Description**: There is no guide for common failure modes: python3 missing, permission denied, audit produces no findings, cleanup fails for specific paths, Trash is full, etc.
**Proposed fix**: Add a `docs/troubleshooting.md` or a troubleshooting section to README.md.

### User Experience

#### MEDIUM: Dry-Run Output Is Insufficient for User Verification
**Location**: `safe_cleanup.py:157-167`
**Description**: The dry-run prints only a summary line (`would_reclaim=...`) and a compact list. It does not show a detailed table with paths, sizes, and actions, making it hard for users to verify exactly what will be deleted before confirming.
**Proposed fix**: Print a formatted table in dry-run mode showing path, size, risk, and action for each approved item. Match the audit report format for consistency.

#### MEDIUM: No Interactive Confirmation in Scripts
**Location**: `safe_cleanup.py`
**Description**: The scripts rely entirely on the agent to handle user interaction. There is no built-in confirmation prompt. If the agent fails to confirm with the user, cleanup proceeds automatically based on CLI args.
**Proposed fix**: Add an optional `--interactive` flag that prompts for confirmation before each deletion. The agent can use this as a safety net.

#### MEDIUM: No Undo or Recovery Guidance
**Location**: `README.md`, `skill/SKILL.md`
**Description**: While Trash is the default, there is no guidance on how to restore files if something goes wrong, or how to verify Trash contents before emptying.
**Proposed fix**: Add a "Recovery" section explaining how to restore from Trash via Finder and how to inspect Trash contents.

### Script Robustness

#### HIGH: No Permission Error Handling During Cleanup
**Location**: `utils.py:252-286`
**Description**: `move_to_trash` and `permanent_delete` do not catch `PermissionError` or `OSError`. If a file is owned by root, has immutable flags, or is locked, the script crashes with an unhandled exception.
**Proposed fix**: Wrap Trash and delete operations in try/except blocks. Catch `PermissionError` and `OSError`, report the failure cleanly, and continue with remaining paths.

#### HIGH: No Validation That Approved Paths Still Match Audit
**Location**: `safe_cleanup.py:70-88`
**Description**: `safe_cleanup.py` checks that approved paths exist and are whitelisted, but does not verify they still match the audit findings (e.g., same size, same category). If a file was replaced between audit and cleanup, the cleanup proceeds with the new file without warning.
**Proposed fix**: Compare the current size of the path against the size recorded in the audit JSON. If they differ significantly (e.g., >10% or absolute threshold), warn the user or refuse to proceed.

#### MEDIUM: `storage_audit.py` Has Confusing Whitelist Logic
**Location**: `storage_audit.py:114-126`
**Description**: The whitelist check in the audit loop is redundant and confusing. It checks `is_whitelisted` multiple times with overlapping conditions, making it hard to reason about which paths are included or excluded.
**Proposed fix**: Simplify to a single clear check: if the root is whitelisted or is a known safe target, scan it. Remove the redundant nested conditions.

#### MEDIUM: No Timeout for Directory Walking
**Location**: `utils.py:45-70`
**Description**: `os.walk` can hang on network volumes, circular symlinks (though `followlinks=False` helps), or extremely deep directory trees. There is no timeout or circuit breaker.
**Proposed fix**: Add a configurable timeout or max-walk-time parameter. Consider using `os.scandir` with explicit depth tracking for better control.

#### MEDIUM: Silent Permission Errors During Audit
**Location**: `storage_audit.py:73-87`, `utils.py:56-69`
**Description**: Permission errors during `os.walk` and `stat` are silently caught and ignored. This means the audit may under-report reclaimable space without telling the user.
**Proposed fix**: Log permission errors at INFO level (not just WARNING) and include a count of skipped items in the audit report summary.

### Testing

#### HIGH: No Tests for Paths with Spaces or Unicode
**Location**: `tests/run_sandbox.sh`
**Description**: The sandbox only creates paths with simple ASCII names and no spaces. Real macOS paths frequently contain spaces (e.g., `Library/Application Support`, `Xcode DerivedData` with spaces). Unicode paths (e.g., user names with accents) are also untested.
**Proposed fix**: Add sandbox fixtures with spaces and Unicode characters. Test audit and cleanup on these paths.

#### HIGH: No Tests for Symlinks
**Location**: `tests/run_sandbox.sh`
**Description**: The sandbox does not create symlinks. There are no tests verifying that symlinks are skipped during audit or refused during cleanup.
**Proposed fix**: Add symlink fixtures: a symlink inside a whitelisted directory pointing to a denied directory, and a symlink at a whitelisted path. Verify audit skips them and cleanup refuses them.

#### HIGH: No Tests for Permission Denied Scenarios
**Location**: `tests/run_sandbox.sh`
**Description**: The sandbox does not create files with restricted permissions (e.g., `chmod 000`). There is no test for how the scripts handle `PermissionError` during audit or cleanup.
**Proposed fix**: Add fixtures with unreadable directories and unwritable files. Verify the scripts handle errors gracefully and report them clearly.

#### MEDIUM: No Tests for Permanent Delete Mode
**Location**: `tests/run_sandbox.sh`
**Description**: The sandbox only tests `--mode trash`. `permanent_delete` is never exercised, so bugs in that code path are undetected.
**Proposed fix**: Add a test case for `--mode permanent --dry-run false` in the sandbox, verifying files are actually removed (not moved to Trash).

#### MEDIUM: No Tests for Stale Audit or Modified Files
**Location**: `tests/run_sandbox.sh`
**Description**: There is no test for using an old audit JSON, or for files that change size between audit and cleanup.
**Proposed fix**: Add a test that modifies a file after audit and verifies cleanup either warns or refuses based on the size mismatch.

#### MEDIUM: No Tests for Empty Results
**Location**: `tests/run_sandbox.sh`
**Description**: There is no explicit test for the case where the audit finds no items above the size threshold, or where the user approves zero paths.
**Proposed fix**: Add test cases for empty findings and zero approved paths, verifying the scripts exit cleanly with appropriate messages.

#### LOW: No Integration Test for Full Agent Workflow
**Location**: `tests/run_sandbox.sh`
**Description**: The sandbox has a simulated agent workflow (test 8), but it is minimal and does not cover error recovery, partial failures, or user interaction patterns.
**Proposed fix**: Expand the agent simulation to cover: partial approval, cleanup failure mid-way, user says "no" after dry-run, and recovery from Trash.

### Installation

#### HIGH: Package Name Does Not Match New Brand
**Location**: `package.json:2`, `bin/install.js:13`, `install.sh:7`
**Description**: The npm package name, binary name, and install script all use `safe-mac-storage-cleanup-skill` and `mac-storage-cleanup`. The desired new name is `cleanme` or `CLEANME`.
**Proposed fix**: Rename npm package to `cleanme`, binary to `cleanme`, skill directory to `cleanme`, and update all references in README, SKILL.md, install scripts, and package.json.

#### MEDIUM: No Handling of Existing Installs
**Location**: `install.sh:23-33`, `bin/install.js:55-65`
**Description**: Both installers blindly copy files over existing installations without backup, warning, or version check. User modifications to the skill would be silently overwritten.
**Proposed fix**: Before copying, check if the target exists. If it does, back it up to a timestamped directory or prompt the user. Add a `--force` flag for overwrites.

#### MEDIUM: No Dependency Check
**Location**: `install.sh`, `bin/install.js`
**Description**: The installers do not verify that `python3` is available on the target system. The skill will fail at runtime with a cryptic error.
**Proposed fix**: Add a post-install check that verifies `python3` is in PATH and prints a warning if missing.

#### LOW: No Uninstall Mechanism
**Location**: Missing
**Description**: There is no uninstall script. Users must manually delete skill directories.
**Proposed fix**: Add an `uninstall.sh` and `bin/uninstall.js` that remove the installed skill directories.

### Agent Compatibility

#### MEDIUM: No OpenCode Support
**Location**: `README.md:61-68`, `bin/install.js:16-22`
**Description**: The README and installer mention Codex, Claude Code, and Cursor, but not OpenCode. OpenCode uses `~/.config/opencode/skills/` as its skill directory.
**Proposed fix**: Add OpenCode to the default install targets in `install.sh` and `bin/install.js`. Update README with OpenCode instructions.

#### MEDIUM: SKILL.md Does Not Specify Agent Loading Convention
**Location**: `skill/SKILL.md`
**Description**: SKILL.md does not explain how different agents load skills (e.g., OpenCode reads `SKILL.md` from the skills directory, Claude Code may need explicit loading). The agent may not know when or how to activate this skill.
**Proposed fix**: Add a section to SKILL.md explaining activation triggers and how the agent should recognize the skill is available.

### Error Handling

#### HIGH: No Check for Missing python3
**Location**: `storage_audit.py`, `safe_cleanup.py`
**Description**: If `python3` is not installed or not in PATH, the scripts fail with `env: python3: No such file or directory`. There is no graceful error message.
**Proposed fix**: Add a shebang check at the top of each script or a wrapper that detects missing python3 and prints a user-friendly message.

#### MEDIUM: Unclear Error Messages for End Users
**Location**: `safe_cleanup.py:146-147`, `utils.py:213-228`
**Description**: Error messages like "Refusing path (not on whitelist)" are technical. The agent must translate them for users. There is no user-facing error documentation.
**Proposed fix**: Add a `--human-errors` flag or error code mapping that produces user-friendly messages. Document common errors in the troubleshooting guide.

#### MEDIUM: No Handling for Zero Approved Paths
**Location**: `safe_cleanup.py:145-147`
**Description**: If the user approves zero paths, the script logs an error and returns exit code 2. The agent may not handle this gracefully.
**Proposed fix**: Return a clear message explaining that no paths were approved and the cleanup was skipped. The agent should treat this as a normal "user declined" outcome, not a failure.

---

## Prioritized Roadmap

### P0: Must Fix Before Any User Runs This

1. **Fix TOCTOU race condition** - Add symlink rejection and inode verification in `safe_cleanup.py`
2. **Fix symlink following in cleanup** - Refuse symlinks in `assert_safe_for_cleanup` and `move_to_trash`
3. **Add python3 presence check** - Graceful error if python3 is missing
4. **Rename package to cleanme** - Update package.json, install scripts, README, SKILL.md
5. **Add permission error handling in cleanup** - Catch and report PermissionError in `move_to_trash` and `permanent_delete`

### P1: Fix in Next Release

6. **Add audit JSON freshness validation** - Reject audits older than 24 hours
7. **Add size mismatch detection** - Warn or refuse if file size changed between audit and cleanup
8. **Add secondary confirmation for permanent delete** - Require explicit `--confirm-permanent` flag
9. **Verify Trash operation success** - Check `not path.exists()` after moving to Trash
10. **Populate `docs/example-report.md`** - Add realistic example report
11. **Add OpenCode to install targets** - Update install.sh and bin/install.js
12. **Add tests for paths with spaces and Unicode** - Expand sandbox fixtures
13. **Add tests for symlinks** - Verify symlink skipping and refusal
14. **Add tests for permission denied** - Test error handling paths
15. **Improve dry-run output** - Show detailed table of what would be deleted

### P2: Nice to Have

16. **Simplify whitelist logic in storage_audit.py** - Clean up redundant checks
17. **Add timeout for dir_size_bytes** - Prevent hangs on network volumes
18. **Add filesystem type exclusion** - Skip non-local volumes
19. **Add uninstall scripts** - uninstall.sh and bin/uninstall.js
20. **Add troubleshooting documentation** - README section or separate doc
21. **Add agent presentation guide to SKILL.md** - Example prompts and decision trees
22. **Add tests for permanent delete mode** - Exercise the permanent code path
23. **Add tests for stale audit and modified files** - Verify freshness and size checks
24. **Add interactive confirmation flag** - `--interactive` for built-in prompts
25. **Add recovery guidance** - How to restore from Trash

### P3: Future Enhancement

26. **Narrow `/var/folders` whitelist** - Reduce scope to specific safe subdirectories
27. **Add audit JSON signing or nonce** - Prevent tampering
28. **Add progress indication for large cleanups** - Show per-file progress
29. **Add soft permanent delete mode** - Quarantine before deletion
30. **Add integration tests for full agent workflow** - Cover error recovery and partial failures
31. **Add support for additional package managers** - Expand SCAN_TARGETS and whitelist
32. **Add configurable whitelist** - Allow users to extend safe prefixes via config file

---

## Rename Recommendations

The skill should be renamed from `safe-mac-storage-cleanup-skill` to **CLEANME** (or `cleanme` for package/binary names).

**Files requiring rename:**
- `package.json`: `"name": "cleanme"`, `"bin": { "cleanme": "bin/install.js" }`
- `bin/install.js`: `SKILL_NAME = 'cleanme'`, log prefix `[cleanme]`
- `install.sh`: `SKILL_NAME="cleanme"`
- `skill/SKILL.md`: `name: cleanme`
- `README.md`: Title, badges, all references
- `.gitignore`: Update audit file patterns to `cleanme-audit-*`

**Directory renames:**
- Skill install directories: `~/.agents/skills/cleanme`, `~/.claude/skills/cleanme`, `~/.codex/skills/cleanme`, `~/.config/opencode/skills/cleanme`

**Naming consistency:**
- Use `cleanme` for npm package, binary, and skill directory
- Use `CLEANME` for display/title purposes in documentation
- Update all internal references, comments, and log messages

---

## What Is Well Designed

- The whitelist/deny list architecture is sound and easy to audit
- The audit-gated cleanup pattern (JSON allowlist) is a strong safety mechanism
- The sandbox test suite is a good foundation and correctly isolates test state
- Trash-by-default with optional permanent delete is the right default for user safety
- The skill correctly avoids `rm -rf` and sudo escalation
- The Markdown + JSON report format is practical for agent consumption
