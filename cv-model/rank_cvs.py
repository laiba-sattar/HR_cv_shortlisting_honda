#!/usr/bin/env python3
"""
Command-line entry point.

    python rank_cvs.py --jd data/jds/mech_design_engineer.txt \
                       --cvs data/sample_cvs \
                       --top 10 \
                       --out results.json

If the job description is missing a mandatory requirement, the run stops and
tells you which fields to supply — the same rule the frontend enforces.
Supply them with --qualification / --experience / --age.
"""

from __future__ import annotations

import argparse
import logging
import sys

from cv_ranker.config import settings
from cv_ranker.embeddings import get_embedder
from cv_ranker.pipeline import (
    MissingRequirementsError,
    collect_cv_paths,
    prepare_job,
    run_ranking,
)


def build_overrides(args) -> dict:
    out = {}
    if args.qualification:
        out["qualification"] = {"text": args.qualification}
    if args.experience:
        out["experience"] = {"text": args.experience, "min_value": args.experience_min}
    if args.age:
        out["age"] = {"text": args.age, "min_value": args.age_min, "max_value": args.age_max}
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Rank CVs against a job description.")
    p.add_argument("--jd", required=True, help="Path to the job description file.")
    p.add_argument("--cvs", required=True, help="Folder containing CV files.")
    p.add_argument("--top", type=int, default=10, choices=[5, 10, 20, 30])
    p.add_argument("--out", default="results.json")
    p.add_argument("--skills", nargs="*", help="Override the required skills list.")
    p.add_argument("--no-transferability", action="store_true",
                   help="Skip the LLM transferability check (faster, cheaper, less accurate).")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("-v", "--verbose", action="store_true")

    # Manual values for requirements missing from the JD
    p.add_argument("--qualification")
    p.add_argument("--experience")
    p.add_argument("--experience-min", type=float)
    p.add_argument("--age")
    p.add_argument("--age-min", type=float)
    p.add_argument("--age-max", type=float)

    args = p.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )

    cv_paths = collect_cv_paths(args.cvs)
    if not cv_paths:
        print(f"No supported CV files found in {args.cvs}", file=sys.stderr)
        return 1

    print(f"LLM        : {settings.llm_provider} / {settings.llm_model}")
    print(f"Embeddings : {get_embedder().name}")
    print(f"CVs found  : {len(cv_paths)}")
    print()

    print("Reading job description…")
    job = prepare_job(
        jd_path=args.jd,
        manual_overrides=build_overrides(args),
        required_skills=args.skills,
    )
    print(f"  Title  : {job.job_title}")
    print(f"  Skills : {', '.join(job.required_skills) or '(none found)'}")
    for key in ("qualification", "experience", "age"):
        eff = job.effective(key)
        found = (job.requirements.get(key) or {}).get("mentioned")
        mark = "found in JD" if found else "NOT in JD"
        if eff["source"] == "manual":
            mark = "manual (overrides JD)"
        print(f"  {key:<14}: {mark} — {eff['text'] or '—'}")
    print()

    def progress(done: int, total: int, path: str) -> None:
        print(f"  [{done}/{total}] {path.split('/')[-1]}")

    try:
        print("Extracting and scoring…")
        run = run_ranking(
            job,
            cv_paths,
            use_llm_transferability=not args.no_transferability,
            max_workers=args.workers,
            progress=progress,
        )
    except MissingRequirementsError as e:
        print()
        print("CANNOT RANK — the job description is missing required fields:")
        for m in e.missing:
            print(f"  - {m}")
        print()
        print("Supply them and run again, e.g.:")
        print('  --experience "2-4 years relevant experience" --experience-min 2')
        return 2

    print()
    if run.failures:
        print(f"{len(run.failures)} file(s) could not be read:")
        for f in run.failures:
            print(f"  - {f.path.split('/')[-1]}: {f.reason}")
        print()

    top = run.top(args.top)
    print(f"TOP {len(top)} CANDIDATES")
    print("-" * 76)
    print(f"{'#':>2}  {'Candidate':<24} {'Final':>6} {'Qual':>6} {'Exp':>6} {'Skills':>7}")
    print("-" * 76)
    for i, s in enumerate(top, 1):
        print(f"{i:>2}  {s.candidate_name[:24]:<24} {s.final:>5.1f}% "
              f"{s.qualification.value:>5.1f}% {s.experience.value:>5.1f}% "
              f"{s.jd_skills.value:>6.1f}%")
    print("-" * 76)

    if top:
        best = top[0]
        print()
        print(f"Why {best.candidate_name} ranked first:")
        print(f"  Qualification : {best.qualification.explanation}")
        print(f"  Experience    : {best.experience.explanation}")
        print(f"  JD & skills   : {best.jd_skills.explanation}")
        if best.flags:
            print("  Flags         : " + "; ".join(best.flags))

    run.save(args.out, top_n=args.top)
    print()
    print(f"Full results with per-skill reasoning written to {args.out}")
    print("Ranking is decision support — a human makes the final call.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
