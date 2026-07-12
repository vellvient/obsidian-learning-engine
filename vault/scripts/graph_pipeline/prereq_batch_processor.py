"""
Prerequisite Mining Batch Processor for Hermes + DeepSeek V4 Flash

This script:
1. Reads all exercise notes from the vault
2. Groups them by domain
3. Generates batch prompt files ready for Hermes to process
4. Merges results back into the vault

Usage:
  Step 1 (generate batches): python prereq_batch_processor.py --generate
  Step 2 (after Hermes runs):  python prereq_batch_processor.py --merge
  Step 3 (apply to vault):     python prereq_batch_processor.py --apply
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

VAULT_PATH = Path(__file__).resolve().parents[2]
ENGINE_PATH = VAULT_PATH / ".engine"
OUTPUT_DIR = ENGINE_PATH / "prereq_mining"
EDGES_FILE = ENGINE_PATH / "prerequisite_edges.json"

# Domain mapping (topic -> domain)
TOPIC_TO_DOMAIN = {
    # Number
    "number": "Number",
    
    # Ratio & Proportion
    "ratio-proportion": "Ratio and Proportion",
    
    # Geometry & Measures
    "geometry-and-measures": "Geometry and Measures",
    
    # Statistics & Probability
    "statistics-and-probability": "Statistics and Probability",
    
    # Calculus
    "calculus": "Calculus",
    
    # Complex Numbers
    "complex-numbers": "Complex Numbers",
    
    # Matrix Algebra
    "matrix-algebra": "Matrix Algebra",
    
    # Mechanics
    "mechanics": "Mechanics",
    
    # Discrete Maths
    "discrete-maths": "Discrete Maths",
    
    # Algebra subtopics
    "algebraic-fractions": "Algebra",
    "algebraic-notation-and-manipulation": "Algebra",
    "algebraic-notation-manipulation": "Algebra",
    "algebraic-proof": "Algebra",
    "binomial-expansion": "Algebra",
    "boolean-algebra-and-logic": "Algebra",
    "changing-the-subject": "Algebra",
    "conics": "Algebra",
    "estimating-gradient-and-area-under-a-curve": "Algebra",
    "expanding-brackets": "Algebra",
    "factorising-expressions": "Algebra",
    "functions": "Algebra",
    "graph-plotting-and-recognition": "Algebra",
    "graphs-of-circles": "Algebra",
    "graphs-of-exponential-functions": "Algebra",
    "graphs-of-quadratic-and-polynomial-functions": "Algebra",
    "graphs-of-reciprocal-functions": "Algebra",
    "hyperbolic-functions": "Algebra",
    "inequalities": "Algebra",
    "laws-of-indices": "Algebra",
    "linear-graphs": "Algebra",
    "logarithms-and-solving-exponential-equations": "Algebra",
    "modulus-function": "Algebra",
    "numerical-methods": "Algebra",
    "parametric-equations": "Algebra",
    "partial-fractions": "Algebra",
    "polynomials-division,-roots-and-factor-theorem": "Algebra",
    "sequences-and-series-advanced": "Algebra",
    "sequences-fundamentals": "Algebra",
    "simultaneous-equations-systems-of-equations": "Algebra",
    "solving-linear-equations": "Algebra",
    "solving-quadratic-equations": "Algebra",
    "substitution": "Algebra",
    "transformations-of-curves": "Algebra",
    
    # AS Pure
    "as-algebra-and-functions": "AS Pure",
    "as-algebraic-proof": "AS Pure",
    "as-differentiation": "AS Pure",
    "as-integration": "AS Pure",
    "as-trigonometry": "AS Pure",
    "as-vectors": "AS Pure",
    
    # AS Stats
    "as-data-representation-and-interpretation": "AS Stats",
    "as-probability": "AS Stats",
    "as-statistical-distributions": "AS Stats",
    "as-statistical-hypothesis-testing": "AS Stats",
    "as-statistical-sampling": "AS Stats",
    
    # AS Mechanics
    "as-kinematics": "AS Mechanics",
    "as-forces-and-newtons-laws": "AS Mechanics",
    "as-variable-acceleration": "AS Mechanics",
}

# Skip meta topics
SKIP_TOPICS = {"diagnostics", "error-log", "fire-dashboard", "master", "plan", "priority", "progress", "resources", "srs"}


def parse_note(filepath: Path) -> Optional[dict]:
    """Parse an exercise note's frontmatter and subskills."""
    content = filepath.read_text(encoding="utf-8", errors="replace")
    
    # Extract frontmatter
    fm_match = re.match(r"^---\r?\n(.*?)\r?\n---", content, re.DOTALL)
    if not fm_match:
        return None
    
    fm = fm_match.group(1)
    
    # Extract fields
    topic_m = re.search(r"^topic:\s*(.+)", fm, re.MULTILINE)
    exercise_m = re.search(r"^exercise:\s*(\d+)", fm, re.MULTILINE)
    name_m = re.search(r'^name:\s*"?(.+?)"?\s*$', fm, re.MULTILINE)
    prereqs_m = re.search(r"^prerequisites:\s*\[([^\]]*)\]", fm, re.MULTILINE)
    leads_m = re.search(r"^leads-to:\s*\[([^\]]*)\]", fm, re.MULTILINE)
    
    if not topic_m or not exercise_m:
        return None
    
    topic = topic_m.group(1).strip()
    if topic in SKIP_TOPICS:
        return None
    
    exercise_num = int(exercise_m.group(1))
    name = name_m.group(1).strip() if name_m else filepath.stem
    
    # Extract prerequisites
    prereqs = []
    if prereqs_m and prereqs_m.group(1).strip():
        prereqs = [int(x.strip()) for x in prereqs_m.group(1).split(",") if x.strip()]
    
    # Extract leads-to
    leads = []
    if leads_m and leads_m.group(1).strip():
        leads = [int(x.strip()) for x in leads_m.group(1).split(",") if x.strip()]
    
    # Extract subskills from body
    subskills = re.findall(r"- \[[ x]\] (.+)", content)
    
    domain = TOPIC_TO_DOMAIN.get(topic, "Unknown")
    
    return {
        "num": exercise_num,
        "name": name,
        "topic": topic,
        "domain": domain,
        "file": filepath.name,
        "prerequisites": prereqs,
        "leads_to": leads,
        "subskills": subskills,
    }


