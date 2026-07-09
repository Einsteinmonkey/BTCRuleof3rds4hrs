#!/usr/bin/env python3
"""
BTC/USDT 4H Rule of Thirds calculator.

Fetches public BTC-USDT 4H candles from OKX, keeps only fully closed candles,
calculates the Rule of Thirds, and regenerates the GitHub Pages homepage.

Rule of Thirds:
  range = high - low
  one_third = range / 3
  level_1 = low + one_third
  level_2 = level_1 + one_third
  level_3 = level_2 + one_third
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable, List

GOCHARTING_URL = "https://gocharting.com/terminal/chart/_p1jPU7Zg"
OKX_API_URL = "https://www.okx.com/api/v5/market/candles"
RESULTS_DIR = Path("results")
INDEX_FILE = Path("index.html")
LATEST_MD_FILE = RESULTS_DIR / "latest.md"
LAST_10_MD_FILE = RESULTS_DIR / "last_10.md"
HISTORY_CSV_FILE = RESULTS_DIR / "history.csv"


@dataclass(frozen=True)
class Candle:
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float

    @property
    def label(self) -> str:
        return self.open_time.strftime("%Y-%m-%d %H:%M UTC")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def fetch_okx_candles(inst_id: str, bar: str, limit: int) -> list[list[str]]:
    params = urllib.parse.urlencode({"instId": inst_id, "bar": bar, "limit": str(limit)})
    url = f"{OKX_API_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "btc-rule-of-thirds-github-action/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if payload.get("code") != "0":
        raise RuntimeError(f"OKX API error: {payload}")

    data = payload.get("data") or []
    if not data:
        raise RuntimeError("OKX returned no candle data")
    return data


def parse_okx_4h_candles(raw_rows: Iterable[list[str]], now: datetime) -> List[Candle]:
    candles: list[Candle] = []

    for row in raw_rows:
        # OKX candle format:
        # [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
        if len(row) < 5:
            continue

        open_ms = int(row[0])
        open_time = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc)
        close_time = open_time + timedelta(hours=4)
        confirm = row[8] if len(row) > 8 else None

        # Keep only fully closed candles. OKX's latest candle can be live/unfinished.
        if confirm == "0" or close_time > now:
            continue

        candles.append(
            Candle(
                open_time=open_time,
                close_time=close_time,
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
            )
        )

    candles.sort(key=lambda candle: candle.open_time)
    return candles


def rule_of_thirds(candle: Candle) -> dict[str, float]:
    price_range = candle.high - candle.low
    one_third = price_range / 3
    level_1 = candle.low + one_third
    level_2 = level_1 + one_third
    level_3 = level_2 + one_third
    return {
        "range": price_range,
        "one_third": one_third,
        "level_1": level_1,
        "level_2": level_2,
        "level_3": level_3,
    }


def fmt(value: float) -> str:
    if value >= 1000:
        return f"{value:,.2f}"
    return f"{value:.6f}".rstrip("0").rstrip(".")


def write_markdown(latest: Candle, candles: list[Candle]) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    latest_levels = rule_of_thirds(latest)

    LATEST_MD_FILE.write_text(
        "\n".join(
            [
                "# BTC/USDT 4H Rule of Thirds",
                "",
                f"Candle open UTC: {latest.open_time.isoformat()}",
                f"Candle close UTC: {latest.close_time.isoformat()}",
                f"Low: {fmt(latest.low)}",
                f"High: {fmt(latest.high)}",
                f"Range: {fmt(latest_levels['range'])}",
                f"One Third: {fmt(latest_levels['one_third'])}",
                f"Level 1: {fmt(latest_levels['level_1'])}",
                f"Level 2 / Middle: {fmt(latest_levels['level_2'])}",
                f"Level 3 / High Average: {fmt(latest_levels['level_3'])}",
                f"Updated UTC: {utc_now().isoformat()}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = ["# Last 10 days of BTC/USDT 4H Rule of Thirds", "", "| Candle UTC | Low | High | Range | 1/3 | Level 1 | Level 2 / Middle | Level 3 / High Avg |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for candle in reversed(candles):
        levels = rule_of_thirds(candle)
        rows.append(
            f"| {candle.label} | {fmt(candle.low)} | {fmt(candle.high)} | {fmt(levels['range'])} | {fmt(levels['one_third'])} | {fmt(levels['level_1'])} | {fmt(levels['level_2'])} | {fmt(levels['level_3'])} |"
        )
    LAST_10_MD_FILE.write_text("\n".join(rows) + "\n", encoding="utf-8")


def update_history_csv(candles: list[Candle]) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    existing: dict[str, dict[str, str]] = {}

    if HISTORY_CSV_FILE.exists():
        with HISTORY_CSV_FILE.open("r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                existing[row["open_time_utc"]] = row

    for candle in candles:
        levels = rule_of_thirds(candle)
        existing[candle.open_time.isoformat()] = {
            "open_time_utc": candle.open_time.isoformat(),
            "close_time_utc": candle.close_time.isoformat(),
            "open": f"{candle.open:.10f}",
            "high": f"{candle.high:.10f}",
            "low": f"{candle.low:.10f}",
            "close": f"{candle.close:.10f}",
            "range": f"{levels['range']:.10f}",
            "one_third": f"{levels['one_third']:.10f}",
            "level_1": f"{levels['level_1']:.10f}",
            "level_2_middle": f"{levels['level_2']:.10f}",
            "level_3_high_average": f"{levels['level_3']:.10f}",
            "updated_utc": utc_now().isoformat(),
        }

    fieldnames = [
        "open_time_utc",
        "close_time_utc",
        "open",
        "high",
        "low",
        "close",
        "range",
        "one_third",
        "level_1",
        "level_2_middle",
        "level_3_high_average",
        "updated_utc",
    ]
    ordered_rows = [existing[key] for key in sorted(existing.keys())]
    with HISTORY_CSV_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(ordered_rows)


def render_table_rows(candles: list[Candle]) -> str:
    rows: list[str] = []
    for candle in reversed(candles):
        levels = rule_of_thirds(candle)
        rows.append(
            "<tr>"
            f"<td>{html.escape(candle.label)}</td>"
            f"<td>{fmt(candle.low)}</td>"
            f"<td>{fmt(candle.high)}</td>"
            f"<td>{fmt(levels['range'])}</td>"
            f"<td>{fmt(levels['one_third'])}</td>"
            f"<td>{fmt(levels['level_1'])}</td>"
            f"<td>{fmt(levels['level_2'])}</td>"
            f"<td>{fmt(levels['level_3'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_index(latest: Candle, candles: list[Candle]) -> str:
    levels = rule_of_thirds(latest)
    updated = utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
    table_rows = render_table_rows(candles)
    chart_url = html.escape(GOCHARTING_URL, quote=True)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BTC/USDT 4H Rule of Thirds</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b1017;
      --card: #151c25;
      --card-2: #0f151d;
      --text: #f4f7fb;
      --muted: #a9bad1;
      --line: #2d3948;
      --accent: #f7b955;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top, #172234 0%, var(--bg) 48%, #070b10 100%);
      color: var(--text);
    }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 48px 24px 72px; }}
    h1 {{ font-size: clamp(42px, 7vw, 76px); margin: 0 0 22px; line-height: .95; letter-spacing: -0.06em; }}
    h2 {{ margin: 0 0 16px; font-size: 24px; }}
    .card {{
      background: rgba(21, 28, 37, 0.92);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 28px;
      box-shadow: 0 22px 60px rgba(0,0,0,.25);
      margin-bottom: 28px;
    }}
    .subtle {{ color: var(--muted); font-size: 16px; margin: 0 0 24px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin: 20px 0; }}
    .metric {{ background: var(--card-2); border: 1px solid var(--line); border-radius: 18px; padding: 22px; }}
    .metric .label {{ color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: .08em; }}
    .metric .value {{ font-size: clamp(32px, 5vw, 48px); font-weight: 800; margin-top: 8px; }}
    .result-list {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
    .result-list th, .result-list td {{ border-bottom: 1px solid var(--line); padding: 14px 10px; text-align: right; }}
    .result-list th:first-child, .result-list td:first-child {{ text-align: left; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 18px; }}
    table.history {{ min-width: 900px; width: 100%; border-collapse: collapse; }}
    table.history th, table.history td {{ padding: 13px 14px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }}
    table.history th:first-child, table.history td:first-child {{ text-align: left; }}
    table.history thead th {{ color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: .08em; background: #101822; }}
    .button-card {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; }}
    .chart-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 48px;
      padding: 12px 18px;
      background: var(--accent);
      color: #111;
      border-radius: 999px;
      text-decoration: none;
      font-weight: 800;
      box-shadow: 0 10px 30px rgba(247,185,85,.22);
    }}
    .footnote {{ color: var(--muted); font-size: 14px; margin-top: 18px; }}
    @media (max-width: 720px) {{ .grid {{ grid-template-columns: 1fr; }} .card {{ padding: 20px; }} }}
  </style>
</head>
<body>
  <main>
    <h1>BTC/USDT Rule of Thirds</h1>

    <section class="card">
      <p class="subtle">Latest fully closed 4-hour candle · {html.escape(latest.label)}</p>
      <div class="grid">
        <div class="metric"><div class="label">Low</div><div class="value">{fmt(latest.low)}</div></div>
        <div class="metric"><div class="label">High</div><div class="value">{fmt(latest.high)}</div></div>
      </div>
      <table class="result-list">
        <thead><tr><th>Result</th><th>Price</th></tr></thead>
        <tbody>
          <tr><td>Range</td><td>{fmt(levels['range'])}</td></tr>
          <tr><td>One Third</td><td>{fmt(levels['one_third'])}</td></tr>
          <tr><td>Level 1</td><td>{fmt(levels['level_1'])}</td></tr>
          <tr><td>Level 2 / Middle</td><td>{fmt(levels['level_2'])}</td></tr>
          <tr><td>Level 3 / High Average</td><td>{fmt(levels['level_3'])}</td></tr>
        </tbody>
      </table>
      <p class="footnote">Candle close UTC: {html.escape(latest.close_time.isoformat())}<br>Last updated UTC: {html.escape(updated)}<br>Rule data source: OKX public BTC-USDT 4H candles.</p>
    </section>

    <section class="card">
      <h2>Last 10 days of 4H candles</h2>
      <div class="table-wrap">
        <table class="history">
          <thead>
            <tr>
              <th>Candle UTC</th><th>Low</th><th>High</th><th>Range</th><th>1/3</th><th>Level 1</th><th>Level 2 / Middle</th><th>Level 3 / High Avg</th>
            </tr>
          </thead>
          <tbody>
            {table_rows}
          </tbody>
        </table>
      </div>
    </section>

    <section class="card button-card">
      <div>
        <h2>BTC chart</h2>
        <p class="subtle" style="margin-bottom:0;">GoCharting blocks this shared chart from loading directly inside GitHub Pages, so use the button to open it.</p>
      </div>
      <a class="chart-button" href="{chart_url}" target="_blank" rel="noopener noreferrer">Open chart in GoCharting →</a>
    </section>
  </main>
</body>
</html>
"""


