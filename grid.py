import os
import time
import math
import asyncio
import telegram
import traceback
from dotenv import load_dotenv
from binance.spot import Spot
from binance.error import ClientError, ServerError


# 配置参数
initialBuyQuantity=0.007
buyIncrement=0.001
sellQuantity=0.007
priceStep = 1000
quantityDecimals = 3
priceDecimals = 2
baseAsset = 'BTC'
quoteAsset = 'FDUSD'
pair = baseAsset + quoteAsset
numOrders = 3
dryRun = True

# 初始化 Binance API 客户端
load_dotenv()
api_key = os.getenv('API_KEY')
api_secret = os.getenv('API_SECRET')
client = Spot(api_key, api_secret)

# 初始化Telegram Bot
bot_token = os.getenv('BOT_TOKEN')
chat_id = os.getenv('CHAT_ID')
bot = telegram.Bot(bot_token)
loop = asyncio.get_event_loop()

# 辅助变量
buy_orders = []
sell_orders = []
last_refer_price = 0

def send_message(message):
    '''
    发送信息到Telegram
    '''
    print(message)  # 输出到日志
    if not dryRun:
        loop.run_until_complete(bot.send_message(chat_id=chat_id, text=message))

def format_price(price):
    """价格抹零，格式化为priceStep的整数倍"""
    return int(float(price) // priceStep * priceStep)

def get_balance():
    """获取资产余额"""
    balance = {}
    account_info = client.account()
    for each in account_info['balances']:
        if each['asset'] in [baseAsset, quoteAsset]:
            balance[each['asset']] = {'free': float(each['free']), 'locked': float(each['locked'])}
    return balance

def get_last_trade(symbol):
    """获取最新成交订单信息"""
    my_trades = client.my_trades(symbol)
    return my_trades[-1]

def wait_asset_unlock(base_balance, quote_balance, attempts=5, wait_time=1):
    """检查是否所有挂单已取消，资金解锁"""
    for attempt in range(attempts):
        balance = get_balance()
        base_free_balance = balance[baseAsset]['free']
        quote_free_balance = balance[quoteAsset]['free']
        if (math.isclose(base_free_balance, base_balance, abs_tol=1e-9) and 
            math.isclose(quote_free_balance, quote_balance, abs_tol=1e-9)):
            return True
        else:
            if attempt < attempts - 1:
                print(f"资金尚未全部解锁，等待{wait_time}秒再检查... (尝试 {attempt + 1}/{attempts})")
                time.sleep(wait_time)
    # 仍未解锁
    print("资金未能全部解锁，退出程序。")
    return False

def place_order(side, quantity, price):
    """挂单函数"""
    try:
        order = client.new_order(
            symbol=pair,
            side=side,
            type='LIMIT',
            timeInForce='GTC',
            quantity=round(quantity, quantityDecimals),
            price=round(price, priceDecimals)
        )
        return order
    except ClientError as e:
        send_message(f"挂单失败!\nerror_code: {e.error_code}\nerror_message: {e.error_message}")
        return None
    except ServerError as e:
        send_message(f"挂单服务器错误！\n{e.message}")
        return None

def update_orders(current_price):
    """检查并更新买卖挂单，保持每侧 3 个挂单"""
    global buy_orders, sell_orders, last_refer_price

    # 获取余额
    balance = get_balance()
    base_balance = balance[baseAsset]['free'] + balance[baseAsset]['locked']
    quote_balance = balance[quoteAsset]['free'] + balance[quoteAsset]['locked']

    # 检查是否有挂单成交
    open_orders = client.get_open_orders(symbol=pair)
    open_orders = [order['orderId'] for order in open_orders]
    filled_orders = set(buy_orders + sell_orders) - set(open_orders)

    # 获取最后一笔成交信息作为初始数据
    last_trade = get_last_trade(pair)
    last_trade_side = 'BUY' if last_trade['isBuyer'] else 'SELL'
    last_trade_qty = float(last_trade['qty'])
    last_trade_price = last_trade['price']

    # 挂单没有减少，分情况处理
    if not filled_orders:
        # 卖单一侧有挂单
        if sell_orders:
            print('等待挂单成交...')
            return
        # 只有买单一侧有挂单(仓位已清空，追高接货)
        elif buy_orders:
            if current_price >= (last_refer_price + priceStep):
                # 风控
                if current_price < (last_trade_price + 10 * priceStep):
                    refer_price = (last_refer_price + priceStep)
                else:
                    print('价格偏离最近成交价太远，停止挂买单')
                    return
            else:
                print('等待挂单成交...')
                return
        # 买卖两侧均无挂单(首次启动)
        else:
            refer_price = format_price(last_trade_price)
    # 挂单减少(成交或取消)
    else:
        # 确认消失的挂单是否成交
        refer_price = last_refer_price
        filled_message = ''
        last_trade_time = 0
        for order in filled_orders:
            order_info = client.get_order(symbol=pair, orderId=int(order))
            # 确认成交，使用最新成交订单的数据
            if order_info['status'] == 'FILLED':
                filled_trade_side = order_info['side']
                filled_trade_qty = round(float(order_info['executedQty']), quantityDecimals)
                filled_trade_price = round(float(order_info['price']), priceDecimals)
                filled_message += f"{filled_trade_side} {filled_trade_qty}{baseAsset} at {filled_trade_price}"
                if filled_trade_side == 'BUY':
                    refer_price -= priceStep
                else:
                    refer_price += priceStep
                # 更新最新成交订单数据
                filled_time = order_info['updateTime']
                if filled_time > last_trade_time:
                    last_trade_time = filled_time
                    last_trade_side = filled_trade_side
                    last_trade_qty = filled_trade_qty

    # 取消剩余挂单
    if open_orders:
        client.cancel_open_orders(symbol=pair)

    # 资金是否全部解锁
    if not wait_asset_unlock(base_balance, quote_balance):
        send_message("资金尚未全部解锁，无法创建新挂单")
        return

    # 发送成交信息
    if filled_orders and filled_message:
        send_message(filled_message)

    buy_orders.clear()
    sell_orders.clear()

    if last_trade_side == 'BUY':
        initial_buy_qty = last_trade_qty + buyIncrement
    else:
        initial_buy_qty = initialBuyQuantity

    # 买单：往下挂 priceStep 整数倍的价格
    for i in range(numOrders):
        buy_price = round(refer_price - (i + 1) * priceStep, priceDecimals)
        buy_qty = round(initial_buy_qty + i * buyIncrement, quantityDecimals)
        if quote_balance < buy_price * buy_qty:
            send_message(f"{quoteAsset}余额: {quote_balance}，无法在{buy_price}买入{buy_qty}{baseAsset}")
            break
        if dryRun:
            print(f'在{buy_price}买入{buy_qty}{baseAsset}挂单成功')
            continue
        order = place_order('BUY', buy_qty, buy_price)
        if order:
            print(f'在{buy_price}买入{buy_qty}{baseAsset}挂单成功')
            buy_orders.append(order['orderId'])
            quote_balance -= (buy_price * buy_qty)

    # 卖单：往上挂 priceStep 整数倍的价格
    for i in range(numOrders):
        sell_price = round(refer_price + (i + 1) * priceStep, priceDecimals)
        if base_balance < sellQuantity:
            print(f"{baseAsset}余额: {base_balance}，无法在{sell_price}卖出{sellQuantity}{baseAsset}")
            break
        if dryRun:
            print(f'在{sell_price}卖出{sellQuantity}{baseAsset}挂单成功')
            continue
        order = place_order('SELL', sellQuantity, sell_price)
        if order:
            print(f'在{sell_price}卖出{sellQuantity}{baseAsset}挂单成功')
            sell_orders.append(order['orderId'])
            base_balance -= sellQuantity

    # 记录参考价
    last_refer_price = round(refer_price, priceDecimals)

def main():
    """主程序：实时更新价格，执行网格交易"""
    # send_message('程序启动')
    while True:
        try:
            # 获取最新价格
            current_price = float(client.ticker_price(symbol=pair)['price'])
            print(f"最新价格: {current_price}")

            # 更新挂单
            update_orders(current_price)

            # 间隔 3 秒更新价格
            time.sleep(3)

        except ClientError as e:
            if e.status_code == 429:
                send_message("达到API速率限制，程序暂停10分钟")
                time.sleep(600)
            elif e.status_code == 418:
                send_message("超出API速率限制，IP被封禁，程序暂停30分钟")
                time.sleep(1800)
            else:
                send_message(f"API客户端错误\nerror_code: {e.error_code}\nerror_message: {e.error_message}")
        except Exception as e:
            traceback.print_exc()
            send_message(f"一般错误: {str(e)}")
            time.sleep(60)  # 发生其他错误后短暂暂停再重试

if __name__ == "__main__":
    main()