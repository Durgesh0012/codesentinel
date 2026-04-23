"""
CodeSentinel Performance Evaluation System
==========================================

Scores agent performance on a scale of 1–10,000.
Runs a battery of test cases across bug detection, security, and performance categories.

Score Formula:
  Raw Score = Σ (category_weight × correctness_ratio × speed_factor)
  Final Score = Raw Score × 100  (normalized to 0–10,000)
"""

import time
import json
from typing import TypedDict
from src.agent import chat, reset_session

# ─── Test Cases ────────────────────────────────────────────────────────────────

class TestCase(TypedDict):
    id: str
    category: str          # "bug" | "security" | "performance" | "clean"
    weight: float          # importance weight (sums to 1.0 across all)
    code: str
    expected_keywords: list[str]   # keywords the agent MUST mention
    forbidden_keywords: list[str]  # false-positive traps (agent should NOT flag)
    description: str

TEST_CASES: list[TestCase] = [
    # ── Bug Detection ──────────────────────────────────────────────────────────
    {
        "id": "BUG-001",
        "category": "bug",
        "weight": 0.12,
        "code": """
def get_user(users, id):
    for u in users:
        if u['id'] == id:
            return u['name']
    # Returns None implicitly — caller does users[0]['name'].upper() without checking
""",
        "expected_keywords": ["none", "null", "return", "check", "AttributeError"],
        "forbidden_keywords": [],
        "description": "Missing None check — classic AttributeError trap",
    },
    {
        "id": "BUG-002",
        "category": "bug",
        "weight": 0.12,
        "code": """
def merge_dicts(a, b):
    result = a
    result.update(b)
    return result
""",
        "expected_keywords": ["mutates", "original", "copy", "a.copy", "reference"],
        "forbidden_keywords": [],
        "description": "Mutates input dict — aliasing bug",
    },
    {
        "id": "BUG-003",
        "category": "bug",
        "weight": 0.10,
        "code": """
total = 0
items = [1, 2, 3, 4, 5]
for i in range(len(items) + 1):
    total += items[i]
""",
        "expected_keywords": ["IndexError", "off-by-one", "range(len"],
        "forbidden_keywords": [],
        "description": "Off-by-one error — IndexError",
    },

    # ── Security ───────────────────────────────────────────────────────────────
    {
        "id": "SEC-001",
        "category": "security",
        "weight": 0.15,
        "code": """
import sqlite3
def get_user(username):
    conn = sqlite3.connect('db.sqlite')
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor.execute(query)
    return cursor.fetchone()
""",
        "expected_keywords": ["injection", "SQL", "parameterized", "?", "placeholder"],
        "forbidden_keywords": [],
        "description": "SQL Injection vulnerability",
    },
    {
        "id": "SEC-002",
        "category": "security",
        "weight": 0.13,
        "code": """
import subprocess
def run_command(user_input):
    result = subprocess.run(f"ls {user_input}", shell=True, capture_output=True)
    return result.stdout
""",
        "expected_keywords": ["injection", "shell=True", "shell=False", "sanitize", "command"],
        "forbidden_keywords": [],
        "description": "Shell injection via shell=True",
    },

    # ── Performance ────────────────────────────────────────────────────────────
    {
        "id": "PERF-001",
        "category": "performance",
        "weight": 0.10,
        "code": """
def find_duplicates(lst):
    duplicates = []
    for i in range(len(lst)):
        for j in range(len(lst)):
            if i != j and lst[i] == lst[j] and lst[i] not in duplicates:
                duplicates.append(lst[i])
    return duplicates
""",
        "expected_keywords": ["O(n²)", "O(n^2)", "quadratic", "set", "Counter", "seen"],
        "forbidden_keywords": [],
        "description": "O(n³) duplicate finder — should suggest O(n) with set",
    },
    {
        "id": "PERF-002",
        "category": "performance",
        "weight": 0.08,
        "code": """
import re
def validate_emails(emails):
    results = []
    for email in emails:
        pattern = re.compile(r'^[\\w.+-]+@[\\w-]+\\.[\\w.]+$')
        results.append(bool(pattern.match(email)))
    return results
""",
        "expected_keywords": ["compile", "outside", "loop", "recompile"],
        "forbidden_keywords": [],
        "description": "Regex recompiled every iteration — should compile outside loop",
    },

    # ── False-Positive / Clean Code Test ──────────────────────────────────────
    {
        "id": "CLEAN-001",
        "category": "clean",
        "weight": 0.10,
        "code": """
from typing import Optional

def divide(a: float, b: float) -> Optional[float]:
    \"\"\"Safely divide two numbers. Returns None if b is zero.\"\"\"
    if b == 0:
        return None
    return a / b
""",
        "expected_keywords": ["clean", "correct", "safe", "good", "well"],
        "forbidden_keywords": ["bug", "critical", "vulnerability", "issue"],
        "description": "Clean code — agent must NOT flag false positives",
    },
    {
        "id": "CLEAN-002",
        "category": "clean",
        "weight": 0.10,
        "code": """
def fibonacci(n: int) -> list[int]:
    \"\"\"Return Fibonacci sequence up to n terms.\"\"\"
    if n <= 0:
        return []
    if n == 1:
        return [0]
    seq = [0, 1]
    while len(seq) < n:
        seq.append(seq[-1] + seq[-2])
    return seq
""",
        "expected_keywords": ["correct", "clean", "good", "efficient", "no"],
        "forbidden_keywords": ["critical", "vulnerability", "security", "injection"],
        "description": "Clean Fibonacci — agent must NOT hallucinate bugs",
    },
]

