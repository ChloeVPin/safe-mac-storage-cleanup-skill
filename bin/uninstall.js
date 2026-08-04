#!/usr/bin/env node
/**
 * Uninstaller for cleanme
 * Removes the skill from common AI agent skill directories.
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const SKILL_NAME = 'cleanme';

const COMMON_SKILL_DIRS = [
  path.join(os.homedir(), '.codex', 'skills', SKILL_NAME),
  path.join(os.homedir(), '.agents', 'skills', SKILL_NAME),
  path.join(os.homedir(), '.claude', 'skills', SKILL_NAME),
  path.join(os.homedir(), '.config', 'opencode', 'skills', SKILL_NAME),
  path.join(os.homedir(), '.cursor', 'skills', SKILL_NAME),
  path.join(os.homedir(), 'Library', 'Application Support', 'Codex', 'skills', SKILL_NAME),
];

function log(msg) {
  console.log(`[cleanme] ${msg}`);
}

function removeRecursive(dir) {
  if (!fs.existsSync(dir)) {
    return false;
  }
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        removeRecursive(fullPath);
      } else {
        fs.unlinkSync(fullPath);
      }
    }
    fs.rmdirSync(dir);
    return true;
  } catch (e) {
    log(`Failed to remove ${dir}: ${e.message}`);
    return false;
  }
}

function main() {
  const args = process.argv.slice(2);
  const isHelp = args.includes('--help') || args.includes('-h');
  const targetArg = args.find(a => !a.startsWith('--'));

  if (isHelp) {
    console.log(`
Usage: npx cleanme --uninstall [options]

Options:
  --help            Show this help
  [target]          Optional specific target directory to remove

Removes the cleanme skill from common AI agent skill directories.
`);
    process.exit(0);
  }

  log('Starting cleanme uninstall...');

  let removedCount = 0;

  if (targetArg) {
    if (removeRecursive(targetArg)) {
      log(`Removed: ${targetArg}`);
      removedCount++;
    } else {
      log(`Target not found or could not be removed: ${targetArg}`);
    }
  } else {
    for (const target of COMMON_SKILL_DIRS) {
      if (removeRecursive(target)) {
        log(`Removed: ${target}`);
        removedCount++;
      }
    }
  }

  if (removedCount === 0) {
    log('No cleanme installations found.');
  } else {
    log(`Removed ${removedCount} installation(s).`);
  }

  log('To reinstall, run npx cleanme or ./install.sh');
}

main();
