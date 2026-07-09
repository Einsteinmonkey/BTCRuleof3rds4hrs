#!/usr/bin/env python3
"""
BTC/USDT Multi-Timeframe Rule of Thirds calculator.

Fetches public BTC-USDT candles from OKX, keeps only fully closed candles,
calculates Rule of Thirds levels, and regenerates the GitHub Pages homepage.

Shows the last 20 fully closed candles for:
- 4H
- 1D
- 1H
- 15M
"""

from __future__ import annotations

import csv
import html
import json
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

GOCHARTING_URL = "https://gocharting.com/terminal/chart/_p1jPU7Zg"
OKX_API_URL = "https://www.okx.com/api/v5/market/candles"
SYMBOL = "BTC-USDT"
CANDLE_COUNT = 20

RESULTS_DIR = Path("results")
INDEX_FILE = Path("index.html")
HISTORY_CSV_FILE = RESULTS_DIR / "history.csv"
LATEST_MD_FILE = RESULTS_DIR / "latest.md"


@dataclass(frozen=True)
class Timeframe:
    label: str
    okx_bar: str
    duration: timedelta
    title: str


TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe("4H", "4H", timedelta(hours=4), "Last 20 4-hour candles"),
    Timeframe("1D", "1Dutc", timedelta(days=1), "Last 20 1-day candles"),
    Timeframe("1H", "1H", timedelta(hours=1), "Last 20 1-hour candles"),
    Timeframe("15M", "15m", timedelta(minutes=15), "Last 20 15-minute candles"),
)


@dataclass(frozen=True)
class Candle:
    timeframe: str
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
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "btc-rule-of-thirds-github-action/2.0"},
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if payload.get("code") != "0":
        raise RuntimeError(f"OKX API error for {bar}: {payload}")

    data = payload.get("data") or []
    if not data:
        raise RuntimeError(f"OKX returned no candle data for {bar}")

    return data


