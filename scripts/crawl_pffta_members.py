"""ペットフード公正取引協議会 会員一覧クローラ（母集団＝フード版「行政名簿」）

なぜ最初にこれを取るか:
  ②網羅性の定義（docs/catfood_concept/03_coverage_and_affiliate.md）。
  「全フード網羅」は不可能なので、表示ルールを守る加盟ブランドの母集団を宣言し、
  その中のカバー率を出すための土台にする。病院の行政名簿JOINと同型。

出力: catfood/data/pffta_members.csv
  会社名 / 郵便番号 / 住所 / 会員区分（正会員・準会員）/ 出典URL / 取得日

LLM API は使わない（トークン課金ゼロ）。HTML テーブルの素直なパースのみ。
"""
from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from catfood_common import (
    DATA_DIR,
    log_line,
    polite_get,
    safe_print,
    today_stamp,
    write_csv,
)

MEMBERS_URL = "https://pffta.org/about/members/"
FIELDNAMES = [
    "company_name",
    "postal_code",
    "address",
    "member_type",
    "source_url",
    "fetched_at",
]


def _nearest_category(table: Tag) -> str:
    """テーブル直前の見出し/テキストから 正会員 / 準会員 を判定。"""
    for prev in table.find_all_previous(string=True):
        text = str(prev).strip()
        if "準会員" in text:
            return "準会員"
        if "正会員" in text:
            return "正会員"
    return "不明"


def _is_member_table(table: Tag) -> bool:
    head = table.get_text(" ", strip=True)[:60]
    return "会社名" in head and ("住所" in head or "郵便番号" in head)


def parse_members(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    stamp = today_stamp()

    for table in soup.find_all("table"):
        if not _is_member_table(table):
            continue
        category = _nearest_category(table)
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) < 3:
                continue
            name, postal, address = cells[0], cells[1], cells[2]
            # ヘッダー行・空行を除外
            if name in ("会社名", "", "会員区分") or "会社名" in name:
                continue
            if not name:
                continue
            rows.append(
                {
                    "company_name": name,
                    "postal_code": postal,
                    "address": address,
                    "member_type": category,
                    "source_url": MEMBERS_URL,
                    "fetched_at": stamp,
                }
            )
    return rows


def main() -> None:
    safe_print(f"[GET] {MEMBERS_URL}")
    resp = polite_get(MEMBERS_URL)
    if resp is None:
        log_line("crawl_pffta_members", f"FAIL {MEMBERS_URL}")
        raise SystemExit("会員一覧の取得に失敗しました")

    rows = parse_members(resp.text)
    if not rows:
        log_line("crawl_pffta_members", "PARSED 0 rows (構造変化の可能性)")
        raise SystemExit("0件: ページ構造が変わった可能性。HTMLを確認してください")

    # 区分別件数
    seisei = sum(1 for r in rows if r["member_type"] == "正会員")
    junkai = sum(1 for r in rows if r["member_type"] == "準会員")
    out = DATA_DIR / "pffta_members.csv"
    write_csv(out, rows, FIELDNAMES)
    log_line(
        "crawl_pffta_members",
        f"OK rows={len(rows)} 正会員={seisei} 準会員={junkai}",
    )
    safe_print(f"  合計 {len(rows)} 社  （正会員 {seisei} / 準会員 {junkai}）")


if __name__ == "__main__":
    main()
