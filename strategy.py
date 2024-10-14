import os
import time
import pytz
import asyncio
import traceback
import datetime as dt
from utils import *
from config import Config
from pairdata import PairData
from tgbot import TelegramBot
from dotenv import load_dotenv


# basic configs
tz = pytz.timezone('Asia/Shanghai')
watchlist_path = Config.WL_PATH
pricealert_path = Config.PA_PATH
market_base_url = Config.MKT_BASE_URL

debug_mode = False
if debug_mode == True:
    proxies = {
    'https': 'http://127.0.0.1:7890/',
    'http': 'http://127.0.0.1:7890/'
    }
else:
    proxies = None
    load_dotenv()
    bot_token = os.getenv('BOT_TOKEN')
    chat_id = os.getenv('CHAT_ID')
    bot = TelegramBot(bot_token)

def send_message(message):
    if debug_mode == True:
        print(message)
    else:
        asyncio.run(bot.send_message(chat_id=chat_id, text=message))

def check_pricealert(pair, price, high_data, low_data):
    if ((high_data[-2] < price) and (high_data[-1] >= price)) or ((low_data[-2] > price) and (low_data[-1] <= price)):
        send_message(f'Price Alert Triggered: {pair} {price}')
    else:
        pass

def run():
    operate_timeframe = Config.SMALL_TIMEFRAME
    operate_timeframe_sec = timeframe_to_seconds(operate_timeframe)
    observe_timeframe = Config.LARGE_TIMEFRAME

    all_pairs = read_json_file(watchlist_path)
    for pair in all_pairs:
        try:
            # print(pair, str(all_pairs.index(pair)+1)+'/'+str(len(all_pairs)))
            data = PairData(pair, proxies)

            # Data acquisition and preprocessing
            last_candle_opentime = int(time.time())-(int(time.time())%operate_timeframe_sec)
            klines = data.get_klines(operate_timeframe)
            while klines['opentime'][-1] != last_candle_opentime:
                time.sleep(1)
                klines = data.get_klines(operate_timeframe)
            window_width = Config.MAXMIN_WINDOW_WIDTH
            oc_max = data.get_oc_max(operate_timeframe)
            local_peaks_index = data.get_peaks(oc_max, window_width)
            local_peaks = [(klines['opentime'][i], oc_max[i]) for i in local_peaks_index]

            oc_min = data.get_oc_min(operate_timeframe)
            oc_min_neg = [-each for each in oc_min]
            local_valleys_index = data.get_peaks(oc_min_neg, window_width)
            local_valleys = [(klines['opentime'][i], oc_min[i]) for i in local_valleys_index]

            operate_trend = data.check_ema(operate_timeframe)
            observe_trend = data.check_ema(observe_timeframe)

            # Check price alerts
            pricealert = read_json_file(pricealert_path)
            if pair in pricealert.keys():
                check_pricealert(pair, pricealert[pair], klines['high'], klines['low'])

            # Main Strategy: Bullish/Bearish Flag Strategy
            # Check Bullish Flag & Descending Channel Pattern
            if local_peaks[-2][1] > local_peaks[-1][1]:
                flag_message = f'H2: %s  %f\nH1: %s  %f\n' % (
                                str(dt.datetime.fromtimestamp(local_peaks[-2][0]/1000, tz)), local_peaks[-2][1],
                                str(dt.datetime.fromtimestamp(local_peaks[-1][0]/1000, tz)), local_peaks[-1][1])
                for i in range(2, len(local_peaks)):
                    if local_peaks[-i-1][1] > local_peaks[-i][1]:
                        flag_message = f'H{i+1}: %s  %f\n' % (
                            str(dt.datetime.fromtimestamp(local_peaks[-i-1][0]/1000, tz)), local_peaks[-i-1][1]
                        ) + flag_message
                    else:
                        break
                pair_market_url = market_base_url + pair
                if ((oc_max[-2] < local_peaks[-1][1]) and (oc_max[-1] >= local_peaks[-1][1]) and 
                    (operate_trend == 'LONG') and (observe_trend != 'SHORT')):
                    message2send = f'\U0001F42E\U0001F4C8 {pair}\n' + flag_message + pair_market_url
                    send_message(message2send)
                '''
                if local_valleys[-2][1] >= local_valleys[-1][1]:
                    peak_trend_slope = (local_peaks[-2][1] - local_peaks[-1][1])/(local_peaks[-2][0] - local_peaks[-1][0])
                    peak_trend_value = local_peaks[-1][1] + peak_trend_slope * (klines['opentime'][-1] - local_peaks[-1][0])
                    valley_trend_slope = (local_valleys[-2][1] - local_valleys[-1][1])/(local_valleys[-2][0] - local_valleys[-1][0])
                    if ((peak_trend_slope <= valley_trend_slope) and (klines['high'][-2] < peak_trend_value) and 
                        (klines['high'][-1] >= peak_trend_value) and (observe_trend != 'LONG')):
                        flag_message += f'L2: %s  %f\nL1: %s  %f\n' % (
                                        str(dt.datetime.fromtimestamp(local_valleys[-2][0]/1000, tz)), local_valleys[-2][1],
                                        str(dt.datetime.fromtimestamp(local_valleys[-1][0]/1000, tz)), local_valleys[-1][1])
                        message2send = f'\U00002197\U00002198 {pair}\n' + flag_message + pair_market_url
                        send_message(message2send)
                '''

            # Check Bearish Flag & Ascending Channel Pattern
            if local_valleys[-2][1] < local_valleys[-1][1]:
                flag_message = f'L2: %s  %f\nL1: %s  %f\n' % (
                                str(dt.datetime.fromtimestamp(local_valleys[-2][0]/1000, tz)), local_valleys[-2][1],
                                str(dt.datetime.fromtimestamp(local_valleys[-1][0]/1000, tz)), local_valleys[-1][1])
                for i in range(2, len(local_valleys)):
                    if local_valleys[-i-1][1] < local_valleys[-i][1]:
                        flag_message = f'L{i+1}: %s  %f\n' % (
                            str(dt.datetime.fromtimestamp(local_valleys[-i-1][0]/1000, tz)), local_valleys[-i-1][1]
                        ) + flag_message
                    else:
                        break
                pair_market_url = market_base_url + pair
                if ((oc_min[-2] > local_valleys[-1][1]) and (oc_min[-1] <= local_valleys[-1][1]) and 
                    (operate_trend == 'SHORT') and (observe_trend != 'LONG')):
                    message2send = f'\U0001F43B\U0001F4C9 {pair}\n' + flag_message + pair_market_url
                    send_message(message2send)
                '''
                if local_peaks[-2][1] <= local_peaks[-1][1]:
                    valley_trend_slope = (local_valleys[-2][1] - local_valleys[-1][1])/(local_valleys[-2][0] - local_valleys[-1][0])
                    valley_trend_value = local_valleys[-1][1] + valley_trend_slope * (klines['opentime'][-1] - local_valleys[-1][0])
                    peak_trend_slope = (local_peaks[-2][1] - local_peaks[-1][1])/(local_peaks[-2][0] - local_peaks[-1][0])
                    if ((valley_trend_slope >= peak_trend_slope) and (klines['low'][-2] > valley_trend_value) and 
                        (klines['low'][-1] <= valley_trend_value) and (observe_trend != 'SHORT')):
                        flag_message += f'H2: %s  %f\nH1: %s  %f\n' % (
                                       str(dt.datetime.fromtimestamp(local_peaks[-2][0]/1000, tz)), local_peaks[-2][1],
                                       str(dt.datetime.fromtimestamp(local_peaks[-1][0]/1000, tz)), local_peaks[-1][1])
                        message2send = f'\U00002198\U00002197 {pair}\n' + flag_message + pair_market_url
                        send_message(message2send)
                '''

        except Exception as e:
            error_message = 'Error Occurred!\n' + pair + ': ' + traceback.format_exc()
            send_message(error_message)
        finally:
            continue


if __name__ == '__main__':

    #logging
    print(dt.datetime.now(tz))

    # main function
    run()
