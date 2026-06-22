# -*- coding: utf-8 -*-
"""確定メーカー（人手URL中心）の製品一覧→詳細をBFSで巡回し成分抽出（トークンゼロ）。

★ハング対策: 各社を「タイムアウト付きの別プロセス」で実行する。1社のサイトが
  trickle 応答等で固まっても PER_MAKER_TIMEOUT 秒で打ち切り、次へ進む（全体は止まらない）。
  （以前 morinyu-pet.com で read タイムアウトをすり抜け21時間ハングした事故への対策）

除外:
  - sitemap で取得済みの大手（harvest_sitemap_products.SOURCES）
  - すでに product_facts_raw.csv に出ているメーカー
  - 処理済みログ logs/seed_processed.txt にあるメーカー（0件で終わった社も再試行しない）
出力: data/product_facts_raw.csv に追記（URL重複は除去）。後で summarize_disclosure.py で集計。
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys

from catfood_common import DATA_DIR, LOG_DIR, log_line, safe_print
from catfood_nutrition_patterns import EXTRACT_FIELDS
from extract_product_facts import crawl_site
from harvest_sitemap_products import SOURCES as SITEMAP_SOURCES

MAKER_SITES = DATA_DIR / "maker_sites.csv"
FACTS = DATA_DIR / "product_facts_raw.csv"
PROCESSED = LOG_DIR / "seed_processed.txt"
PER_MAKER_TIMEOUT = 120  # 秒/社（これを超えたら打ち切り）


def confirmed_targets() -> list[tuple[str, str]]:
    out = []
    with MAKER_SITES.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            url = (r.get("official_url") or "").strip()
            if r.get("matched") == "yes" and r.get("needs_review") == "no" and url:
                out.append((r["company_name"].strip(), url))
    return out


def existing_urls() -> set[str]:
    urls: set[str] = set()
    if FACTS.exists():
        with FACTS.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("url"):
                    urls.add(r["url"].strip())
    return urls


def existing_makers() -> set[str]:
    s: set[str] = set()
    if FACTS.exists():
        with FACTS.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("maker"):
                    s.add(r["maker"].strip())
    return s


def processed_makers() -> set[str]:
    if PROCESSED.exists():
        return set(l.strip() for l in PROCESSED.read_text(encoding="utf-8").splitlines() if l.strip())
    return set()


def mark_processed(maker: str) -> None:
    with PROCESSED.open("a", encoding="utf-8") as fh:
        fh.write(maker + "\n")


def append_facts(rows: list[dict]) -> None:
    new = not FACTS.exists()
    with FACTS.open("a", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=EXTRACT_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def run_one(maker: str, url: str, max_pages: int, sleep: float) -> None:
    """子プロセス: 1社だけcrawl→重複除去→追記。

    ★自爆タイマー: trickle応答で固まっても 75秒で os._exit する（親のkillに依存しない。
      これが無いと socket recv が requests のreadタイムアウトをすり抜けて無限待ちになる）。
    """
    import os
    import threading
    bomb = threading.Timer(75, lambda: os._exit(0))
    bomb.daemon = True
    bomb.start()
    rows = crawl_site(url, maker, max_pages, sleep)
    bomb.cancel()
    seen = existing_urls()
    rows = [r for r in rows if r.get("url") not in seen]
    if rows:
        append_facts(rows)
    safe_print(f"   [one] {maker} 追記 {len(rows)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=25)
    ap.add_argument("--sleep", type=float, default=0.8)
    ap.add_argument("--one", nargs=2, metavar=("MAKER", "URL"),
                    help="（内部用）1社だけ実行")
    args = ap.parse_args()

    if args.one:
        run_one(args.one[0], args.one[1], args.max_pages, args.sleep)
        return

    skip = set(SITEMAP_SOURCES) | existing_makers() | processed_makers()
    targets = [(m, u) for (m, u) in confirmed_targets() if m not in skip]
    safe_print(f"[seed-harvest] 対象 {len(targets)} 社（各社 {PER_MAKER_TIMEOUT}s で打ち切り）")

    hung, ok = [], 0
    for i, (maker, url) in enumerate(targets, 1):
        safe_print(f"\n({i}/{len(targets)}) {maker}  {url}")
        cmd = [sys.executable, "-u", __file__, "--one", maker, url,
               "--max-pages", str(args.max_pages), "--sleep", str(args.sleep)]
        # ★ capture_output は使わない（タイムアウト時に communicate() がパイプで
        #   デッドロックし5時間ハングした事故への対策）。出力は捨て、子は直接CSVへ追記。
        proc = subprocess.Popen(cmd, cwd=str(DATA_DIR.parent),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            proc.wait(timeout=PER_MAKER_TIMEOUT)
            safe_print("   done")
            ok += 1
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            safe_print(f"   !! TIMEOUT {PER_MAKER_TIMEOUT}s → 打ち切り（Playwright/手当て候補）")
            hung.append(maker)
        mark_processed(maker)

    safe_print(f"\n[done] 完了 {ok} / 打ち切り {len(hung)} / 計 {len(targets)}")
    if hung:
        safe_print("  打ち切り社:")
        for m in hung:
            safe_print(f"    - {m}")
    log_line("harvest_seed_sites", f"targets={len(targets)} ok={ok} hung={len(hung)}")


if __name__ == "__main__":
    main()
