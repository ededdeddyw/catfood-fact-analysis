# -*- coding: utf-8 -*-
"""取得HTMLのローカルキャッシュ（取得と抽出を分離する本丸）。

なぜ:
  * 抽出ロジックを変えるたびに全件再取得＝そのたびに trickle ハングのリスク、を断つ。
  * 一度キャッシュすれば、再抽出は**ネット不要・一瞬**（reextract_from_cache.py）。
  * ハーベストが途中で固まっても、再実行すれば既取得分はキャッシュから即返り**再開**できる。

設計: URL を sha1 でキー化し data/html_cache/<hash>.html に本文、<hash>.url に元URL。
LLM不使用。
"""
from __future__ import annotations

import hashlib

from catfood_common import DATA_DIR, polite_get

CACHE_DIR = DATA_DIR / "html_cache"


def _key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def cache_file(url: str):
    return CACHE_DIR / (_key(url) + ".html")


def read_cache(url: str) -> str | None:
    f = cache_file(url)
    if f.exists():
        return f.read_text(encoding="utf-8", errors="replace")
    return None


def write_cache(url: str, html: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file(url).write_text(html, encoding="utf-8", errors="replace")
    (CACHE_DIR / (_key(url) + ".url")).write_text(url, encoding="utf-8", errors="replace")


def fetch(url: str, *, use_cache: bool = True, **kw) -> tuple[str | None, bool]:
    """(html, from_cache) を返す。キャッシュ優先。失敗時 (None, False)。

    kw は polite_get にそのまま渡す（timeout/retries/sleep 等）。
    """
    if use_cache:
        cached = read_cache(url)
        if cached is not None:
            return cached, True
    resp = polite_get(url, **kw)
    if resp is None:
        return None, False
    write_cache(url, resp.text)
    return resp.text, False


def is_cached(url: str) -> bool:
    return cache_file(url).exists()
