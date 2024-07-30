# !/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import json
import time
import asyncio
import requests
import traceback
import numpy as np
import pandas as pd
import datetime as dt
import portfolio as pf
from telegram import Bot
from config import Config
from dotenv import load_dotenv
from fetchPairs import update_pairs


os.environ['TZ'] = 'Asia/Shanghai'
time.tzset()
pairs_path = Config.PAIRS_PATH
watchlist_path = Config.WL_PATH
load_dotenv()
bot_token = os.getenv('BOT_TOKEN')
chat_id = os.getenv('CHAT_ID')
bot = Bot(bot_token)
loop = asyncio.get_event_loop()
MKT_BASE_URL = 'https://www.binance.com/zh-CN/futures/'

debug_mode = True
if debug_mode == True:
    proxies = {
    'https': 'http://127.0.0.1:7890/',
    'http': 'http://127.0.0.1:7890/'
    }
else:
    proxies = None

class PairData(object):

    def __init__(self, pair):
        self.pair = pair
        self.base_url = Config.BASE_URL
        self.kline_url = Config.KLINE_URL
        self.fast_period = Config.FAST_PERIOD
        self.mid_period = Config.MID_PERIOD
        self.slow_period = Config.SLOW_PERIOD

    def get_klines(self, interval, endTime=None, limit=None):
        if not hasattr(self, 'klines'):
            self.klines = {}
        if (interval not in self.klines.keys()):
            url = self.base_url + self.kline_url
            params = {'symbol': self.pair, 'interval': interval, 'endTime': endTime, 'limit': limit}
            res = requests.get(url, params=params, proxies=proxies)
            if res.status_code == 200:
                raw_data = json.loads(res.text)
                self.klines[interval] = {}
                # remove the lastest candle becuase it is not finished
                self.klines[interval]['opentime'] = [float(each[0]) for each in raw_data[:-1]]
                self.klines[interval]['open'] = [float(each[1]) for each in raw_data[:-1]]
                self.klines[interval]['high'] = [float(each[2]) for each in raw_data[:-1]]
                self.klines[interval]['low'] = [float(each[3]) for each in raw_data[:-1]]
                self.klines[interval]['close'] = [float(each[4]) for each in raw_data[:-1]]
                self.klines[interval]['volume'] = [float(each[7]) for each in raw_data[:-1]]
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

def read_json_file(file_path):
    with open(file_path, 'r') as f:
        file_text = json.load(f)
    return file_text

def write_to_json_file(json_text, file_path):
    with open(file_path, 'w') as f:
        json.dump(json_text, f)

def send_message(message):
    if debug_mode == True:
        print(message)
    else:
        loop.run_until_complete(bot.send_message(chat_id=chat_id, text=message))

