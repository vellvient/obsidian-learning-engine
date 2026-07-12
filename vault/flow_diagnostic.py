#!/usr/bin/env python3
"""
Math Academy Flow Zone Diagnostic
==================================
Scans the Obsidian vault, computes progress per exercise, checks prerequisite
chains, and outputs a diagnostic report showing:
  - 🔥 Flow Zone: exercises ready to learn (prerequisites mastered, not yet done)
  - 🔴 SRS Due: items due for review today
  - ⛔ Blocked: exercises with unmet prerequisites
  - ⏸️ Stalled: in-progress exercises with no recent activity
  - 📊 Top-level topic mastery summary

Usage:
  python flow_diagnostic.py                  # normal output
  python flow_diagnostic.py --markdown       # as vault-ready markdown note
  python flow_diagnostic.py --json           # machine-readable JSON
"""

import os
import re
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
from pathlib import Path
from datetime import datetime, date, timedelta
from collections import defaultdict

VAULT = Path(__file__).parent.resolve()
SRS_FILE = VAULT / ".obsidian" / "srs_state.json"
IGNORE_FILES = {"00 - Master Index.md", "00 - Weak Spots Priority.md",
                "00 - Error Log.md", "00 - Quadratic Fluency Diagnostic.md",
                "00 - SRS Review Tracker.md", "00 - Khan Academy Progress.md",
                "00 - Algebra 1 Study Plan.md", "00 - 2-Week Algebra Mastery Sprint.md",
                "00 - 2-Week AS Maths Sprint.md", "flow_diagnostic.py"}
IGNORE_PREFIXES = ("00 -",)
TOPIC_INDEX_FILES = {
    "Algebraic Fractions", "Algebraic Notation and Manipulation", "Algebraic Proof",
    "Binomial Expansion", "Boolean Algebra and Logic", "Changing the Subject",
    "Conics", "Estimating Gradient and Area Under a Curve", "Expanding Brackets",
    "Factorising Expressions", "Functions", "Graph Plotting and Recognition",
    "Graphs of Circles", "Graphs of Exponential Functions",
    "Graphs of Quadratic and Polynomial Functions", "Graphs of Reciprocal Functions",
    "Hyperbolic Functions", "Inequalities", "Laws of Indices", "Linear Graphs",
    "Logarithms and Solving Exponential Equations", "Modulus Function",
    "Numerical Methods", "Parametric Equations", "Partial Fractions",
    "Polynomials Division, Roots and Factor Theorem", "Sequences Fundamentals",
    "Sequences and Series Advanced", "Simultaneous Equations Systems of Equations",
    "Solving Linear Equations", "Solving Quadratic Equations", "Substitution",
    "Transformations of Curves", "Substitution.md",
    "AS - Proof", "AS - Algebra and functions", "AS - Coordinate geometry in the (x,y) plane",
    "AS - Sequences and series", "AS - Trigonometry", "AS - Exponentials and logarithms",
    "AS - Differentiation", "AS - Integration", "AS - Vectors",
    "AS - Statistical sampling", "AS - Data representation and interpretation",
    "AS - Probability", "AS - Statistical distributions",
    "AS - Statistical hypothesis testing",
    "AS - Kinematics", "AS - Forces and Newton's laws", "AS - Variable acceleration",
}


_RETRIEVAL_CACHE = None  # lazy-loaded exercise_id -> bool


def _has_retrieval_proof(ex, num) -> bool:
    """True if this exercise has a successful delayed FSRS review (Good/Easy).

    Checkbox 100% alone is NOT enough for `mastered` — need evidence of
    retrieval after a delay. Already-mastered labels are preserved.
    """
    global _RETRIEVAL_CACHE
    if ex.get("mastery") == "mastered":
        return True
    if _RETRIEVAL_CACHE is None:
        _RETRIEVAL_CACHE = {}
        if SRS_FILE.exists():
            try:
                data = json.loads(SRS_FILE.read_text(encoding="utf-8"))
                for key, info in data.get("reviews", {}).items():
                    try:
                        eid = int(str(key).split(":")[0].split(" - ")[0])
                    except Exception:
                        continue
                    fsrs = info.get("fsrs") or {}
                    hist = fsrs.get("history") or []
                    if any(h.get("rating") in (3, 4) for h in hist):
                        _RETRIEVAL_CACHE[eid] = True
                    elif int(fsrs.get("reseed_stage") or 0) >= 3 and not hist:
                        _RETRIEVAL_CACHE.setdefault(eid, True)
            except Exception:
                pass
    return bool(_RETRIEVAL_CACHE.get(num, False))


def sync_exercise_mastery(exercises, vault=None):
    """
    Sync each exercise file's frontmatter `mastery` field and body tag
    to match actual checkbox progress. Call after scan_vault().
    
    Returns: list of (filename, old_mastery, new_mastery) changes made.
    """
    if vault is None:
        vault = VAULT
    changes = []
    
    for num, ex in sorted(exercises.items()):
        fpath = Path(ex["path"])
        if not fpath.exists():
            continue
        
        text = fpath.read_text(encoding='utf-8', errors='replace')
        done, total = ex["progress"]
        if total == 0:
            continue
        
        # Compute expected mastery
        pct = done / total
        if pct >= 1.0:
            # Retrieval-proof gate: 100% checkboxes alone → proficient max.
            # mastered only if delayed successful FSRS review exists.
            if _has_retrieval_proof(ex, num):
                expected = "mastered"
            else:
                expected = "proficient"
        elif pct >= 0.75:
            expected = "proficient"
        elif pct >= 0.25:
            expected = "familiar"
        elif pct > 0:
            expected = "familiar"
        else:
            expected = "not-started"
        
        current = ex["mastery"]
        if current == expected:
            # Check if body display text is also correct
            body_mastery_m = re.search(r'Mastery:\s*\*\*(\S+)\*\*', text)
            body_ok = True
            if body_mastery_m:
                body_ok = (body_mastery_m.group(1).lower() == expected)
            
            # Check if tags frontmatter field has correct mastery
            # Only check within frontmatter (between first two --- markers)
            tags_ok = True
            fm_m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
            if fm_m:
                fm_block = fm_m.group(1)
                # Inline: tags: [familiar, ...]
                tags_inline = re.search(r'^tags:\s*\[(.*?)\]', fm_block, re.MULTILINE)
                if tags_inline:
                    tags_ok = re.search(rf'\b{re.escape(expected)}\b', tags_inline.group(1)) is not None
                else:
                    # List:   - familiar  (inside frontmatter only)
                    tags_val = re.search(r'^tags:', fm_block, re.MULTILINE)
                    if tags_val:
                        tags_list = re.search(r'^(\s*-\s*)(\S+)', fm_block, re.MULTILINE)
                        if tags_list:
                            tags_ok = (tags_list.group(2).lower() == expected)
            
            if body_ok and tags_ok:
                continue  # everything in sync
        
        new_text = text
        
        # Update frontmatter mastery field
        new_text = re.sub(
            r'^(mastery:\s*)\S+',
            f'\\g<1>{expected}',
            new_text,
            count=1,
            flags=re.MULTILINE
        )
        
        # Update body tag (the #not-started / #familiar / #proficient / #mastered line)
        new_text = re.sub(
            r'^#\S+',
            f'#{expected}',
            new_text,
            count=1,
            flags=re.MULTILINE
        )
        
        # Update hardcoded display text: "Mastery: **Familiar**" etc. in the body
        new_text = re.sub(
            r'(Mastery:\s*\*\*)\S+(\*\*)',
            f'\\g<1>{expected}\\g<2>',
            new_text,
            count=1,
        )
        
        # Update tags list in frontmatter — both inline and list YAML formats
        # e.g. tags: [familiar, topic]  or  tags:\n  - familiar\n
        # Replace any mastery-level word in the tags field with the expected one
        mastery_words = "not-started|attempted|familiar|proficient|mastered"
        # Inline format: tags: [familiar, ...]
        new_text = re.sub(
            rf'(tags:\s*\[)\s*(?:{mastery_words})\b',
            f'\\g<1>{expected}',
            new_text,
            flags=re.MULTILINE
        )
        # List format:   - familiar
        new_text = re.sub(
            rf'^(\s*-\s*)(?:{mastery_words})\b',
            f'\\g<1>{expected}',
            new_text,
            flags=re.MULTILINE
        )
        
        # Update the exercise dict in-place for downstream use
        ex["mastery"] = expected
        ex["body_tag"] = expected
        
        fpath.write_text(new_text, encoding='utf-8')
        changes.append((fpath.name[:55], current, expected))
    
    return changes


