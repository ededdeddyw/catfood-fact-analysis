"""キャットフード分析サービス — クロール共通ユーティリティ

方針（病院プロジェクト準拠）:
* LLM API は使わない（トークン課金ゼロ）。requests + BeautifulSoup + 正規表現のみ。
* 一次ソース優先・出典URL + 取得日を必ず残す。
* 礼儀正しいクロール: User-Agent 明示・sleep・リトライ・失敗ログ。
* Windows(cp932) でも落ちないログ/CSV出力（utf-8 / utf-8-sig）。
"""
from __future__ import annotations

import csv
import sys
import time
from datetime import date
from pathlib import Path

import requests

# --- パス（catfood/ 配下で完結。病院データには触れない） ---
ROOT = Path(__file__).resolve().parents[1]          # .../catfood
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (compatible; CatFoodFactBot/0.1; "
    "research; respects robots & rate limits)"
)
DEFAULT_HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.8"}


def safe_print(*args) -> None:
    """cp932 端末でも絵文字・全角ダッシュで落ちない print。"""
    msg = " ".join(str(a) for a in args)
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        sys.stdout.buffer.write(msg.encode("utf-8", "replace"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.flush()


def today_stamp() -> str:
    return date.today().isoformat()


def polite_get(
    url: str,
    *,
    timeout: int = 20,
    retries: int = 3,
    sleep: float = 1.5,
    backoff: float = 2.0,
) -> requests.Response | None:
    """リトライ + sleep 付き GET。文字コードは apparent_encoding で補正。

    失敗時は None を返し、呼び出し側でログ化する（例外で全体を止めない）。
    """
    last = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            if resp.status_code == 200:
                if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                    resp.encoding = resp.apparent_encoding
                time.sleep(sleep)  # サーバー負荷軽減
                return resp
            last = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            last = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(sleep * (backoff ** (attempt - 1)))
    safe_print(f"[FAIL] {url} ({last})")
    return None


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    """utf-8-sig で CSV 出力（Excel で文字化けしない）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    safe_print(f"[WRITE] {path}  ({len(rows)} rows)")


def log_line(name: str, message: str) -> None:
    """logs/{name}.log に追記（取得履歴・失敗理由）。"""
    line = f"{today_stamp()}\t{message}\n"
    with (LOG_DIR / f"{name}.log").open("a", encoding="utf-8") as fh:
        fh.write(line)
