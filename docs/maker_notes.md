# メーカー別 人手メモ（目検 2026-06-21）

> ユーザーが79社を目検し、キャットフードの所在を確認した記録。
> 構造化済みの確定URLは `data/maker_sites.csv`（method=human / human_memo、note列）に反映。
> ここは「セルに収まらない補足」を残す場所。

## 確定（特殊ケース）

| メーカー | URL / メモ |
|----------|-----------|
| 株式会社カラーズ | **3ブランド全部該当**: <https://yumyumyum.jp/cat/products> / <https://bioliob.com/lineup> / <https://www.green-dog.com/shop/category/cat>（maker_sites には yumyumyum を代表で登録） |
| グローバルワン株式会社 | 会社別サイトに転送される。<https://natures-taste.jp/?mode=srh&cid=&keyword=> が該当 |
| 住商アグロインターナショナル株式会社 | <https://hartz.jp/> の商品を扱う**商社**（自社ブランドでなく Hartz 扱い） |
| ドギーマンハヤシ株式会社 | ⚠️ <https://www.doggyman.com/newitem/?ca1=猫> は**新商品しか出ない**ので注意。一覧は <https://www.doggyman.com/product/> |
| アイリスオーヤマ株式会社 | <https://www.irisohyama.co.jp/products/>（公式がbot対策で requests タイムアウト＝要Playwright/手当て） |
| 株式会社レティシアン | <https://pet.laetitien.co.jp/products/catfood/>（403。UA等の手当て要） |

## 除外（キャットフードなし＝母集団対象外）

| メーカー | 理由 |
|----------|------|
| エヌピーエフジャパン株式会社 | ニップン子会社っぽい。HPなしかも |
| 特定非営利活動法人cambio | npo-cambio.org/tashika/ に転送されるが商品一覧が404 → 無視 |
| 株式会社クキ・イーアンドティー | ペット関係なし |
| ナッシュ株式会社 | キャットフードなし（nosh.jp/dog/menu はドッグのみ） |

## 要再確認（キャットフード無いかも）

| メーカー | メモ |
|----------|------|
| キョーリンフード工業株式会社 | <https://www.kyorin-net.co.jp/animal/> だがキャットフード無いかも |
| 株式会社黒龍堂 | キャットフード無いかも |
| シーズイシハラ株式会社 | キャットフード無いかも |

## 補足
- Human 列が**空欄の企業＝キャットフード無し**と判断し対象外（ユーザー目検）。
- 確定URLの多くは**製品一覧/詳細ページ**で「成分」キーワードを含む → 次フェーズ（成分ハーベスト）の良いシード。
