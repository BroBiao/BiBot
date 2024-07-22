# !/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import json
import time
import asyncio
import requests
import numpy as np
import pandas as pd
import datetime as dt
import portfolio as pf
from telegram import Bot
from config import Config
from dotenv import load_dotenv
from fetchPairs import update_pairs


pairs_path = Config.PAIRS_PATH
watchlist_path = Config.WL_PATH
load_dotenv()
bot_token = os.getenv('BOT_TOKEN')
chat_id = os.getenv('CHAT_ID')
bot = Bot(bot_token)
loop = asyncio.get_event_loop()
MKT_BASE_URL = 'https://www.binance.com/zh-CN/futures/'

# proxies = {
# 'https': 'http://127.0.0.1:7890/',
# 'http': 'http://127.0.0.1:7890/'
# }

proxies = None

class PairData(object):

    def __init__(self, pair):
        self.pair = pair
        self.base_url = Config.BASE_URL
        self.kline_url = Config.KLINE_URL
        self.fast_period = Config.FAST_PERIOD
        self.mid_period = Config.MID_PERIOD
        self.slow_period = Config.SLOW_PERIOD

    def get_klines(self, interval):
        if not hasattr(self, 'klines'):
            self.klines = {}
        if (interval not in self.klines.keys()):
            url = self.base_url + self.kline_url
            params = {'symbol': self.pair, 'interval': interval}
            res = requests.get(url, params=params, proxies=proxies)
            if res.status_code == 200:
                raw_data = json.loads(res.text)
                self.klines[interval] = {}
                self.klines[interval]['open'] = [float(each[1]) for each in raw_data]
                self.klines[interval]['high'] = [float(each[2]) for each in raw_data]
                self.klines[interval]['low'] = [float(each[3]) for each in raw_data]
                self.klines[interval]['close'] = [float(each[4]) for each in raw_data]
                self.klines[interval]['volume'] = [float(each[7]) for each in raw_data]
            else:
                print(self.pair + '  ' + str(res.status_code) + '  ' + res.reason)
                raise Exception('Requests failed: ' + res.reason)
        else:
            pass
        return self.klines[interval]

    def get_ema3(self, interval):
        if hasattr(self, 'ema3') and self.ema3['interval'] == interval:
            pass
        else:
            klines = self.get_klines(interval)
            df = pd.DataFrame({'price':klines['close']})
            self.ema3 = {}
            self.ema3['interval'] = interval
            self.ema3['fast'] = df['price'].ewm(span=self.fast_period, adjust=False, min_periods=self.fast_period).mean().to_list()
            self.ema3['mid'] = df['price'].ewm(span=self.mid_period, adjust=False, min_periods=self.mid_period).mean().to_list()
            self.ema3['slow'] = df['price'].ewm(span=self.slow_period, adjust=False, min_periods=self.slow_period).mean().to_list()
        return self.ema3

    def check_ema(self, interval, shift):
        self.get_ema3(interval)
        fast_ema = self.ema3['fast'][shift]
        mid_ema = self.ema3['mid'][shift]
        slow_ema = self.ema3['slow'][shift]
        if fast_ema > mid_ema > slow_ema:
            return 'LONG'
        elif fast_ema < mid_ema < slow_ema:
            return 'SHORT'
        else:
            return 'WAIT'

    def cumul_ema_trend(self, interval, span):
        self.get_ema3(interval)
        fast_ema = self.ema3['fast']
        slow_ema = self.ema3['slow']
        diff = [fast_ema[i] - slow_ema[i] for i in range(min(len(fast_ema), len(slow_ema)))][-span:]
        diff_array = np.array(diff)
        zero_crossing = ((diff_array[:-1] * diff_array[1:]) <= 0).sum()
        zero_count = np.count_nonzero(diff_array==0)
        zero_crossing -= zero_count
        cumul_ema = sum(diff)
        if cumul_ema > 0:
            trend = 'LONG'
        elif cumul_ema < 0:
            trend = 'SHORT'
        else:
            trend = 'WAIT'
        return [trend, zero_crossing]

