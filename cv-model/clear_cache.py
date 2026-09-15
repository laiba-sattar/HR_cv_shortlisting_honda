"""
Delete every stored CV extraction.

Extractions are cached by file content, so an unchanged CV is never re-read.
That is what you want almost always. Run this when you deliberately want a
fresh reading: after changing LLM_MODEL back to one you used before, or when
demonstrating that the pipeline really does call the model.

    python clear_cache.py
"""

from cv_ranker import cache
from cv_ranker.config import settings

if __name__ == "__main__":
    n = cache.clear()
    print(f"Removed {n} cached extraction(s) from {settings.extraction_cache_dir}")
