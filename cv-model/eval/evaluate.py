#!/usr/bin/env python3
"""
Accuracy evaluation harness.

This is the thing that lets you say "the system is accurate" with evidence
instead of a demo. Build the gold set once, then re-run this after every
model, prompt or threshold change to see whether you improved or regressed.

Two measurements:

1. FIELD ACCURACY — did extraction pull the right values out of the CV?
   Precision / recall / F1 per field against human-verified ground truth.

2. RANKING AGREEMENT — does the system's ordering match HR's manual ranking?
   Spearman's rho, Kendall's tau, and top-N overlap.

Usage:
    python eval/evaluate.py --gold eval/gold/ --cvs data/sample_cvs \
                            --jd data/jds/mech_design_engineer.txt

Gold format — one JSON file per CV in --gold, named after the CV file:

    {
      "source_file": "ayesha_khan.txt",
      "qualifications": [{"degree_title": "...", "level": "bachelors",
                          "field_of_study": "Mechanical Engineering"}],
      "skills": ["Solid Works", "Auto CAD", "GD&T"],
      "total_experience_years": 4.0,
      "hr_rank": 1          // HR's manual position for this JD, 1 = best
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cv_ranker.extract import extract_cv_safe  # noqa: E402
from cv_ranker.pipeline import prepare_job, run_ranking  # noqa: E402


# ---------------------------------------------------------------------------
# Rank correlation, implemented directly so scipy is not a hard dependency
# ---------------------------------------------------------------------------


def spearman_rho(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 2:
        return float("nan")

    def ranks(xs: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: xs[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else float("nan")


def kendall_tau(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 2:
        return float("nan")
    con = dis = 0
    for i in range(n):
        for j in range(i + 1, n):
            sa = (a[i] - a[j])
            sb = (b[i] - b[j])
            if sa * sb > 0:
                con += 1
            elif sa * sb < 0:
                dis += 1
    total = con + dis
    return (con - dis) / total if total else float("nan")


# ---------------------------------------------------------------------------
# Field-level accuracy
# ---------------------------------------------------------------------------


def prf(predicted: set[str], truth: set[str]) -> tuple[float, float, float]:
    if not predicted and not truth:
        return 1.0, 1.0, 1.0
    tp = len(predicted & truth)
    p = tp / len(predicted) if predicted else 0.0
    r = tp / len(truth) if truth else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def norm(s: str) -> str:
    """Loose normalisation for comparison only — never for storage."""
    return "".join(ch for ch in s.lower() if ch.isalnum())


def evaluate_extraction(gold_dir: Path, cv_dir: Path) -> dict[str, Any]:
    results: dict[str, list[float]] = {"skills_f1": [], "level_correct": [], "years_abs_error": []}
    per_file = []

    for gold_path in sorted(gold_dir.glob("*.json")):
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        cv_path = cv_dir / gold["source_file"]
        if not cv_path.exists():
            print(f"  skip: {cv_path} not found")
            continue

        profile, err = extract_cv_safe(str(cv_path))
        if profile is None:
            print(f"  FAIL: {cv_path.name}: {err}")
            continue

        pred_skills = {norm(s) for s in profile.skills}
        true_skills = {norm(s) for s in gold.get("skills", [])}
        p, r, f1 = prf(pred_skills, true_skills)

        gold_levels = [q["level"] for q in gold.get("qualifications", [])]
        pred_levels = [q.level for q in profile.qualifications]
        level_ok = float(bool(gold_levels) and bool(pred_levels)
                         and pred_levels[0] == gold_levels[0])

        pred_years = sum(e.duration_years for e in profile.experience)
        true_years = float(gold.get("total_experience_years", 0))
        years_err = abs(pred_years - true_years)

        results["skills_f1"].append(f1)
        results["level_correct"].append(level_ok)
        results["years_abs_error"].append(years_err)
        per_file.append({
            "file": gold["source_file"],
            "skills_precision": round(p, 3),
            "skills_recall": round(r, 3),
            "skills_f1": round(f1, 3),
            "level_correct": bool(level_ok),
            "years_predicted": round(pred_years, 2),
            "years_truth": true_years,
            "flags": profile.extraction_notes,
        })

    def mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else float("nan")

    return {
        "n": len(per_file),
        "skills_f1_mean": round(mean(results["skills_f1"]), 3),
        "level_accuracy": round(mean(results["level_correct"]), 3),
        "years_mean_abs_error": round(mean(results["years_abs_error"]), 2),
        "per_file": per_file,
    }


# ---------------------------------------------------------------------------
# Ranking agreement
# ---------------------------------------------------------------------------


def evaluate_ranking(gold_dir: Path, cv_dir: Path, jd_path: str,
                     overrides: dict | None = None) -> dict[str, Any]:
    hr_rank: dict[str, int] = {}
    for gp in sorted(gold_dir.glob("*.json")):
        g = json.loads(gp.read_text(encoding="utf-8"))
        if "hr_rank" in g:
            hr_rank[g["source_file"]] = int(g["hr_rank"])
    if len(hr_rank) < 2:
        return {"error": "Need at least 2 gold files with an 'hr_rank' field."}

    cv_paths = [str(cv_dir / name) for name in hr_rank if (cv_dir / name).exists()]
    job = prepare_job(jd_path=jd_path, manual_overrides=overrides)
    run = run_ranking(job, cv_paths, use_llm_transferability=False)

    sys_scores, hr_positions, rows = [], [], []
    for s in run.top():
        name = Path(s.source_file or "").name
        if name not in hr_rank:
            continue
        sys_scores.append(s.final)
        # Invert rank so higher = better, matching the score direction.
        hr_positions.append(-float(hr_rank[name]))
        rows.append({"file": name, "system_score": s.final, "hr_rank": hr_rank[name]})

    sys_order = [r["file"] for r in sorted(rows, key=lambda r: -r["system_score"])]
    hr_order = [r["file"] for r in sorted(rows, key=lambda r: r["hr_rank"])]

    overlaps = {}
    for n in (5, 10):
        if len(rows) >= n:
            overlaps[f"top_{n}_overlap"] = len(set(sys_order[:n]) & set(hr_order[:n])) / n

    return {
        "n": len(rows),
        "spearman_rho": round(spearman_rho(sys_scores, hr_positions), 3),
        "kendall_tau": round(kendall_tau(sys_scores, hr_positions), 3),
        **{k: round(v, 3) for k, v in overlaps.items()},
        "system_order": sys_order,
        "hr_order": hr_order,
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate extraction and ranking accuracy.")
    ap.add_argument("--gold", required=True)
    ap.add_argument("--cvs", required=True)
    ap.add_argument("--jd", help="Run the ranking-agreement evaluation too.")
    ap.add_argument("--out", default="eval/report.json")
    args = ap.parse_args()

    gold_dir, cv_dir = Path(args.gold), Path(args.cvs)
    report: dict[str, Any] = {}

    print("Evaluating extraction accuracy…")
    report["extraction"] = evaluate_extraction(gold_dir, cv_dir)
    e = report["extraction"]
    print(f"  files evaluated       : {e['n']}")
    print(f"  skills F1 (mean)      : {e['skills_f1_mean']}")
    print(f"  degree level accuracy : {e['level_accuracy']}")
    print(f"  experience yrs MAE    : {e['years_mean_abs_error']}")

    if args.jd:
        print("\nEvaluating ranking agreement with HR…")
        report["ranking"] = evaluate_ranking(gold_dir, cv_dir, args.jd)
        r = report["ranking"]
        if "error" in r:
            print("  " + r["error"])
        else:
            print(f"  candidates            : {r['n']}")
            print(f"  Spearman rho          : {r['spearman_rho']}   (1.0 = identical order)")
            print(f"  Kendall tau           : {r['kendall_tau']}")
            for k in ("top_5_overlap", "top_10_overlap"):
                if k in r:
                    print(f"  {k:<22}: {r[k]}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFull report written to {args.out}")
    print("\nInterpretation: treat rho >= 0.7 and top-10 overlap >= 0.7 as a")
    print("reasonable bar for a pilot, and agree the real threshold with HR")
    print("before the system influences any hiring decision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
