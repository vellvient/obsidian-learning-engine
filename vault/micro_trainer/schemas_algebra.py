#!/usr/bin/env python3
"""
schemas_algebra.py
==================
Algebra micro-schema configurations for the CCT engine.

Batch 1 (transformation trainers — production mode):
    diff_squares    a^2 - b^2  -> (a-b)(a+b) instant recognition
    perfect_square  a^2 ± 2ab + b^2 -> (a ± b)^2 and disguised forms
    complete_square ax^2+bx+c  -> a(x+h)^2 + k
    distributive    fluent expansion of products (1, 2, 3-term factors)

Rule sets (detection mode — VALID vs DISTRACTION):
    discriminant    classify roots from b^2 - 4ac (mental pruning)
    exponent_rules  product/quotient/power/zero/negative/fractional exponents

Each schema carries generator + display + answer + solution + detection items.
"""

import random
from dataclasses import dataclass
from typing import Dict, List, Tuple

from micro_trainer import SchemaConfig


# ── polynomial formatting helpers ────────────────────────────────────────────

def fmt_poly(d: Dict[int, int]) -> str:
    """Render a power->coefficient dict as a clean polynomial string."""
    parts: List[str] = []
    for p in sorted(d, reverse=True):
        c = d[p]
        if c == 0:
            continue
        # token without sign
        if p == 0:
            body = f"{abs(c)}"
        elif p == 1:
            body = f"x" if abs(c) == 1 else f"{abs(c)}x"
        else:
            body = f"x^{p}" if abs(c) == 1 else f"{abs(c)}x^{p}"
        if not parts:
            parts.append(("-" if c < 0 else "") + body)
        else:
            parts.append((" - " if c < 0 else " + ") + body)
    return "".join(parts) if parts else "0"


def _expand_two(a: Tuple[int, int], b: Tuple[int, int]) -> Dict[int, int]:
    """(a1 x + a0) * (b1 x + b0) -> power dict."""
    (a1, a0), (b1, b0) = a, b
    return {2: a1 * b1, 1: a1 * b0 + a0 * b1, 0: a0 * b0}


def _expand_trino_bin(tri: Dict[int, int], b: Tuple[int, int]) -> Dict[int, int]:
    """(x^2 + px + q) * (b1 x + b0) -> power dict (b1 usually 1)."""
    (b1, b0) = b
    out = {0: 0, 1: 0, 2: 0, 3: 0}
    for p, c in tri.items():
        out[p + 1] += c * b1
        out[p] += c * b0
    return out


# ── 1. Difference of squares ─────────────────────────────────────────────────

def gen_diff_squares(level: int) -> dict:
    c = random.randint(2, 12)
    d = random.randint(2, 12)
    if level == 0:
        # (c x)^2 - d^2
        expr = fmt_poly({2: c * c, 0: -d * d})
        ans = f"({c}x - {d})({c}x + {d})"
    elif level == 1:
        # (c x)^2 - (d y)^2
        expr = f"{c*c}x^2 - {d*d}y^2"
        ans = f"({c}x - {d}y)({c}x + {d}y)"
    else:
        # disguised: (e x^2)^2 - f^2
        e = random.randint(2, 6)
        f = random.randint(2, 6)
        expr = f"{e*e}x^4 - {f*f}"
        ans = f"({e}x^2 - {f})({e}x^2 + {f})"
    return {"expr": expr, "ans": ans}


diff_squares = SchemaConfig(
    id="diff_squares",
    name="Difference of Squares",
    domain="Algebraic Manipulation",
    blurb="a^2 - b^2 = (a-b)(a+b) instant recognition",
    generate=gen_diff_squares,
    display=lambda p: f"Factor:  {p['expr']}",
    answer_expr=lambda p: p["ans"],
    source_expr=lambda p: p["expr"],
    must_transform=True,
    solution=lambda p: f"{p['expr']} = {p['ans']}",
    detect_items=[
        ("a^2 - b^2 = (a-b)(a+b)", True),
        ("a^2 - b^2 = (a-b)^2", False),
        ("a^2 + b^2 = (a+b)(a-b)", False),
        ("4x^2 - 9 = (2x-3)(2x+3)", True),
        ("x^2 - 1 = (x-1)^2", False),
        ("16y^2 - 25 = (4y-5)(4y+5)", True),
        ("x^2 - 4y^2 = (x-2y)^2", False),
    ],
    max_level=2,
)


