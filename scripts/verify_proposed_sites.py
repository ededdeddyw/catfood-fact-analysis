# -*- coding: utf-8 -*-
"""提案された公式URLを実取得して検証する（③ 人手確定の事実化ツール）。

入力: data/maker_url_proposals.csv  (company_name, proposed_url)
   - resolve_maker_sites.py が needs_review にした社などへ、人が候補URLを入れる。
出力: 標準出力に matched/status/root を表示（捏造を防ぐ＝必ず取得して会社名一致を確認）。

LLM API 不使用。requests + bs4 のみ。
"""
from __future__ import annotations

import csv
import sys

from bs4 import BeautifulSoup

from catfood_common import DATA_DIR, polite_get, safe_print
from resolve_maker_sites import core_name, host_of, is_noise, normalize, root_url

PROPOSALS = DATA_DIR / "maker_url_proposals.csv"


def verify(name: str, url: str) -> dict:
    core = core_name(name)
    full = normalize(name)
    if is_noise(url):
        return {"company_name": name, "proposed_url": url, "matched": "noise_domain",
                "official_url": "", "token": ""}
    resp = polite_get(url, retries=2, sleep=0.8, timeout=20)
    if resp is None:
        return {"company_name": name, "proposed_url": url, "matched": "fetch_fail",
                "official_url": "", "token": ""}
    body = normalize(BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True))
    official = root_url(getattr(resp, "url", url) or url)
    tok = ""
    if full and full in body:
        tok = "full"
    elif len(core) >= 3 and core in body:
        tok = core
    elif len(core) == 2 and core in body:
        tok = core + "(weak)"
    return {
        "company_name": name,
        "proposed_url": url,
        "matched": "yes" if tok else "no_name_on_page",
        "official_url": official if tok else "",
        "token": tok,
    }


def main() -> None:
    if not PROPOSALS.exists():
        safe_print(f"[skip] {PROPOSALS} がありません。company_name,proposed_url のCSVを作成してください。")
        return
    rows = []
    with PROPOSALS.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            name = (r.get("company_name") or "").strip()
            url = (r.get("proposed_url") or "").strip()
            if not name or not url:
                continue
            res = verify(name, url)
            flag = {"yes": "OK ", "no_name_on_page": "NAME?", "fetch_fail": "DEAD",
                    "noise_domain": "NOISE"}.get(res["matched"], "??")
            safe_print(f"[{flag}] {name}  {res['official_url'] or url}  ({res['token'] or res['matched']})")
            rows.append(res)
    ok = sum(1 for r in rows if r["matched"] == "yes")
    safe_print(f"\n[verify] {ok}/{len(rows)} 件が会社名一致で確定")


if __name__ == "__main__":
    main()