def run():
    small_interval = Config.SMALL_INTERVAL
    mid_interval = Config.MID_INTERVAL
    large_interval = Config.LARGE_INTERVAL

    # new position
    volume_pairs = read_json_file(pairs_path)
    old_watchlist = read_json_file(watchlist_path)
    all_pairs = set(volume_pairs + old_watchlist)
    new_watchlist = []
    for pair in old_watchlist:
        try:
            # print(str(all_pairs.index(pair)+1)+'/'+str(len(all_pairs)))
            data = PairData(pair)

            # Main Strategy: Bullish/Bearish Flag Strategy
            small_klines = data.get_klines(small_interval)
            klines_num = len(small_klines['open'])
            print(str(dt.datetime.fromtimestamp(small_klines['opentime'][-1]/1000)))
            oc_max = [max(small_klines['open'][i], small_klines['close'][i]) for i in range(klines_num)]
            oc_min = [min(small_klines['open'][i], small_klines['close'][i]) for i in range(klines_num)]
            local_peaks = []
            local_valleys = []
            for i in range(5, klines_num-5):
                if (oc_max[i] >= max(oc_max[i-5:i+5+1])) and (oc_max[i] > oc_max[i+1]):
                    # print('HH: ' + str(dt.datetime.fromtimestamp(small_klines['opentime'][i]/1000)) + ' ' + str(oc_max[i]))
                    local_peaks.append((i, oc_max[i]))
                elif (oc_min[i] <= min(oc_min[i-5:i+5+1])) and (oc_min[i] < oc_min[i+1]):
                    # print('LL: ' + str(dt.datetime.fromtimestamp(small_klines['opentime'][i]/1000)) + ' ' + str(oc_min[i]))
                    local_valleys.append((i, oc_min[i]))
                else:
                    pass

            def find_prev_PV_index(start_index, PV_type):
                if PV_type == 'peak':
                    # start index is ahead of the first peak, cannot find a peak before it
                    if start_index < local_peaks[0][0]:
                        return 0
                    else:
                        for i in range(len(local_peaks)-1):
                            if (local_peaks[i][0] < start_index) and (local_peaks[i+1][0] > start_index):
                                return local_peaks[i][0]
                            else:
                                pass
                        return local_peaks[-1][0]
                elif PV_type == 'valley':
                    # start index if ahead of the first valley, cannot find a valley before it
                    if start_index < local_valleys[0][0]:
                        return 0
                    else:
                        for i in range(len(local_valleys)-1):
                            if (local_valleys[i][0] < start_index) and (local_valleys[i+1][0] > start_index):
                                return local_valleys[i][0]
                            else:
                                pass
                        return local_valleys[-1][0]
                else:
                    raise ValueError("The input parameter 'PV_type' should be 'peak' or 'valley'.")

            def get_latest_PVs(num):
                latest_PVs = []
                for PV in [local_peaks, local_valleys]:
                    latest_PV_index = [PV[i][0] for i in range(-num, 0)]
                    latest_PV_time = [str(dt.datetime.fromtimestamp(small_klines['opentime'][i]/1000)) for i in latest_PV_index]
                    latest_PVs += latest_PV_time
                message = f'Latest {num} Peaks:\n' + '\n'.join(latest_PVs[:num]) + \
                          f'\n\nLatest {num} Valleys:\n' +'\n'.join(latest_PVs[num:])
                return message


            # Check Bullish Flag
            peak_count = 1
            for i in range(1, len(local_peaks)):
                if local_peaks[-i][1] < local_peaks[-i-1][1]:
                    peak_count += 1
                else:
                    if peak_count >= 2:
                        flag_message = ''
                        for j in range(peak_count):
                            peak_index = local_peaks[-i+j][0]
                            flag_message += f'H{j+1}: %s  %f\n' % (
                                str(dt.datetime.fromtimestamp(small_klines['opentime'][peak_index]/1000)), oc_max[peak_index]
                                )
                        valley_index = find_prev_PV_index(local_peaks[-i][0], 'valley')
                        flag_message += 'L0: %s  %f\n' % (
                            str(dt.datetime.fromtimestamp(small_klines['opentime'][valley_index]/1000)), oc_min[valley_index]
                            )
                        hh = local_peaks[-i][0]    # the highest/furthest peak
                        h1 = local_peaks[-i+j][0]    # the lowest/nearest peak
                        h2 = local_peaks[-i+j-1][0]    # the second lowest/nearest peak
                        if min(oc_min[hh:]) > oc_min[valley_index]:
                            peak_trend = oc_max[h1] + ((oc_max[h1] - oc_max[h2]) / (h1 - h2)) * (klines_num-1 - h1)
                            if (oc_max[-1] >= peak_trend) and (oc_max[-2] < peak_trend):
                                message2send = f'\U0001F42E\U0001F4C8 Bullish Flag Breakout!\n{pair}\n' + flag_message
                                send_message(message2send)
                            elif h1 == klines_num-5-1:
                                message2send = f'\U0001F42E\U0001F6A9 Bullish Flag Detected!\n{pair}\n' + flag_message
                                send_message(message2send)
                            else:
                                pass
                    break

            # Check Bearish Flag
            valley_count = 1
            for i in range(1, len(local_valleys)):
                if local_valleys[-i][1] > local_valleys[-i-1][1]:
                    valley_count += 1
                else:
                    if valley_count >= 2:
                        flag_message = ''
                        for j in range(valley_count):
                            valley_index = local_valleys[-i+j][0]
                            flag_message += f'L{j+1}: %s  %f\n' % (
                                str(dt.datetime.fromtimestamp(small_klines['opentime'][valley_index]/1000)), oc_min[valley_index]
                                )
                        peak_index = find_prev_PV_index(local_valleys[-i][0], 'peak')
                        flag_message += 'H0: %s  %f\n' % (
                            str(dt.datetime.fromtimestamp(small_klines['opentime'][peak_index]/1000)), oc_max[peak_index]
                            )
                        ll = local_valleys[-i][0]    # the lowest/furthest valley
                        l1 = local_valleys[-i+j][0]    # the highst/nearest valley
                        l2 = local_valleys[-i+j-1][0]    # the second highest/nearest valley
                        if max(oc_max[ll:]) < oc_max[peak_index]:
                            valley_trend = oc_min[l1] + ((oc_min[l1] - oc_min[l2]) / (l1 - l2)) * (klines_num-1 - l1)
                            if (oc_min[-1] <= valley_trend) and (oc_min[-2] > valley_trend):
                                message2send = f'\U0001F43B\U0001F4C9 Bearish Flag Breakout!\n{pair}\n' + flag_message
                                send_message(message2send)
                            elif h1 == klines_num-5-1:
                                message2send = f'\U0001F43B\U0001F6A9 Bearish Flag Detected!\n{pair}\n' + flag_message
                                send_message(message2send)
                            else:
                                pass
                    break


            # # Backtest Section
            # # Bullish Flag: peaks get lower but the 'flag' is higher than the start of the 'pole'
            # peak_count = 1
            # for i in range(1, len(local_peaks)):
            #     if local_peaks[-i][1] < local_peaks[-i-1][1]:
            #         peak_count += 1
            #     else:
            #         if peak_count >= 2:
            #             flag_message = ''
            #             for j in range(peak_count):
            #                 peak_index = local_peaks[-i+j][0]
            #                 flag_message += f'H{j+1}: %s  %f\n' % (
            #                     str(dt.datetime.fromtimestamp(small_klines['opentime'][peak_index]/1000)), oc_max[peak_index]
            #                     )
            #             valley_index = find_prev_PV_index(local_peaks[-i][0], 'valley')
            #             flag_message += 'L0: %s  %f\n' % (
            #                 str(dt.datetime.fromtimestamp(small_klines['opentime'][valley_index]/1000)), oc_min[valley_index]
            #                 )
            #             hh = local_peaks[-i][0]    # the highest/furthest peak
            #             h1 = local_peaks[-i+j][0]    # the lowest/nearest peak
            #             h2 = local_peaks[-i+j-1][0]    # the second lowest/nearest peak
            #             if min(oc_min[hh:h1+6]) > oc_min[valley_index]:
            #                 message2send = f'\U0001F42E\U0001F6A9 Bullish Flag Detected!\n{pair}\n' + flag_message
            #                 send_message(message2send)
            #         peak_count = 1



            '''
            small_ema3 = data.get_ema3(small_interval)
            if (small_klines['low'][-2] < small_ema3['slow'][-2]) and (small_klines['high'][-2] > small_ema3['slow'][-2]):
                message = pair + ' touchs ' + small_interval.upper() + ' EMA' + str(Config.SLOW_PERIOD) + '\n' + MKT_BASE_URL + pair
                send_message
            else:
                pass
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
            error_message = 'Error Occurred!\n' + pair + ': ' + traceback.format_exc()
            send_message(error_message)
        finally:
            continue

    # update pairs json file
    # update_pairs()
    # write_to_json_file(new_watchlist, watchlist_path)


if __name__ == '__main__':

    # main function
    run()
