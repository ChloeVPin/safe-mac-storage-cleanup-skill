# cleanme Audit Example

This document shows a realistic example of the Markdown report produced by `storage_audit.py`.

## Sample Output

```markdown
# cleanme Audit (read-only)

- Generated: `2026-08-03T14:30:00Z`
- Home: `/Users/alice`
- Sandbox: `False`
- Min size: `100 MB`
- Items: **8**
- Total reclaimable (listed): **4.2 GB**
- Low-risk subset: **3.8 GB**

## Ranked findings

| # | Size | Risk | Category | Recommended | Path |
|---|------|------|----------|-------------|------|
| 1 | 1.8 GB | low | developer | trash | `/Users/alice/Library/Developer/Xcode/DerivedData/MyApp-abc` |
| 2 | 1.2 GB | low | caches | trash | `/Users/alice/Library/Caches/BigAppCache` |
| 3 | 850.0 MB | low | package_cache | trash | `/Users/alice/.npm/_cacache/content-v2` |
| 4 | 650.0 MB | low | logs | trash | `/Users/alice/Library/Logs` |
| 5 | 320.0 MB | low | temp | trash | `/tmp/com.apple.launchd.*` |
| 6 | 280.0 MB | medium | developer | review | `/Users/alice/Library/Developer/CoreSimulator/Caches` |
| 7 | 150.0 MB | low | package_cache | trash | `/Users/alice/Library/Caches/Homebrew` |
| 8 | 120.0 MB | low | trash | trash | `/Users/alice/.Trash` |

## Next steps

1. Review paths carefully.
2. Approve specific paths in chat.
3. Run `safe_cleanup.py` with `--approved-paths` (prefer `--mode trash`).

**Nothing has been deleted or moved.**
```

## JSON Structure

The corresponding JSON file (`cleanme-audit-20260803-1430.json`) contains:

```json
{
  "generated_at": "2026-08-03T14:30:00Z",
  "home": "/Users/alice",
  "sandbox": false,
  "min_size_mb": 100,
  "summary": {
    "item_count": 8,
    "total_bytes": 4509715660,
    "total_human": "4.2 GB",
    "low_risk_bytes": 4026531840,
    "low_risk_human": "3.8 GB"
  },
  "findings": [
    {
      "path": "/Users/alice/Library/Developer/Xcode/DerivedData/MyApp-abc",
      "size_bytes": 1929379840,
      "size_human": "1.8 GB",
      "category": "developer",
      "risk": "low",
      "label": "Xcode DerivedData",
      "recommended_action": "trash",
      "inode": [16777220, 12345678]
    }
  ]
}
```

## Notes

- The `inode` field records the device and inode number at audit time. During cleanup, `safe_cleanup.py` verifies the inode has not changed to prevent race conditions.
- `risk: low` items are safe to trash without further review.
- `risk: medium` items require explicit user confirmation even if they appear in the audit.
- The audit is read-only. No files are modified or deleted during scanning.