def parse_okx_candles(
    raw_rows: Iterable[list[str]],
    timeframe: Timeframe,
    now: datetime,
) -> list[Candle]:
    candles: list[Candle] = []

    for row in raw_rows:
        # OKX candle format:
        # [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
        if len(row) < 5:
            continue

        open_ms = int(row[0])
        open_time = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc)
        close_time = open_time + timeframe.duration
        confirm = row[8] if len(row) > 8 else None

        # Keep only fully closed candles. OKX's latest candle can be live/unfinished.
        if confirm == "0" or close_time > now:
            continue

        candles.append(
            Candle(
                timeframe=timeframe.label,
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
    return f"{value:,.3f}"


def fetch_last_20_for_timeframe(timeframe: Timeframe, now: datetime) -> list[Candle]:
    # Fetch extra rows because the newest OKX candle can be unfinished.
    fetch_limit = max(CANDLE_COUNT + 10, 80)
    raw = fetch_okx_candles(SYMBOL, timeframe.okx_bar, fetch_limit)
    closed = parse_okx_candles(raw, timeframe, now)

    if len(closed) < CANDLE_COUNT:
        raise RuntimeError(
            f"Only found {len(closed)} closed {timeframe.label} candles; "
            f"need {CANDLE_COUNT}"
        )

    return closed[-CANDLE_COUNT:]


def latest_summary_html(label: str, candles: list[Candle]) -> str:
    latest = candles[-1]
    levels = rule_of_thirds(latest)

    return f"""
      <article class="summary-card">
        <h2>{html.escape(label)}</h2>
        <p>Latest fully closed candle · {html.escape(latest.label)}</p>
        <div class="metrics">
          <div><span>Low</span><strong>{fmt(latest.low)}</strong></div>
          <div><span>High</span><strong>{fmt(latest.high)}</strong></div>
          <div><span>Range</span><strong>{fmt(levels['range'])}</strong></div>
          <div><span>1/3</span><strong>{fmt(levels['one_third'])}</strong></div>
          <div><span>Level 1</span><strong>{fmt(levels['level_1'])}</strong></div>
          <div><span>Level 2 / Middle</span><strong>{fmt(levels['level_2'])}</strong></div>
          <div><span>Level 3 / High Avg</span><strong>{fmt(levels['level_3'])}</strong></div>
        </div>
        <p class="small">Candle close UTC: {html.escape(latest.close_time.isoformat())}</p>
      </article>
    """


def table_rows_html(candles: list[Candle]) -> str:
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


def timeframe_section_html(timeframe: Timeframe, candles: list[Candle]) -> str:
    return f"""
      <section class="table-section" id="{html.escape(timeframe.label.lower())}">
        <h2>{html.escape(timeframe.title)}</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Candle UTC</th>
                <th>Low</th>
                <th>High</th>
                <th>Range</th>
                <th>1/3</th>
                <th>Level 1</th>
                <th>Level 2 / Middle</th>
                <th>Level 3 / High Avg</th>
              </tr>
            </thead>
            <tbody>
              {table_rows_html(candles)}
            </tbody>
          </table>
        </div>
      </section>
    """


def render_index(series: dict[str, list[Candle]]) -> str:
    updated = utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
    chart_url = html.escape(GOCHARTING_URL, quote=True)

    cards = "\n".join(
        latest_summary_html(tf.label, series[tf.label]) for tf in TIMEFRAMES
    )
    sections = "\n".join(
        timeframe_section_html(tf, series[tf.label]) for tf in TIMEFRAMES
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BTC/USDT Multi-Timeframe Rule of Thirds</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b1020;
      --card: #121a2f;
      --muted: #94a3b8;
      --text: #e5e7eb;
      --line: #23304d;
      --accent: #f59e0b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    main {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 32px 0 56px;
    }}
    h1, h2 {{ margin: 0 0 12px; }}
    p {{ margin: 0 0 16px; }}
    .hero {{
      background: linear-gradient(135deg, #111827, #172554);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 26px;
      margin-bottom: 22px;
    }}
    .hero p, .small {{ color: var(--muted); }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .summary-card, .table-section {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 18px;
    }}
    .summary-card h2 {{ color: var(--accent); }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin: 12px 0;
    }}
    .metrics div {{
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.06);
      border-radius: 12px;
      padding: 10px;
    }}
    .metrics span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
    }}
    .metrics strong {{
      display: block;
      font-size: 16px;
      margin-top: 2px;
    }}
    .table-section {{ margin-top: 18px; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 900px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 8px;
      text-align: right;
      white-space: nowrap;
    }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ color: var(--muted); font-weight: 700; }}
    a.button {{
      display: inline-block;
      background: var(--accent);
      color: #111827;
      text-decoration: none;
      font-weight: 700;
      padding: 10px 14px;
      border-radius: 999px;
      margin-top: 8px;
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>BTC/USDT Rule of Thirds</h1>
      <p>Last 20 fully closed candles for 4H, 1D, 1H, and 15M.</p>
      <p class="small">Last updated UTC: {html.escape(updated)} · Data source: OKX public BTC-USDT candles.</p>
      <a class="button" href="{chart_url}" target="_blank" rel="noopener">Open chart in GoCharting →</a>
    </section>

    <section class="summary-grid">
      {cards}
    </section>

    {sections}
  </main>
</body>
</html>
"""


def write_markdown(series: dict[str, list[Candle]]) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)

    latest_rows = ["# BTC/USDT Rule of Thirds - Latest Fully Closed Candles", ""]

    for tf in TIMEFRAMES:
        candles = series[tf.label]
        latest = candles[-1]
        levels = rule_of_thirds(latest)

        latest_rows.extend(
            [
                f"## {tf.label}",
                "",
                f"Candle open UTC: {latest.open_time.isoformat()}",
                f"Candle close UTC: {latest.close_time.isoformat()}",
                f"Low: {fmt(latest.low)}",
                f"High: {fmt(latest.high)}",
                f"Range: {fmt(levels['range'])}",
                f"One Third: {fmt(levels['one_third'])}",
                f"Level 1: {fmt(levels['level_1'])}",
                f"Level 2 / Middle: {fmt(levels['level_2'])}",
                f"Level 3 / High Average: {fmt(levels['level_3'])}",
                "",
            ]
        )

        rows = [
            f"# {tf.title} - BTC/USDT Rule of Thirds",
            "",
            "| Candle UTC | Low | High | Range | 1/3 | Level 1 | Level 2 / Middle | Level 3 / High Avg |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for candle in reversed(candles):
            levels = rule_of_thirds(candle)
            rows.append(
                f"| {candle.label} | {fmt(candle.low)} | {fmt(candle.high)} | "
                f"{fmt(levels['range'])} | {fmt(levels['one_third'])} | "
                f"{fmt(levels['level_1'])} | {fmt(levels['level_2'])} | "
                f"{fmt(levels['level_3'])} |"
            )

        output_name = f"last_20_{tf.label.lower()}.md"
        (RESULTS_DIR / output_name).write_text("\n".join(rows) + "\n", encoding="utf-8")

    latest_rows.append(f"Updated UTC: {utc_now().isoformat()}")
    LATEST_MD_FILE.write_text("\n".join(latest_rows) + "\n", encoding="utf-8")


def update_history_csv(series: dict[str, list[Candle]]) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)

    fieldnames = [
        "timeframe",
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

    existing: dict[str, dict[str, str]] = {}
    if HISTORY_CSV_FILE.exists():
        with HISTORY_CSV_FILE.open("r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if "timeframe" in row and "open_time_utc" in row:
                    existing[f"{row['timeframe']}|{row['open_time_utc']}"] = row

    updated_utc = utc_now().isoformat()

    for candles in series.values():
        for candle in candles:
            levels = rule_of_thirds(candle)
            key = f"{candle.timeframe}|{candle.open_time.isoformat()}"
            existing[key] = {
                "timeframe": candle.timeframe,
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
                "updated_utc": updated_utc,
            }

    ordered_rows = [existing[key] for key in sorted(existing.keys())]

    with HISTORY_CSV_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(ordered_rows)


def main() -> int:
    try:
        now = utc_now()
        series: dict[str, list[Candle]] = {}

        for timeframe in TIMEFRAMES:
            series[timeframe.label] = fetch_last_20_for_timeframe(timeframe, now)

        write_markdown(series)
        update_history_csv(series)
        INDEX_FILE.write_text(render_index(series), encoding="utf-8")

        print("Updated BTC/USDT Rule of Thirds for 4H, 1D, 1H, and 15M")
        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
