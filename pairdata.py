import json
import requests
import pandas as pd
from config import Config


class PairData(object):

    def __init__(self, pair, proxies=None):
        self.pair = pair
        self.proxies = proxies
        self.base_url = Config.API_BASE_URL
        self.kline_url = Config.KLINE_URL
        self.fast_period = Config.FAST_PERIOD
        self.mid_period = Config.MID_PERIOD
        self.slow_period = Config.SLOW_PERIOD

    def get_klines(self, timeframe, endTime=None, limit=None):
        if not hasattr(self, 'klines'):
            self.klines = {}
        if (timeframe not in self.klines.keys()):
            url = self.base_url + self.kline_url
            params = {'symbol': self.pair, 'interval': timeframe, 'endTime': endTime, 'limit': limit}
            res = requests.get(url, params=params, proxies=self.proxies)
            if res.status_code == 200:
                raw_data = json.loads(res.text)
                self.klines[timeframe] = {}
                # remove the lastest candle becuase it is not finished
                self.klines[timeframe]['opentime'] = [float(each[0]) for each in raw_data[:-1]]
                self.klines[timeframe]['open'] = [float(each[1]) for each in raw_data[:-1]]
                self.klines[timeframe]['high'] = [float(each[2]) for each in raw_data[:-1]]
                self.klines[timeframe]['low'] = [float(each[3]) for each in raw_data[:-1]]
                self.klines[timeframe]['close'] = [float(each[4]) for each in raw_data[:-1]]
                self.klines[timeframe]['volume'] = [float(each[7]) for each in raw_data[:-1]]
            else:
                raise Exception('Requests failed: ' + res.reason)
        else:
            pass
        return self.klines[timeframe]

    def get_ema3(self, timeframe, endTime=None, limit=None):
        if hasattr(self, 'ema3') and self.ema3['timeframe'] == timeframe:
            pass
        else:
            klines = self.get_klines(timeframe, endTime, limit)
            df = pd.DataFrame({'price':klines['close']})
            self.ema3 = {}
            self.ema3['timeframe'] = timeframe
            self.ema3['fast'] = df['price'].ewm(span=self.fast_period, adjust=False, min_periods=self.fast_period).mean().to_list()
            self.ema3['mid'] = df['price'].ewm(span=self.mid_period, adjust=False, min_periods=self.mid_period).mean().to_list()
            self.ema3['slow'] = df['price'].ewm(span=self.slow_period, adjust=False, min_periods=self.slow_period).mean().to_list()
        return self.ema3

    def check_ema(self, timeframe, shift=-1, endTime=None, limit=None):
        self.get_ema3(timeframe, endTime, limit)
        fast_ema = self.ema3['fast'][shift]
        mid_ema = self.ema3['mid'][shift]
        slow_ema = self.ema3['slow'][shift]
        if fast_ema > mid_ema > slow_ema:
            return 'LONG'
        elif fast_ema < mid_ema < slow_ema:
            return 'SHORT'
        else:
            return 'WAIT'

    def get_oc_max(self, timeframe, endTime=None, limit=None):
        if hasattr(self, 'oc_max') and self.oc_max['timeframe'] == timeframe:
            pass
        else:
            klines = self.get_klines(timeframe, endTime, limit)
            klines_num = len(klines['open'])
            self.oc_max = {}
            self.oc_max['timeframe'] = timeframe
            self.oc_max['data'] = [max(klines['open'][i], klines['close'][i]) for i in range(klines_num)]
        return self.oc_max['data']

    def get_oc_min(self, timeframe, endTime=None, limit=None):
        if hasattr(self, 'oc_min') and self.oc_min['timeframe'] == timeframe:
            pass
        else:
            klines = self.get_klines(timeframe, endTime, limit)
            klines_num = len(klines['open'])
            self.oc_min = {}
            self.oc_min['timeframe'] = timeframe
            self.oc_min['data'] = [min(klines['open'][i], klines['close'][i]) for i in range(klines_num)]
        return self.oc_min['data']

    def get_peaks(self, data, width):
        data_len = len(data)
        if data_len <= 2*width:
            raise Exception('The length of data list must be greater than twice the width.')
        else:
            peaks_index = []
            for i in range(width, data_len-width):
                data_window = data[i-width:i+width+1]
                if data_window.index(max(data_window)) == width:
                    peaks_index.append(i)
            return peaks_index