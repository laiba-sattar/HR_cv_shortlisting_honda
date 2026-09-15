#!/usr/bin/env python3
"""
Semantic sanity check — run this FIRST, before trusting any ranking.

It tests the exact thing the model has to get right: recognising that the
same skill written differently is the same skill, that a different tool in
the same discipline is related, and that unrelated things are unrelated.

    python check_semantics.py

If the PASS/FAIL column is mostly PASS, the embedding model is doing its job.
If not, change EMBED_MODEL and run it again — that is the whole point of this
script: it lets you compare models on evidence instead of reputation.
"""

from __future__ import annotations

import sys

from cv_ranker.config import settings
from cv_ranker.embeddings import cosine_matrix, embed_texts, get_embedder

# (text_a, text_b, expectation)
#   "same"      -> should be at or above the match threshold
#   "related"   -> should be clearly non-zero but may be below threshold
#   "unrelated" -> should be low
CASES: list[tuple[str, str, str]] = [
    # --- Same skill, written differently -------------------------------
    ("ReactJS", "React", "same"),
    ("React.js", "React", "same"),
    ("Node JS", "Node.js", "same"),
    ("MS Excel", "Microsoft Excel", "same"),
    ("Auto CAD", "AutoCAD", "same"),
    ("Solid Works", "SolidWorks", "same"),
    ("6 Sigma", "Six Sigma", "same"),
    ("customer support", "client relations", "same"),
    ("BSc Mechanical Engineering", "Bachelor of Science in Mechanical Engg", "same"),
    ("Production Planning", "production scheduling", "same"),

    # --- Different tool, same discipline (transferable) -----------------
    ("Vue.js", "React", "related"),
    ("SolidWorks", "Autodesk Inventor", "related"),
    ("MySQL", "PostgreSQL", "related"),
    ("Java backend development", ".NET backend development", "related"),
    ("Production Engineer", "Manufacturing Engineer", "related"),
    ("Lean Manufacturing", "Kaizen continuous improvement", "related"),

    # --- Genuinely unrelated -------------------------------------------
    ("AutoCAD", "payroll administration", "unrelated"),
    ("React", "baking and pastry", "unrelated"),
    ("Six Sigma", "veterinary surgery", "unrelated"),
]


def main() -> int:
    embedder = get_embedder()
    print(f"Embedding model : {embedder.name}")
    print(f"Match threshold : {settings.skill_match_threshold}")
    if not embedder.is_real:
        print("\n!! Non-semantic backend active. These results mean nothing.")
        print("   Set EMBED_PROVIDER=sentence_transformers to test properly.\n")

    texts = [t for pair in CASES for t in pair[:2]]
    vecs = embed_texts(texts)

    passed = failed = 0
    print()
    print(f"{'sim':>6}  {'verdict':<9} {'expected':<10} pair")
    print("-" * 78)

    for i, (a, b, expectation) in enumerate(CASES):
        sim = float(cosine_matrix(vecs[2 * i], vecs[2 * i + 1])[0][0])

        if expectation == "same":
            ok = sim >= settings.skill_match_threshold
        elif expectation == "related":
            ok = settings.skill_consider_threshold <= sim < settings.skill_match_threshold + 0.2
        else:
            ok = sim < settings.skill_consider_threshold

        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"{sim:6.3f}  {'PASS' if ok else 'FAIL':<9} {expectation:<10} {a!r} vs {b!r}")

    print("-" * 78)
    print(f"{passed} passed, {failed} failed out of {len(CASES)}")
    print()
    print("Notes:")
    print("  'same'      cases must clear the match threshold to be auto-matched.")
    print("  'related'   cases are meant to land in the middle band, where the")
    print("              LLM transferability check decides how much credit to give.")
    print("  'unrelated' cases must stay low so no LLM call is wasted on them.")
    print()
    print("If many 'same' cases fail, either the model is too weak or the")
    print("threshold is too high. Tune SKILL_MATCH_THRESHOLD against this table,")
    print("not by guesswork.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
