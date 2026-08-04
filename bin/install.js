#!/usr/bin/env node
/**
 * Smart installer for cleanme
 * Supports multiple agent skill directories (Codex, Claude Code, Cursor, OpenCode, generic ~/.agents/skills, ~/.codex/skills, etc.)
 * Zero dependencies. Works on macOS (primary) and warns elsewhere.
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const SKILL_NAME = 'cleanme';
const SKILL_SOURCE = path.join(__dirname, '..', 'skill');

const COMMON_SKILL_DIRS = [
  path.join(os.homedir(), '.codex', 'skills', SKILL_NAME),
  path.join(os.homedir(), '.agents', 'skills', SKILL_NAME),
  path.join(os.homedir(), '.claude', 'skills', SKILL_NAME),
  path.join(os.homedir(), '.cursor', 'skills', SKILL_NAME),
  path.join(os.homedir(), '.config', 'opencode', 'skills', SKILL_NAME),
  path.join(os.homedir(), 'Library', 'Application Support', 'Codex', 'skills', SKILL_NAME), // fallback
];

function log(msg) {
  console.log(`[cleanme] ${msg}`);
}

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
    return true;
  }
  return false;
}

function copyRecursive(src, dest) {
  if (!fs.existsSync(src)) {
    throw new Error(`Source missing: ${src}`);
  }
  ensureDir(dest);

  const entries = fs.readdirSync(src, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);

    if (entry.isDirectory()) {
      copyRecursive(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

function installTo(dir, label) {
  try {
    const created = ensureDir(dir);
    copyRecursive(SKILL_SOURCE, dir);
    log(`Installed to ${label}: ${dir}`);
    return true;
  } catch (e) {
    log(`Failed to install to ${label} (${dir}): ${e.message}`);
    return false;
  }
}

function main() {
  const args = process.argv.slice(2);
  const isPostinstall = args.includes('--postinstall');
  const isHelp = args.includes('--help') || args.includes('-h');
  const isUninstall = args.includes('--uninstall');

  if (isHelp) {
    console.log(`
Usage: npx cleanme --help

Options:
  --postinstall     Run as postinstall hook (non-interactive where possible)
  --help            Show this help
  --uninstall       Remove cleanme from agent skill directories

Installs the cleanme skill into common AI agent skill directories.
After install, tell your agent to use the "cleanme" skill.
 `);
    process.exit(0);
  }

  log('Starting cleanme installation...');

  if (os.platform() !== 'darwin') {
    log('WARNING: This skill is optimized for macOS. Some paths and Trash integration are macOS-specific. It may still work partially on other platforms.');
  }

  let installedCount = 0;

  for (const target of COMMON_SKILL_DIRS) {
    const label = path.basename(path.dirname(target)) + '/' + SKILL_NAME;
    if (installTo(target, label)) {
      installedCount++;
    }
  }

  if (installedCount === 0) {
    log('No standard locations succeeded. Manual install recommended:');
    log(`  mkdir -p ~/.agents/skills/${SKILL_NAME} && cp -r skill/* ~/.agents/skills/${SKILL_NAME}/`);
    log('Then tell your agent the skill is available.');
   } else {
    log(`Successfully installed to ${installedCount} location(s).`);
    log('');
    log('Next steps:');
    log('1. Restart/reload your AI agent (Codex, Claude Code, Cursor, OpenCode, etc.) if it caches skills.');
    log('2. In a new chat: "Load the cleanme skill" or simply "My disk is almost full - run cleanme".');
    log('3. The agent will guide you through a read-only audit first. Nothing is deleted without your explicit approval.');
    log('');
    log('Safety: Strict whitelists + path validation + Trash-by-default. See README and skill/SKILL.md for details.');
  }

  // Optional: show where SKILL.md ended up
  const examplePath = COMMON_SKILL_DIRS[0];
  if (fs.existsSync(path.join(examplePath, 'SKILL.md'))) {
    log(`Primary SKILL.md location example: ${path.join(examplePath, 'SKILL.md')}`);
  }
}

if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.includes('--uninstall')) {
    // Delegate to uninstall script
    const uninstallPath = path.join(__dirname, 'uninstall.js');
    require(uninstallPath);
  } else {
    main();
  }
}