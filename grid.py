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
initialBuyQuantity=0.001
buyIncrement=0.0001
sellQuantity=0.001
priceStep = 1000
quantityDecimals = 4
priceDecimals = 2
baseAsset = 'BTC'
quoteAsset = 'USDT'
pair = baseAsset + quoteAsset
numOrders = 3

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
fund_warn_count = 0
buy_orders = []
sell_orders = []
last_highest_open_price = 0

def send_message(message):
    '''
    发送信息到Telegram
    '''
    print(message)  # 输出到日志
    loop.run_until_complete(bot.send_message(chat_id=chat_id, text=message))

def format_price(price):
    """价格抹零，格式化为1000的整数倍"""
    return int(float(price) // 1000 * 1000)

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

def wait_asset_unlock(base_balance, quote_balance, attempts=15, wait_time=1):
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
    global fund_warn_count, buy_orders, sell_orders, last_highest_open_price

    # 获取余额
    balance = get_balance()
    base_balance = balance[baseAsset]['free'] + balance[baseAsset]['locked']
    quote_balance = balance[quoteAsset]['free'] + balance[quoteAsset]['locked']

    # 取消全部挂单
    open_orders = client.get_open_orders(symbol=pair)
    open_orders = [order['orderId'] for order in open_orders]
    if open_orders:
        client.cancel_open_orders(symbol=pair)

    # 检查消失的挂单是否成交
    for order in (set(buy_orders + sell_orders) - set(open_orders)):
        order_info = client.get_order(symbol=pair, orderId=int(order))
        if order_info['status'] == 'FILLED':
            executed_qty = round(float(order_info['executedQty']), quantityDecimals)
            executed_price = round(float(order_info['price']), priceDecimals)
            send_message(f"{order_info['side']} {executed_qty}{baseAsset} at {executed_price}")

    # 资金是否全部解锁
    if not wait_asset_unlock(base_balance, quote_balance):
        send_message("资金未能全部解锁，放弃创建新挂单")
        return

    buy_orders.clear()
    sell_orders.clear()

    last_trade = get_last_trade(pair)
    last_trade_price = float(last_trade['price'])
    last_trade_qty = float(last_trade['qty'])
    last_trade_side = 'BUY' if last_trade['isBuyer'] else 'SELL'
    if base_balance >= sellQuantity:
        refer_price = format_price(last_trade_price)
    else:
        refer_price = max(format_price(last_highest_open_price + priceStep), format_price(current_price))
    if last_trade_side == 'BUY':
        initial_buy_qty = last_trade_qty + buyIncrement
    else:
        initial_buy_qty = initialBuyQuantity

    # 记录最高买单价
    last_highest_open_price = round(refer_price - priceStep, priceDecimals)

    # 买单：往下挂 1000 整数倍的价格
    for i in range(numOrders):
        buy_price = round(refer_price - (i + 1) * priceStep, priceDecimals)
        buy_qty = round(initial_buy_qty + i * buyIncrement, quantityDecimals)
        if quote_balance < buy_price * buy_qty:
            if (fund_warn_count % 60) == 0:
                send_message(f"{quoteAsset}余额: {quote_balance}，无法在{buy_price}买入{buy_qty}{baseAsset}")
            fund_warn_count += 1
            break
        order = place_order('BUY', buy_qty, buy_price)
        if order:
            print(f'在{buy_price}买入{buy_qty}{baseAsset}挂单成功')
            buy_orders.append(order['orderId'])
            quote_balance -= (buy_price * buy_qty)
        if i == (numOrders - 1):
            fund_warn_count = 0

    # 卖单：往上挂 1000 整数倍的价格
    for i in range(numOrders):
        sell_price = round(refer_price + (i + 1) * priceStep, priceDecimals)
        if base_balance < sellQuantity:
            print(f"{baseAsset}余额: {base_balance}，无法在{sell_price}卖出{sellQuantity}{baseAsset}")
            break
        order = place_order('SELL', sellQuantity, sell_price)
        if order:
            print(f'在{sell_price}卖出{sellQuantity}{baseAsset}挂单成功')
            sell_orders.append(order['orderId'])
            base_balance -= sellQuantity

def main():
    """主程序：实时更新价格，执行网格交易"""
    send_message('程序启动')
    while True:
        try:
            # 获取最新价格
            current_price = float(client.ticker_price(symbol=pair)['price'])
            print(f"最新价格: {current_price}")

            # 更新挂单
            update_orders(current_price)

            # 间隔 60 秒更新价格
            time.sleep(60)

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
            time.sleep(5)  # 发生其他错误后短暂暂停再重试

if __name__ == "__main__":
    main()
