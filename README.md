# BiBot

BiBot is a single-pair Binance Spot trading bot. The strategy is implemented in `grid.py` and combines a fixed-step grid with a separate stagnation-order layer for unusually long periods of inactivity near the yearly range extremes.

Run only one instance of the bot for a given trading pair and account at a time. The bot can cancel open orders for its configured symbol during a grid rebuild.

## Strategy At A Glance

The bot has two layers. The grid is the primary strategy. The stagnation layer is an occasional extra order, designed to add BTC more readily at relatively low prices and reduce BTC more conservatively at relatively high prices.

```text
                        Binance Spot account
                                 |
                  +--------------+--------------+
                  |                             |
          Fixed-step grid                Stagnation opportunity
          tracked in memory              not tracked by the grid
                  |                             |
       Rebuilds after grid order       Places one extra limit order
       fill or cancellation             only after time/range checks
```

The stagnation layer never updates the grid reference price and never adds its order ID to `buy_orders` or `sell_orders`.

## Base Grid Logic

At any time, the grid is centered on a reference price `R`. With price step `S` and `numOrders = N`, it creates:

| Side | Price for level `i` | Quantity |
| --- | --- | --- |
| Buy | `R - (i + 1) * S` | Initial buy quantity plus `i * buyIncrement` |
| Sell | `R + (i + 1) * S` | Fixed `sellQuantity` |

`i` starts at zero. Prices and quantities are rounded down to the symbol's Binance `tickSize` and `stepSize`; each order must also satisfy the symbol's minimum notional requirement.

### Buy Quantity Progression

The first buy quantity of a rebuilt grid is determined by the most recent relevant trade:

- After a grid buy fill: the filled cumulative quantity plus `buyIncrement`.
- After a grid sell fill: `initialBuyQuantity`.
- On startup or after a cancellation-only rebuild: the account's most recent trade is used as the fallback. This may be a stagnation-order trade; that behavior is intentional for this version.

This makes consecutive grid buys progressively larger, while a sell resets the next buy size back to the initial amount.

### Reference Price Movement

For each fully filled tracked grid order:

- A buy fill moves `R` down by one `priceStep`.
- A sell fill moves `R` up by one `priceStep`.

The bot does not chase price upward. If its active tracked grid orders remain open, it waits rather than moving the grid because market price rose.

### Rebuild Rules

The bot tracks only IDs it created as normal grid orders.

```text
Tracked grid order reaches a terminal state
                |
                v
Main loop reconciles the account through REST
                |
                +-- FILLED: move reference price for the filled side
                |
                +-- CANCELED / EXPIRED / REJECTED: keep the reference price
                |
                v
Cancel remaining open orders for the configured symbol
                |
                v
Create the next grid from the updated state
```

Manual cancellation of a tracked grid order is therefore treated as a rebuild request. A cancellation alone does not move the reference price.

## Stagnation Opportunity Orders

The bot adds an optional limit order when the market has stayed inactive for a long time near the lower or upper end of the historical range.

### Range Position

The bot fetches daily candles for `history_symbol` (default `BTCUSDT`) over `lookback_days` (default `365`). It takes the highest daily high and lowest daily low, then evaluates the current price of the actual trading pair (default `BTCU`):

```text
range_position = (current_price - range_low) / (range_high - range_low)
```

The implementation intentionally uses `BTCUSDT` only as a history source. It does not convert prices between `U` and `USDT`, following the design assumption that their difference is negligible for this range classification.

### Low-Range Buy

An extra buy order is eligible only when all conditions hold:

- `enable_stagnation_buy` is enabled.
- `range_position <= low_percentile` (default `0.20`).
- The account has had no trade for at least `stagnation_buy_hours` (default `24`).
- The global stagnation cooldown has expired (default `48` hours).
- There is enough free quote balance and the order meets minimum notional.

Quantity rule:

- If the latest account trade was a buy, use exactly that trade's cumulative order quantity.
- If the latest account trade was a sell, use `stagnation_buy_qty_default`.

### High-Range Sell

An extra sell order is eligible only when all conditions hold:

- `enable_stagnation_sell` is enabled.
- `range_position >= high_percentile` (default `0.90`).
- The account has had no trade for at least `stagnation_sell_hours` (default `48`).
- The global stagnation cooldown has expired.
- There is enough free base-asset balance and the order meets minimum notional.

The sell quantity is always `stagnation_sell_qty`.

### Order Price, Balance, and Cooldown

Both opportunity orders use Binance `LIMIT_MAKER` (maker-only) orders. If an order would immediately match and take liquidity, Binance rejects it instead of allowing a taker fill; the bot leaves the cooldown unchanged and retries during the next scheduled check.

- A stagnation buy is placed one price tick below the latest price.
- A stagnation sell is placed one price tick above the latest price.

