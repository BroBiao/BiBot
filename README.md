# BiBot

BiBot is a small Binance Spot grid trading bot for a single trading pair. The current default pair is `BTCFU`.

The bot keeps a fixed number of buy and sell limit orders around a reference price. When one of its tracked orders is filled, it cancels the remaining open orders and rebuilds the grid around the updated reference price. It does not chase price upward.

## Current Strategy

Default parameters are defined at the top of `grid.py`:

```python
initialBuyQuantity = 0.003
buyIncrement = 0.0003
sellQuantity = 0.003
priceStep = 1000
baseAsset = 'BTC'
quoteAsset = 'U'
numOrders = 3
dryRun = True
```

Behavior summary:

- Places up to `numOrders` buy orders below the reference price.
- Places up to `numOrders` sell orders above the reference price.
- Buy order quantity starts from the last buy quantity plus `buyIncrement` after a buy fill.
- Buy order quantity resets to `initialBuyQuantity` after a sell fill.
- Sell order quantity is fixed at `sellQuantity`.
- The reference price moves down one `priceStep` after a buy fill and up one `priceStep` after a sell fill.
- If there are still tracked open orders and no fill, the bot waits.
- There is no upward chase logic.

## Execution Model

`grid.py` uses a hybrid API model:

- REST is used for account balances, open orders, order placement, order cancellation, and periodic reconciliation.
- Binance WebSocket API User Data Stream is used for `executionReport` order events.
- Filled WebSocket events are queued and processed by the main loop, so order rebuilding remains single-threaded.
- A REST reconciliation runs every 5 minutes as a fallback.
- The WebSocket connection is restarted before Binance's 24-hour connection limit.

## Dry Run Mode

`dryRun = True` is the default.

In dry-run mode the bot:

- Reads account and market/account data.
- Prints the orders it would place.
- Does not place real orders.
- Does not cancel existing open orders.
- Does not send Telegram messages.

Set `dryRun = False` only after reviewing the code, configuration, balances, and symbol filters.

## Setup

Use Python 3. Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file for the trading bot:

```env
API_KEY=your_binance_api_key
API_SECRET=your_binance_api_secret
BOT_TOKEN=your_telegram_bot_token
CHAT_ID=your_telegram_chat_id
```

The public API debug script does not need `.env` or API keys.

## Running

Dry-run trading bot:

```bash
python3 grid.py
```

Public API debug helper:

```bash
python3 api_debug.py ping
python3 api_debug.py time
python3 api_debug.py ticker --symbol BTCU
python3 api_debug.py exchangeInfo --symbol BTCU
python3 api_debug.py depth --symbol BTCU --depth-limit 5
python3 api_debug.py klines --symbol BTCU --interval 1m --kline-limit 5
python3 api_debug.py all --symbol BTCU
```

## Public API Debug Script

`api_debug.py` calls only Binance Spot public REST endpoints:

- `/api/v3/ping`
- `/api/v3/time`
- `/api/v3/exchangeInfo`
- `/api/v3/ticker/price`
- `/api/v3/ticker/bookTicker`
- `/api/v3/depth`
- `/api/v3/klines`

It is useful for checking symbol availability, filters, price data, order book data, and basic connectivity without using private credentials.

## Systemd

A sample service file is included as `bngrid.service`. Review paths, user, working directory, and environment handling before enabling it on a server.

## Important Notes

- This is not financial advice.
- The bot currently tracks its own order IDs in memory. A restart loses `buy_orders`, `sell_orders`, and `last_refer_price` state.
- Restart recovery relies on REST data and the latest trade summary.
- The bot currently cancels open orders for the configured symbol when rebuilding the grid in live mode.
- For stronger isolation, add a strategy-specific `clientOrderId` prefix and only cancel/process orders with that prefix.

## Quick Checks

```bash
python3 -m py_compile grid.py api_debug.py
python3 api_debug.py ping
```
