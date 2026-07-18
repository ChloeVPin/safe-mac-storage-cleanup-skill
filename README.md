# safe-mac-storage-cleanup-skill

**A production-ready, safety-first macOS storage cleanup skill for AI agents** (Codex, Claude Code, Cursor, and any Agent Skills compatible tool).

Unlike engagement-bait stubs, this is a fully implemented, portable, and rigorously safe tool. It **never** deletes, moves, or modifies anything without your explicit approval in the chat. It uses strict whitelists, path validation gates in helper scripts, prefers moving to Trash over permanent deletion, and is designed for conversational, step-by-step interaction with your agent of choice.

## Why This Exists (and Why the Original Was Engagement Bait)

The original `codex-mac-storage-cleanup` had:
- Hard-coded author paths (e.g. `/Users/francescomistero/...`)
- Incomplete or minimally functional helpers
- Vague safety claims without enforceable guardrails in code
- Single-commit repo with no tests, docs, or multi-agent support
- Risk of hallucinated dangerous `rm` commands by the agent

This version fixes all of that and adds real usability.

## Safety Guarantees (Non-Negotiable)

- **Read-only audit first, always.** No modifications until you approve specific items.
- **Strict whitelist only.** Only scans and operates on known safe locations (user caches, logs, package caches, dev artifacts, Trash, temps). Never touches system roots, user documents, photos libraries, keychains, mail, iCloud, source code repos (unless explicitly whitelisted by you), or anything in `~/Documents`, `~/Desktop`, `~/Pictures`, `~/Music`, `~/Movies`, `~/Public`, or `~/Downloads` (except as optional high-caution suggestions).
- **Path validation gate.** The cleanup script refuses any path not matching the safe whitelist or not present in a recent audit report.
- **Trash by default.** Uses Finder to move items to Trash (recoverable). Permanent `rm` only for pure caches/logs with extra confirmation and `--permanent` flag.
- **No sudo by default.** Avoids privilege escalation unless you explicitly approve and justify.
- **Human + agent reviewable.** Generates both beautiful Markdown reports and machine-parseable JSON.
- **Logged actions.** All proposed and executed cleanups are logged.

**You are always in control.** Treat broad phrases like "just clean it" as approval **only** for already-listed low-risk items. The agent will ask for confirmation on anything else.

## Installation (Works with Any Compatible Agent)

### Option 1: npx (Recommended for Codex and quick start)
```bash
npx safe-mac-storage-cleanup-skill@latest
```
This installs the skill to common locations and detects your setup.

### Option 2: Manual / Multi-Agent (Best for Claude Code, Cursor, etc.)
```bash
git clone https://github.com/ChloeVPin/safe-mac-storage-cleanup-skill.git
cd safe-mac-storage-cleanup-skill

# For Codex / agents using ~/.agents/skills or ~/.codex/skills
mkdir -p ~/.agents/skills/mac-storage-cleanup
cp -r skill/* ~/.agents/skills/mac-storage-cleanup/

# For Claude Code
mkdir -p ~/.claude/skills/mac-storage-cleanup
cp -r skill/* ~/.claude/skills/mac-storage-cleanup/

# For Cursor or others (check your agent's docs for the skills dir)
# Usually similar copy of the `skill/` folder contents
```

The `skill/` folder is the portable standard unit (contains `SKILL.md` + helpers).

### Option 3: Automated Bash Installer
```bash
curl -fsSL https://raw.githubusercontent.com/ChloeVPin/safe-mac-storage-cleanup-skill/main/install.sh | bash
```
(Or run `./install.sh` after clone — it supports prompting for target agent(s).)

After install, tell your agent: **"Use the mac-storage-cleanup skill"** or just say **"My disk is full, run storage cleanup"** — it should auto-discover and load `SKILL.md`.

## Usage (Fully Interactive)

1. **Trigger**: In chat with your agent:  
   `"My Mac is low on storage. Run the safe mac storage cleanup."`  
   or `"Scan for wasted space and show me what I can safely delete."`

