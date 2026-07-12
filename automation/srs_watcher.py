import os, re, json, subprocess, sys
from datetime import datetime, timedelta

VAULT = os.environ.get('LEARNING_VAULT') or (sys.argv[1] if len(sys.argv) > 1 else None)
if not VAULT or not os.path.isdir(VAULT):
    sys.exit('usage: srs_watcher.py <vault-path>  (or set LEARNING_VAULT env var)')
SRS_FILE = os.path.join(VAULT, '.obsidian', 'srs_state.json')

# Load or init SRS state
if os.path.exists(SRS_FILE):
    with open(SRS_FILE) as f:
        srs = json.load(f)
else:
    srs = {"last_commit": "", "reviews": {}, "mastery_changes": []}

# Step 1: Check for unstaged changes (user ticking boxes in Obsidian)
result = subprocess.run(['git', 'status', '--porcelain', '--', '*.md'], cwd=VAULT, capture_output=True, text=True)
status_output = result.stdout.strip()

if not status_output:
    # No changes at all
    print("NO_CHANGES")
    exit(0)

# Step 2: Stage and commit the changes
subprocess.run(['git', 'add', '-A'], cwd=VAULT, capture_output=True)
result = subprocess.run(['git', 'commit', '-m', f'Auto-sync {datetime.now().strftime("%Y-%m-%d %H:%M")}'], 
                       cwd=VAULT, capture_output=True, text=True)

if result.returncode != 0 and "nothing to commit" not in result.stdout:
    print(f"COMMIT_ERROR:{result.stderr}")
    exit(1)

# Step 3: Get current hash
result = subprocess.run(['git', 'log', '-1', '--format=%H'], cwd=VAULT, capture_output=True, text=True)
current_hash = result.stdout.strip()

if not srs["last_commit"]:
    srs["last_commit"] = current_hash
    with open(SRS_FILE, 'w') as f:
        json.dump(srs, f, indent=2)
    print("NO_CHANGES")
    exit(0)

# Step 4: Diff against last checked commit
result = subprocess.run(['git', 'diff', srs["last_commit"], 'HEAD', '--', '*.md'], 
                       cwd=VAULT, capture_output=True, text=True)
diff = result.stdout

if not diff.strip():
    srs["last_commit"] = current_hash
    with open(SRS_FILE, 'w') as f:
        json.dump(srs, f, indent=2)
    print("NO_CHANGES")
    exit(0)

# Step 5: Parse diff to find newly ticked subskills
newly_ticked = []
current_file = ""
line_buffer = None

for line in diff.split('\n'):
    if line.startswith('+++ b/'):
        current_file = os.path.basename(line[6:].strip())
    elif line.startswith('--- a/'):
        continue
    
    # Track old lines to match with new [x] entries
    if line.startswith('-') and '- [ ]' in line:
        line_buffer = line[1:].strip()
    elif line.startswith('+') and '- [x]' in line:
        # Found a newly ticked item
        skill_match = re.search(r'\[x\]\s*(.+)', line)
        if skill_match:
            skill = skill_match.group(1).strip()[:100]
            newly_ticked.append({
                "skill": skill,
                "file": current_file or "unknown",
                "ticked_at": datetime.now().isoformat()
            })
    else:
        line_buffer = None

if not newly_ticked:
    srs["last_commit"] = current_hash
    with open(SRS_FILE, 'w') as f:
        json.dump(srs, f, indent=2)
    print("NO_TICKED_FOUND")
    exit(0)

# Step 6: Schedule SRS reviews for new items
today = datetime.now()
for item in newly_ticked:
    skill_key = f"{item['file']}:{item['skill']}"
    if skill_key not in srs["reviews"]:
        srs["reviews"][skill_key] = {
            "file": item["file"],
            "skill": item["skill"],
            "ticked_at": item["ticked_at"],
            "review_stages": [
                {"due": (today + timedelta(days=1)).isoformat(), "stage": 1},
                {"due": (today + timedelta(days=3)).isoformat(), "stage": 2},
                {"due": (today + timedelta(days=7)).isoformat(), "stage": 3},
                {"due": (today + timedelta(days=14)).isoformat(), "stage": 4},
                {"due": (today + timedelta(days=30)).isoformat(), "stage": 5},
            ]
        }

srs["mastery_changes"] = newly_ticked
srs["last_commit"] = current_hash

# ── FSRS live wiring (improvements #1 & #2) ──
# When a subskill is newly ticked it's a successful recall -> grade it Good in
# FSRS (adaptive intervals replace fixed stages) and run the chain-weighted FIRe
# boost on its prerequisites. Only touches reviews that already carry an `fsrs`
# sub-object (un-migrated entries are left on the legacy fixed-stage path).
try:
    import sys as _sys
    _sys.path.insert(0, VAULT)
    from srs_fsrs import VaultFSRS, Rating
    _v = VaultFSRS(srs_path=SRS_FILE)
    _v.state = srs  # operate on the daemon's in-memory dict (single write path)
    for item in newly_ticked:
        _key = f"{item['file']}:{item['skill']}"
        _info = srs["reviews"].get(_key)
        if not _info or "fsrs" not in _info:
            continue
        _v.grade_review(_key, Rating.Good)
        # chain-FIRe: boost prerequisites of the ticked exercise
        try:
            _num = int(item["file"].split(" - ")[0])
            _v.apply_fire_chain(_num, edge_weights={}, ticked_at=datetime.now())
        except Exception:
            pass
except Exception as e:
    # Never let FSRS wiring break the core sync
    print(f"FSRS_WIRING_SKIPPED:{e}")

with open(SRS_FILE, 'w') as f:
    json.dump(srs, f, indent=2)


# Output for LLM to consume
print(f"SRS_UPDATE:{json.dumps(newly_ticked)}")
