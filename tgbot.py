import os
import pytz
import datetime as dt
from utils import *
from config import Config
from pairdata import PairData
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


class TelegramBot:
    def __init__(self, token):
        self.tz = pytz.timezone('Asia/Shanghai')
        self.watchlist_path = Config.WL_PATH
        self.pricealert_path = Config.PA_PATH
        self.application = Application.builder().token(token).build()

    async def start_command(self, update, context):
        await update.message.reply_text("Hello, welcome to Biao's Nice Soup!")

    async def tp_command(self, update, context):
        msg_text = str(update.message.text).split()
        if len(msg_text) == 3:
            pair = msg_text[1].upper() + 'USDT'
            timeframe = msg_text[2].lower()
            try:
                data = PairData(pair)
                ema3 = data.get_ema3(timeframe)
                if ema3['fast'][-2] > ema3['slow'][-2]:
                    tp1 = ema3['fast'][-2] + 1*(ema3['fast'][-2] - ema3['slow'][-2])
                    tp2 = ema3['fast'][-2] + 2*(ema3['fast'][-2] - ema3['slow'][-2])
                else:
                    tp1 = ema3['fast'][-2] - 1*(ema3['slow'][-2] - ema3['fast'][-2])
                    tp2 = ema3['fast'][-2] - 2*(ema3['slow'][-2] - ema3['fast'][-2])
                await update.message.reply_text('TP1: ' + str(tp1) + '\nTP2: ' + str(tp2))
            except Exception as e:
                await update.message.reply_text('Error Occurred!\n' + str(e))
        else:
            await update.message.reply_text("Sorry, invalid input.\nUsage example: /tp BTC 1h")

    async def get_peaks(self, update, context):
        msg_text = str(update.message.text).split()
        if len(msg_text) >= 3:
            pair = msg_text[1].upper() + 'USDT'
            timeframe = msg_text[2].lower()
            peak_num = 3
            if len(msg_text) >= 4:
                peak_num = int(msg_text[3])
            try:
                data = PairData(pair)
                klines = data.get_klines(timeframe)
                window_width = Config.MAXMIN_WINDOW_WIDTH
                oc_max = data.get_oc_max(timeframe)
                local_peaks_index = data.get_peaks(oc_max, window_width)
                local_peaks = [(klines['opentime'][i], oc_max[i]) for i in local_peaks_index]
                peak_message = ''
                for i in range(peak_num):
                    peak_message += f'H{peak_num-i}: %s  %f\n' % (
                        str(dt.datetime.fromtimestamp(local_peaks[-peak_num+i][0]/1000, self.tz)), 
                        local_peaks[-peak_num+i][1])
                await update.message.reply_text(pair + '\n' + peak_message)
            except Exception as e:
                await update.message.reply_text('Error Occurred!\n' + str(e))
        else:
            await update.message.reply_text("Sorry, invalid input.\nUsage example: /hh BTC 1h [4]")

    async def get_valleys(self, update, context):
        msg_text = str(update.message.text).split()
        if len(msg_text) >= 3:
            pair = msg_text[1].upper() + 'USDT'
            timeframe = msg_text[2].lower()
            valley_num = 3
            if len(msg_text) >= 4:
                valley_num = int(msg_text[3])
            try:
                data = PairData(pair)
                klines = data.get_klines(timeframe)
                window_width = Config.MAXMIN_WINDOW_WIDTH
                oc_min = data.get_oc_min(timeframe)
                oc_min_neg = [-each for each in oc_min]
                local_valleys_index = data.get_peaks(oc_min_neg, window_width)
                local_valleys = [(klines['opentime'][i], oc_min[i]) for i in local_valleys_index]
                valley_message = ''
                for i in range(valley_num):
                    valley_message += f'L{valley_num-i}: %s  %f\n' % (
                        str(dt.datetime.fromtimestamp(local_valleys[-valley_num+i][0]/1000, self.tz)), 
                        local_valleys[-valley_num+i][1])
                await update.message.reply_text(pair + '\n' + valley_message)
            except Exception as e:
                await update.message.reply_text('Error Occurred!\n' + str(e))
        else:
            await update.message.reply_text("Sorry, invalid input.\nUsage example: /ll BTC 1h")

    async def get_bullflag(self, update, context):
        msg_text = str(update.message.text).split()
        if len(msg_text) >= 2:
            timeframe = msg_text[1].lower()
            try:
                watchlist = read_json_file(self.watchlist_path)
                await update.message.reply_text(f'Start checking {len(watchlist)} pairs...')
                bullflag_message = f'{timeframe} BullFlag:\n'
                for pair in watchlist:
                    data = PairData(pair)
                    klines = data.get_klines(timeframe)
                    window_width = Config.MAXMIN_WINDOW_WIDTH
                    oc_max = data.get_oc_max(timeframe)
                    local_peaks_index = data.get_peaks(oc_max, window_width)
                    ema_trend = data.check_ema(timeframe=timeframe, shift=local_peaks_index[-1])
                    if (ema_trend == 'LONG') and (oc_max[-1] <= oc_max[local_peaks_index[-1]]):
                        peak_time = str(dt.datetime.fromtimestamp(klines['opentime'][local_peaks_index[-1]]/1000, self.tz))
                        bullflag_message += f'{pair}  {peak_time}\n'
                await update.message.reply_text(bullflag_message)
            except Exception as e:
                await update.message.reply_text('Error Occurred!\n' + str(e))
        else:
            await update.message.reply_text("Sorry, invalid input.\nUsage example: /bull 1h")

    async def get_bearflag(self, update, context):
        msg_text = str(update.message.text).split()
        if len(msg_text) >= 2:
            timeframe = msg_text[1].lower()
            try:
                watchlist = read_json_file(self.watchlist_path)
                await update.message.reply_text(f'Start checking {len(watchlist)} pairs...')
                bearflag_message = f'{timeframe} BearFlag:\n'
                for pair in watchlist:
                    data = PairData(pair)
                    klines = data.get_klines(timeframe)
                    window_width = Config.MAXMIN_WINDOW_WIDTH
                    oc_min = data.get_oc_min(timeframe)
                    oc_min_neg = [-each for each in oc_min]
                    local_valleys_index = data.get_peaks(oc_min_neg, window_width)
                    ema_trend = data.check_ema(timeframe=timeframe, shift=local_valleys_index[-1])
                    if (ema_trend == 'SHORT') and (oc_min[-1] >= oc_min[local_valleys_index[-1]]):
                        valley_time = str(dt.datetime.fromtimestamp(klines['opentime'][local_valleys_index[-1]]/1000, self.tz))
                        bearflag_message += f'{pair}  {valley_time}\n'
                await update.message.reply_text(bearflag_message)
            except Exception as e:
                await update.message.reply_text('Error Occurred!\n' + str(e))
        else:
            await update.message.reply_text("Sorry, invalid input.\nUsage example: /bear 1h")

    async def get_pricealert(self, update, context):
        try:
            pricealert = read_json_file(self.pricealert_path)
            if not pricealert:
                pa_message = 'Price Alerts:\n'
                for key, value in pricealert.items():
                    pa_message += f'{key}  {value}\n'
            else:
                pa_message = 'No price alert found.'
            await update.message.reply_text(pa_message)
        except Exception as e:
            await update.message.reply_text('Failed to read price alerts.\n' + str(e))

    async def add_pricealert(self, update, context):
        try:
            pricealert = read_json_file(self.pricealert_path)
            msg_text = str(update.message.text).split()
            if len(msg_text) >= 3:
                pair = msg_text[1].upper() + 'USDT'
                price = msg_text[2]
                pricealert[pair] = price
                write_to_json_file(pricealert, self.pricealert_path)
                await update.message.reply_text(f'Added ({pair}, {price}) to price alerts.')
            else:
                await update.message.reply_text("Sorry, invalid input.\nUsage example: /addpa BTC 60000")
        except Exception as e:
            await update.message.reply_text(f'Failed to add new price alert.\n' + str(e))

    async def del_pricealert(self, update, context):
        try:
            pricealert = read_json_file(self.pricealert_path)
            msg_text = str(update.message.text).split()
            if len(msg_text) == 2:
                pair = msg_text[1].upper() + 'USDT'
                if pair in pricealert.keys():
                    price = pricealert.pop(pair)
                    write_to_json_file(pricealert, self.pricealert_path)
                    await update.message.reply_text(f'Removed ({pair}, {price}) from price alerts.')
                else:
                    await update.message.reply_text(f'{pair} is not in price alerts')
            else:
                await update.message.reply_text("Sorry, invalid input.\nUsage example: /delpa BTC")
        except Exception as e:
            await update.message.reply_text(f'Failed to delete this price alert.\n' + str(e))

    def add_handlers(self):
        self.application.add_handler(CommandHandler('start', self.start_command))
        self.application.add_handler(CommandHandler('tp', self.tp_command))
        self.application.add_handler(CommandHandler('hh', self.get_peaks))
        self.application.add_handler(CommandHandler('ll', self.get_valleys))
        self.application.add_handler(CommandHandler('bull', self.get_bullflag))
        self.application.add_handler(CommandHandler('bear', self.get_bearflag))
        self.application.add_handler(CommandHandler('getpa', self.get_pricealert))
        self.application.add_handler(CommandHandler('addpa', self.add_pricealert))
        self.application.add_handler(CommandHandler('delpa', self.del_pricealert))

    def run(self):
        self.add_handlers()
        print("Bot is running...")
        self.application.run_polling()

    async def send_message(self, chat_id, text):
        await self.application.bot.send_message(chat_id=chat_id, text=text)

if __name__ == '__main__':
    load_dotenv()
    token = os.getenv('BOT_TOKEN')
    bot = TelegramBot(token)
    bot.run()