2. **Agent loads the skill** → runs `python3 .../scripts/storage_audit.py --output /tmp/mac-audit` (or equivalent).

3. **You get**:
   - A ranked Markdown report (top wasters by category + risk)
   - Parseable JSON for the agent to use precisely
   - Clear recommendations (low-risk first)

4. **Review & Approve**: Reply with specifics, e.g.:
   - "Trash the top 5 largest caches and all logs"
   - "Delete the Xcode DerivedData and old simulators (permanent ok)"
   - "Show me details on the node_modules ones first"
   - "Only do low-risk items under 5GB total"

5. **Agent calls safe_cleanup.py** with exact approved paths from the audit JSON. Script validates everything, shows dry-run summary, then executes only after your final "yes, proceed".

6. **Post-cleanup**: Agent shows `df -h /` before/after delta and any follow-up advice (e.g. "restart Xcode", "empty Trash in Finder if you want permanent free space").

You can run partial scans: `--category caches logs developer` etc.

## What's Included

- `SKILL.md`: Complete instructions + safety rules the agent follows.
- `scripts/storage_audit.py`: Robust, zero-dep, portable read-only scanner with JSON + MD output. Strict whitelists + excludes.
- `scripts/safe_cleanup.py`: The enforcement layer. Validates paths, supports dry-run / trash / permanent (guarded), uses native macOS Trash.
- `scripts/utils.py`: Shared helpers (size formatting, path safety checks, logging).
- `references/safety.md`: Deep reference for the agent (and curious humans).
- Per-agent notes in `agents/`.
- Example reports in `docs/`.

## Supported Cleanup Categories (Safe by Design)

**Low Risk (usually safe to trash/delete after review)**:
- User & app caches (`~/Library/Caches/*`)
- Logs (`~/Library/Logs/*`)
- Package manager caches (npm, pnpm, yarn, pip, cargo, go, brew if applicable)
- `/tmp` and `/private/tmp` (stale)
- `~/.Trash` (empty it)
- Old Xcode derived data & unavailable simulators

**Medium Risk (review carefully)**:
- Large `node_modules` folders (may be active projects)
- Docker build cache / images / volumes (if Docker running)
- Old downloads or archives in `~/Downloads` (listed separately, high caution)
- Project build artifacts (if you know they're stale)

**Never Touched**:
- Anything in `~/Documents`, `~/Desktop`, `~/Pictures`, `~/Music`, `~/Movies`, `~/Public`
- Photos libraries, iCloud Drive/Mobile Documents, Mail, Keychains, Application Support databases with user data
- System `/`, `/System`, `/Library` (except user-writable caches where explicitly safe)
- Active source code repositories or important dev projects (flagged for review only)
- Anything requiring sudo unless you explicitly approve

## Limitations & Recommendations

- Not a duplicate finder or photo cleaner (use dedicated tools for that).
- Best on user-initiated interactive sessions. Not for fully autonomous cron jobs (though you can extend it).
- Large `~/Library/Caches` can be regenerated by apps; some apps may feel slower temporarily until they rebuild cache.
- Always have a recent Time Machine or cloud backup before any cleanup session.
- Test on a non-critical Mac first if paranoid.

## Development & Contributing

This is meant to be the gold standard for safe agent-driven macOS maintenance skills. PRs welcome for:
- Additional safe categories (with justification + test paths)
- Better size calculation performance
- Integration with `brew cleanup`, `docker system prune`, `xcrun simctl`, etc. (guarded)
- Windows/Linux analogs (future)

Run `python3 -m pytest` (if tests added) or manually test the scripts on your Mac.

## License

MIT — use freely, improve it, share the safe way to clean Macs with agents.

---

**Created as a proper, usable replacement for engagement-bait versions.**  
If your disk is full right now, just paste this repo URL to your agent and say "install and run the safe version".

Star it if it actually helped you reclaim space safely. 

## File Tree (High Level)

See the full organized structure in the repo. The important part is `skill/SKILL.md` + the three Python scripts in `skill/scripts/`. Everything else supports distribution and multi-agent use.