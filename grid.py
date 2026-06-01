import os
import time
import hmac
import json
import hashlib
import asyncio
from decimal import Decimal
import threading
import telegram
import traceback
from dotenv import load_dotenv
from binance.spot import Spot
from websocket import WebSocketApp
from binance.error import ClientError, ServerError
import systemd.daemon


# 配置参数
initialBuyQuantity=0.003
buyIncrement=0.0003
sellQuantity=0.003
priceStep = 1000
baseAsset = 'BTC'
quoteAsset = 'U'
pair = baseAsset + quoteAsset
numOrders = 1
dryRun = True  # 只读预演：读取账户和成交数据，但不真实下单、不发Telegram
tradingEnabled = not dryRun
telegramEnabled = not dryRun
websocketRestartInterval = 23 * 60 * 60
restReconcileInterval = 5 * 60
price_step = Decimal(str(priceStep))
buy_increment = Decimal(str(buyIncrement))
initial_buy_quantity = Decimal(str(initialBuyQuantity))
sell_quantity = Decimal(str(sellQuantity))

# 初始化 Binance API 客户端
load_dotenv()
api_key = os.getenv('API_KEY')
api_secret = os.getenv('API_SECRET')
if not api_key or not api_secret:
    raise RuntimeError('API_KEY/API_SECRET must be set for grid.py')
client = Spot(api_key, api_secret)


def get_symbol_filters(symbol):
    """Load Binance symbol filters used for price, quantity and notional checks."""
    exchange_info = client.exchange_info(symbol=symbol)
    filters = {item['filterType']: item for item in exchange_info['symbols'][0]['filters']}
    min_notional_filter = filters.get('MIN_NOTIONAL') or filters.get('NOTIONAL') or {}
    return {
        'price_quantum': Decimal(filters['PRICE_FILTER']['tickSize']),
        'quantity_quantum': Decimal(filters['LOT_SIZE']['stepSize']),
        'min_notional': Decimal(min_notional_filter.get('minNotional', '0')),
    }

symbol_filters = get_symbol_filters(pair)
price_quantum = symbol_filters['price_quantum']
quantity_quantum = symbol_filters['quantity_quantum']
min_notional = symbol_filters['min_notional']
print(f"Loaded {pair} filters: tickSize={price_quantum}, stepSize={quantity_quantum}, minNotional={min_notional}")

# 初始化Telegram Bot
bot_token = os.getenv('BOT_TOKEN')
chat_id = os.getenv('CHAT_ID')
bot = telegram.Bot(bot_token) if telegramEnabled and bot_token and chat_id else None
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# 辅助变量
buy_orders = []
sell_orders = []
last_refer_price = Decimal('0')
filled_order_events = []
filled_order_events_lock = threading.RLock()
order_update_event = threading.Event()
ws_restart_event = threading.Event()
ws_stopping_event = threading.Event()
user_stream_ready_event = threading.Event()

def to_decimal(value):
    return Decimal(str(value))

