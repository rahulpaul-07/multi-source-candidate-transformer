"""GitHub extractor — unstructured source via the public API.

For determinism (same inputs -> same output) and offline runs, this reads a
**cached fixture** by default: a saved copy of the GitHub API response. Live
fetching is opt-in (allow_network=True) and never used in tests or the demo.
A production version would fetch live and write through to this same cache.

Maps: name -> full_name, bio -> headline, profile/blog -> links, location ->
location.{city,country}, repo languages -> skills.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from ..schema import Method, Observation, SourceRecord, SourceType
from .base import Extractor, register

_URL = re.compile(r"^https?://(www\.)?github\.com/", re.I)


def _username(ref: str) -> Optional[str]:
    r = ref.strip()
    if r.endswith(".github.json"):
        return None
    r = r[7:] if r.lower().startswith("github:") else r
    r = _URL.sub("", r)
    r = r.strip("/").split("/")[0]
    r = r[:-4] if r.endswith(".git") else r
    return r or None


class GitHubExtractor(Extractor):
    source_type = SourceType.GITHUB

    def __init__(self, cache_dir: str = "samples/github_cache", allow_network: bool = False):
        self.cache_dir = cache_dir
        self.allow_network = allow_network

    def _fixture_path(self, ref: str) -> Optional[str]:
        if ref.strip().endswith(".github.json"):
            return ref.strip()
        user = _username(ref)
        return os.path.join(self.cache_dir, f"{user}.github.json") if user else None

    def extract(self, ref: str) -> list[SourceRecord]:
        path = self._fixture_path(ref)
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        elif self.allow_network and _username(ref):
            data = self._fetch_live(_username(ref))   # pragma: no cover (opt-in)
        else:
            raise FileNotFoundError(f"no GitHub fixture for {ref!r} (network disabled)")
        return [self._profile_to_record(data)]

    def _profile_to_record(self, d: dict) -> SourceRecord:
        rec = SourceRecord(source=self.source_type)
        add = lambda f, v, raw=None: rec.observations.append(Observation(
            field=f, value=v, source=self.source_type, method=Method.API, raw=raw))

        if d.get("name"):
            add("full_name", str(d["name"]).strip(), d.get("name"))
        if d.get("bio"):
            add("headline", str(d["bio"]).strip(), d.get("bio"))

        gh = d.get("html_url") or (f"https://github.com/{d['login']}" if d.get("login") else None)
        if gh:
            add("links.github", gh)
        if d.get("blog"):
            add("links.portfolio", str(d["blog"]).strip(), d.get("blog"))

        loc = (d.get("location") or "").strip()
        if loc:
            parts = [p.strip() for p in loc.split(",") if p.strip()]
            if parts:
                add("location.city", parts[0], loc)
            if len(parts) >= 2:
                add("location.country", parts[-1], loc)

        # languages: explicit list, else aggregated from repos (deterministic order)
        langs = d.get("languages")
        if not langs:
            langs = []
            for repo in d.get("repos", []):
                lang = repo.get("language")
                if lang and lang not in langs:
                    langs.append(lang)
        for lang in langs:
            if isinstance(lang, str) and lang.strip():
                add("skills", lang.strip(), {"from": "repo_language"})

        return rec

    def _fetch_live(self, user: str) -> dict:   # pragma: no cover (opt-in, networked)
        import urllib.request
        with urllib.request.urlopen(f"https://api.github.com/users/{user}", timeout=10) as r:
            profile = json.load(r)
        with urllib.request.urlopen(f"https://api.github.com/users/{user}/repos?per_page=100", timeout=10) as r:
            profile["repos"] = json.load(r)
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(os.path.join(self.cache_dir, f"{user}.github.json"), "w", encoding="utf-8") as fh:
            json.dump(profile, fh, indent=2)        # write through to cache
        return profile


register(GitHubExtractor())
