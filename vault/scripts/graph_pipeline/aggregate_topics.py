import re
import json
from pathlib import Path
from collections import defaultdict

VAULT_PATH = Path(__file__).resolve().parents[2]
ENGINE_PATH = VAULT_PATH / ".engine"
EDGES_FILE = ENGINE_PATH / "prerequisite_edges.json"
ENRICHED_EDGES_FILE = ENGINE_PATH / "prerequisite_edges_enriched.json"

def clean_wikilink(link):
    link = link.replace("[[", "").replace("]]", "")
    if "|" in link:
        link = link.split("|")[0]
    return link.strip()

def run_aggregation():
    edges_path = ENRICHED_EDGES_FILE if ENRICHED_EDGES_FILE.exists() else EDGES_FILE
    if not edges_path.exists():
        print("No prerequisite edges file found.")
        return
        
    print(f"Reading edges from {edges_path.name}...")
    try:
        edges = json.loads(edges_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error reading edges: {e}")
        return
        
    exercise_files = {}
    exercise_parents = {}
    
    for f in VAULT_PATH.glob("*.md"):
        m = re.match(r"^(\d+)\s*-", f.name)
        if not m:
            continue
        num = int(m.group(1))
        exercise_files[num] = f
        
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
            
        fm_match = re.match(r"^---\r?\n(.*?)\r?\n---", content, re.DOTALL)
        if not fm_match:
            continue
            
        fm = fm_match.group(1)
        
        parents = []
        parents_match = re.search(r"^parents:\s*\[(.*?)\]\r?$", fm, re.MULTILINE)
        if parents_match:
            for p in re.findall(r'"\[\[(.*?)\]\]"', parents_match.group(1)):
                parents.append(p)
            for p in re.findall(r"'\[\[(.*?)\]\]'", parents_match.group(1)):
                parents.append(p)
        else:
            parent_match = re.search(r'^parent:\s*"?\[\[(.*?)\]\]"?\r?$', fm, re.MULTILINE)
            if parent_match:
                parents.append(parent_match.group(1))
                
        exercise_parents[num] = parents

    topic_edges = defaultdict(list)
    
    for edge in edges:
        frm_ex = edge["from"]
        to_ex = edge["to"]
        
        frm_parents = exercise_parents.get(frm_ex, [])
        to_parents = exercise_parents.get(to_ex, [])
        
        for fp in frm_parents:
            for tp in to_parents:
                if fp != tp:
                    topic_edges[tp].append({
                        "from_topic": fp,
                        "from_ex": frm_ex,
                        "to_ex": to_ex
                    })

    updated_topics = 0
    
    for topic_name, incoming in topic_edges.items():
        topic_file = VAULT_PATH / f"{topic_name}.md"
        if not topic_file.exists():
            matched_files = [f for f in VAULT_PATH.glob("*.md") if f.stem.lower() == topic_name.lower()]
            if matched_files:
                topic_file = matched_files[0]
            else:
                clean_name = topic_name.replace("&", "and")
                matched_files = [f for f in VAULT_PATH.glob("*.md") if f.stem.replace("&", "and").lower() == clean_name.lower()]
                if matched_files:
                    topic_file = matched_files[0]
                else:
                    print(f"Warning: Topic note not found for '{topic_name}'")
                    continue
                    
        try:
            content = topic_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error reading topic file {topic_file.name}: {e}")
            continue
            
        original_content = content
        
        from_topics_summary = defaultdict(list)
        for detail in incoming:
            from_topics_summary[detail["from_topic"]].append(f"{detail['from_ex']}→{detail['to_ex']}")
            
        prereq_lines = []
        for ft, ex_links in sorted(from_topics_summary.items()):
            ex_links_str = ", ".join(ex_links[:5])
            if len(ex_links) > 5:
                ex_links_str += ", ..."
            prereq_lines.append(f"- [[{ft}]] (via exercises {ex_links_str})")
            
        prereqs_section_content = "## Topic Prerequisites\n\n" + "\n".join(prereq_lines) + "\n"
        
        if "## Topic Prerequisites" in content:
            content = re.sub(
                r"## Topic Prerequisites\n.*?(?=\n##|$)",
                prereqs_section_content,
                content,
                flags=re.DOTALL
            )
        else:
            if "## Related Topics" in content:
                content = content.replace("## Related Topics", f"{prereqs_section_content}\n## Related Topics", 1)
            else:
                content = content.rstrip() + f"\n\n{prereqs_section_content}"
                
        if content != original_content:
            try:
                topic_file.write_text(content, encoding="utf-8")
                updated_topics += 1
            except Exception as e:
                print(f"Error writing to {topic_file.name}: {e}")
                
    print(f"Successfully updated {updated_topics} topic-level notes with aggregated connections.")

if __name__ == "__main__":
    run_aggregation()