def parse_frontmatter(text):
    """Extract YAML-like frontmatter as a dict. Simple parser, no PyYAML needed."""
    m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
    if not m:
        return {}
    data = {}
    for line in m.group(1).split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' in line:
            key, _, val = line.partition(':')
            key = key.strip()
            val = val.strip()
            # Handle quoted strings
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            elif val.startswith("'") and val.endswith("'"):
                val = val[1:-1]
            # Extract parent topics — handles all formats:
            #   parent: "[[Topic]]"
            #   parents: ["[[T1]]", "[[T2]]"]
            #   parents: [[[T1]], [[T2]]]
            #   parent: "Topic"
            if key in ('parent', 'parents'):
                # Find all [[wikilink]] patterns
                wikilinks = re.findall(r'\[\[([^\]]+)\]\]', val)
                if wikilinks:
                    # Clean captured content — strip any leftover brackets
                    data[key] = [w.strip().lstrip('[').rstrip(']').strip() for w in wikilinks]
                else:
                    # Plain text — strip quotes and brackets
                    val = val.strip().strip('"').strip("'").strip('[').strip(']').strip()
                    if val:
                        data[key] = val
                    else:
                        data[key] = []
            # Handle other arrays [a, b, c]
            elif val.startswith('[') and val.endswith(']'):
                items = []
                # Parse comma-separated items respecting quotes and parentheses
                inner = val[1:-1]
                depth = 0
                current = []
                for ch in inner:
                    if ch == ',' and depth == 0:
                        item = ''.join(current).strip()
                        if item:
                            items.append(item)
                        current = []
                    else:
                        if ch == '(' or ch == '[':
                            depth += 1
                        elif ch == ')' or ch == ']':
                            depth -= 1
                        current.append(ch)
                item = ''.join(current).strip()
                if item:
                    items.append(item)
                # Clean each item
                cleaned = []
                for item in items:
                    item = item.strip().replace('[[', '').replace(']]', '').strip()
                    item = item.strip('"').strip("'").strip()
                    if item:
                        cleaned.append(item)
                data[key] = cleaned
            else:
                # Remove wikilink brackets and quotes from single value
                val = val.replace('[[', '').replace(']]', '').strip().strip('"').strip("'").strip()
                data[key] = val
    return data


def parse_checkboxes(text):
    """Count [x] and [ ] checkboxes in the body."""
    done = len(re.findall(r'\[x\]', text))
    total = done + len(re.findall(r'\[ \]', text))
    return done, total


def extract_exercise_number(filename):
    """Extract the exercise number from filename like '252 - Expanding.md' or '334 - simplifying-surds.md'."""
    m = re.match(r'^(\d+)\s*-\s*(.+)\.md$', filename)
    if m:
        return int(m.group(1)), m.group(2)
    return None, None


def is_exercise_file(filename):
    """Check if a markdown file is an individual exercise file (has a number prefix)."""
    if filename.startswith(IGNORE_PREFIXES):
        return False
    if filename in IGNORE_FILES:
        return False
    # Topic index files (no number prefix) are not exercise files
    base = filename.replace('.md', '')
    if base in TOPIC_INDEX_FILES:
        return False
    # Check if it has a number prefix
    num, _ = extract_exercise_number(filename)
    return num is not None


def compute_mastery_from_progress(done, total):
    """Compute mastery level from checkbox progress."""
    if total == 0:
        return "not-started", 0.0
    pct = done / total
    if pct == 0:
        return "not-started", 0.0
    elif pct == 1.0:
        return "mastered", 1.0
    elif pct >= 0.75:
        return "proficient", pct
    elif pct >= 0.25:
        return "familiar", pct
    else:
        return "familiar", pct


def format_mastery_emoji(mastery):
    return {"not-started": "⬜", "familiar": "🟡", "proficient": "🟢", "mastered": "🔵"}.get(mastery, "⬜")


# ── Exercise Type Classification ──────────────────────────────────────────
# Every exercise is tagged with its primary learning mode so the diagnostic
# can recommend the right study approach for each one.
#
#   🧠 NEW CONCEPT   — First exposure; understand definitions & ideas first
#   🔁 PROCEDURAL   — Drill for speed & automaticity (repetition-heavy)
#   🎯 PATTERN      — Choose the right tool among several options
#   📝 APPLIED      — Word problems, modelling, real-world translation
#   🔗 PROOF        — Logical chains, algebraic proof, deduction
# ──────────────────────────────────────────────────────────────────────────

