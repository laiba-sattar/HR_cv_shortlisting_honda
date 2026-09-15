"""
When deployed, one address serves both the website and the API.

Two things must hold. The API routes must still win — a request for
/api/health must never be answered with the website's index.html, or the
frontend silently falls back to demo mode and shows simulated candidates for
real uploaded CVs. And the catch-all that serves the site must not hand out
files from outside it: the same process holds the .env file with the API key.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("EMBED_PROVIDER", "hash")
os.environ.setdefault("LLM_PROVIDER", "fixture")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from api.main import FRONTEND_DIST, app

    if not FRONTEND_DIST.is_dir():
        pytest.skip("no built site present — run the frontend build first")
    return TestClient(app)


def test_api_routes_are_not_swallowed_by_the_site(client):
    """The catch-all is mounted last; /api/... must still reach the API."""
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "application/json" in r.headers["content-type"]
    assert "llm_provider" in r.json()


def test_the_site_is_served_at_the_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_unknown_paths_fall_back_to_the_site(client):
    """Client-side routes have no file of their own; they must load the app."""
    r = client.get("/history")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


@pytest.mark.parametrize("path", [
    "/../.env",
    "/../../etc/passwd",
    "/..%2f..%2f.env",
    "/cv_ranker/config.py",
])
def test_files_outside_the_site_are_never_served(client, path):
    """A traversal attempt gets the app shell, never a file from the server."""
    r = client.get(path)
    body = r.text
    assert "LLM_API_KEY" not in body
    assert "root:x:" not in body
    assert "llm_api_key" not in body
