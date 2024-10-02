import os


class Config:
    # url configs
    API_BASE_URL = 'https://fapi.binance.com'
    PAIRS_URL = '/fapi/v1/exchangeInfo'
    KLINE_URL = '/fapi/v1/klines'
    DAILY_CHANGE_URL = '/fapi/v1/ticker/24hr'
    MKT_BASE_URL = 'https://www.binance.com/zh-CN/futures/'

    # EMA period configs (only for tp calculation)
    FAST_PERIOD = 30
    MID_PERIOD = 60
    SLOW_PERIOD = 120

    # timeframe configs
    SMALL_TIMEFRAME = '1h'
    LARGE_TIMEFRAME = '4h'
    MAXMIN_WINDOW_WIDTH = 6

    # commission and slippage
    FEES_RATE = 0.001    # 0.07% fee + 0.03% slippage

    # file to story qualified trade pairs
    portfolio_file_name = 'portfolio.csv'
    watchlist_file_name = 'watchlist.json'

    # convert the json file name to absolute path
    dir_path = os.path.dirname(os.path.abspath(__file__))
    PF_PATH = os.path.join(dir_path, portfolio_file_name)
    WL_PATH = os.path.join(dir_path, watchlist_file_name)
