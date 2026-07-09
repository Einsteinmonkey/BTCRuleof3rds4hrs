#!/usr/bin/env python3
"""Calculate BTC/USDT 4H Rule of Thirds levels from OKX public candles.

This script is designed for GitHub Actions + GitHub Pages. It fetches the most
recent closed 4-hour candles, calculates the rule-of-thirds levels, and writes:
  - index.html
  - results/latest.md
  - results/last_10_days.md
  - results/history.csv

No API key is required. This is not financial advice.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Iterable

getcontext().prec = 28

ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results"
LATEST_MD = RESULTS_DIR / "latest.md"
LAST_10_MD = RESULTS_DIR / "last_10_days.md"
HISTORY_CSV = RESULTS_DIR / "history.csv"
INDEX_HTML = ROOT / "index.html"

OKX_CANDLES_URL = "https://www.okx.com/api/v5/market/candles"
SOURCE_LABEL = "OKX public candles"
GOCHARTING_CHART_URL = "https://gocharting.com/terminal/chart/_p1jPU7Zg"


@dataclass(frozen=True)
class CandleResult:
    symbol: str
    interval: str
    start: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    range_value: Decimal
    one_third: Decimal
    level_1: Decimal
    level_2_middle: Decimal
    level_3_high_average: Decimal


def parse_decimal(value: str) -> Decimal:
    return Decimal(value)


def q(value: Decimal, places: str = "0.01") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def money(value: Decimal) -> str:
    return f"${float(q(value)):,.2f}"


def number(value: Decimal) -> str:
    return f"{float(q(value)):,.2f}"


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def label_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def fetch_okx_candles(symbol: str, interval: str, limit: int = 100) -> list[list[str]]:
    params = urllib.parse.urlencode({"instId": symbol, "bar": interval, "limit": str(limit)})
    url = f"{OKX_CANDLES_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "btc-rule-of-thirds-github-action/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - keep GitHub Actions logs clear
        raise RuntimeError(f"Could not fetch candles from OKX: {exc}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OKX returned invalid JSON: {body[:300]}") from exc

    if payload.get("code") != "0":
        raise RuntimeError(f"OKX API error: {payload}")

    data = payload.get("data") or []
    if not data:
        raise RuntimeError("OKX returned no candle data.")

    return data


def candle_to_result(row: list[str], symbol: str, interval: str) -> CandleResult:
    # OKX row format:
    # [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
    start = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
    close_time = start + timedelta(hours=4)
    open_price = parse_decimal(row[1])
    high = parse_decimal(row[2])
    low = parse_decimal(row[3])
    close = parse_decimal(row[4])

    range_value = high - low
    one_third = range_value / Decimal("3")
    level_1 = low + one_third
    level_2_middle = level_1 + one_third
    level_3_high_average = level_2_middle + one_third

    return CandleResult(
        symbol=symbol,
        interval=interval,
        start=start,
        close_time=close_time,
        open=open_price,
        high=high,
        low=low,
        close=close,
        range_value=range_value,
        one_third=one_third,
        level_1=level_1,
        level_2_middle=level_2_middle,
        level_3_high_average=level_3_high_average,
    )


def get_closed_results(symbol: str, interval: str, days: int) -> list[CandleResult]:
    # Ten days of 4H candles = 60 closed candles. Fetch extra for safety.
    candles_needed = max(days * 6, 1)
    raw_rows = fetch_okx_candles(symbol=symbol, interval=interval, limit=min(max(candles_needed + 20, 80), 100))

    closed_rows: list[list[str]] = []
    for row in raw_rows:
        if len(row) < 9:
            continue
        confirm = str(row[8])
        if confirm == "1":
            closed_rows.append(row)

    if not closed_rows:
        raise RuntimeError("No fully closed candles were returned by OKX.")

    results = [candle_to_result(row, symbol, interval) for row in closed_rows]
    results.sort(key=lambda item: item.start)
    return results[-candles_needed:]


def latest_markdown(latest: CandleResult, updated_at: datetime) -> str:
    return f"""# {latest.symbol} {latest.interval} Rule of Thirds

Latest fully closed 4-hour candle: **{label_dt(latest.start)}** to **{label_dt(latest.close_time)}**

| Result | Price |
|---|---:|
| Low | {money(latest.low)} |
| High | {money(latest.high)} |
| Range | {money(latest.range_value)} |
| One Third | {money(latest.one_third)} |
| Level 1 | {money(latest.level_1)} |
| Level 2 / Middle | {money(latest.level_2_middle)} |
| Level 3 / High Average | {money(latest.level_3_high_average)} |