# ─── Category Weights ─────────────────────────────────────────────────────────
CATEGORY_MULTIPLIERS = {
    "bug": 1.0,
    "security": 1.2,    # security issues weighted higher
    "performance": 0.9,
    "clean": 1.1,       # avoiding false positives is important
}

SPEED_THRESHOLDS = {
    "excellent": (0, 5),     # < 5s   → 1.0x
    "good":      (5, 12),    # 5–12s  → 0.9x
    "fair":      (12, 25),   # 12–25s → 0.75x
    "slow":      (25, 999),  # > 25s  → 0.6x
}

def speed_factor(elapsed: float) -> float:
    if elapsed < 5:  return 1.0
    if elapsed < 12: return 0.9
    if elapsed < 25: return 0.75
    return 0.6

def score_response(response: str, tc: TestCase) -> dict:
    """Score one test case response."""
    response_lower = response.lower()

    # Check expected keywords
    expected_hits = [kw for kw in tc["expected_keywords"]
                     if kw.lower() in response_lower]
    expected_ratio = len(expected_hits) / max(len(tc["expected_keywords"]), 1)

    # Check forbidden keywords (false positives)
    forbidden_hits = [kw for kw in tc["forbidden_keywords"]
                      if kw.lower() in response_lower]
    false_positive_penalty = len(forbidden_hits) / max(len(tc["forbidden_keywords"]), 1)

    correctness = expected_ratio * (1 - false_positive_penalty * 0.5)
    return {
        "expected_hits": expected_hits,
        "forbidden_hits": forbidden_hits,
        "correctness": round(correctness, 3),
    }


def run_evaluation(verbose: bool = True) -> dict:
    """
    Run all test cases and compute the final 1–10,000 score.
    
    Score Formula:
      For each test case:
        case_score = weight × category_multiplier × correctness × speed_factor
      
      raw_total = Σ case_scores  (max possible ≈ 1.0 if perfect)
      final_score = round(raw_total × 10_000)
    """
    if verbose:
        print("=" * 60)
        print("  🧪 CodeSentinel Performance Evaluation")
        print("=" * 60)

    results = []
    total_weighted_score = 0.0
    total_possible = 0.0

    for tc in TEST_CASES:
        reset_session()

        prompt = f"Review this code for bugs, security issues, and performance problems:\n\n```python\n{tc['code']}\n```"

        start = time.time()
        response = chat(prompt)
        elapsed = time.time() - start

        scoring = score_response(response, tc)
        sf = speed_factor(elapsed)
        cm = CATEGORY_MULTIPLIERS[tc["category"]]

        case_score = tc["weight"] * cm * scoring["correctness"] * sf
        max_case   = tc["weight"] * cm * 1.0 * 1.0
        total_weighted_score += case_score
        total_possible += max_case

        result = {
            "id": tc["id"],
            "category": tc["category"],
            "description": tc["description"],
            "correctness": scoring["correctness"],
            "speed_seconds": round(elapsed, 2),
            "speed_factor": sf,
            "case_score": round(case_score, 4),
            "expected_hits": scoring["expected_hits"],
            "false_positives": scoring["forbidden_hits"],
        }
        results.append(result)

        if verbose:
            icon = "✅" if scoring["correctness"] >= 0.7 else ("⚠️" if scoring["correctness"] >= 0.4 else "❌")
            print(f"\n{icon} [{tc['id']}] {tc['description']}")
            print(f"   Correctness: {scoring['correctness']:.0%} | Speed: {elapsed:.1f}s | Case Score: {case_score:.4f}")

    # Normalize to 1–10,000
    normalized = total_weighted_score / total_possible if total_possible > 0 else 0
    final_score = round(normalized * 10_000)

    summary = {
        "final_score": final_score,
        "max_possible": 10_000,
        "normalized_ratio": round(normalized, 4),
        "total_tests": len(TEST_CASES),
        "breakdown": results,
        "grade": grade(final_score),
    }

    if verbose:
        print("\n" + "=" * 60)
        print(f"  🏆 FINAL SCORE: {final_score} / 10,000")
        print(f"  📊 Grade: {summary['grade']}")
        print("=" * 60)

    return summary


def grade(score: int) -> str:
    if score >= 9000: return "S — Exceptional"
    if score >= 7500: return "A — Excellent"
    if score >= 6000: return "B — Good"
    if score >= 4500: return "C — Adequate"
    if score >= 3000: return "D — Needs Improvement"
    return "F — Poor"


if __name__ == "__main__":
    result = run_evaluation(verbose=True)
    with open("eval/results.json", "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n📁 Results saved to eval/results.json")
