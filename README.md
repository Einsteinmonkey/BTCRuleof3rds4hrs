# BTC/USDT 4H Rule of Thirds

This repo automatically calculates the Rule of Thirds for BTC/USDT using fully closed 4-hour candles.

Formula:

```text
range = high - low
one_third = range / 3
level_1 = low + one_third
level_2_middle = level_1 + one_third
level_3_high_average = level_2_middle + one_third
```

The GitHub Pages homepage shows only the results:

- Latest fully closed 4H candle
- Last 10 days of fully closed 4H candles
- Embedded GoCharting chart from `https://gocharting.com/terminal/chart/_p1jPU7Zg`

Rule-of-Thirds data source: OKX public candlesticks for `BTC-USDT` with `bar=4H`.

Chart source: GoCharting shared chart link: `https://gocharting.com/terminal/chart/_p1jPU7Zg`.

## Run manually

Go to:

```text
Actions → BTC 4H Rule of Thirds → Run workflow
```

## Automatic schedule

The workflow runs every 4 hours, shortly after the 4H candle closes:

```text
00:12 UTC
04:12 UTC
08:12 UTC
12:12 UTC
16:12 UTC
20:12 UTC
```

## Files updated by the automation

```text
index.html
results/latest.md
results/last_10_days.md
results/history.csv
```

This is only a calculator/automation tool. It is not financial advice or a trading recommendation.