def floor_to_step(value, step):
    value = to_decimal(value)
    return (value // step) * step

def quantize_quantity(quantity):
    return floor_to_step(quantity, quantity_quantum)

def quantize_price(price):
    return floor_to_step(price, price_quantum)


def has_min_notional(price, quantity):
    return min_notional <= 0 or price * quantity >= min_notional

def send_message(message):
    """
    发送信息到Telegram
    """
    print(message)  # 输出到日志
    if telegramEnabled and bot:
        try:
            loop.run_until_complete(bot.send_message(chat_id=chat_id, text=message))
        except Exception as e:
            print(f"发送消息时发生错误: {e}")

def format_price(price):
    """价格抹零，格式化为priceStep的整数倍加priceStep/2"""
    return quantize_price((to_decimal(price) // price_step * price_step) + (price_step / 2))

def get_balance():
    """获取资产余额"""
    balance = {
        baseAsset: {'free': Decimal('0'), 'locked': Decimal('0')},
        quoteAsset: {'free': Decimal('0'), 'locked': Decimal('0')},
    }
    try:
        account_info = client.account()
        for each in account_info['balances']:
            if each['asset'] in [baseAsset, quoteAsset]:
                balance[each['asset']] = {'free': to_decimal(each['free']), 'locked': to_decimal(each['locked'])}
        return balance
    except Exception as e:
        print(f"获取余额失败: {e}")
        raise

def get_last_trade_summary(symbol):
    """获取最近成交所属订单的累计成交数量"""
    try:
        my_trades = client.my_trades(symbol)
        if not my_trades:
            print("无法获取历史交易数据，跳过本次更新")
            return None
        last_trade = my_trades[-1]
    except Exception as e:
        print(f"获取最新交易失败: {e}")
        raise

    try:
        order_info = client.get_order(symbol=symbol, orderId=int(last_trade['orderId']))
        qty = to_decimal(order_info['executedQty'])
    except Exception as e:
        print(f"获取订单累计成交数量失败，回退到单笔成交数量: {e}")
        qty = to_decimal(last_trade['qty'])

    return {
        'side': 'BUY' if last_trade['isBuyer'] else 'SELL',
        'qty': qty,
        'price': to_decimal(last_trade['price']),
    }

def refresh_balance_if_needed(asset, current_balance, required_balance, attempts=3, wait_time=1):
    """余额不足时短暂刷新，避免取消挂单后的余额延迟造成误判"""
    if current_balance >= required_balance:
        return current_balance

    for attempt in range(attempts):
        try:
            print(f"{asset}余额暂不足，等待{wait_time}秒后刷新... (尝试 {attempt + 1}/{attempts})")
            time.sleep(wait_time)
            balance = get_balance()
            latest_balance = balance[asset]['free'] + balance[asset]['locked']
            if latest_balance >= required_balance:
                return latest_balance
            current_balance = latest_balance
        except Exception as e:
            print(f"刷新{asset}余额时发生错误: {e}")

    return current_balance

def push_filled_event(data):
    event = {
        'orderId': int(data['i']),
        'side': data['S'],
        'qty': to_decimal(data['z']),
        'price': to_decimal(data['p']),
        'time': int(data.get('T') or data.get('E') or 0),
    }
    with filled_order_events_lock:
        filled_order_events.append(event)


def pop_filled_events():
    with filled_order_events_lock:
        events = list(filled_order_events)
        filled_order_events.clear()
    return events

def sign_websocket_params(params):
    payload = '&'.join(f"{key}={params[key]}" for key in sorted(params))
    return hmac.new(api_secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()

def parse_websocket_message(message):
    if isinstance(message, str):
        message = json.loads(message)
    if isinstance(message, dict) and 'data' in message:
        message = message['data']
    if isinstance(message, dict) and 'event' in message:
        message = message['event']
    return message

def handle_websocket_message(_, message):
    try:
        data = parse_websocket_message(message)
        if not isinstance(data, dict):
            return

        if data.get('id') == 'user-data-subscribe':
            if data.get('status') == 200:
                print(f"User Data Stream订阅成功: {data.get('result')}")
                user_stream_ready_event.set()
            else:
                print(f"User Data Stream订阅失败: {data}")
                ws_restart_event.set()
            return

        event_type = data.get('e')
        if event_type == 'executionReport' and data.get('s') == pair:
            status = data.get('X')
            order_id = int(data.get('i'))
            print(f"订单事件: {data.get('S')} {status} orderId={order_id} lastQty={data.get('l')} cumQty={data.get('z')}")
            if status == 'FILLED' and order_id in buy_orders + sell_orders:
                push_filled_event(data)
                order_update_event.set()
            return

        if event_type in ['eventStreamTerminated', 'serverShutdown']:
            print(f"WebSocket事件流结束: {event_type}")
            ws_restart_event.set()
    except Exception as e:
        print(f"处理WebSocket消息失败: {e}")
        traceback.print_exc()

def handle_websocket_error(_, error):
    print(f"WebSocket错误: {error}")
    ws_restart_event.set()

def handle_websocket_close(*_):
    if ws_stopping_event.is_set():
        return
    print('WebSocket连接关闭，准备重连')
    ws_restart_event.set()

def subscribe_user_data_stream(ws):
    params = {
        'apiKey': api_key,
        'recvWindow': 5000,
        'timestamp': int(time.time() * 1000),
    }
    params['signature'] = sign_websocket_params(params)
    ws.send(json.dumps({
        'id': 'user-data-subscribe',
        'method': 'userDataStream.subscribe.signature',
        'params': params,
    }))

def start_websocket_client():
    ws_stopping_event.clear()
    ws_restart_event.clear()
    user_stream_ready_event.clear()
    ws = WebSocketApp(
        'wss://ws-api.binance.com:443/ws-api/v3?returnRateLimits=false',
        on_open=subscribe_user_data_stream,
        on_message=handle_websocket_message,
        on_error=handle_websocket_error,
        on_close=handle_websocket_close,
    )
    threading.Thread(target=ws.run_forever, name='user-data-websocket', daemon=True).start()
    print('User Data Stream WebSocket已启动')
    return ws, time.time()

def start_ready_websocket_client(user_ws=None, attempts=3):
    if user_ws:
        stop_websocket_client(user_ws)
        time.sleep(1)

    for attempt in range(attempts):
        user_ws, started_at = start_websocket_client()
        if user_stream_ready_event.wait(timeout=10):
            return user_ws, started_at

        print(f"User Data Stream订阅确认超时，准备重试... (尝试 {attempt + 1}/{attempts})")
        stop_websocket_client(user_ws)
        time.sleep(3)

    raise RuntimeError('User Data Stream订阅确认超时')

def stop_websocket_client(user_ws):
    if not user_ws:
        return

    ws_stopping_event.set()
    try:
        user_ws.close()
    except Exception as e:
        print(f"停止WebSocket失败: {e}")

def place_order(side, quantity, price):
    """挂单函数"""
    try:
        order = client.new_order(
            symbol=pair,
            side=side,
            type='LIMIT',
            timeInForce='GTC',
            quantity=format(quantize_quantity(quantity), 'f'),
            price=format(quantize_price(price), 'f')
        )
        return order
    except ClientError as e:
        send_message(f"挂单失败!\nerror_code: {e.error_code}\nerror_message: {e.error_message}")
        return None
    except ServerError as e:
        send_message(f"挂单服务器错误！\n{e.message}")
        return None
    except Exception as e:
        print(f"挂单时发生未知错误: {e}")
        send_message(f"挂单时发生未知错误: {e}")
        return None

def update_orders():
    """更新挂单"""
    global buy_orders, sell_orders, last_refer_price

    try:
        balance = get_balance()
        base_balance = balance[baseAsset]['free'] + balance[baseAsset]['locked']
        quote_balance = balance[quoteAsset]['free'] + balance[quoteAsset]['locked']

        open_orders = client.get_open_orders(symbol=pair)
        open_orders = [order['orderId'] for order in open_orders]

        filled_events = pop_filled_events()
        filled_event_by_id = {event['orderId']: event for event in filled_events}
        filled_orders = set(buy_orders + sell_orders) - set(open_orders)
        filled_orders.update(filled_event_by_id.keys())

        if not filled_orders:
            if sell_orders or buy_orders:
                print('等待挂单成交...')
                return

            last_trade = get_last_trade_summary(pair)
            if not last_trade:
                return

            last_trade_side = last_trade['side']
            last_trade_qty = last_trade['qty']
            refer_price = format_price(last_trade['price'])
        else:
            refer_price = last_refer_price
            filled_message = ''
            last_trade_time = 0
            processed_fills = 0

            for order in filled_orders:
                event = filled_event_by_id.get(int(order))
                if event:
                    filled_trade_side = event['side']
                    filled_trade_qty = quantize_quantity(event['qty'])
                    filled_trade_price = quantize_price(event['price'])
                    filled_time = event['time']
                else:
                    order_info = client.get_order(symbol=pair, orderId=int(order))
                    if order_info['status'] != 'FILLED':
                        continue
                    filled_trade_side = order_info['side']
                    filled_trade_qty = quantize_quantity(order_info['executedQty'])
                    filled_trade_price = quantize_price(order_info['price'])
                    filled_time = int(order_info['updateTime'])

                processed_fills += 1
                filled_message += f"{filled_trade_side} {filled_trade_qty}{baseAsset} at {filled_trade_price}\n"
                if filled_trade_side == 'BUY':
                    refer_price -= price_step
                else:
                    refer_price += price_step

                if filled_time > last_trade_time:
                    last_trade_time = filled_time
                    last_trade_side = filled_trade_side
                    last_trade_qty = filled_trade_qty

            if processed_fills == 0:
                last_trade = get_last_trade_summary(pair)
                if not last_trade:
                    return
                last_trade_side = last_trade['side']
                last_trade_qty = last_trade['qty']

        if open_orders and tradingEnabled:
            client.cancel_open_orders(symbol=pair)
        elif open_orders:
            print('只读预演模式，跳过取消现有挂单')

        if filled_orders and filled_message:
            send_message(filled_message.strip())

        buy_orders.clear()
        sell_orders.clear()

        if last_trade_side == 'BUY':
            initial_buy_qty = last_trade_qty + buy_increment
        else:
            initial_buy_qty = initial_buy_quantity

        for i in range(numOrders):
            buy_price = quantize_price(refer_price - (i + 1) * price_step)
            buy_qty = quantize_quantity(initial_buy_qty + i * buy_increment)
            required_quote = buy_price * buy_qty
            if not has_min_notional(buy_price, buy_qty):
                send_message(f"订单金额: {required_quote}，低于最小名义金额: {min_notional}")
                break
            quote_balance = refresh_balance_if_needed(quoteAsset, quote_balance, required_quote)
            if quote_balance < required_quote:
                send_message(f"{quoteAsset}余额: {quote_balance}，无法在{buy_price}买入{buy_qty}{baseAsset}")
                break
            if not tradingEnabled:
                print(f'在{buy_price}买入{buy_qty}{baseAsset}挂单成功')
                continue
            order = place_order('BUY', buy_qty, buy_price)
            if order:
                print(f'在{buy_price}买入{buy_qty}{baseAsset}挂单成功')
                buy_orders.append(order['orderId'])
                quote_balance -= required_quote

        for i in range(numOrders):
            sell_price = quantize_price(refer_price + (i + 1) * price_step)
            if not has_min_notional(sell_price, sell_quantity):
                send_message(f"订单金额: {sell_price * sell_quantity}，低于最小名义金额: {min_notional}")
                break
            base_balance = refresh_balance_if_needed(baseAsset, base_balance, sell_quantity)
            if base_balance < sell_quantity:
                print(f"{baseAsset}余额: {base_balance}，无法在{sell_price}卖出{sell_quantity}{baseAsset}")
                break
            if not tradingEnabled:
                print(f'在{sell_price}卖出{sell_quantity}{baseAsset}挂单成功')
                continue
            order = place_order('SELL', sell_quantity, sell_price)
            if order:
                print(f'在{sell_price}卖出{sell_quantity}{baseAsset}挂单成功')
                sell_orders.append(order['orderId'])
                base_balance -= sell_quantity

        last_refer_price = quantize_price(refer_price)

    except Exception as e:
        print(f"更新订单时发生错误: {e}")
        traceback.print_exc()
        send_message(f"更新订单时发生错误: {str(e)}")

def main():
    """主程序：WebSocket接收订单事件，REST负责下单、撤单和兜底对账"""
    print('程序启动')
    user_ws = None
    ws_started_at = 0
    next_rest_reconcile = 0
    last_watchdog = 0

    try:
        user_ws, ws_started_at = start_ready_websocket_client()
        next_rest_reconcile = time.time() + restReconcileInterval

        update_orders()
        systemd.daemon.notify('READY=1')

        while True:
            try:
                now = time.time()

                if ws_restart_event.is_set() or now - ws_started_at >= websocketRestartInterval:
                    ws_restart_event.clear()
                    user_ws, ws_started_at = start_ready_websocket_client(user_ws)

                if order_update_event.wait(timeout=1):
                    order_update_event.clear()
                    update_orders()
                    next_rest_reconcile = time.time() + restReconcileInterval

                if time.time() >= next_rest_reconcile:
                    print('执行REST兜底对账')
                    update_orders()
                    next_rest_reconcile = time.time() + restReconcileInterval

                if time.time() - last_watchdog >= 15:
                    systemd.daemon.notify('WATCHDOG=1')
                    last_watchdog = time.time()

            except ClientError as e:
                systemd.daemon.notify('WATCHDOG=1')
                if e.status_code == 429:
                    send_message("达到API速率限制，程序暂停10分钟")
                    time.sleep(600)
                elif e.status_code == 418:
                    send_message("超出API速率限制，IP被封禁，程序暂停30分钟")
                    time.sleep(1800)
                else:
                    send_message(f"API客户端错误\nerror_code: {e.error_code}\nerror_message: {e.error_message}")
                    time.sleep(30)
            except Exception as e:
                systemd.daemon.notify('WATCHDOG=1')
                traceback.print_exc()
                send_message(f"一般错误: {str(e)}")
                time.sleep(60)
    finally:
        stop_websocket_client(user_ws)

if __name__ == "__main__":
    main()