Updated UTC: {iso(updated_at)}  
Source: {SOURCE_LABEL}
"""


def last_10_markdown(results: list[CandleResult], updated_at: datetime) -> str:
    rows = [
        "# Last 10 Days - BTC/USDT 4H Rule of Thirds",
        "",
        f"Updated UTC: {iso(updated_at)}",
        "",
        "| Candle Start UTC | Low | High | Range | One Third | Level 1 | Level 2 / Middle | Level 3 / High Avg |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in reversed(results):
        rows.append(
            "| "
            + " | ".join(
                [
                    label_dt(item.start),
                    money(item.low),
                    money(item.high),
                    money(item.range_value),
                    money(item.one_third),
                    money(item.level_1),
                    money(item.level_2_middle),
                    money(item.level_3_high_average),
                ]
            )
            + " |"
        )
    rows.append("")
    return "\n".join(rows)


def render_table_rows(results: Iterable[CandleResult]) -> str:
    rows = []
    for item in reversed(list(results)):
        rows.append(
            "<tr>"
            f"<td>{html.escape(label_dt(item.start))}</td>"
            f"<td>{html.escape(money(item.low))}</td>"
            f"<td>{html.escape(money(item.high))}</td>"
            f"<td>{html.escape(money(item.range_value))}</td>"
            f"<td>{html.escape(money(item.one_third))}</td>"
            f"<td>{html.escape(money(item.level_1))}</td>"
            f"<td>{html.escape(money(item.level_2_middle))}</td>"
            f"<td>{html.escape(money(item.level_3_high_average))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_index(results: list[CandleResult], updated_at: datetime, days: int) -> str:
    latest = results[-1]
    table_rows = render_table_rows(results)
    candle_count = len(results)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BTC/USDT 4H Rule of Thirds</title>
  <style>
    :root {{
      --bg: #0b0f14;
      --card: #151a21;
      --card-2: #0f141b;
      --border: #2a3441;
      --text: #f6f8fb;
      --muted: #a7b1c2;
      --accent: #f7931a;
      --accent-soft: rgba(247, 147, 26, 0.16);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: radial-gradient(circle at top, #182230 0, var(--bg) 42%);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    main {{
      width: min(1180px, calc(100% - 32px));
      margin: 42px auto;
    }}
    .card {{
      background: rgba(21, 26, 33, 0.94);
      border: 1px solid var(--border);
      border-radius: 22px;
      padding: 28px;
      box-shadow: 0 24px 80px rgba(0,0,0,0.35);
    }}
    .topline {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      flex-wrap: wrap;
      margin-bottom: 24px;
    }}
    h1 {{
      font-size: clamp(2.1rem, 5vw, 4.3rem);
      line-height: 1;
      margin: 0 0 10px;
      letter-spacing: -0.05em;
    }}
    .subtitle, .meta, footer {{ color: var(--muted); }}
    .badge {{
      border: 1px solid rgba(247,147,26,0.5);
      background: var(--accent-soft);
      color: #ffd199;
      border-radius: 999px;
      padding: 8px 12px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin: 24px 0;
    }}
    .box {{
      background: var(--card-2);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 18px;
    }}
    .label {{
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .08em;
      font-size: .8rem;
      margin-bottom: 4px;
    }}
    .value {{
      font-size: clamp(2rem, 5vw, 3.1rem);
      font-weight: 850;
      letter-spacing: -0.04em;
    }}
    .levels {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 20px 0 26px;
    }}
    .level .value {{ font-size: clamp(1.2rem, 2vw, 1.65rem); }}
    h2 {{
      margin: 34px 0 12px;
      font-size: clamp(1.2rem, 3vw, 1.75rem);
    }}
    .table-wrap {{
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 16px;
      max-height: 650px;
      background: var(--card-2);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 980px;
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      text-align: right;
      white-space: nowrap;
    }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{
      position: sticky;
      top: 0;
      background: #111821;
      color: var(--muted);
      font-weight: 750;
      z-index: 1;
    }}
    tr:hover td {{ background: rgba(247,147,26,0.08); }}
    .chart-section {{
      margin-top: 30px;
    }}
    .chart-frame-wrap {{
      overflow: hidden;
      border: 1px solid var(--border);
      border-radius: 16px;
      background: var(--card-2);
      min-height: 720px;
    }}
    .chart-frame {{
      display: block;
      width: 100%;
      height: 720px;
      border: 0;
      background: var(--card-2);
    }}
    .chart-link {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-top: 12px;
      color: #ffd199;
      text-decoration: none;
      font-weight: 750;
    }}
    .chart-link:hover {{ text-decoration: underline; }}
    footer {{
      margin-top: 22px;
      font-size: .92rem;
    }}
    @media (max-width: 760px) {{
      main {{ width: min(100% - 20px, 1180px); margin: 18px auto; }}
      .card {{ padding: 18px; border-radius: 18px; }}
      .summary, .levels {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="card">
      <div class="topline">
        <div>
          <h1>BTC/USDT Rule of Thirds</h1>
          <div class="subtitle">Latest fully closed 4-hour candle: {html.escape(label_dt(latest.start))}</div>
        </div>
        <div class="badge">4H · Last {days} days</div>
      </div>

      <div class="summary">
        <div class="box">
          <div class="label">Low</div>
          <div class="value">{html.escape(number(latest.low))}</div>
        </div>
        <div class="box">
          <div class="label">High</div>
          <div class="value">{html.escape(number(latest.high))}</div>
        </div>
      </div>

      <div class="levels">
        <div class="box level">
          <div class="label">Range</div>
          <div class="value">{html.escape(number(latest.range_value))}</div>
        </div>
        <div class="box level">
          <div class="label">One Third</div>
          <div class="value">{html.escape(number(latest.one_third))}</div>
        </div>
        <div class="box level">
          <div class="label">Level 1</div>
          <div class="value">{html.escape(number(latest.level_1))}</div>
        </div>
        <div class="box level">
          <div class="label">Level 2 / Middle</div>
          <div class="value">{html.escape(number(latest.level_2_middle))}</div>
        </div>
      </div>

      <div class="box">
        <div class="label">Level 3 / High Average</div>
        <div class="value">{html.escape(number(latest.level_3_high_average))}</div>
      </div>

      <div class="meta" style="margin-top:18px;">
        Candle close UTC: {html.escape(iso(latest.close_time))}<br>
        Last updated UTC: {html.escape(iso(updated_at))}<br>
        Source: {html.escape(SOURCE_LABEL)}
      </div>

      <h2>Last {days} days of 4H candles</h2>
      <div class="subtitle" style="margin-bottom:12px;">Showing {candle_count} fully closed 4-hour candles, newest first.</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Candle Start UTC</th>
              <th>Low</th>
              <th>High</th>
              <th>Range</th>
              <th>One Third</th>
              <th>Level 1</th>
              <th>Level 2 / Middle</th>
              <th>Level 3 / High Avg</th>
            </tr>
          </thead>
          <tbody>
            {table_rows}
          </tbody>
        </table>
      </div>

      <section class="chart-section">
        <h2>BTC 4H chart</h2>
        <div class="subtitle" style="margin-bottom:12px;">GoCharting chart provided from your shared chart link.</div>
        <div class="chart-frame-wrap">
          <iframe
            class="chart-frame"
            src="{html.escape(GOCHARTING_CHART_URL)}"
            title="BTC 4H GoCharting chart"
            loading="lazy"
            allowfullscreen>
          </iframe>
        </div>
        <a class="chart-link" href="{html.escape(GOCHARTING_CHART_URL)}" target="_blank" rel="noopener noreferrer">Open chart in GoCharting →</a>
      </section>

      <footer>
        This page is an automated calculator only. It is not financial advice or a trading recommendation.
      </footer>
    </section>
  </main>
</body>
</html>
"""


