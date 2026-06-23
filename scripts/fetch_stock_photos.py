# -*- coding: utf-8 -*-
"""Wikimedia Commons から猫の実写フリー素材を取得（キー不要・PD/CC0優先）。

リンク切れ回避のため画像を data/stock_candidates/ に**ダウンロードして自己ホスト**。
ライセンス/作者も記録（クレジット用）。中身は人(Claude)がReadで目視検証してから採用する。
"""
from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request

from catfood_common import DATA_DIR, safe_print

OUT = DATA_DIR / "stock_candidates"
API = "https://commons.wikimedia.org/w/api.php"
UA = "CatFoodFactBot/0.1 (https://github.com/ededdeddyw/catfood-fact-analysis; research)"
HDRS = {"User-Agent": UA, "Referer": "https://commons.wikimedia.org/", "Accept": "image/*"}

QUERIES = ["cat eating food bowl", "kitten eating food", "cat eating from bowl",
           "tabby cat closeup", "cute kitten", "cat portrait face",
           "cat sitting indoor", "domestic cat looking"]
WANT_LICENSE = ("cc0", "public domain", "cc by")  # 小文字一致で許容


def api_get(params: dict) -> dict:
    params = {**params, "format": "json"}
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def search(q: str) -> list[dict]:
    data = api_get({
        "action": "query", "generator": "search",
        "gsrsearch": q, "gsrnamespace": "6", "gsrlimit": "8",
        "prop": "imageinfo", "iiprop": "url|extmetadata|mime|size",
        "iiurlwidth": "1280",
    })
    out = []
    for pid, page in (data.get("query", {}).get("pages", {}) or {}).items():
        ii = (page.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {}) or {}
        lic = (meta.get("LicenseShortName", {}) or {}).get("value", "")
        artist = (meta.get("Artist", {}) or {}).get("value", "")
        mime = ii.get("mime", "")
        if not ii.get("thumburl") or "image" not in mime:
            continue
        out.append({
            "title": page.get("title", ""),
            "thumburl": ii.get("thumburl", ""),
            "descurl": ii.get("descriptionurl", ""),
            "license": lic, "artist_html": artist[:200], "query": q,
            "width": ii.get("thumbwidth"), "height": ii.get("thumbheight"),
        })
    return out


def lic_ok(lic: str) -> bool:
    l = (lic or "").lower()
    return any(w in l for w in WANT_LICENSE)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    seen = set()
    rows = []
    for q in QUERIES:
        for c in search(q):
            if c["title"] in seen or not lic_ok(c["license"]):
                continue
            seen.add(c["title"])
            rows.append(c)
    safe_print(f"[stock] 候補 {len(rows)} 件（PD/CC0/CC BY）")
    # download
    manifest = []
    for i, c in enumerate(rows, 1):
        ext = c["thumburl"].rsplit(".", 1)[-1].split("?")[0].lower()
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        fn = f"cand_{i:02d}.{ext}"
        ok = False
        for attempt in (1, 2):
            try:
                req = urllib.request.Request(c["thumburl"], headers=HDRS)
                with urllib.request.urlopen(req, timeout=40) as r:
                    (OUT / fn).write_bytes(r.read())
                ok = True
                break
            except Exception as exc:
                last = f"{type(exc).__name__}"
                time.sleep(1.0)
        if ok:
            c["file"] = fn
            manifest.append(c)
            safe_print(f"  {fn:14} {c['license'][:18]:18} {c['title'][:50]}")
        else:
            safe_print(f"  [skip] {last} {c['title'][:40]}")
        time.sleep(0.5)
    with (OUT / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "title", "license", "artist_html",
                                           "descurl", "query", "width", "height", "thumburl"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(manifest)
    safe_print(f"[stock] DL {len(manifest)} 件 -> {OUT}")


if __name__ == "__main__":
    main()