LEARNING_TYPE = {
    # ── New Concepts ──
    "functions": "🧠 New Concept",
    "hyperbolic functions": "🧠 New Concept",
    "conics": "🧠 New Concept",
    "parametric equations": "🧠 New Concept",
    "modulus function": "🧠 New Concept",
    "partial fractions": "🧠 New Concept",
    "numerical methods": "🧠 New Concept",
    "boolean algebra and logic": "🧠 New Concept",
    "column vector notation": "🧠 New Concept",
    "differentiating from first principles": "🧠 New Concept",
    "the fundamental theorem of calculus and accumulation": "🧠 New Concept",
    "discrete random variables including functional": "🧠 New Concept",
    "binomial distribution": "🧠 New Concept",
    "hypothesis tests on a proportion": "🧠 New Concept",
    "trial and improvement": "🧠 New Concept",
    "population and censuses": "🧠 New Concept",
    "types of data": "🧠 New Concept",
    "sampling techniques": "🧠 New Concept",
    "set builder notation": "🧠 New Concept",
    "sketching the gradient function": "🧠 New Concept",
    "general iterative processes": "🧠 New Concept",
    "syllogisms and tautologies": "🧠 New Concept",
    "parametric equations and conversion": "🧠 New Concept",
    "vectors using variables": "🧠 New Concept",
    "position vectors": "🧠 New Concept",
    "trigonometry involving vectors": "🧠 New Concept",
    "definitions and graphs of hyperbolic functions": "🧠 New Concept",
    "geometric definitions of conic sections": "🧠 New Concept",
    
    # ── Procedural Drill ──
    "expanding single bracket": "🔁 Procedural Drill",
    "expanding double brackets": "🔁 Procedural Drill",
    "expanding three or more brackets": "🔁 Procedural Drill",
    "factorising out a single term": "🔁 Procedural Drill",
    "factorising quadratic expressions": "🔁 Procedural Drill",
    "factorising the difference of two squares": "🔁 Procedural Drill",
    "factorising a quadratic where the coefficient": "🔁 Procedural Drill",
    "multiplying single algebraic terms": "🔁 Procedural Drill",
    "dividing single algebraic terms": "🔁 Procedural Drill",
    "collecting like terms": "🔁 Procedural Drill",
    "numerical index laws basic": "🔁 Procedural Drill",
    "negative indices": "🔁 Procedural Drill",
    "fractional indices": "🔁 Procedural Drill",
    "expressing a power using a different base": "🔁 Procedural Drill",
    "laws of logs": "🔁 Procedural Drill",
    "simplifying surds": "🔁 Procedural Drill",
    "multiplying and dividing surds": "🔁 Procedural Drill",
    "adding and subtracting surds": "🔁 Procedural Drill",
    "expanding brackets with surds": "🔁 Procedural Drill",
    "rationalising the denominator": "🔁 Procedural Drill",
    "simplifying single algebraic fractions": "🔁 Procedural Drill",
    "multiplying and dividing algebraic fractions": "🔁 Procedural Drill",
    "adding and subtracting algebraic fractions": "🔁 Procedural Drill",
    "solving linear equations one side": "🔁 Procedural Drill",
    "solving linear equations both sides": "🔁 Procedural Drill",
    "solving linear equations involving fractions": "🔁 Procedural Drill",
    "solving linear equations with brackets": "🔁 Procedural Drill",
    "solving quadratic equations by factorisation": "🔁 Procedural Drill",
    "solving quadratic equations by completing the square": "🔁 Procedural Drill",
    "quadratic formula": "🔁 Procedural Drill",
    "completing the square to put an expression in the form": "🔁 Procedural Drill",
    "basic substitution": "🔁 Procedural Drill",
    "further substitution with positive integers": "🔁 Procedural Drill",
    "substitution with decimals": "🔁 Procedural Drill",
    "gradient of a line": "🔁 Procedural Drill",
    "intercepts of a line": "🔁 Procedural Drill",
    "plotting a straight line from a table": "🔁 Procedural Drill",
    "understanding the equation of a straight line": "🔁 Procedural Drill",
    "determining the equation of a straight line": "🔁 Procedural Drill",
    "distance between two points": "🔁 Procedural Drill",
    "introduction to sequences": "🔁 Procedural Drill",
    "nth term formula for arithmetic": "🔁 Procedural Drill",
    "nth term formula for geometric": "🔁 Procedural Drill",
    "adding, subtracting and scaling column vectors": "🔁 Procedural Drill",
    "converting a vector between component form": "🔁 Procedural Drill",
    "suvat equations": "🔁 Procedural Drill",
    "differentiating powers": "🔁 Procedural Drill",
    "integrating powers": "🔁 Procedural Drill",
    "evaluating definite integrals": "🔁 Procedural Drill",
    "coding data": "🔁 Procedural Drill",
    "sigma notation mean": "🔁 Procedural Drill",
    "variance and standard deviation": "🔁 Procedural Drill",
    "outliers": "🔁 Procedural Drill",
    "interpolation": "🔁 Procedural Drill",
    "frequency polygons": "🔁 Procedural Drill",
    "cumulative frequency graphs": "🔁 Procedural Drill",
    "box plots": "🔁 Procedural Drill",
    "quartiles from discrete data": "🔁 Procedural Drill",
    "deciles and percentiles": "🔁 Procedural Drill",
    "comparing data sets": "🔁 Procedural Drill",
    "using the unit circle": "🔁 Procedural Drill",
    "plotting and recognising trig graphs": "🔁 Procedural Drill",
    "sine rule": "🔁 Procedural Drill",
    "cosine rule": "🔁 Procedural Drill",
    "area of triangle using sine": "🔁 Procedural Drill",
    "simple random sampling": "🔁 Procedural Drill",
    "non random sampling": "🔁 Procedural Drill",
    "stratified sampling": "🔁 Procedural Drill",
    "restricted domain": "🔁 Procedural Drill",
    "successive dependent events": "🔁 Procedural Drill",
    "probability independent events": "🔁 Procedural Drill",
    "probabilities from venn diagrams": "🔁 Procedural Drill",
    "mid-ordinate rule": "🔁 Procedural Drill",
    "simpsons rule": "🔁 Procedural Drill",
    "scatter graphs": "🔁 Procedural Drill",
    "histograms and frequency density": "🔁 Procedural Drill",
    
    # ── Pattern Recognition ──
    "factorising more difficult expressions by combining": "🎯 Pattern Recognition",
    "solving hidden quadratic equations": "🎯 Pattern Recognition",
    "discriminant of a quadratic function": "🎯 Pattern Recognition",
    "quadratic graphs and their features": "🎯 Pattern Recognition",
    "properties of exponential graphs": "🎯 Pattern Recognition",
    "recognising the shape of basic forms": "🎯 Pattern Recognition",
    "recognising the shape of more complex": "🎯 Pattern Recognition",
    "graph transformations of": "🎯 Pattern Recognition",
    "combinations of graph transformations": "🎯 Pattern Recognition",
    "graph representation of functions": "🎯 Pattern Recognition",
    "properties of functions": "🎯 Pattern Recognition",
    "one-to-one vs many-to-one functions": "🎯 Pattern Recognition",
    "graphs of more general reciprocal functions": "🎯 Pattern Recognition",
    "graphs of reciprocal functions with quadratics": "🎯 Pattern Recognition",
    "graphs of root functions": "🎯 Pattern Recognition",
    "graphs of polynomials of order 3 or more": "🎯 Pattern Recognition",
    "solving linear inequalities in one variable": "🎯 Pattern Recognition",
    "solving two-ended linear inequalities": "🎯 Pattern Recognition",
    "inequalities for expressions given a restricted domain": "🎯 Pattern Recognition",
    "linear inequalities on a 2d plane": "🎯 Pattern Recognition",
    "solving quadratic inequalities": "🎯 Pattern Recognition",
    "solving cubic and quartic inequalities": "🎯 Pattern Recognition",
    "sketching graphs involving the modulus function": "🎯 Pattern Recognition",
    "solving equations involving the modulus equation": "🎯 Pattern Recognition",
    "solving inequalities involving the modulus function": "🎯 Pattern Recognition",
    "solving simple trigonometric equations": "🎯 Pattern Recognition",
    "solving trigonometric equations involving": "🎯 Pattern Recognition",
    "solving equations involving negative and fractional powers and surds": "🎯 Pattern Recognition",
    "solving equations involving fractions that lead to a quadratic": "🎯 Pattern Recognition",
    "determining if a term belongs in an arithmetic sequence": "🎯 Pattern Recognition",
    "distinguishing between different types of sequences": "🎯 Pattern Recognition",
    "describing generating and continuing sequences": "🎯 Pattern Recognition",
    "using graphs to count solutions": "🎯 Pattern Recognition",
    "graphs of exponential functions": "🎯 Pattern Recognition",
    "graphs of circles centred at the origin": "🎯 Pattern Recognition",
    "coordinate geometry on circles": "🎯 Pattern Recognition",
    "dealing with logical true-false": "🎯 Pattern Recognition",
    "solving linear simultaneous equations using graphical": "🎯 Pattern Recognition",
    "solving non-linear simultaneous equations": "🎯 Pattern Recognition",
    "second derivative of a polynomial function": "🎯 Pattern Recognition",
    "increasing and decreasing polynomial functions": "🎯 Pattern Recognition",
    "equations of tangents and normals": "🎯 Pattern Recognition",
    "sigma notation for sums of series": "🎯 Pattern Recognition",
    "writing vectors in terms of unit vectors": "🎯 Pattern Recognition",
    "histograms and frequency density": "🎯 Pattern Recognition",
    "using log graphs to estimate parameters": "🎯 Pattern Recognition",
    "graphs of log": "🎯 Pattern Recognition",
    
    # ── Applied ──
    "forming linear algebraic expressions": "📝 Applied",
    "forming and solving linear equations from a given context": "📝 Applied",
    "forming and solving quadratic expressions or equations from context": "📝 Applied",
    "real-life linear graphs": "📝 Applied",
    "linear model output": "📝 Applied",
    "optimisation problems": "📝 Applied",
    "bearings problems": "📝 Applied",
    "logarithmic scales and modelling": "📝 Applied",
    "exponential growth/decay in context": "📝 Applied",
    "displacement-time graphs and velocity-time graphs": "📝 Applied",
    "projectile motion in 1d": "📝 Applied",
    "forces on a single particle in equilibrium": "📝 Applied",
    "forces on an accelerating single particle": "📝 Applied",
    "forces on accelerating connected particles": "📝 Applied",
    "calculus in kinematics": "📝 Applied",
    "considering forces on accelerating particles": "📝 Applied",
    "forces as vectors": "📝 Applied",
    "regression line": "📝 Applied",
    "determining a function given its derivative": "📝 Applied",
    "maxima and minima stationary points": "📝 Applied",
    "summing terms in arithmetic series": "📝 Applied",
    "summing terms in geometric series": "📝 Applied",
    "nth term formula arithmetic standard": "📝 Applied",
    "nth term formula geometric standard": "📝 Applied",
    "sigma notation and mean in statistical context": "📝 Applied",
    "further sampling techniques": "📝 Applied",
    "binomial expansion of": "📝 Applied",
    
    # ── Proof & Reasoning ──
    "testing conjectures and identifying counterexamples": "🔗 Proof & Reasoning",
    "equating coefficients in an identity": "🔗 Proof & Reasoning",
    "proof by deduction": "🔗 Proof & Reasoning",
    "proof by exhaustion": "🔗 Proof & Reasoning",
    "proof by contradiction": "🔗 Proof & Reasoning",
    "algebraic proofs involving integers": "🔗 Proof & Reasoning",
    "the factor theorem": "🔗 Proof & Reasoning",
    "the remainder theorem": "🔗 Proof & Reasoning",
    "polynomial division": "🔗 Proof & Reasoning",
    "solving cubic equations": "🔗 Proof & Reasoning",
    "relationship between roots and coefficients": "🔗 Proof & Reasoning",
    "parallel vectors and straight line proofs using vectors": "🔗 Proof & Reasoning",
    "solving vector problems by introduction of a scalar": "🔗 Proof & Reasoning",
    "constructing proofs involving trig identities": "🔗 Proof & Reasoning",
    "newtons forward difference interpolation": "🔗 Proof & Reasoning",
    "lagranges interpolating polynomial": "🔗 Proof & Reasoning",
    "taylor series": "🔗 Proof & Reasoning",
    "lagrange error bound": "🔗 Proof & Reasoning",
    "series solution of differential equations": "🔗 Proof & Reasoning",
    "am-gm inequality": "🔗 Proof & Reasoning",
    "cauchy-schwarz inequality": "🔗 Proof & Reasoning",
    "generalised triangle inequality": "🔗 Proof & Reasoning",
    "de morgan law": "🔗 Proof & Reasoning",
    "proof by induction with recurrence relations": "🔗 Proof & Reasoning",
    "fibonacci-like sequences": "🔗 Proof & Reasoning",
    "solutions of first-order recurrence relations": "🔗 Proof & Reasoning",
    "equations of perpendicular lines": "🔗 Proof & Reasoning",
}