Only `free` balance is considered available for an opportunity order. Funds already locked by grid orders are not counted. The cooldown starts only after a real order is accepted, or after a simulated trigger in dry-run mode.

### Interaction With The Grid

| Situation | Result |
| --- | --- |
| A stagnation order remains open while tracked grid orders remain open | Both remain active. |
| A tracked grid order later requires a rebuild | `cancel_open_orders(symbol=pair)` cancels the unfilled stagnation order too. |
| A stagnation order fills first | The grid ignores that WebSocket event and keeps its existing reference price and tracked orders. |
| A grid order is manually canceled after a stagnation fill | The subsequent fallback rebuild may use the stagnation trade as the latest account trade. This is accepted behavior. |
| The process restarts | In-memory grid state and the stagnation cooldown are lost; initialization falls back to REST account data and the latest account trade. |

## Event And Reconciliation Model

The bot uses WebSocket for speed and REST for authoritative reconciliation.

```text
Binance User Data Stream executionReport
                |
                v
Cache tracked terminal grid events
                |
                v
Main thread calls update_orders()
                |
                +-- REST balances, open orders, and order status
                +-- rebuild grid when required
                +-- retry failed terminal-event processing with exponential backoff

Every restReconcileInterval (default: 5 minutes)
                |
                +-- REST grid reconciliation
                +-- stagnation opportunity check
```

Only terminal events for tracked grid orders trigger an immediate grid update. `FILLED` changes the reference price; `CANCELED`, `EXPIRED`, `EXPIRED_IN_MATCH`, and `REJECTED` trigger a rebuild without being treated as a fill. Cached terminal events are removed only after successful processing. Failed processing is retried with exponential backoff, capped at five minutes.

The WebSocket connection is proactively restarted before Binance's 24-hour connection lifetime. Systemd watchdog heartbeats are sent every 15 seconds when the service supports them.

## Configuration

All configuration is at the top of `grid.py`. These are the current defaults:

```python
initialBuyQuantity = 0.003
buyIncrement = 0.0003
sellQuantity = 0.003
priceStep = 1000
baseAsset = 'BTC'
quoteAsset = 'U'
pair = 'BTCU'
numOrders = 1
dryRun = True

history_symbol = 'BTCUSDT'
lookback_days = 365
low_percentile = Decimal('0.20')
high_percentile = Decimal('0.90')
stagnation_buy_hours = 24
stagnation_sell_hours = 48
stagnation_cooldown_hours = 24
stagnation_buy_qty_default = Decimal('0.003')
stagnation_sell_qty = Decimal('0.003')
```

Before changing a pair, verify its `PRICE_FILTER`, `LOT_SIZE`, and minimum-notional rules. The bot loads those filters automatically at startup, but it cannot make an invalid strategy quantity economically sensible.

## Dry Run

`dryRun = True` is the default.

In dry-run mode the bot reads private account data and public market data, prints grid and stagnation actions it would take, and simulates the stagnation cooldown. It does not place or cancel orders, and it does not send Telegram messages.

Set `dryRun = False` only after validating the configured symbol, balances, API permissions, and expected order sizes.

## Setup

Use Python 3 and install dependencies:

```bash
pip install -r requirements.txt
```

Create `.env`:

```env
API_KEY=your_binance_api_key
API_SECRET=your_binance_api_secret
BOT_TOKEN=your_telegram_bot_token
CHAT_ID=your_telegram_chat_id
```

The bot requires a Binance key with account-read permissions. Live trading additionally requires trading permission. The public debug helper does not require `.env` or API keys.

## Running

Run the strategy in dry-run mode first:

```bash
python3 grid.py
```

If using `bngrid.service`, review its executable path and working directory before enabling it.

## Public API Debug Helper

`api_debug.py` calls public Binance Spot REST endpoints only:

```bash
python3 api_debug.py ping
python3 api_debug.py time
python3 api_debug.py ticker --symbol BTCU
python3 api_debug.py exchangeInfo --symbol BTCU
python3 api_debug.py depth --symbol BTCU --depth-limit 5
python3 api_debug.py klines --symbol BTCUSDT --interval 1d --kline-limit 5
python3 api_debug.py all --symbol BTCU
```

It is useful for checking symbol availability, filters, price data, order-book data, and connectivity before enabling live trading.

## Operational Risks

- This is not financial advice.
- State is kept in memory. A restart loses tracked grid order IDs, the reference price, cached terminal events, and the stagnation cooldown.
- Live grid rebuilds cancel all open orders for the configured symbol, including manually placed orders and unfilled stagnation orders.
- The bot uses the latest account trade as a fallback after restart or cancellation-only rebuilds. Manual trades can therefore affect the next grid's initial buy quantity.
- The strategy has been syntax-checked and mock-tested, but should be observed in dry-run mode before live use.

## Quick Checks

```bash
python3 -m py_compile grid.py api_debug.py
python3 api_debug.py ping
```
