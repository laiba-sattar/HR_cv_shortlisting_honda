"""
Extraction cache.

Reading a CV is the expensive step: one large LLM call per file, and on a
free-tier key that call is what runs into the tokens-per-minute limit. It is
also the step that makes a re-run disagree with itself — the same CV can come
back slightly differently read, so a candidate's qualification score moves
between two runs of the same batch. For a hiring tool that is not a cosmetic
problem: HR cannot explain a number that changes on its own.

Caching the extraction by file *content* fixes both at once. The second run of
a batch costs no tokens and returns byte-identical profiles, so a shortlist can
be reproduced and audited. The key deliberately covers everything that could
change the answer — the file's bytes, the model, and the prompt itself — so a
changed prompt or a switched model re-reads rather than serving a stale answer.

One consequence worth knowing: a cached extraction freezes "years of
experience" at the moment it was first read. Over a hiring cycle that is what
you want — the same batch keeps ranking the same way. Clear the cache (delete
the folder, or set EXTRACTION_CACHE=0) when re-reading is the point.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from .config import settings

log = logging.getLogger(__name__)

# Bump when a change to parsing or post-processing should invalidate every
# stored entry, even though the prompt and model are unchanged.
CACHE_VERSION = "1"


def _hash_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_key(path: str | Path, model: str, prompt_template: str) -> str:
    """Identity of one extraction: these bytes, read by this model, this way."""
    parts = "|".join([
        CACHE_VERSION,
        _hash_file(path),
        model,
        hashlib.sha256(prompt_template.encode("utf-8")).hexdigest(),
    ])
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


def _entry_path(key: str) -> Path:
    root = Path(settings.extraction_cache_dir)
    # Two-character shard so a directory listing stays usable at 10k+ CVs.
    return root / key[:2] / f"{key}.json"


def load(key: str) -> dict[str, Any] | None:
    """Return the stored extraction, or None. Never raises — a broken cache
    entry must degrade into a fresh read, not into a failed CV."""
    if not settings.extraction_cache_enabled:
        return None
    p = _entry_path(key)
    try:
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))["output"]
    except Exception as e:  # noqa: BLE001
        log.warning("Ignoring unreadable cache entry %s: %s", p.name, e)
        return None


def store(key: str, output: dict[str, Any], source_name: str) -> None:
    """Save an extraction. Failure to cache is never failure to extract."""
    if not settings.extraction_cache_enabled:
        return
    p = _entry_path(key)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file and move it into place, so an interrupted run
        # cannot leave a half-written entry that later reads as valid JSON.
        tmp = p.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"source": source_name, "output": output}, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(p)
    except Exception as e:  # noqa: BLE001
        log.warning("Could not cache extraction for %s: %s", source_name, e)


def clear() -> int:
    """Delete every stored extraction. Returns how many were removed."""
    root = Path(settings.extraction_cache_dir)
    if not root.exists():
        return 0
    n = 0
    for f in root.rglob("*.json"):
        f.unlink(missing_ok=True)
        n += 1
    return n
