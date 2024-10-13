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
                bullflag_message = f'{timeframe} BullFlag:\n'
                for pair in watchlist:
                    data = PairData(pair)
                    klines = data.get_klines(timeframe)
                    window_width = Config.MAXMIN_WINDOW_WIDTH
                    oc_max = data.get_oc_max(timeframe)
                    local_peaks_index = data.get_peaks(oc_max, window_width)
                    ema_trend = data.check_ema(timeframe=timeframe, shift=local_peaks_index[-1])
                    if (ema_trend == 'LONG') and (oc_max[-1] <= oc_max[local_peaks_index[-1]]):
                        peak_time = str(dt.datetime.fromtimestamp(klines['opentime'][local_peaks_index[-1]]/1000, tz))
                        bullflag_message += f'{pair}  {peak_time}\n'
                await update.message.reply_text(bullflag_message)
            except Exception as e:
                await update.message.reply_text('Error Occurred!\n' + str(e))
        else:
            await update.message.reply_text("Sorry, invalid input.\nUsage example: /bullflag 1h")

    async def get_bearflag(self, update, context):
        msg_text = str(update.message.text).split()
        if len(msg_text) >= 2:
            timeframe = msg_text[1].lower()
            try:
                watchlist = read_json_file(self.watchlist_path)
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
                        valley_time = str(dt.datetime.fromtimestamp(klines['opentime'][local_valleys_index[-1]]/1000, tz))
                        bearflag_message += f'{pair}  {valley_time}\n'
                await update.message.reply_text(bearflag_message)
            except Exception as e:
                await update.message.reply_text('Error Occurred!\n' + str(e))
        else:
            await update.message.reply_text("Sorry, invalid input.\nUsage example: /bearflag 1h")

    async def get_watchlist(self, update, context):
        try:
            watchlist = str(read_json_file(self.watchlist_path))
            await update.message.reply_text(watchlist)
        except Exception as e:
            await update.message.reply_text('Failed to read watchlist\n' + str(e))

    async def add_watchlist(self, update, context):
        try:
            watchlist = read_json_file(self.watchlist_path)
            msg_text = str(update.message.text).split()
            if len(msg_text) == 2:
                pair = msg_text[1].upper() + 'USDT'
                if pair not in watchlist:
                    watchlist.append(pair)
                    write_to_json_file(watchlist, self.watchlist_path)
                    watchlist = str(read_json_file(self.watchlist_path))
                    await update.message.reply_text(f'Added {pair} to watchlist. New watchlist:\n' + watchlist)
                else:
                    await update.message.reply_text(f'{pair} already in watchlist.')
            else:
                await update.message.reply_text("Sorry, invalid input.\nUsage example: /addwl BTC")
        except Exception as e:
            await update.message.reply_text(f'Failed to add {pair}\n' + str(e))

    async def del_watchlist(self, update, context):
        try:
            watchlist = read_json_file(self.watchlist_path)
            msg_text = str(update.message.text).split()
            if len(msg_text) == 2:
                pair = msg_text[1].upper() + 'USDT'
                if pair in watchlist:
                    watchlist.remove(pair)
                    write_to_json_file(watchlist, self.watchlist_path)
                    await update.message.reply_text(f'Removed {pair} from watchlist. New watchlist:\n' + str(watchlist))
                else:
                    await update.message.reply_text(f'{pair} is not in watchlist')
            else:
                await update.message.reply_text("Sorry, invalid input.\nUsage example: /delwl BTC")
        except Exception as e:
            await update.message.reply_text(f'Failed to delete {pair}\n' + str(e))

    def add_handlers(self):
        self.application.add_handler(CommandHandler('start', self.start_command))
        self.application.add_handler(CommandHandler('tp', self.tp_command))
        self.application.add_handler(CommandHandler('hh', self.get_peaks))
        self.application.add_handler(CommandHandler('ll', self.get_valleys))
        self.application.add_handler(CommandHandler('bull', self.get_bullflag))
        self.application.add_handler(CommandHandler('bear', self.get_bearflag))
        self.application.add_handler(CommandHandler('getwl', self.get_watchlist))
        self.application.add_handler(CommandHandler('addwl', self.add_watchlist))
        self.application.add_handler(CommandHandler('delwl', self.del_watchlist))

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