def classify_exercise(num, name=""):
    """Return the learning-type category for an exercise."""
    name_lower = name.lower()
    
    # Try direct lookup by name keywords (most specific first)
    for keyword, category in LEARNING_TYPE.items():
        if keyword in name_lower:
            return category
    
    # Fallback: broader heuristics
    # Check for 'proof', 'prove', 'theorem' in name
    if any(w in name_lower for w in ["proof", "prove", "theorem", "identity"]):
        return "🔗 Proof & Reasoning"
    
    # Check for 'word problem', 'context', 'real-life', 'modelling'
    if any(w in name_lower for w in ["context", "real-life", "word problem", "modelling", "optimisation"]):
        return "📝 Applied"
    
    # Check for 'recognise', 'identify', 'sketch', 'feature' — pattern recognition
    if any(w in name_lower for w in ["recognis", "identify", "sketch", "feature", "shape", "discriminant"]):
        return "🎯 Pattern Recognition"
    
    # Check for 'form', 'solve', 'simplify', 'expand', 'factoris' — procedural
    if any(w in name_lower for w in ["simplify", "expand", "factoris", "multiply", "divide", "collect", "substitut"]):
        return "🔁 Procedural Drill"
    
    # Default for numbers — classify by range
    if isinstance(num, int):
        if num < 200:
            return "🔁 Procedural Drill"  # Early algebra is mostly drill
        elif num < 400:
            return "🎯 Pattern Recognition"  # Mid-range mixes pattern and drill
        elif num < 600:
            return "🧠 New Concept"  # Later content introduces new ideas
        elif num < 800:
            return "🔗 Proof & Reasoning"  # Advanced = proof-heavy
        else:
            return "🔗 Proof & Reasoning"
    
    return "🔁 Procedural Drill"  # safest default


LAST_LEGACY_SRS_META = {"overdue_stage_entries": 0, "unique_skills": 0}


def load_srs_due():
    """Load SRS state and find items due today.

    Prefers FSRS when migrated. Stores legacy backlog in LAST_LEGACY_SRS_META
    for dual-due display in the diagnostic report.
    """
    global LAST_LEGACY_SRS_META
    LAST_LEGACY_SRS_META = {"overdue_stage_entries": 0, "unique_skills": 0}
    if not SRS_FILE.exists():
        return []
    try:
        data = json.loads(SRS_FILE.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, Exception):
        return []

    try:
        from srs_fsrs import VaultFSRS
        v = VaultFSRS()
        LAST_LEGACY_SRS_META = v.legacy_overdue_summary()
        seeded = sum(1 for r in v.state.get("reviews", {}).values() if "fsrs" in r)
        if seeded:
            due_keys = v.due_today()
            out = []
            for key in due_keys:
                info = v.state["reviews"].get(key, {})
                fsrs_obj = info.get("fsrs", {})
                due_str = fsrs_obj.get("due", "")
                try:
                    due_date = datetime.fromisoformat(due_str).date()
                except Exception:
                    due_date = date.today()
                out.append({
                    "file": info.get("file", ""),
                    "skill": info.get("skill", ""),
                    "stage": fsrs_obj.get("state", 0),
                    "due_date": due_date,
                    "fsrs": True,
                    "stability": fsrs_obj.get("stability"),
                })
            return out
    except Exception:
        pass

    today = date.today()
    due = []
    skills = set()
    reviews = data.get("reviews", {})
    for key, info in reviews.items():
        for stage in info.get("review_stages", []):
            due_date_str = stage.get("due", "")
            if due_date_str:
                try:
                    due_date = datetime.fromisoformat(due_date_str).date()
                    if due_date <= today:
                        due.append({
                            "file": info.get("file", ""),
                            "skill": info.get("skill", ""),
                            "stage": stage.get("stage", 0),
                            "due_date": due_date,
                        })
                        skills.add(key)
                except (ValueError, TypeError):
                    pass
    LAST_LEGACY_SRS_META = {
        "overdue_stage_entries": len(due),
        "unique_skills": len(skills),
    }
    return due


def scan_vault():
    """Scan all exercise files and build the knowledge graph."""
    exercises = {}      # num -> {name, filename, mastery, progress, prerequisites, leads_to, parents, body_tag}
    topic_progress = defaultdict(lambda: {"done": 0, "total": 0})
    
    for fpath in sorted(VAULT.glob("*.md")):
        fname = fpath.name
        if not is_exercise_file(fname):
            continue
        
        text = fpath.read_text(encoding='utf-8', errors='replace')
        fm = parse_frontmatter(text)
        done, total = parse_checkboxes(text)
        
        num, slug = extract_exercise_number(fname)
        if num is None:
            continue
        
        # Read mastery from frontmatter, otherwise compute
        fm_mastery = fm.get("mastery", "not-started")
        computed_mastery, pct = compute_mastery_from_progress(done, total)
        
        # Use frontmatter mastery as authoritative, but flag mismatch
        mastery = fm_mastery
        
        # Prerequisites
        prereqs = fm.get("prerequisites", [])
        if isinstance(prereqs, str):
            prereqs = [prereqs]
        # Filter to only numeric prerequisites
        prereqs_numeric = []
        for p in prereqs:
            if isinstance(p, int):
                prereqs_numeric.append(p)
            elif isinstance(p, str) and p.strip().isdigit():
                prereqs_numeric.append(int(p.strip()))
        prereqs = prereqs_numeric
        
        # FIRe — Fractional Implicit Repetition
        # Which older exercises does working on THIS exercise implicitly review?
        # Supports formats:
        #   implicit_review: [252, 299]                    (default weight 0.3 each)
        #   implicit_review: [[252, 0.5], [299, 0.25]]     (custom weights)
        implicit_review = fm.get("implicit_review", [])
        if isinstance(implicit_review, str):
            implicit_review = [implicit_review]
        ireview_numeric = []
        fire_weights = {}
        for item in implicit_review:
            if isinstance(item, list) and len(item) >= 2:
                try:
                    pnum = int(item[0])
                    weight = float(item[1])
                    fire_weights[pnum] = weight
                    ireview_numeric.append(pnum)
                except (ValueError, TypeError):
                    pass
            elif isinstance(item, (int, str)):
                try:
                    pnum = int(item)
                    ireview_numeric.append(pnum)
                except (ValueError, TypeError):
                    pass
        # If no explicit implicit_review set, default to prerequisites
        if not ireview_numeric:
            ireview_numeric = list(prereqs_numeric)
        # Assign default weight 0.3 to any prereq without explicit weight
        for p in ireview_numeric:
            if p not in fire_weights:
                fire_weights[p] = 0.3
        
        leads_to = fm.get("leads-to", [])
        if isinstance(leads_to, str):
            leads_to = [leads_to]
        
        # Parents — handle both list (from parents:) and string (from parent:)
        raw_parents = []
        if "parents" in fm:
            raw_parents = fm["parents"]
            if isinstance(raw_parents, str):
                raw_parents = [raw_parents]
        elif "parent" in fm:
            p = fm["parent"]
            if isinstance(p, str):
                raw_parents = [p]
            elif isinstance(p, list):
                raw_parents = p
        parents = [str(p).strip() for p in raw_parents if str(p).strip()]
        
        # Body tag
        body_tag_m = re.search(r'^#(\S+)', text, re.MULTILINE)
        body_tag = body_tag_m.group(1) if body_tag_m else "not-started"
        
        name = fm.get("name", slug or fname)
        
        exercises[num] = {
            "name": name,
            "slug": slug or fname,
            "filename": fname,
            "path": str(fpath),
            "mastery": mastery,
            "computed_mastery": computed_mastery,
            "progress": (done, total),
            "pct": pct,
            "prerequisites": prereqs,
            "implicit_review": ireview_numeric,
            "fire_weights": fire_weights,
            "leads_to": leads_to,
            "parents": parents,
            "body_tag": body_tag,
            "learning_type": classify_exercise(num, name),
        }
        
        # Accumulate topic progress — normalize consistently (case-insensitive)
        for parent in parents:
            parent_clean = parent.strip()
            key = parent_clean.lower()
            if key not in topic_progress:
                topic_progress[key] = {"display": parent_clean, "done": 0, "total": 0}
            topic_progress[key]["done"] += done
            topic_progress[key]["total"] += total
    
    return exercises, dict(topic_progress)