def load_existing_edges() -> List[dict]:
    """Load existing prerequisite edges."""
    if EDGES_FILE.exists():
        return json.loads(EDGES_FILE.read_text(encoding="utf-8"))
    return []


def generate_batches(exercises: List[dict], existing_edges: List[dict], batch_size: int = 40) -> None:
    """Generate batch prompt files grouped by domain."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Group by domain
    domains: Dict[str, List[dict]] = {}
    for ex in exercises:
        d = ex["domain"]
        if d not in domains:
            domains[d] = []
        domains[d].append(ex)
    
    # Create a compact existing edges reference
    existing_pairs = set()
    for e in existing_edges:
        existing_pairs.add((e["from"], e["to"]))
    
    existing_edges_str = json.dumps(
        [{"from": e["from"], "to": e["to"], "reason": e.get("reason", "")} for e in existing_edges],
        indent=2
    )
    
    # Build a master index for cross-domain reference
    master_index = []
    for ex in sorted(exercises, key=lambda x: x["num"]):
        master_index.append({
            "num": ex["num"],
            "name": ex["name"],
            "domain": ex["domain"],
            "topic": ex["topic"],
        })
    
    batch_num = 0
    batch_manifest = []
    
    for domain, domain_exercises in sorted(domains.items()):
        # Sort by exercise number
        domain_exercises.sort(key=lambda x: x["num"])
        
        # Split into batches
        for i in range(0, len(domain_exercises), batch_size):
            batch = domain_exercises[i:i + batch_size]
            batch_num += 1
            
            # Create the prompt
            exercise_data = []
            for ex in batch:
                exercise_data.append({
                    "num": ex["num"],
                    "name": ex["name"],
                    "topic": ex["topic"],
                    "domain": ex["domain"],
                    "existing_prerequisites": ex["prerequisites"],
                    "existing_leads_to": ex["leads_to"],
                    "subskills": ex["subskills"][:15],  # Limit to avoid token overflow
                })
            
            prompt_data = {
                "batch_id": f"batch_{batch_num:03d}_{domain.lower().replace(' ', '_')}",
                "domain": domain,
                "exercise_count": len(batch),
                "exercises": exercise_data,
                "master_index": master_index,  # Full index for cross-domain references
                "existing_edges_in_batch": [
                    e for e in existing_edges
                    if e["from"] in [ex["num"] for ex in batch] or e["to"] in [ex["num"] for ex in batch]
                ],
            }
            
            batch_file = OUTPUT_DIR / f"{prompt_data['batch_id']}.json"
            batch_file.write_text(json.dumps(prompt_data, indent=2), encoding="utf-8")
            
            batch_manifest.append({
                "batch_id": prompt_data["batch_id"],
                "domain": domain,
                "exercise_count": len(batch),
                "exercises": [ex["num"] for ex in batch],
                "file": str(batch_file.name),
                "status": "pending",
            })
    
    # Write manifest
    manifest_file = OUTPUT_DIR / "manifest.json"
    manifest_file.write_text(json.dumps({
        "total_batches": batch_num,
        "total_exercises": len(exercises),
        "domains": {d: len(exs) for d, exs in domains.items()},
        "batches": batch_manifest,
    }, indent=2), encoding="utf-8")
    
    # Write the system prompt
    system_prompt = """You are a mathematics curriculum graph specialist, modeled after Math Academy's knowledge graph system. Your job is to analyze exercise descriptions and determine prerequisite relationships between them.

