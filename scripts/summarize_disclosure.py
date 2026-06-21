# -*- coding: utf-8 -*-
"""product_facts_raw.csv から開示率を集計し直す（クロール非依存）。

run_disclosure_audit.py は「巡回しながら」集計するが、sitemap ハーベスト
(harvest_sitemap_products.py) で追記したデータも含めて、いつでも最新の
開示率マトリクスを再生成できるようにした standalone 版。

出力:
  data/disclosure_matrix.csv  … メーカー別×項目別の開示数（再生成）
  標準出力                     … 全体開示率＋メーカー別リン＋撤退ライン判定
"""
from __future__ import annotations

import csv
from collections import defaultdict

from catfood_common import DATA_DIR, safe_print, today_stamp

FACTS = DATA_DIR / "product_facts_raw.csv"
MATRIX = DATA_DIR / "disclosure_matrix.csv"
FIELDS = ["crude_protein", "crude_fat", "crude_fiber", "crude_ash",
          "moisture", "calorie", "phosphorus", "ingredients"]
COLS = ["maker", "product_pages"] + [f"d_{f}" for f in FIELDS] + ["phosphorus_pct"]


def main() -> None:
    rows = list(csv.DictReader(FACTS.open(encoding="utf-8-sig", newline="")))
    n = len(rows)
    if not n:
        safe_print("（データ0件）")
        return

    by = defaultdict(lambda: defaultdict(int))
    counts = defaultdict(int)
    for r in rows:
        m = r["maker"]
        counts[m] += 1
        for f in FIELDS:
            if r.get(f"disclosed_{f}") == "yes":
                by[m][f] += 1

    # マトリクス再生成
    with MATRIX.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for m in sorted(counts, key=lambda x: -counts[x]):
            t = counts[m]
            row = {"maker": m, "product_pages": t,
                   "phosphorus_pct": 100 * by[m]["phosphorus"] // t}
            for f in FIELDS:
                row[f"d_{f}"] = by[m][f]
            w.writerow(row)

    safe_print(f"=== 開示率サマリ（{today_stamp()} / 総成分ページ {n}）===")
    for f in FIELDS:
        c = sum(by[m][f] for m in counts)
        safe_print(f"  {f:16} {c:4}/{n}  ({100*c//n:3}%)")

    safe_print("\n=== メーカー別リン開示（製品数順）===")
    for m in sorted(counts, key=lambda x: -counts[x]):
        t = counts[m]
        p = by[m]["phosphorus"]
        safe_print(f"  {m[:22]:22} {t:4}p  リン {p:3} ({100*p//t:3}%)")

    p_all = sum(by[m]["phosphorus"] for m in counts)
    ppct = 100 * p_all // n
    # 開示する社だけに絞った場合のカバー（縮小版の現実性）
    discloser_pages = sum(counts[m] for m in counts if counts[m] and by[m]["phosphorus"] / counts[m] >= 0.4)
    verdict = ("GO（腎臓シート成立）" if ppct >= 40
               else "縮小版＝リン開示メーカーに絞れば成立" if ppct >= 20
               else "見送り")
    safe_print(f"\n[全体] リン開示率 {ppct}%  -> {verdict}")
    safe_print(f"[縮小版] リン開示率40%以上のメーカーの製品 {discloser_pages} ページが腎臓シート母体になり得る")


if __name__ == "__main__":
    main()