# ── 2. Perfect square trinomial ──────────────────────────────────────────────

def gen_perfect_square(level: int) -> dict:
    if level == 0:
        b = random.randint(2, 9)
        expr = fmt_poly({2: 1, 1: 2 * b, 0: b * b})
        ans = f"(x + {b})^2"
    elif level == 1:
        c = random.randint(2, 5)
        d = random.randint(2, 9)
        expr = fmt_poly({2: c * c, 1: 2 * c * d, 0: d * d})
        ans = f"({c}x + {d})^2"
    else:
        e = random.randint(2, 6)
        expr = f"x^4 + {2*e}x^2 + {e*e}"
        ans = f"(x^2 + {e})^2"
    return {"expr": expr, "ans": ans}


perfect_square = SchemaConfig(
    id="perfect_square",
    name="Perfect Square Trinomial",
    domain="Algebraic Manipulation",
    blurb="a^2 ± 2ab + b^2 = (a ± b)^2 (incl. disguised forms)",
    generate=gen_perfect_square,
    display=lambda p: f"Factor:  {p['expr']}",
    answer_expr=lambda p: p["ans"],
    source_expr=lambda p: p["expr"],
    must_transform=True,
    solution=lambda p: f"{p['expr']} = {p['ans']}",
    detect_items=[
        ("x^2 + 6x + 9 = (x+3)^2", True),
        ("x^2 + 6x + 9 = (x+3)(x-3)", False),
        ("4x^2 + 12x + 9 = (2x+3)^2", True),
        ("x^2 - 10x + 25 = (x-5)^2", True),
        ("x^2 + 4x + 4 = (x+4)^2", False),
        ("x^4 + 2x^2 + 1 = (x^2+1)^2", True),
    ],
    max_level=2,
)


# ── 3. Completing the square ─────────────────────────────────────────────────

def gen_complete_square(level: int) -> dict:
    if level == 0:
        b = random.randint(-9, 9)
        while b == 0 or b % 2 != 0:
            b = random.randint(-9, 9)
        c = random.randint(-9, 9)
        expr = fmt_poly({2: 1, 1: b, 0: c})
        p = b // 2
        q = c - p * p
        ans = f"(x + {p})^2 + {q}" if q >= 0 else f"(x + {p})^2 - {-q}"
    else:
        a = random.choice([2, 3, 5])
        b = random.randint(-12, 12)
        while b == 0 or b % (2 * a) != 0:
            b = random.randint(-12, 12)
        c = random.randint(-12, 12)
        expr = fmt_poly({2: a, 1: b, 0: c})
        h = b // (2 * a)
        k = c - a * h * h
        inn = f"x + {h}" if h >= 0 else f"x - {-h}"
        ans = f"{a}({inn})^2 + {k}" if k >= 0 else f"{a}({inn})^2 - {-k}"
    return {"expr": expr, "ans": ans}


complete_square = SchemaConfig(
    id="complete_square",
    name="Completing the Square",
    domain="Algebraic Manipulation",
    blurb="ax^2 + bx + c -> a(x+h)^2 + k under time pressure",
    generate=gen_complete_square,
    display=lambda p: f"Complete the square:  {p['expr']}",
    answer_expr=lambda p: p["ans"],
    source_expr=lambda p: p["expr"],
    must_transform=True,
    solution=lambda p: f"{p['expr']} = {p['ans']}",
    detect_items=[
        ("x^2 + 4x + 7 = (x+2)^2 + 3", True),
        ("x^2 + 4x + 7 = (x+2)^2 + 11", False),
        ("2x^2 + 8x = 2(x+2)^2 - 8", True),
        ("x^2 - 6x = (x-3)^2 - 9", True),
        ("x^2 + 6x + 5 = (x+3)^2 + 5", False),
    ],
    max_level=1,
)