def append_history(latest: CandleResult, updated_at: datetime) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    fieldnames = [
        "run_updated_utc",
        "candle_start_utc",
        "candle_close_utc",
        "symbol",
        "interval",
        "open",
        "low",
        "high",
        "close",
        "range",
        "one_third",
        "level_1",
        "level_2_middle",
        "level_3_high_average",
        "source",
    ]

    existing: dict[tuple[str, str, str], dict[str, str]] = {}
    if HISTORY_CSV.exists():
        with HISTORY_CSV.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row.get("symbol", ""), row.get("interval", ""), row.get("candle_start_utc", ""))
                existing[key] = row

    row = {
        "run_updated_utc": iso(updated_at),
        "candle_start_utc": iso(latest.start),
        "candle_close_utc": iso(latest.close_time),
        "symbol": latest.symbol,
        "interval": latest.interval,
        "open": str(q(latest.open)),
        "low": str(q(latest.low)),
        "high": str(q(latest.high)),
        "close": str(q(latest.close)),
        "range": str(q(latest.range_value)),
        "one_third": str(q(latest.one_third)),
        "level_1": str(q(latest.level_1)),
        "level_2_middle": str(q(latest.level_2_middle)),
        "level_3_high_average": str(q(latest.level_3_high_average)),
        "source": SOURCE_LABEL,
    }
    existing[(latest.symbol, latest.interval, iso(latest.start))] = row

    rows = sorted(existing.values(), key=lambda r: r.get("candle_start_utc", ""))
    with HISTORY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="BTC/USDT 4H Rule of Thirds calculator")
    parser.add_argument("--symbol", default="BTC-USDT", help="OKX instrument ID, e.g. BTC-USDT")
    parser.add_argument("--interval", default="4H", help="OKX candle interval, e.g. 4H")
    parser.add_argument("--days", type=int, default=10, help="Number of 24-hour days to display")
    args = parser.parse_args()

    updated_at = datetime.now(timezone.utc)
    results = get_closed_results(symbol=args.symbol, interval=args.interval, days=args.days)
    latest = results[-1]

    RESULTS_DIR.mkdir(exist_ok=True)
    LATEST_MD.write_text(latest_markdown(latest, updated_at), encoding="utf-8")
    LAST_10_MD.write_text(last_10_markdown(results, updated_at), encoding="utf-8")
    INDEX_HTML.write_text(render_index(results, updated_at, args.days), encoding="utf-8")
    append_history(latest, updated_at)

    print(f"Updated {INDEX_HTML.relative_to(ROOT)}")
    print(f"Latest candle: {label_dt(latest.start)} to {label_dt(latest.close_time)}")
    print(f"Low={latest.low} High={latest.high} Level1={latest.level_1} Level2={latest.level_2_middle}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - print a clear GitHub Actions error
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