def compute_fire_scores(exercises, by_num):
    """
    FIRe — Fractional Implicit Repetition scoring.
    
    For each exercise, compute which prereqs working on it will fractionally
    review, and at what weight. An exercise with high FIRe score reviews many
    older topics while you learn new material.
    
    Returns: dict[exercise_num] -> {
        total_weight: sum of all fractional credits,
        credits: [ {prereq_num, prereq_name, weight, is_mastered}, ... ],
        unique_count: number of distinct prereqs reviewed
    }
    """
    fire_data = {}
    for num, ex in sorted(exercises.items()):
        if ex["pct"] >= 1.0:
            continue  # already mastered, no implicit review benefit needed
        
        ireview = ex.get("implicit_review", [])
        weights = ex.get("fire_weights", {})
        
        credits = []
        total_weight = 0.0
        for pnum in ireview:
            if pnum == num:
                continue  # don't count self-review
            p_ex = by_num.get(pnum)
            weight = weights.get(pnum, 0.3)
            total_weight += weight
            credits.append({
                "prereq_num": pnum,
                "prereq_name": p_ex["name"] if p_ex else f"#{pnum}",
                "weight": weight,
                "is_mastered": p_ex["pct"] >= 1.0 if p_ex else False,
                "prereq_mastery": p_ex["mastery"] if p_ex else "unknown",
            })
        
        # Count how many of the reviewed prereqs are (a) not yet mastered and (b) due for SRS
        active_review_count = sum(1 for c in credits if not c["is_mastered"])
        
        fire_data[num] = {
            "credits": credits,
            "total_weight": round(total_weight, 2),
            "unique_count": len(credits),
            "active_count": active_review_count,
            "prereq_count": len(ex.get("prerequisites", [])),
            "fire_ratio": round(total_weight / max(len(credits), 1), 2),
        }
    return fire_data


def apply_fire_to_srs(exercises, srs_path=None):
    """
    Apply FIRe fractional credit to SRS state.
    
    When an exercise has been worked on recently (SRS ticked), its
    implicit_review prerequisites get fractional credit toward their
    next review. This means their due dates get extended by
    (weight × current_interval).
    
    Effect: reviewing a prereq is "less urgent" because you just
    practiced it implicitly through a new exercise.
    
    Returns: list of strings describing what changed.
    """
    from datetime import timedelta
    
    if srs_path is None:
        srs_path = SRS_FILE
    if not srs_path.exists():
        return ["⚠️ No SRS state file found — nothing to apply."]
    
    try:
        state = json.loads(srs_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, Exception) as e:
        return [f"⚠️ Could not read SRS state: {e}"]
    
    today = date.today()
    yesterday = today - timedelta(days=1)
    changes = []
    
    # Build lookup: exercise file -> exercise data
    ex_by_file = {}
    for num, ex in exercises.items():
        ex_by_file[ex["filename"]] = {**ex, "num": num}
    
    reviews = state.get("reviews", {})
    for key, info in reviews.items():
        filename = info.get("file", "")
        ex_data = ex_by_file.get(filename)
        if not ex_data:
            continue
        
        # Check if this exercise was worked on recently
        ticked_at_str = info.get("ticked_at", "")
        if not ticked_at_str:
            continue
        try:
            ticked_at = datetime.fromisoformat(ticked_at_str).date()
        except (ValueError, TypeError):
            continue
        
        # Only apply FIRe credit if worked on today or yesterday
        if ticked_at < yesterday:
            continue
        
        # This exercise was recently practiced. Its prereqs get credit.
        ireview = ex_data.get("implicit_review", [])
        weights = ex_data.get("fire_weights", {})
        
        for pnum in ireview:
            if pnum == ex_data["num"]:
                continue
            # Find SRS entries for this prereq
            prereq_ex = exercises.get(pnum)
            if not prereq_ex:
                continue
            
            prereq_file = prereq_ex["filename"]
            # Look for SRS entries matching this prereq file
            for pkey, pinfo in reviews.items():
                if pinfo.get("file") != prereq_file:
                    continue
                # Found an SRS entry for the prereq — extend its next due date
                weight = weights.get(pnum, 0.3)
                stages = pinfo.get("review_stages", [])
                for stage in stages:
                    due_str = stage.get("due", "")
                    if not due_str:
                        continue
                    try:
                        due_date = datetime.fromisoformat(due_str)
                        days_until_due = (due_date.date() - today).days
                        
                        # Calculate interval length based on stage
                        stage_num = stage.get("stage", 1)
                        interval_days = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}.get(stage_num, 7)
                        
                        # Only extend if not already past due
                        if days_until_due >= 0:
                            extension = timedelta(days=int(weight * interval_days))
                            new_due = due_date + extension
                            if new_due != due_date:
                                old_due_str = due_date.strftime("%Y-%m-%d")
                                new_due_str = new_due.strftime("%Y-%m-%d")
                                stage["due"] = new_due.isoformat()
                                changes.append(
                                    f"  🔥 #{ex_data['num']} → #{pnum}: "
                                    f"FIRe credit {weight:.1f}×{interval_days}d = {extension.days}d extension. "
                                    f"Due {old_due_str} → {new_due_str}"
                                )
                    except (ValueError, TypeError):
                        continue
    
    if changes:
        # Save updated SRS state
        state["last_fire_apply"] = datetime.now().isoformat()
        srs_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
        changes.insert(0, f"🔥 **FIRe Applied:** {len(changes)} fractional reviews credited")
    else:
        changes.append("  No fractional credits to apply — all prereqs are up to date.")
    
    return changes