# ── 4. Distributive / expansion fluency ──────────────────────────────────────

def gen_distributive(level: int) -> dict:
    if level == 0:
        a0, b0 = random.randint(2, 9), random.randint(2, 9)
        poly = {2: 1, 1: a0 + b0, 0: a0 * b0}
        expr = f"(x + {a0})(x + {b0})"
    elif level == 1:
        a1, a0 = random.randint(2, 4), random.randint(2, 9)
        b1, b0 = random.randint(2, 4), random.randint(2, 9)
        poly = _expand_two((a1, a0), (b1, b0))
        expr = f"({a1}x + {a0})({b1}x + {b0})"
    else:
        a = random.randint(2, 8)
        p = random.randint(2, 6)
        q = random.randint(2, 9)
        b0 = random.randint(2, 6)
        poly = _expand_trino_bin({2: 1, 1: p, 0: q}, (1, b0))
        expr = f"(x + {a})(x^2 + {p}x + {q})"
    return {"expr": expr, "ans": fmt_poly(poly)}


distributive = SchemaConfig(
    id="distributive",
    name="Expansion Fluency",
    domain="Algebraic Manipulation",
    blurb="instant expansion of (a+b)(c+d), (a+b)(c+d+e), ...",
    generate=gen_distributive,
    display=lambda p: f"Expand:  {p['expr']}",
    answer_expr=lambda p: p["ans"],
    source_expr=lambda p: p["expr"],
    must_transform=True,
    solution=lambda p: f"{p['expr']} = {p['ans']}",
    detect_items=[
        ("(x+2)(x+3) = x^2 + 5x + 6", True),
        ("(x+2)(x+3) = x^2 + 6x + 5", False),
        ("(2x+1)(3x+4) = 6x^2 + 11x + 4", True),
        ("(x+1)(x-1) = x^2 - 1", True),
        ("(x+2)^2 = x^2 + 4", False),
    ],
    max_level=2,
)


# ── 5. Discriminant (detection-only) ─────────────────────────────────────────

discriminant = SchemaConfig(
    id="discriminant",
    name="Discriminant Pruning",
    domain="Equation Solving",
    blurb="from b^2 - 4ac, instantly classify root nature",
    generate=lambda level: {},  # not used in production mode
    display=lambda p: "",
    answer_expr=lambda p: "",
    detect_items=[
        ("Δ > 0 and perfect square → two distinct rational roots", True),
        ("Δ > 0 not square → two distinct irrational roots", True),
        ("Δ = 0 → one repeated real root", True),
        ("Δ < 0 → two complex conjugate roots", True),
        ("Δ > 0 → two complex roots", False),
        ("Δ = 0 → no real roots", False),
        ("Δ < 0 → two distinct rational roots", False),
    ],
    max_level=0,
)


# ── 6. Exponent rules (detection-only) ───────────────────────────────────────

exponent_rules = SchemaConfig(
    id="exponent_rules",
    name="Exponent Rules",
    domain="Algebraic Manipulation",
    blurb="product / quotient / power / zero / negative / fractional",
    generate=lambda level: {},
    display=lambda p: "",
    answer_expr=lambda p: "",
    detect_items=[
        ("x^a · x^b = x^(a+b)", True),
        ("x^a / x^b = x^(a-b)", True),
        ("(x^a)^b = x^(ab)", True),
        ("x^0 = 1 (x ≠ 0)", True),
        ("x^(-a) = 1/x^a", True),
        ("x^(1/2) = √x", True),
        ("x^a · x^b = x^(ab)", False),
        ("(x^a)^b = x^(a+b)", False),
        ("x^0 = 0", False),
        ("x^(-a) = -x^a", False),
    ],
    max_level=0,
)