def read_json_file(file_path):
    with open(file_path, 'r') as f:
        file_text = json.load(f)
    return file_text

def write_to_json_file(json_text, file_path):
    with open(file_path, 'w') as f:
        json.dump(json_text, f)

def run():
    small_interval = Config.SMALL_INTERVAL
    mid_interval = Config.MID_INTERVAL
    large_interval = Config.LARGE_INTERVAL

    # new position
    volume_pairs = read_json_file(pairs_path)
    old_watchlist = read_json_file(watchlist_path)
    all_pairs = set(volume_pairs + old_watchlist)
    new_watchlist = []
    for pair in volume_pairs:
        try:
            # print(str(all_pairs.index(pair)+1)+'/'+str(len(all_pairs)))
            data = PairData(pair)

            # 策略：触及1H EMA120
            small_klines = data.get_klines(small_interval)
            small_ema3 = data.get_ema3(small_interval)
            if (small_klines['low'][-2] < small_ema3['slow'][-2]) and (small_klines['high'][-2] > small_ema3['slow'][-2]):
                message = pair + ' touchs ' + small_interval.upper() + ' EMA' + str(Config.SLOW_PERIOD) + '\n' + MKT_BASE_URL + pair
                loop.run_until_complete(bot.send_message(chat_id=chat_id, text=message))
            else:
                pass
            '''
            ema_trends = {}
            for interval in [small_interval, mid_interval, large_interval]:
                klines = data.get_klines(interval)
                ema3 = data.get_ema3(interval)
                ema_trends[interval] = data.check_ema(interval, -2)
            pair_trends_msg = '\n'.join([f"{key}: {value}" for key, value in ema_trends.items()])
            print(str(dt.datetime.today()) + '  ' + pair + '\n' + pair_trends_msg)

            if pair not in old_watchlist:
                cond_1 = (ema_trends[small_interval] == ema_trends[mid_interval] == 'LONG') and (ema_trends[large_interval]=='SHORT')
                cond_2 = (ema_trends[small_interval] == ema_trends[mid_interval] == 'SHORT') and (ema_trends[large_interval]=='LONG')
                if cond_1 or cond_2:
                    message = f'Add {pair} to watchlist\n' + pair_trends_msg + '\n' + MKT_BASE_URL + pair
                    loop.run_until_complete(bot.send_message(chat_id=chat_id, text=message))
                    new_watchlist.append(pair)
                else:
                    pass
            else:    # pairs already in watchlist
                # check if remove fromwatchlist
                cond_1 = (ema_trends[small_interval] == ema_trends[mid_interval] == ema_trends[large_interval] == 'LONG')
                cond_2 = (ema_trends[small_interval] == ema_trends[mid_interval] == ema_trends[large_interval] == 'SHORT')
                if cond_1 or cond_2:
                    message = f'Remove {pair} from watchlist\n' + pair_trends_msg + '\n' + MKT_BASE_URL + pair
                    loop.run_until_complete(bot.send_message(chat_id=chat_id, text=message))
                else:
                    new_watchlist.append(pair)
                # check ema touch
                small_klines = data.get_klines(small_interval)
                small_ema3 = data.get_ema3(small_interval)
                if (small_klines['low'][-2] < small_ema3['slow'][-2]) and (small_klines['high'][-2] > small_ema3['slow'][-2]):
                    message = pair + ' touchs ' + small_interval.upper() + ' EMA' + str(Config.SLOW_PERIOD) + '\n' + MKT_BASE_URL + pair
                    loop.run_until_complete(bot.send_message(chat_id=chat_id, text=message))
                else:
                    pass
            '''

        except Exception as e:
            error_message = 'Error Occurred!\n' + pair + ': ' + str(e)
            loop.run_until_complete(bot.send_message(chat_id=chat_id, text=error_message))
        finally:
            continue

    # update pairs json file
    update_pairs()
    # write_to_json_file(new_watchlist, watchlist_path)


if __name__ == '__main__':

    # main function
    run()