def write_placeholder_index() -> None:
    chart_url = html.escape(GOCHARTING_URL, quote=True)
    INDEX_FILE.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BTC/USDT 4H Rule of Thirds</title>
  <style>
    :root {{ color-scheme: dark; --bg:#0b1017; --card:#151c25; --text:#f4f7fb; --muted:#b5c3d6; --line:#2d3948; --accent:#f7b955; }}
    body {{ margin:0; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
    main {{ max-width:1020px; margin:0 auto; padding:48px 24px; }}
    h1 {{ font-size:clamp(44px,7vw,76px); margin:0 0 24px; letter-spacing:-.06em; }}
    .card {{ background:var(--card); border:1px solid var(--line); border-radius:20px; padding:24px; margin-bottom:24px; }}
    p {{ color:var(--muted); font-size:17px; line-height:1.55; }}
    a.button {{ display:inline-flex; padding:13px 18px; border-radius:999px; background:var(--accent); color:#111; text-decoration:none; font-weight:800; }}
  </style>
</head>
<body>
  <main>
    <h1>BTC/USDT Rule of Thirds</h1>
    <section class="card">
      <p>No result yet. Run the GitHub Action once and this page will update automatically with the latest 4H result and the last 10 days of 4H candles.</p>
    </section>
    <section class="card">
      <p>GoCharting chart opens in a new tab because the shared chart cannot be embedded directly on GitHub Pages.</p>
      <a class="button" href="{chart_url}" target="_blank" rel="noopener noreferrer">Open chart in GoCharting →</a>
    </section>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate BTC/USDT 4H Rule of Thirds")
    parser.add_argument("--symbol", default="BTC-USDT", help="OKX instrument ID, default BTC-USDT")
    parser.add_argument("--interval", default="4H", help="OKX candle interval, default 4H")
    parser.add_argument("--days", type=int, default=10, help="Number of days to show, default 10")
    args = parser.parse_args()

    periods_needed = args.days * 6  # six 4H candles per day for crypto
    fetch_limit = min(max(periods_needed + 10, 80), 300)

    try:
        now = utc_now()
        raw = fetch_okx_candles(args.symbol, args.interval, fetch_limit)
        closed = parse_okx_4h_candles(raw, now)
        if len(closed) < periods_needed:
            raise RuntimeError(f"Only found {len(closed)} closed candles, need {periods_needed}")

        candles = closed[-periods_needed:]
        latest = candles[-1]

        write_markdown(latest, candles)
        update_history_csv(candles)
        INDEX_FILE.write_text(render_index(latest, candles), encoding="utf-8")

        print(f"Updated BTC/USDT Rule of Thirds for {latest.label}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