# ── Phase 3: sum of cubes ────────────────────────────────────────────────────

def gen_sum_cubes(level: int) -> dict:
    a = random.randint(2, 6)
    b = random.randint(1, 6)
    if level == 0:
        expr = f"x^3 - {b**3}" if a == 1 else f"{a**3}x^3 - {b**3}"
        if a == 1:
            ans = f"(x - {b})(x^2 + {b}x + {b*b})"
        else:
            ans = f"({a}x - {b})({a*a}x^2 + {a*b}x + {b*b})"
    else:
        if a == 1:
            expr = f"x^3 + {b**3}"
            ans = f"(x + {b})(x^2 - {b}x + {b*b})"
        else:
            expr = f"{a**3}x^3 + {b**3}"
            ans = f"({a}x + {b})({a*a}x^2 - {a*b}x + {b*b})"
    return {"expr": expr, "ans": ans}


sum_cubes = SchemaConfig(
    id="sum_cubes",
    name="Sum / Difference of Cubes",
    domain="Algebraic Manipulation",
    blurb="a^3±b^3 → (a±b)(a^2∓ab+b^2) under time pressure",
    generate=gen_sum_cubes,
    display=lambda p: f"Factor:  {p['expr']}",
    answer_expr=lambda p: p["ans"],
    source_expr=lambda p: p["expr"],
    must_transform=True,
    solution=lambda p: f"{p['expr']} = {p['ans']}",
    detect_items=[
        ("a^3 - b^3 = (a-b)(a^2+ab+b^2)", True),
        ("a^3 + b^3 = (a+b)(a^2-ab+b^2)", True),
        ("a^3 - b^3 = (a-b)(a^2-ab+b^2)", False),
        ("x^3 - 8 = (x-2)(x^2+2x+4)", True),
        ("x^3 + 8 = (x+2)(x^2+2x+4)", False),
    ],
    max_level=1,
)


# ── Phase 3: conjugate rationalising ─────────────────────────────────────────

def gen_conjugate(level: int) -> dict:
    a = random.randint(2, 12)
    b = random.randint(2, 12)
    while b == a:
        b = random.randint(2, 12)
    if level == 0:
        expr = f"1/(√{a})"
        ans = f"√{a}/{a}"
    else:
        expr = f"1/(√{a} + √{b})" if random.random() < 0.5 else f"1/(√{a} - √{b})"
        if "+" in expr:
            ans = f"(√{a} - √{b})/({a}-{b})"
        else:
            ans = f"(√{a} + √{b})/({a}-{b})"
    return {"expr": expr, "ans": ans}


conjugate = SchemaConfig(
    id="conjugate",
    name="Conjugate Rationalising",
    domain="Surds",
    blurb="rationalise denominators using conjugates",
    generate=gen_conjugate,
    display=lambda p: f"Rationalise:  {p['expr']}",
    answer_expr=lambda p: p["ans"],
    source_expr=lambda p: p["expr"],
    must_transform=True,
    solution=lambda p: f"{p['expr']} = {p['ans']}",
    detect_items=[
        ("1/√a = √a/a", True),
        ("1/(√a+√b) = (√a-√b)/(a-b)", True),
        ("1/(√a-√b) = (√a+√b)/(a-b)", True),
        ("1/√a = a/√a", False),
        ("1/(√a+√b) = (√a+√b)/(a-b)", False),
    ],
    max_level=1,
)


# ── Phase 4: absolute value splitting ────────────────────────────────────────

def gen_abs_value(level: int) -> dict:
    c = random.randint(1, 9)
    if level == 0:
        expr = f"|x| = {c}"
        ans = f"x = {c} or x = -{c}"
    else:
        a = random.randint(1, 8)
        expr = f"|x - {a}| = {c}"
        ans = f"x = {a + c} or x = {a - c}"
    return {"expr": expr, "ans": ans}