## Types of Edges
1. **HARD_PREREQ**: Skills that MUST be understood before attempting this one.
2. **SOFT_PREREQ**: Skills that are helpful but not strictly required.
3. **IMPLICIT_REVIEW**: When practicing this skill, which prerequisite skills get naturally reviewed?

## Rules
1. Be GRANULAR — link specific exercise numbers, not broad categories
2. Avoid transitivity — don't add A→C if A→B and B→C already exist
3. Cross-domain links are important (e.g., algebra exercises that use geometry)
4. Consider both conceptual and procedural prerequisites
5. Use the subskills to judge granularity
6. Direction: `from` = prerequisite, `to` = dependent skill
7. Provide a brief reason (1 short sentence)
8. Do NOT duplicate edges listed in existing_edges_in_batch
9. Reference the master_index to find exercises outside this batch for cross-domain links

## Output Format
Return ONLY a JSON array of edge objects:
[
  {
    "from": 132,
    "to": 207,
    "type": "HARD_PREREQ",
    "reason": "mean as average needed before mode/median/range"
  }
]
"""
    
    prompt_file = OUTPUT_DIR / "system_prompt.txt"
    prompt_file.write_text(system_prompt, encoding="utf-8")
    
    # Write Hermes agent config
    hermes_config = {
        "name": "prereq-miner",
        "description": "Mines prerequisite relationships between math exercises",
        "model": "deepseek-v4-flash",
        "system_prompt_file": "system_prompt.txt",
        "batch_dir": str(OUTPUT_DIR),
        "output_dir": str(OUTPUT_DIR / "results"),
        "instructions": """
For each batch file in the batch directory:
1. Read the batch JSON file
2. Send the system prompt + the batch data as the user message
3. Parse the JSON array response
4. Save the result to output_dir/{batch_id}_result.json
5. Update the manifest status to 'completed'

