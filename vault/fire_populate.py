#!/usr/bin/env python3
"""
fire_populate.py — Add implicit_review frontmatter to all exercise files.

For every exercise that has `prerequisites` but no `implicit_review`,
this adds `implicit_review` mirroring the prerequisites list.

Run this once to make the FIRe engine's data visible to Dataview queries.
Afterwards you can edit individual files to customise weights.

Usage:
    python fire_populate.py                # Dry run — show what would change
    python fire_populate.py --apply        # Actually write changes
"""

import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
from pathlib import Path

VAULT = Path(__file__).parent.resolve()

def parse_frontmatter_raw(text):
    """Return frontmatter section text and the rest, or (None, text)."""
    m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not m:
        return None, text
    return m.group(1), text[m.end():]

def get_field(fm_text, key):
    """Simple regex to extract a YAML field value as a string."""
    m = re.search(rf'^{key}:\s*(.*)', fm_text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return None

def has_field(fm_text, key):
    """Check if a field exists in frontmatter."""
    return re.search(rf'^{key}:', fm_text, re.MULTILINE) is not None

def field_as_list(value):
    """Try to convert a field value to a Python list."""
    if not value:
        return []
    # YAML: [252, 299] or "[[252]], [[299]]" or 252
    # Find all numbers
    nums = re.findall(r'\b(\d+)\b', value)
    return [int(n) for n in nums]

def insert_field(fm_text, key, value):
    """Insert a new field into frontmatter text after the last existing field."""
    lines = fm_text.split('\n')
    # Find the last non-empty/non-comment line
    insert_pos = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() and not lines[i].strip().startswith('#'):
            insert_pos = i + 1
            break
    lines.insert(insert_pos, f"{key}: {value}")
    return '\n'.join(lines)

def main():
    dry_run = "--apply" not in sys.argv
    
    changes = []
    for fpath in sorted(VAULT.glob("*.md")):
        fname = fpath.name
        
        # Skip non-exercise files (index/diagnostic/plan files)
        if fname.startswith("00 -") or fname.startswith("AS -"):
            continue
        if not re.match(r'^\d+\s*-', fname):
            continue
        
        text = fpath.read_text(encoding='utf-8', errors='replace')
        fm_text, body = parse_frontmatter_raw(text)
        if fm_text is None:
            continue
        
        # Has prerequisites but no implicit_review?
        if not has_field(fm_text, 'prerequisites'):
            continue
        if has_field(fm_text, 'implicit_review'):
            continue
        
        prereqs = field_as_list(get_field(fm_text, 'prerequisites'))
        if not prereqs:
            continue
        
        # Build implicit_review YAML list
        ireview_str = "[" + ", ".join(str(p) for p in prereqs) + "]"
        
        # Update frontmatter
        new_fm = insert_field(fm_text, 'implicit_review', ireview_str)
        new_text = f"---\n{new_fm}\n---{body}"
        
        changes.append((fpath, fname, new_text))
        print(f"  {fname:60s} → implicit_review: {ireview_str}")
    
    if not changes:
        print("✅ All exercise files already have implicit_review (or no prerequisites).")
        return
    
    print(f"\n{'=' * 70}")
    print(f"Total: {len(changes)} files would be modified.")
    
    if dry_run:
        print(f"\nThis is a DRY RUN. Run with --apply to write changes.")
        print(f"  python fire_populate.py --apply")
    else:
        for fpath, fname, new_text in changes:
            fpath.write_text(new_text, encoding='utf-8')
        print(f"✅ Written {len(changes)} files.")
        print(f"\nNext step: Run python flow_diagnostic.py --markdown")
        print(f"to regenerate the diagnostic with explicit FIRe data.")
        print(f"\nAfter that, you can fine-tune weights in individual files:")
        print(f"  implicit_review:")
        print(f"    - [252, 0.5]   # 50% credit")
        print(f"    - [299, 0.25]  # 25% credit")

if __name__ == "__main__":
    main()