def build_diagnostic(exercises, topic_progress):
    """
    Build the full diagnostic:
    - Flow Zone: prerequisites mastered, exercise not mastered
    - Ready to Start: no prerequisites, exercise not started
    - Blocked: exercise has unmet prerequisites
    - Stalled: in-progress but stuck
    - SRS Due
    """
    today = date.today()
    
    # Index by number for lookup
    by_num = {}
    for num, ex in exercises.items():
        by_num[num] = ex
    
    # FIRe scoring
    fire_data = compute_fire_scores(exercises, by_num)
    
    # Which exercises are fully mastered? (progress pct >= 1.0)
    mastered_set = {num for num, ex in exercises.items() if ex["pct"] >= 1.0}
    
    flow_zone = []
    ready_to_start = []
    blocked = []
    stalled = []
    
    for num, ex in sorted(exercises.items()):
        done, total = ex["progress"]
        prereqs = ex["prerequisites"]
        
        # Check if all prerequisites are mastered
        prereqs_met = True
        missing_prereqs = []
        for p in prereqs:
            if p in mastered_set:
                continue
            elif p in by_num:
                prereqs_met = False
                missing_prereqs.append((p, by_num[p]["name"], by_num[p]["pct"]))
            else:
                prereqs_met = False
                missing_prereqs.append((p, f"Unknown #{p}", 0.0))
        
        if ex["pct"] >= 1.0:
            # Already mastered — skip
            continue
        
        if prereqs_met:
            if ex["pct"] == 0.0 and not prereqs:
                # No prereqs, not started — entry point
                ready_to_start.append((num, ex))
            elif ex["pct"] == 0.0:
                # Has prereqs, all met, not started — prime flow zone candidate
                flow_zone.append((num, ex, "not started"))
            elif ex["pct"] < 1.0:
                # In progress, prereqs met — in flow zone
                flow_zone.append((num, ex, f"in progress ({done}/{total})"))
            elif done > 0 and total > 0 and ex["pct"] < 1.0:
                # Already picked up (not needed due to above)
                pass
        else:
            blocked.append((num, ex, missing_prereqs))
        
        # Stalled detection: in progress (1-99%) but prereqs met
        if 0 < ex["pct"] < 1.0:
            # Check if SRS has entries for this file (was worked on recently)
            stalled.append((num, ex))
    
    # SRS due items
    srs_due = load_srs_due()
    
    # Topic mastery summary
    topic_summary = {}
    for topic_key, prog in sorted(topic_progress.items()):
        if prog["total"] == 0:
            continue
        display_name = prog.get("display", topic_key)
        pct = prog["done"] / prog["total"]
        if pct >= 1.0:
            emoji, label = "🔵", "Mastered"
        elif pct >= 0.75:
            emoji, label = "🟢", "Proficient"
        elif pct >= 0.25:
            emoji, label = "🟡", "Familiar"
        elif pct > 0:
            emoji, label = "🟡", "Familiar"
        else:
            emoji, label = "⬜", "Not Started"
        topic_summary[display_name] = {
            "done": prog["done"],
            "total": prog["total"],
            "pct": pct,
            "emoji": emoji,
            "label": label,
        }
    
    return {
        "flow_zone": flow_zone,
        "ready_to_start": ready_to_start,
        "blocked": blocked,
        "stalled": stalled,
        "srs_due": srs_due,
        "legacy_srs_meta": dict(LAST_LEGACY_SRS_META),
        "fire_data": fire_data,
        "topic_summary": topic_summary,
        "total_exercises": len(exercises),
        "mastered_count": len(mastered_set),
        "mastered_pct": len(mastered_set) / len(exercises) * 100 if exercises else 0,
        "blocker_chains": build_blocker_chains(exercises, by_num, mastered_set),
        "leverage_exercises": find_highest_leverage(exercises, by_num, mastered_set),
    }


def build_blocker_chains(exercises, by_num, mastered_set):
    """
    For each not-mastered exercise, find the chain of prerequisites
    that form the shortest bottleneck path.  Returns a dict:
      exercise_num -> [chain of (num, name, progress%)]
    The chain ends with the first unmastered prerequisite.
    """
    chains = {}
    for num, ex in sorted(exercises.items()):
        if ex["pct"] >= 1.0:
            continue
        chain = []
        visited = set()
        cursor = num
        while True:
            prereqs = by_num.get(cursor, {}).get("prerequisites", [])
            # Find the first unmastered prerequisite
            bottleneck = None
            for p in prereqs:
                if p not in mastered_set:
                    bottleneck = p
                    break
            if bottleneck is None or bottleneck in visited:
                break
            visited.add(bottleneck)
            p_ex = by_num.get(bottleneck)
            if p_ex:
                chain.append((bottleneck, p_ex["name"], p_ex["pct"]))
            else:
                chain.append((bottleneck, f"Unknown #{bottleneck}", 0.0))
            cursor = bottleneck
        if chain:
            chains[num] = chain
    return chains


def find_highest_leverage(exercises, by_num, mastered_set):
    """
    Find exercises whose completion would unlock the MOST downstream
    blocked exercises.  Returns list of (num, name, count_blocked, pct).
    """
    # Build dependency tree: for each exercise, what depends on it?
    dependents = {}
    for num, ex in exercises.items():
        for p in ex.get("prerequisites", []):
            if p not in dependents:
                dependents[p] = []
            dependents[p].append(num)
    
    # Count how many blocked exercises would be (transitively) unlocked
    leverage = []
    for num, ex in sorted(exercises.items()):
        if ex["pct"] >= 1.0:
            continue  # already mastered, can't "unlock" more
        # BFS from this exercise through the dependency tree
        visited = set()
        queue = [num]
        unlock_count = 0
        while queue:
            c = queue.pop(0)
            if c in visited:
                continue
            visited.add(c)
            for dep in dependents.get(c, []):
                dep_ex = by_num.get(dep)
                if dep_ex and dep_ex["pct"] < 1.0:
                    unlock_count += 1
                    queue.append(dep)
        if unlock_count > 0:
            leverage.append((num, ex["name"], unlock_count, ex["pct"]))
    
    leverage.sort(key=lambda x: -x[2])
    return leverage[:20]


