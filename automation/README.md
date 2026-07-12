# Automation — SRS watcher

`srs_watcher.py` makes the SRS hands-off: it git-detects checkbox ticks in the vault,
creates/advances review cards, FSRS-grades each tick **Good**, and runs the
chain-weighted FIRe boost on prerequisite ancestors. Full context:
`../docs/06-automation.md`.

The vault must be a git repository (the watcher commits changes itself).

```bash
python srs_watcher.py "C:\path\to\your\vault"
# or
LEARNING_VAULT=/path/to/vault python srs_watcher.py
```

Schedule hourly:

- **cron:** `0 * * * * python /path/to/repo/automation/srs_watcher.py /path/to/vault`
- **Windows:** `schtasks /Create /TN "SRS Watcher" /SC HOURLY /TR "python C:\...\srs_watcher.py C:\...\vault"`

The watcher only sees successful ticks (grades `Good` only). Grade anything shaky
manually from the vault: `python srs_fsrs.py --grade "<key>" Again|Hard|Easy`.
