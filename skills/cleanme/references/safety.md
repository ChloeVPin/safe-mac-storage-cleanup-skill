# Safety reference

## Allowed (whitelist prefixes under `$HOME`)

- `Library/Caches` (+ Homebrew, pip, Yarn, CocoaPods, Xcode cache names)
- `Library/Logs`
- `Library/Developer/Xcode/DerivedData`
- `Library/Developer/CoreSimulator/Caches`
- `.npm/_cacache`, `.npm/_logs`
- `.cache`
- `.cargo/registry/cache`, `.cargo/git/db`
- `go/pkg/mod/cache`
- `.Trash`

Absolute (non-sandbox only): `/tmp`, `/private/tmp`, limited `/var/folders` temp paths.

## Denied (never scan/clean)

- `Documents`, `Desktop`, `Pictures`, `Music`, `Movies`, `Public`, `Downloads`
- `Library/Mail`, `Keychains`, `Messages`, `Photos`, `Containers`, `Group Containers`
- `Library/Mobile Documents`, `Application Support`, `Preferences`
- `.ssh`, `.gnupg`, `.aws`, `.config`
- System: `/System`, `/usr`, `/bin`, `/sbin`, `/etc`, `/Applications`, system `/Library`

## Cleanup gates

1. Path must pass deny list.
2. Path must match whitelist.
3. Path must appear in the current audit JSON `findings[].path`.
4. User must pass path via `--approved-paths`.
5. Default action is Trash (`--mode trash`), dry-run until confirmed.