def render_markdown_report(diag):
    """Render the diagnostic as a markdown report suitable for the vault."""
    today_str = date.today().strftime("%A, %b %d, %Y")
    
    lines = []
    lines.append("---")
    lines.append("topic: diagnostics")
    lines.append("mastery: reference")
    lines.append("tags: [reference, flow-zone, diagnostic]")
    lines.append(f"generated: {date.today().isoformat()}")
    lines.append("---")
    lines.append("")
    lines.append("#reference")
    lines.append("")
    lines.append(f"# 🌊 Flow Zone Diagnostic — {today_str}")
    lines.append("")
    lines.append(f"**{diag['total_exercises']} exercises tracked** · 🔵 **{diag['mastered_count']} mastered** ({diag['mastered_pct']:.0f}%)")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # === SRS Due Today (dual: FSRS + legacy) ===
    lines.append("## 🔴 SRS Due Today")
    lines.append("")
    srs = diag["srs_due"]
    leg = diag.get("legacy_srs_meta") or {}
    if leg:
        lines.append(
            f"_Legacy stage backlog: **{leg.get('overdue_stage_entries', 0)}** entries / "
            f"**{leg.get('unique_skills', 0)}** skills. FSRS due (compressed): **{len(srs)}**._"
        )
        lines.append("")
    if srs:
        lines.append("| Skill | File | Stage/State | Due |")
        lines.append("|-------|------|-------------|-----|")
        for item in srs[:25]:
            if item.get("fsrs"):
                stage_label = {1: "Learn", 2: "Review", 3: "Relearn"}.get(item["stage"], f"S{item['stage']}")
                S = item.get("stability")
                if isinstance(S, (int, float)):
                    stage_label += f" S≈{S:.1f}"
            else:
                stage_map = {1: "1d", 2: "3d", 3: "7d", 4: "14d", 5: "30d"}
                stage_label = stage_map.get(item["stage"], f"S{item['stage']}")
            fname = item.get("file", "").replace(".md", "")
            link = f"[[{fname}|{fname.split(' - ')[0] if ' - ' in fname else fname}]]"
            lines.append(f"| {item['skill'][:55]} | {link} | {stage_label} | {item['due_date']} |")
        if len(srs) > 25:
            lines.append(f"| ... and {len(srs)-25} more | | | |")
        lines.append("")
        lines.append("Open [[00 - Review Grader]] to grade Again/Hard/Good/Easy (cap ~30 cards).")
    else:
        lines.append("*No FSRS items due after compression. Check legacy backlog above if non-zero.*")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # === Flow Zone ===
    lines.append("## 🔥 Flow Zone — Ready to Learn")
    lines.append("")
    lines.append("*These exercises have all prerequisites mastered. They're at the **just-right difficulty** — challenging but achievable.*")
    lines.append("")
    
    flow = diag["flow_zone"]
    if flow:
        lines.append("| # | Exercise | Status | Type | Prereqs Met | Topic |")
        lines.append("|---|----------|--------|------|-------------|-------|")
        for num, ex, status in flow:
            emoji = format_mastery_emoji(ex["mastery"])
            prereq_count = len(ex["prerequisites"])
            parents = ", ".join(ex["parents"]) if ex["parents"] else "—"
            link = f"[[{ex['filename'].replace('.md', '')}|{num}]]"
            short_name = ex["name"][:55]
            ltype = ex.get("learning_type", "🔁 Procedural Drill")
            lines.append(f"| {num} | {link} {short_name} | {emoji} {status} | {ltype} | {prereq_count} met | {parents} |")
    else:
        lines.append("*No flow zone items right now. Complete more prerequisite exercises first!*")
    lines.append("")
    
    # === Type Breakdown ===
    if flow:
        type_counts = {}
        for _, ex, _ in flow:
            lt = ex.get("learning_type", "🔁 Procedural Drill")
            type_counts[lt] = type_counts.get(lt, 0) + 1
        if type_counts:
            lines.append("**📊 Today's Work Type Breakdown:**")
            lines.append("")
            for ltype in ["🧠 New Concept", "🔁 Procedural Drill", "🎯 Pattern Recognition", "📝 Applied", "🔗 Proof & Reasoning"]:
                if ltype in type_counts:
                    bar = "█" * type_counts[ltype]
                    lines.append(f"- {ltype}: {type_counts[ltype]} exercises {bar}")
            lines.append("")
            lines.append("---")
            lines.append("")
    
    # === FIRe Multiplier — Implicit Review Bonus ===
    fire_data = diag.get("fire_data", {})
    if flow and any(fire_data.get(num) for num, _, _ in flow):
        lines.append("## 🔥 FIRe Multiplier — Implicit Review Bonus")
        lines.append("")
        lines.append("*Each new exercise fractionally reviews its prerequisites. "
                      "Exercises with high multipliers let you 'review old stuff by learning new stuff.'*")
        lines.append("")
        lines.append("| # | Exercise | Prereqs Reviewed | Total FIRe Credit | Unlocks | FIRe/Prereq Ratio |")
        lines.append("|---|----------|-----------------|-----------------|---------|--------------------|")
        # Sort flow zone items by FIRe score descending
        fire_sorted = []
        for num, ex, status in flow:
            fd = fire_data.get(num, {})
            if fd.get("credits"):
                active = [c for c in fd["credits"] if not c["is_mastered"]]
                if active:
                    unmastered_str = ", ".join([f"#{c['prereq_num']}" for c in active[:5]])
                    if len(active) > 5:
                        unmastered_str += f" (+{len(active)-5} more)"
                else:
                    unmastered_str = "all mastered"
                fire_sorted.append((num, ex, fd, unmastered_str))
        fire_sorted.sort(key=lambda x: -x[2]["total_weight"])
        for num, ex, fd, active_str in fire_sorted[:10]:
            link = f"[[{ex['filename'].replace('.md', '')}|{num}]]"
            lines.append(f"| {link} | {ex['name'][:45]} | {fd['unique_count']} ({active_str}) | {fd['total_weight']:.1f}x | {fd['active_count']} active | {fd['fire_ratio']:.2f} |")
        lines.append("")
        # Highlight the single best FIRe exercise
        if fire_sorted:
            best = fire_sorted[0]
            lines.append(f"> **💡 Best FIRe pick today:** *{best[1]['name'][:60]}* — "
                         f"working on this also reviews **{best[2]['active_count']} unmastered prerequisites** "
                         f"(total FIRe credit: {best[2]['total_weight']:.1f}x)")
            lines.append("")
        lines.append("---")
        lines.append("")
    
    # === Ready to Start (entry points) ===
    ready = diag["ready_to_start"]
    if ready:
        lines.append("### 🟢 Entry Points — No Prerequisites Needed")
        lines.append("")
        lines.append("| # | Exercise | Topic |")
        lines.append("|---|----------|-------|")
        for num, ex in ready:
            parents = ", ".join(ex["parents"]) if ex["parents"] else "—"
            link = f"[[{ex['filename'].replace('.md', '')}|{num}]]"
            lines.append(f"| {num} | {link} {ex['name'][:55]} | {parents} |")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    # === In Progress / Stalled ===
    stalled = diag["stalled"]
    if stalled:
        lines.append("## ⏸️ In Progress — Needs Finishing")
        lines.append("")
        lines.append("*You've started these but haven't finished them. Best to complete before moving on.*")
        lines.append("")
        lines.append("| # | Exercise | Progress | Mastery |")
        lines.append("|---|----------|----------|---------|")
        for num, ex in stalled:
            done, total = ex["progress"]
            emoji = format_mastery_emoji(ex["mastery"])
            link = f"[[{ex['filename'].replace('.md', '')}|{num}]]"
            lines.append(f"| {num} | {link} {ex['name'][:55]} | {done}/{total} ({ex['pct']:.0%}) | {emoji} {ex['mastery']} |")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # === Blocked ===
    blocked = diag["blocked"]
    if blocked:
        lines.append("## ⛔ Blocked — Prerequisites Not Met")
        lines.append("")
        lines.append("*These exercises can't be started yet — finish the prerequisites first.*")
        lines.append("")
        lines.append("| # | Exercise | Missing Prereqs |")
        lines.append("|---|----------|-----------------|")
        for num, ex, missing in blocked[:15]:
            missing_str = "; ".join([f"#{p}" for p, n, _ in missing])
            link = f"[[{ex['filename'].replace('.md', '')}|{num}]]"
            lines.append(f"| {num} | {link} {ex['name'][:55]} | {missing_str} |")
        if len(blocked) > 15:
            lines.append(f"| ... | *{len(blocked)-15} more blocked exercises* | |")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # === Highest Leverage Exercises ===
    leverage = diag.get("leverage_exercises", [])
    if leverage:
        lines.append("## 🎯 Highest Leverage — Unlock the Most")
        lines.append("")
        lines.append("*Completing these exercises will unblock the most downstream content. Prioritise these for maximum progress.*")
        lines.append("")
        lines.append("| # | Exercise | Unlocks | Your Progress |")
        lines.append("|---|----------|---------|--------------|")
        for num, name, count, pct in leverage[:10]:
            bar = make_progress_bar(pct, 10)
            lines.append(f"| {num} | {name[:55]} | {count} exercises | {bar} {pct:.0%} |")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # === Topic Mastery Summary ===
    lines.append("## 📊 Topic Mastery Summary")
    lines.append("")
    lines.append("| Topic | Subskills | Mastery | Progress |")
    lines.append("|-------|-----------|---------|----------|")
    for topic, info in sorted(diag["topic_summary"].items()):
        if info["total"] == 0:
            continue
        bar = make_progress_bar(info["pct"])
        lines.append(f"| [[{topic}]] | {info['done']}/{info['total']} | {info['emoji']} {info['label']} | {bar} |")
    lines.append("")
    
    # === Recommendations ===
    lines.append("---")
    lines.append("")
    lines.append("## 🎯 Recommended Today's Study Plan")
    lines.append("")
    if srs:
        lines.append("### Phase 1: Review (30m)")
        lines.append("- Complete SRS-due items above")
        lines.append("")
    
    if flow:
        lines.append("### Phase 2: New Learning (45m × 2)")
        lines.append("Pick 2 flow zone exercises. Work through all subskills:")
        recommendations = flow[:6]
        for num, ex, status in recommendations:
            done, total = ex["progress"]
            link = f"[[{ex['filename'].replace('.md', '')}|{num}: {ex['name'][:50]}]]"
            lines.append(f"- {link}")
        lines.append("")
    elif ready:
        lines.append("### Phase 2: New Learning (45m × 2)")
        lines.append("Start with these entry-point exercises:")
        for num, ex in ready[:6]:
            link = f"[[{ex['filename'].replace('.md', '')}|{num}: {ex['name'][:50]}]]"
            lines.append(f"- {link}")
        lines.append("")
    
    if stalled:
        lines.append("### Phase 3: Finish In-Progress Items")
        lines.append("Close these out before they get cold:")
        for num, ex in stalled[:4]:
            done, total = ex["progress"]
            link = f"[[{ex['filename'].replace('.md', '')}|{num}: {ex['name'][:50]}]]"
            lines.append(f"- {link} ({done}/{total})")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by Math Academy Diagnostic Engine*")
    lines.append("")
    
    return "\n".join(lines)


