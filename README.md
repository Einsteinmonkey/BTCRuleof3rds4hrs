# BTC/USDT 4H Rule of Thirds

This repo calculates the BTC/USDT Rule of Thirds from fully closed 4-hour candles and publishes a clean GitHub Pages results page.

It shows:

- Latest fully closed BTC/USDT 4H candle
- Last 10 days of 4H candles
- Rule of Thirds levels for each candle
- A link button to the GoCharting chart

The GoCharting chart is linked, not embedded, because shared GoCharting chart URLs may be blocked from loading inside GitHub Pages iframes.

## Formula

```text
range = high - low
one_third = range / 3
level_1 = low + one_third
level_2 = level_1 + one_third
level_3 = level_2 + one_third
```

## Data source

Rule of Thirds calculations use OKX public BTC-USDT 4H candles. The GoCharting chart link is only for visual reference.
