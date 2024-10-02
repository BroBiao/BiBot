import os
import time
import asyncio
import traceback
import datetime as dt
from utils import *
from config import Config
from pairdata import PairData
from tgbot import TelegramBot
from dotenv import load_dotenv


# basic configs
os.environ['TZ'] = 'Asia/Shanghai'
time.tzset()
watchlist_path = Config.WL_PATH
market_base_url = Config.MKT_BASE_URL

debug_mode = True
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

def run():
    timeframe = Config.LARGE_TIMEFRAME
    timeframe_sec = timeframe_to_seconds(timeframe)

    all_pairs = read_json_file(watchlist_path)
    for pair in all_pairs:
        try:
            # print(pair, str(all_pairs.index(pair)+1)+'/'+str(len(all_pairs)))
            data = PairData(pair, proxies)

            # Main Strategy: Bullish/Bearish Flag Strategy
            klines = data.get_klines(timeframe)
            window_width = Config.MAXMIN_WINDOW_WIDTH
            oc_max = data.get_oc_max(timeframe)
            local_peaks_index = data.get_peaks(oc_max, window_width)
            local_peaks = [(klines['opentime'][i], oc_max[i]) for i in local_peaks_index]

            oc_min = data.get_oc_min(timeframe)
            oc_min_neg = [-each for each in oc_min]
            local_valleys_index = data.get_peaks(oc_min_neg, window_width)
            local_valleys = [(klines['opentime'][i], oc_min[i]) for i in local_valleys_index]

            # Check Bullish Flag
            if local_peaks[-2][1] > local_peaks[-1][1]:
                flag_message = f'H1: %s  %f\nH2: %s  %f\nH3: %s  %f\n' % (
                                str(dt.datetime.fromtimestamp(local_peaks[-3][0]/1000)), local_peaks[-3][1],
                                str(dt.datetime.fromtimestamp(local_peaks[-2][0]/1000)), local_peaks[-2][1],
                                str(dt.datetime.fromtimestamp(local_peaks[-1][0]/1000)), local_peaks[-1][1]
                                )
                pair_market_url = market_base_url + pair
                if (klines['opentime'][-1] - local_peaks[-1][0]) == window_width*timeframe_sec*1000:
                    message2send = f'\U0001F42E\U0001F6A9 {pair}\n' + flag_message + pair_market_url
                    send_message(message2send)
                elif (oc_max[-1] >= local_peaks[-1][1]) and (oc_max[-2] < local_peaks[-1][1]):
                    message2send = f'\U0001F42E\U0001F4C8 {pair}\n' + flag_message + pair_market_url
                    send_message(message2send)
                else:
                    pass

            # Check Bearish Flag
            if local_valleys[-2][1] > local_valleys[-1][1]:
                flag_message = f'L1: %s  %f\nL2: %s  %f\nL3: %s  %f\n' % (
                                str(dt.datetime.fromtimestamp(local_valleys[-3][0]/1000)), local_valleys[-3][1],
                                str(dt.datetime.fromtimestamp(local_valleys[-2][0]/1000)), local_valleys[-2][1],
                                str(dt.datetime.fromtimestamp(local_valleys[-1][0]/1000)), local_valleys[-1][1]
                                )
                pair_market_url = market_base_url + pair
                if (klines['opentime'][-1] - local_valleys[-1][0]) == window_width*timeframe_sec*1000:
                    message2send = f'\U0001F43B\U0001F6A9 {pair}\n' + flag_message + pair_market_url
                    send_message(message2send)
                elif (oc_min[-1] <= local_valleys[-1][1]) and (oc_min[-2] > local_valleys[-1][1]):
                    message2send = f'\U0001F43B\U0001F4C9 {pair}\n' + flag_message + pair_market_url
                    send_message(message2send)
                else:
                    pass

        except Exception as e:
            error_message = 'Error Occurred!\n' + pair + ': ' + traceback.format_exc()
            send_message(error_message)
        finally:
            continue


if __name__ == '__main__':

    # main function
    run()
