import requests
import json

debug_mode = False
if debug_mode == True:
    proxies = {
    'https': 'http://127.0.0.1:7890/',
    'http': 'http://127.0.0.1:7890/'
    }
else:
    proxies = None

base_url = 'https://fapi.binance.com'
pairs_url = '/fapi/v1/exchangeInfo'
kline_url = '/fapi/v1/klines'


def get_all_pairs(base_url, pairs_url):
    url = base_url + pairs_url
    res = requests.get(url, proxies=proxies)
    raw_data = json.loads(res.text)['symbols']
    pairs = [each['symbol'] for each in raw_data if (each['contractType']=='PERPETUAL' and each['quoteAsset']=='USDT')]
    return pairs

def get_daily_volume(pair):
    url = base_url + kline_url
    params = {'symbol': pair, 'interval': '1M'}
    res = requests.get(url, params=params, proxies=proxies)
    raw_data = json.loads(res.text)
    if len(raw_data) >= 3:
        daily_volume = int(float(raw_data[-2][7])/30/1000000)
    else:
        daily_volume = 0
    return daily_volume

volume_dict = {}
all_pairs = get_all_pairs(base_url, pairs_url)
for pair in all_pairs:
    try:
        print(str(all_pairs.index(pair)) + '/' + str(len(all_pairs)))
        volume = get_daily_volume(pair)
        volume_dict[pair] = volume
    except Exception as e:
        print(pair)
        print(e)
    finally:
        continue
sorted_dict = dict(sorted(volume_dict.items(), key=lambda item: item[1], reverse=True))
for key, value in sorted_dict.items():
    print(key+': '+str(value)+'M')