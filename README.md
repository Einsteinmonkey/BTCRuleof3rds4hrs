# BTC/USDT Multi-Timeframe Rule of Thirds

This repo calculates BTC/USDT Rule of Thirds levels from fully closed OKX candles and publishes a GitHub Pages results page.

It shows the last 20 fully closed candles for:

- 4H
- 1D
- 1H
- 15M

## Formula

```text
range = high - low
one_third = range / 3
level_1 = low + one_third
level_2 = level_1 + one_third
level_3 = level_2 + one_third
```

## Data source

Rule of Thirds calculations use OKX public BTC-USDT candles. The GoCharting chart link is only for visual reference.
