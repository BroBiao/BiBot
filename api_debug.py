#!/usr/bin/env python3
"""Binance Spot public REST API debug helper.

Only calls public endpoints. No API key or .env is required.
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE_URL = 'https://api.binance.com'
DEFAULT_SYMBOL = 'BTCUSDT'


def request_public(path, params=None):
    query = urllib.parse.urlencode(params or {})
    url = f'{BASE_URL}{path}' + (f'?{query}' if query else '')
    req = urllib.request.Request(url, headers={'User-Agent': 'BiBot-public-api-debug/1.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode('utf-8')
        return url, json.loads(body) if body else {}


def print_json(title, url, data):
    print(f'\n## {title}')
    print(f'GET {url}')
    print(json.dumps(data, ensure_ascii=False, indent=2))


def utc_ms_to_iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def run_ping():
    url, data = request_public('/api/v3/ping')
    print_json('ping', url, data)


def run_time():
    url, data = request_public('/api/v3/time')
    if 'serverTime' in data:
        data['serverTimeIso'] = utc_ms_to_iso(data['serverTime'])
    print_json('server time', url, data)


def run_exchange_info(symbol):
    params = {'symbol': symbol} if symbol else None
    url, data = request_public('/api/v3/exchangeInfo', params)
    if symbol and data.get('symbols'):
        symbol_info = data['symbols'][0]
        compact = {
            'symbol': symbol_info.get('symbol'),
            'status': symbol_info.get('status'),
            'baseAsset': symbol_info.get('baseAsset'),
            'quoteAsset': symbol_info.get('quoteAsset'),
            'orderTypes': symbol_info.get('orderTypes'),
            'filters': symbol_info.get('filters'),
        }
        print_json('exchange info', url, compact)
    else:
        print_json('exchange info', url, data)


def run_ticker(symbol):
    url, data = request_public('/api/v3/ticker/price', {'symbol': symbol})
    print_json('ticker price', url, data)


def run_book_ticker(symbol):
    url, data = request_public('/api/v3/ticker/bookTicker', {'symbol': symbol})
    print_json('book ticker', url, data)


def run_depth(symbol, limit):
    url, data = request_public('/api/v3/depth', {'symbol': symbol, 'limit': limit})
    print_json('order book depth', url, data)


def run_klines(symbol, interval, limit):
    url, data = request_public('/api/v3/klines', {
        'symbol': symbol,
        'interval': interval,
        'limit': limit,
    })
    rows = [
        {
            'openTime': utc_ms_to_iso(row[0]),
            'open': row[1],
            'high': row[2],
            'low': row[3],
            'close': row[4],
            'volume': row[5],
            'closeTime': utc_ms_to_iso(row[6]),
        }
        for row in data
    ]
    print_json('klines', url, rows)


def run_all(args):
    run_ping()
    run_time()
    run_exchange_info(args.symbol)
    run_ticker(args.symbol)
    run_book_ticker(args.symbol)
    run_depth(args.symbol, args.depth_limit)
    run_klines(args.symbol, args.interval, args.kline_limit)


def build_parser():
    parser = argparse.ArgumentParser(description='Debug Binance Spot public REST API endpoints.')
    parser.add_argument('--symbol', default=DEFAULT_SYMBOL, help=f'trading pair symbol, default: {DEFAULT_SYMBOL}')
    parser.add_argument('--interval', default='1m', help='kline interval, default: 1m')
    parser.add_argument('--kline-limit', type=int, default=5, help='number of klines, default: 5')
    parser.add_argument('--depth-limit', type=int, default=5, choices=[5, 10, 20, 50, 100, 500, 1000, 5000], help='order book depth limit')
    parser.add_argument('endpoint', nargs='?', default='all', choices=[
        'all', 'ping', 'time', 'exchangeInfo', 'ticker', 'bookTicker', 'depth', 'klines'
    ])
    return parser


def main():
    args = build_parser().parse_args()
    try:
        if args.endpoint == 'all':
            run_all(args)
        elif args.endpoint == 'ping':
            run_ping()
        elif args.endpoint == 'time':
            run_time()
        elif args.endpoint == 'exchangeInfo':
            run_exchange_info(args.symbol)
        elif args.endpoint == 'ticker':
            run_ticker(args.symbol)
        elif args.endpoint == 'bookTicker':
            run_book_ticker(args.symbol)
        elif args.endpoint == 'depth':
            run_depth(args.symbol, args.depth_limit)
        elif args.endpoint == 'klines':
            run_klines(args.symbol, args.interval, args.kline_limit)
    except urllib.error.HTTPError as e:
        print(f'HTTP error {e.code}: {e.read().decode("utf-8", errors="replace")}', file=sys.stderr)
        return 1
    except Exception as e:
        print(f'API debug failed: {e}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