abs_value = SchemaConfig(
    id="abs_value",
    name="Absolute Value Splitting",
    domain="Equations",
    blurb="|x-a|=c → two linear cases",
    generate=gen_abs_value,
    display=lambda p: f"Solve:  {p['expr']}",
    answer_expr=lambda p: p["ans"],
    source_expr=lambda p: p["expr"],
    must_transform=True,
    solution=lambda p: f"{p['expr']} ⇒ {p['ans']}",
    detect_items=[
        ("|x|=3 ⇒ x=3 or x=-3", True),
        ("|x-2|=5 ⇒ x=7 or x=-3", True),
        ("|x|=3 ⇒ x=3 only", False),
        ("|x-1|=0 ⇒ x=1", True),
        ("|x|=-2 has two solutions", False),
    ],
    max_level=1,
)


# ── Phase 4: log/exp fluency ─────────────────────────────────────────────────

def gen_log_exp(level: int) -> dict:
    if level == 0:
        b = random.choice([2, 3, 5, 10])
        k = random.randint(1, 5)
        expr = f"log_{b}({b**k})"
        ans = str(k)
    else:
        b = random.choice([2, 3, 5, 10])
        a = random.randint(2, 8)
        c = random.randint(2, 8)
        expr = f"log_{b}({a}) + log_{b}({c})"
        ans = f"log_{b}({a*c})"
    return {"expr": expr, "ans": ans}


log_exp = SchemaConfig(
    id="log_exp",
    name="Log / Exponential Fluency",
    domain="Exponentials and Logs",
    blurb="log laws and inverse of exp under time pressure",
    generate=gen_log_exp,
    display=lambda p: f"Simplify:  {p['expr']}",
    answer_expr=lambda p: p["ans"],
    source_expr=lambda p: p["expr"],
    must_transform=True,
    solution=lambda p: f"{p['expr']} = {p['ans']}",
    detect_items=[
        ("log_b(b^k) = k", True),
        ("log_b(xy) = log_b x + log_b y", True),
        ("log_b(x/y) = log_b x - log_b y", True),
        ("log_b(x^k) = k log_b x", True),
        ("log_b(xy) = log_b x · log_b y", False),
        ("b^{log_b x} = x", True),
    ],
    max_level=1,
)


# ── Phase 4: factor grouping ─────────────────────────────────────────────────

def gen_factor_grouping(level: int) -> dict:
    a = random.randint(1, 4)
    b = random.randint(1, 6)
    c = random.randint(1, 4)
    d = random.randint(1, 6)
    poly = {2: a * c, 1: a * d + b * c, 0: b * d}
    expr = fmt_poly(poly)
    ans = f"({a}x + {b})({c}x + {d})"
    return {"expr": expr, "ans": ans}


factor_grouping = SchemaConfig(
    id="factor_grouping",
    name="Factor Grouping",
    domain="Algebraic Manipulation",
    blurb="4-term / reverse FOIL grouping under time pressure",
    generate=gen_factor_grouping,
    display=lambda p: f"Factor:  {p['expr']}",
    answer_expr=lambda p: p["ans"],
    source_expr=lambda p: p["expr"],
    must_transform=True,
    solution=lambda p: f"{p['expr']} = {p['ans']}",
    detect_items=[
        ("x^2 + 5x + 6 = (x+2)(x+3)", True),
        ("x^2 + 5x + 6 = (x+1)(x+6)", False),
        ("2x^2 + 7x + 3 = (2x+1)(x+3)", True),
        ("x^2 - 5x + 6 = (x-2)(x-3)", True),
        ("x^2 - 5x + 6 = (x+2)(x-3)", False),
    ],
    max_level=0,
)


# ── Registry ─────────────────────────────────────────────────────────────────

ALGEBRA_SCHEMAS: List[SchemaConfig] = [
    diff_squares,
    perfect_square,
    complete_square,
    distributive,
    discriminant,
    exponent_rules,
    sum_cubes,
    conjugate,
    abs_value,
    log_exp,
    factor_grouping,
]