def make_progress_bar(pct, width=20):
    filled = round(pct * width)
    empty = width - filled
    return "█" * filled + "░" * empty


def render_short_report(diag):
    """Render a compact terminal-friendly report."""
    today_str = date.today().strftime("%a %b %d")
    
    lines = []
    lines.append(f"🌊 Flow Zone Diagnostic — {today_str}")
    lines.append(f"{'='*60}")
    lines.append(f"Total: {diag['total_exercises']} exercises | Mastered: {diag['mastered_count']} ({diag['mastered_pct']:.0f}%)")
    lines.append("")
    
    # SRS
    srs = diag["srs_due"]
    lines.append(f"🔴 SRS Due Today: {len(srs)} items")
    if srs:
        for item in srs[:5]:
            lines.append(f"   • {item['skill'][:70]}")
        if len(srs) > 5:
            lines.append(f"   ... and {len(srs)-5} more")
    lines.append("")
    
    # Flow zone
    flow = diag["flow_zone"]
    fire_data = diag.get("fire_data", {})
    lines.append(f"🔥 Flow Zone (ready to learn): {len(flow)} exercises")
    for num, ex, status in flow[:10]:
        emoji = format_mastery_emoji(ex["mastery"])
        ltype = ex.get("learning_type", "")
        # FIRe indicator
        fd = fire_data.get(num, {})
        fire_tag = ""
        if fd and fd.get("total_weight", 0) > 0:
            fire_tag = f" 🔥FIRe:{fd['total_weight']:.1f}(↺{fd['active_count']})"
        lines.append(f"   {emoji} #{num} — {ex['name'][:50]} ({status}){fire_tag}  [{ltype}]")
    if len(flow) > 10:
        lines.append(f"   ... and {len(flow)-10} more")
    lines.append("")
    
    # Type breakdown (terminal)
    if flow:
        type_counts = {}
        for _, ex, _ in flow:
            lt = ex.get("learning_type", "🔁 Procedural Drill")
            type_counts[lt] = type_counts.get(lt, 0) + 1
        if type_counts:
            parts = []
            for ltype in ["🧠 New Concept", "🔁 Procedural Drill", "🎯 Pattern Recognition", "📝 Applied", "🔗 Proof & Reasoning"]:
                if ltype in type_counts:
                    parts.append(f"{ltype}: {type_counts[ltype]}")
            if parts:
                lines.append("   " + "  |  ".join(parts))
                lines.append("")
    
    # Ready to start
    ready = diag["ready_to_start"]
    if ready:
        lines.append(f"🟢 Entry Points: {len(ready)} exercises")
        for num, ex in ready[:5]:
            lines.append(f"   #{num} — {ex['name'][:60]}")
        lines.append("")
    
    # Stalled
    stalled = diag["stalled"]
    if stalled:
        lines.append(f"⏸️ In Progress: {len(stalled)} exercises")
        for num, ex in stalled[:8]:
            d, t = ex["progress"]
            lines.append(f"   #{num} — {ex['name'][:55]} ({d}/{t})")
        lines.append("")
    
    # Blocked
    blocked = diag["blocked"]
    if blocked:
        lines.append(f"⛔ Blocked (missing prereqs): {len(blocked)} exercises")
        lines.append("")
    
    # Highest leverage
    leverage = diag.get("leverage_exercises", [])
    if leverage:
        lines.append(f"🎯 Highest Leverage (unlock the most):")
        for num, name, count, pct in leverage[:8]:
            bar = make_progress_bar(pct, 10)
            lines.append(f"   #{num} — {name[:55]} → unlocks {count} exercises ({bar} {pct:.0%})")
        lines.append("")
    
    # Topic summary (compact)
    lines.append("📊 Topic Summary:")
    for topic, info in sorted(diag["topic_summary"].items()):
        if info["total"] == 0:
            continue
        bar = make_progress_bar(info["pct"], 15)
        lines.append(f"   {info['emoji']} {bar} {topic} ({info['done']}/{info['total']})")
    
    return "\n".join(lines)


def main():
    exercises, topic_progress = scan_vault()
    
    if "--sync-mastery" in sys.argv:
        # Sync frontmatter mastery + body tags to match checkbox progress
        changes = sync_exercise_mastery(exercises)
        if changes:
            print(f"🔄 Synced {len(changes)} exercise files:")
            for fname, old, new in changes:
                print(f"   {fname:55s} {old} → {new}")
        else:
            print("✅ All exercise mastery tags already in sync.")
        return
    
    if "--apply-fire" in sys.argv:
        # Apply FIRe fractional credit to SRS state.
        # Prefer the chain-weighted FSRS boost (improvement #2) when the vault
        # has been migrated; fall back to the legacy flat-interval logic otherwise.
        print("🔥 Applying FIRe fractional credit to SRS state...")
        try:
            from srs_fsrs import VaultFSRS
            v = VaultFSRS()
            seeded = sum(1 for r in v.state.get("reviews", {}).values() if "fsrs" in r)
            if seeded:
                changes = v.apply_fire_from_srs(exercises)
            else:
                changes = apply_fire_to_srs(exercises)
        except Exception as e:
            print(f"  ⚠️ FSRS path unavailable ({e}); using legacy FIRe.")
            changes = apply_fire_to_srs(exercises)
        for line in changes:
            print(line)
        return
    
    diag = build_diagnostic(exercises, topic_progress)
    
    if "--markdown" in sys.argv:
        # Auto-sync mastery tags before generating the report
        sync_changes = sync_exercise_mastery(exercises)
        # Re-scan and rebuild with fresh data
        exercises, topic_progress = scan_vault()
        diag = build_diagnostic(exercises, topic_progress)
        # Save to vault as a markdown note
        report = render_markdown_report(diag)
        output_path = VAULT / "00 - Flow Zone Diagnostic.md"
        output_path.write_text(report, encoding='utf-8')
        if sync_changes:
            print(f"🔄 Synced {len(sync_changes)} mastery tags")
        print(f"✅ Diagnostic saved to: {output_path}")
        # Regenerate the clickable Review Grader note (FSRS due + grade buttons)
        try:
            from srs_fsrs import VaultFSRS, build_grader_note
            vg = VaultFSRS()
            if any("fsrs" in r for r in vg.state.get("reviews", {}).values()):
                grader_path = VAULT / "00 - Review Grader.md"
                grader_path.write_text(build_grader_note(vg), encoding='utf-8')
                print(f"✅ Review Grader note saved to: {grader_path}")
        except Exception as e:
            print(f"  ⚠️ Review Grader note skipped ({e})")
    elif "--json" in sys.argv:
        # Machine-readable JSON
        json_output = {
            "generated": datetime.now().isoformat(),
            "total_exercises": diag["total_exercises"],
            "mastered_count": diag["mastered_count"],
            "mastered_pct": round(diag["mastered_pct"], 1),
            "flow_zone_count": len(diag["flow_zone"]),
            "srs_due_count": len(diag["srs_due"]),
            "stalled_count": len(diag["stalled"]),
            "blocked_count": len(diag["blocked"]),
            "topics": {k: {"done": v["done"], "total": v["total"], "pct": round(v["pct"], 3)}
                       for k, v in diag["topic_summary"].items()},
        }
        print(json.dumps(json_output, indent=2))
    else:
        print(render_short_report(diag))


if __name__ == "__main__":
    main()
