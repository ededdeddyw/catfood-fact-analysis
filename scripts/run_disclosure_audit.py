# -*- coding: utf-8 -*-
"""02 開示率オーディットの自動実行（全メーカー横断）。

docs/02_data_feasibility_audit.md を「手作業50件」ではなく、確定した公式サイト群へ
extract_product_facts.crawl_site を回して自動で実測する。

入力 : data/maker_sites.csv（official_url が入っている社）
出力 :
  data/product_facts_raw.csv   … 見つかった成分ページ（既存スキーマ）
  data/disclosure_matrix.csv   … メーカー別の取得結果＋項目別開示
  標準出力                      … 02 形式の開示率マトリクス＋撤退ライン判定

方針: LLM 不使用。requests + bs4。逐次書き込み＝途中で落ちても進捗が残る・再開可能。
"""
from __future__ import annotations

import argparse
import csv

from catfood_common import DATA_DIR, log_line, safe_print, today_stamp
from catfood_nutrition_patterns import EXTRACT_FIELDS
from extract_product_facts import crawl_site

MAKER_SITES = DATA_DIR / "maker_sites.csv"
FACTS_OUT = DATA_DIR / "product_facts_raw.csv"
MATRIX_OUT = DATA_DIR / "disclosure_matrix.csv"

FIELDS = ["crude_protein", "crude_fat", "crude_fiber", "crude_ash",
          "moisture", "calorie", "phosphorus", "ingredients"]

MATRIX_COLS = (["maker", "official_url", "product_pages"]
               + [f"d_{f}" for f in FIELDS]
               + ["static_yield", "fetched_at"])


def load_targets(include_review: bool) -> list[tuple[str, str]]:
    """(maker, url) のリスト。official_url が空でない社のみ。"""
    out: list[tuple[str, str]] = []
    if not MAKER_SITES.exists():
        return out
    with MAKER_SITES.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            url = (r.get("official_url") or "").strip()
            if not url:
                continue
            if not include_review and r.get("needs_review") == "yes":
                continue
            out.append((r["company_name"].strip(), url))
    return out


def append_facts(rows: list[dict], write_header: bool) -> None:
    new = not FACTS_OUT.exists()
    with FACTS_OUT.open("a", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=EXTRACT_FIELDS, extrasaction="ignore")
        if new or write_header:
            w.writeheader()
        for row in rows:
            w.writerow(row)


def append_matrix(row: dict, write_header: bool) -> None:
    new = not MATRIX_OUT.exists()
    with MATRIX_OUT.open("a", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MATRIX_COLS, extrasaction="ignore")
        if new or write_header:
            w.writeheader()
        w.writerow(row)


def done_makers() -> set[str]:
    s: set[str] = set()
    if MATRIX_OUT.exists():
        with MATRIX_OUT.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("maker"):
                    s.add(r["maker"].strip())
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=20, help="社あたり巡回上限")
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--include-review", action="store_true",
                    help="needs_review=yes でも official_url があれば対象に含める")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    if args.fresh:
        for p in (FACTS_OUT, MATRIX_OUT):
            if p.exists():
                p.unlink()

    targets = load_targets(args.include_review)
    done = done_makers()
    todo = [(m, u) for (m, u) in targets if m not in done]
    safe_print(f"[audit] 対象 {len(targets)} 社 / 済 {len(targets)-len(todo)} / 残 {len(todo)}")

    facts_header = not FACTS_OUT.exists()
    matrix_header = not MATRIX_OUT.exists()
    stamp = today_stamp()

    for i, (maker, url) in enumerate(todo, 1):
        safe_print(f"\n({i}/{len(todo)}) {maker}  {url}")
        try:
            rows = crawl_site(url, maker, args.max_pages, args.sleep)
        except Exception as exc:
            safe_print(f"   !! {type(exc).__name__}: {exc}")
            rows = []
        if rows:
            append_facts(rows, facts_header)
            facts_header = False
        n = len(rows)
        mrow = {"maker": maker, "official_url": url, "product_pages": n,
                "static_yield": "yes" if n else "no", "fetched_at": stamp}
        for f in FIELDS:
            mrow[f"d_{f}"] = sum(1 for r in rows if r.get(f"disclosed_{f}") == "yes")
        append_matrix(mrow, matrix_header)
        matrix_header = False

    print_matrix()


def print_matrix() -> None:
    if not MATRIX_OUT.exists():
        safe_print("（マトリクスなし）")
        return
    rows = list(csv.DictReader(MATRIX_OUT.open(encoding="utf-8-sig", newline="")))
    makers_with_pages = [r for r in rows if int(r["product_pages"]) > 0]
    total_pages = sum(int(r["product_pages"]) for r in rows)
    safe_print(f"\n=== 02 開示率オーディット（自動実測 {today_stamp()}）===")
    safe_print(f"対象メーカー {len(rows)} 社 / 成分ページが取れた社 {len(makers_with_pages)} 社 / 総成分ページ {total_pages}")
    if total_pages:
        safe_print("\n[項目別 開示率（成分ページ数に対する割合）]")
        for f in FIELDS:
            c = sum(int(r[f"d_{f}"]) for r in rows)
            pct = 100 * c // total_pages if total_pages else 0
            mark = ""
            if f == "phosphorus":
                mark = ("  <- 腎臓シートの根幹（>=40% GO / 20-40% 縮小 / <20% 見送り）")
            safe_print(f"  {f:16} {c:4}/{total_pages}  ({pct:3}%){mark}")
    # 撤退ライン判定（リン）
    if total_pages:
        p = sum(int(r["d_phosphorus"]) for r in rows)
        ppct = 100 * p // total_pages
        verdict = ("GO（腎臓シート成立）" if ppct >= 40
                   else "縮小版（開示している商品だけ）" if ppct >= 20
                   else "見送り→体重管理を看板に")
        safe_print(f"\n[判定] リン開示率 {ppct}% -> {verdict}")
    log_line("run_disclosure_audit", f"makers={len(rows)} with_pages={len(makers_with_pages)} pages={total_pages}")
    safe_print(f"\n-> {MATRIX_OUT}\n-> {FACTS_OUT}")


if __name__ == "__main__":
    main()
