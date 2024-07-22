# !/usr/bin/env python3
# -*- coding: utf-8 -*-


import os


class Config:
    # url configs
    BASE_URL = 'https://fapi.binance.com'
    PAIRS_URL = '/fapi/v1/exchangeInfo'
    KLINE_URL = '/fapi/v1/klines'
    DAILY_CHANGE_URL = '/fapi/v1/ticker/24hr'

    # EMA period configs
    FAST_PERIOD = 30
    MID_PERIOD = 60
    SLOW_PERIOD = 120

    # timeframe configs
    SMALL_INTERVAL = '1h'
    MID_INTERVAL = '4h'
    LARGE_INTERVAL = '1d'

    # volume filter configs
    MIN_VOL_24H = 50000000    # 50 million USDT

    # commission and slippage
    FEES_RATE = 0.001    # 0.07% fee + 0.03% slippage

    # file to story qualified trade pairs
    pairs_file_name = 'pairs.json'
    portfolio_file_name = 'portfolio.csv'
    watchlist_file_name = 'watchlist.json'






    # convert the json file name to absolute path
    dir_path = os.path.dirname(os.path.abspath(__file__))
    PAIRS_PATH = os.path.join(dir_path, pairs_file_name)
    PF_PATH = os.path.join(dir_path, portfolio_file_name)
    WL_PATH = os.path.join(dir_path, watchlist_file_name)