User message template:
"Analyze the following batch of {exercise_count} exercises from the {domain} domain.
Here is the exercise data: {exercises}
Here is the master index of ALL exercises for cross-domain references: {master_index}
These edges already exist (do NOT duplicate): {existing_edges_in_batch}
Return ONLY a JSON array of new prerequisite edges."
""",
    }
    
    config_file = OUTPUT_DIR / "hermes_agent_config.json"
    config_file.write_text(json.dumps(hermes_config, indent=2), encoding="utf-8")
    
    print(f"\n✅ Generated {batch_num} batch files in {OUTPUT_DIR}")
    print(f"📊 Domain breakdown:")
    for d, exs in sorted(domains.items(), key=lambda x: -len(x[1])):
        print(f"   {d}: {len(exs)} exercises")
    print(f"\n📁 Files created:")
    print(f"   - {batch_num} batch JSON files")
    print(f"   - manifest.json (batch tracking)")
    print(f"   - system_prompt.txt (for Hermes)")
    print(f"   - hermes_agent_config.json (Hermes config)")


def merge_results() -> None:
    """Merge Hermes results back into a single edges file."""
    results_dir = OUTPUT_DIR / "results"
    if not results_dir.exists():
        print("❌ No results directory found. Run Hermes first.")
        return
    
    new_edges = []
    errors = []
    
    for result_file in sorted(results_dir.glob("*_result.json")) + sorted(results_dir.glob("*_edges.json")):
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for edge in data:
                    if "from" in edge and "to" in edge:
                        new_edges.append(edge)
            else:
                errors.append(f"{result_file.name}: Expected array, got {type(data)}")
        except json.JSONDecodeError as e:
            errors.append(f"{result_file.name}: JSON parse error: {e}")
    
    # Deduplicate
    seen = set()
    unique_edges = []
    for edge in new_edges:
        key = (edge["from"], edge["to"])
        if key not in seen:
            seen.add(key)
            unique_edges.append(edge)
    
    # Load existing and merge
    existing = load_existing_edges()
    existing_pairs = {(e["from"], e["to"]) for e in existing}
    
    truly_new = [e for e in unique_edges if (e["from"], e["to"]) not in existing_pairs]
    
    merged = existing + truly_new
    
    # Save
    merged_file = ENGINE_PATH / "prerequisite_edges_enriched.json"
    merged_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    
    print(f"\n✅ Merged results:")
    print(f"   Existing edges: {len(existing)}")
    print(f"   New edges from AI: {len(unique_edges)}")
    print(f"   Truly new (not duplicates): {len(truly_new)}")
    print(f"   Total merged: {len(merged)}")
    print(f"   Saved to: {merged_file}")
    
    if errors:
        print(f"\n⚠️ Errors ({len(errors)}):")
        for e in errors:
            print(f"   {e}")


def apply_to_vault() -> None:
    """Apply enriched edges to vault note frontmatter and create wikilinks."""
    enriched_file = ENGINE_PATH / "prerequisite_edges_enriched.json"
    if not enriched_file.exists():
        print("❌ No enriched edges file. Run --merge first.")
        return
    
    edges = json.loads(enriched_file.read_text(encoding="utf-8"))
    
    # Build adjacency lists
    prereqs_for: Dict[int, List[int]] = {}
    leads_from: Dict[int, List[int]] = {}
    implicit_review: Dict[int, List[int]] = {}
    
    for edge in edges:
        frm, to = edge["from"], edge["to"]
        edge_type = edge.get("type", "HARD_PREREQ")
        
        if to not in prereqs_for:
            prereqs_for[to] = []
        prereqs_for[to].append(frm)
        
        if frm not in leads_from:
            leads_from[frm] = []
        leads_from[frm].append(to)
        
        if edge_type == "IMPLICIT_REVIEW":
            if to not in implicit_review:
                implicit_review[to] = []
            implicit_review[to].append(frm)
    
    # Find all exercise files
    exercise_files = {}
    for f in VAULT_PATH.glob("*.md"):
        m = re.match(r"^(\d+)\s*-", f.name)
        if m:
            exercise_files[int(m.group(1))] = f
    
    updated = 0
    for num, filepath in sorted(exercise_files.items()):
        content = filepath.read_text(encoding="utf-8", errors="replace")
        original = content
        
        my_prereqs = sorted(set(prereqs_for.get(num, [])))
        my_leads = sorted(set(leads_from.get(num, [])))
        my_implicit = sorted(set(implicit_review.get(num, [])))
        
        if not my_prereqs and not my_leads:
            continue
        
        # Update prerequisites field
        prereq_str = f"prerequisites: [{', '.join(str(p) for p in my_prereqs)}]"
        leads_str = f"leads-to: [{', '.join(str(l) for l in my_leads)}]"
        implicit_str = f"implicit_review: [{', '.join(str(i) for i in my_implicit)}]" if my_implicit else None
        
        # Replace or insert in frontmatter
        if re.search(r"^prerequisites:", content, re.MULTILINE):
            content = re.sub(r"^prerequisites:.*$", prereq_str, content, count=1, flags=re.MULTILINE)
        else:
            content = content.replace("---\n\n", f"---\n{prereq_str}\n\n", 1)
            content = content.replace("---\r\n\r\n", f"---\r\n{prereq_str}\r\n\r\n", 1)
        
        if re.search(r"^leads-to:", content, re.MULTILINE):
            content = re.sub(r"^leads-to:.*$", leads_str, content, count=1, flags=re.MULTILINE)
        else:
            content = content.replace(prereq_str + "\n", prereq_str + f"\n{leads_str}\n", 1)
            content = content.replace(prereq_str + "\r\n", prereq_str + f"\r\n{leads_str}\r\n", 1)
        
        if my_implicit:
            if re.search(r"^implicit_review:", content, re.MULTILINE):
                content = re.sub(r"^implicit_review:.*$", implicit_str, content, count=1, flags=re.MULTILINE)
        
        # Add wikilinks in body for Prerequisites and Leads To sections
        # (only if they don't already exist)
        if "## Prerequisites" not in content and my_prereqs:
            prereq_links = "\n".join(
                f"- [[{exercise_files[p].stem}]]" for p in my_prereqs if p in exercise_files
            )
            # Find insertion point (after subskills list)
            content = content.rstrip() + f"\n\n## Prerequisites\n\n{prereq_links}\n"
        
        if "## Leads To" not in content and my_leads:
            leads_links = "\n".join(
                f"- [[{exercise_files[l].stem}]]" for l in my_leads if l in exercise_files
            )
            content = content.rstrip() + f"\n\n## Leads To\n\n{leads_links}\n"
        
        if content != original:
            filepath.write_text(content, encoding="utf-8")
            updated += 1
    
    # Also update the master edges file
    EDGES_FILE.write_text(json.dumps(edges, indent=2), encoding="utf-8")
    
    print(f"\n✅ Applied edges to vault:")
    print(f"   Notes updated: {updated}")
    print(f"   Total edges: {len(edges)}")
    print(f"   prerequisite_edges.json updated")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python prereq_batch_processor.py --generate   # Create batch files for Hermes")
        print("  python prereq_batch_processor.py --merge      # Merge Hermes results")
        print("  python prereq_batch_processor.py --apply      # Apply to vault notes")
        print("  python prereq_batch_processor.py --stats      # Show current stats")
        return
    
    action = sys.argv[1]
    
    if action == "--generate":
        # Parse all notes
        exercises = []
        for f in sorted(VAULT_PATH.glob("*.md")):
            if re.match(r"^\d+\s*-", f.name):
                result = parse_note(f)
                if result:
                    exercises.append(result)
        
        existing_edges = load_existing_edges()
        print(f"📚 Found {len(exercises)} exercise notes")
        print(f"🔗 Found {len(existing_edges)} existing edges")
        
        generate_batches(exercises, existing_edges)
    
    elif action == "--merge":
        merge_results()
    
    elif action == "--apply":
        apply_to_vault()
    
    elif action == "--stats":
        exercises = []
        for f in sorted(VAULT_PATH.glob("*.md")):
            if re.match(r"^\d+\s*-", f.name):
                result = parse_note(f)
                if result:
                    exercises.append(result)
        
        existing = load_existing_edges()
        with_prereqs = sum(1 for e in exercises if e["prerequisites"])
        
        print(f"📊 Current Stats:")
        print(f"   Total exercises: {len(exercises)}")
        print(f"   With prerequisites: {with_prereqs} ({100*with_prereqs//len(exercises)}%)")
        print(f"   Total edges: {len(existing)}")
        print(f"   Domains: {len(set(e['domain'] for e in exercises))}")
    
    else:
        print(f"Unknown action: {action}")


if __name__ == "__main__":
    main()
