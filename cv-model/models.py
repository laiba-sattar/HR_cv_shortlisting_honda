"""
Which models can THIS account actually use?

Model IDs change. Providers retire them without warning, and availability
differs per account and per plan — so guessing an ID from documentation is
unreliable. This asks the provider directly, using the key in .env, then
tries a one-word chat call against each candidate so the answer is
"this one works", not "this one is listed".

Run:
    python models.py            # list what the account can use
    python models.py --test     # also send a tiny test call to each

Nothing here prints the API key.
"""

from __future__ import annotations

import sys

from cv_ranker.config import settings
from cv_ranker.llm import PROVIDER_BASE_URLS


def _base_url() -> str | None:
    provider = settings.llm_provider
    if provider in PROVIDER_BASE_URLS:
        return PROVIDER_BASE_URLS[provider]
    if provider in ("ollama", "openai_compatible"):
        return settings.llm_base_url
    if provider == "openai":
        return None
    return None


def main() -> int:
    provider = settings.llm_provider
    key = settings.llm_api_key

    print()
    print(f"  provider    : {provider}")
    print(f"  model in .env: {settings.llm_model}")
    print(f"  api key     : {'set (' + str(len(key)) + ' chars)' if key else 'NOT SET'}")
    print()

    if provider in ("fixture", "stub"):
        print("  This provider needs no key and has no model list.")
        print("  Set LLM_PROVIDER=groq (or another real provider) in .env first.")
        return 0

    if provider == "anthropic":
        print("  Anthropic model IDs: https://docs.claude.com/en/docs/about-claude/models")
        return 0

    if not key:
        print("  No LLM_API_KEY found in .env — nothing to ask.")
        return 1

    try:
        from openai import OpenAI
    except ImportError:
        print("  pip install openai")
        return 1

    client = OpenAI(api_key=key, base_url=_base_url(), timeout=30)

    try:
        listing = client.models.list()
    except Exception as e:  # noqa: BLE001
        print(f"  Could not list models: {e}")
        print("  Most likely the key is wrong, or the provider name in .env is wrong.")
        return 1

    ids = sorted(m.id for m in listing.data)
    if not ids:
        print("  The provider returned an empty model list.")
        return 1

    # Whisper/TTS/guard models can't do this job — hide them so the list is
    # short enough to actually read.
    skip = ("whisper", "tts", "guard", "embed", "moderation", "distil")
    chat = [i for i in ids if not any(s in i.lower() for s in skip)]

    print(f"  {len(ids)} models on this account, {len(chat)} usable for extraction:")
    print()
    for i in chat:
        mark = "  <-- currently in .env" if i == settings.llm_model else ""
        print(f"    {i}{mark}")
    print()

    if settings.llm_model not in ids:
        print(f"  '{settings.llm_model}' is NOT in that list. That is the 404.")
        print("  Copy one of the IDs above into LLM_MODEL in .env, then restart the backend.")
        print()

    if "--test" not in sys.argv:
        print("  Run 'python models.py --test' to check which ones really answer.")
        return 0

    print("  Testing each (one short call, JSON mode):")
    print()
    working = []
    for i in chat:
        try:
            r = client.chat.completions.create(
                model=i,
                max_tokens=32,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": 'Reply with {"ok": true}'}],
            )
            body = (r.choices[0].message.content or "").strip().replace("\n", " ")
            print(f"    OK    {i}  -> {body[:40]}")
            working.append(i)
        except Exception as e:  # noqa: BLE001
            reason = str(e).split("\n")[0][:70]
            print(f"    FAIL  {i}  -> {reason}")
    print()
    if working:
        print("  Put one of these in .env as LLM_MODEL:")
        for i in working:
            print(f"    LLM_MODEL={i}")
    else:
        print("  None answered. Check the key and the provider name in .env.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
