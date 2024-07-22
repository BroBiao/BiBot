# !/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import strategy as st
from config import Config
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


load_dotenv()
bot_token = os.getenv('BOT_TOKEN')
chat_id = os.getenv('CHAT_ID')
watchlist_path = Config.WL_PATH

async def start_command(update, context):
    await update.message.reply_text("Hello, welcome to Biao's Nice Soup!")

async def tp_command(update, context):
    msg_text = str(update.message.text).split()
    if len(msg_text) == 3:
        pair = msg_text[1].upper() + 'USDT'
        interval = msg_text[2].lower()
        try:
            data = st.PairData(pair)
            ema3 = data.get_ema3(interval)
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

async def get_watchlist(update, context):
    try:
        watchlist = str(st.read_json_file(watchlist_path))
        await update.message.reply_text(watchlist)
    except Exception as e:
        await update.message.reply_text('Failed to read watchlist\n' + str(e))

async def add_watchlist(update, context):
    try:
        watchlist = st.read_json_file(watchlist_path)
        msg_text = str(update.message.text).split()
        if len(msg_text) == 2:
            pair = msg_text[1].upper() + 'USDT'
            if pair not in watchlist:
                watchlist.append(pair)
                st.write_to_json_file(watchlist, watchlist_path)
                watchlist = str(st.read_json_file(watchlist_path))
                await update.message.reply_text(f'Added {pair} to watchlist. New watchlist:\n' + watchlist)
            else:
                await update.message.reply_text(f'{pair} already in watchlist.')
        else:
            await update.message.reply_text("Sorry, invalid input.\nUsage example: /addwl BTC")
    except Exception as e:
        await update.message.reply_text(f'Failed to add {pair}\n' + str(e))

async def del_watchlist(update, context):
    try:
        watchlist = st.read_json_file(watchlist_path)
        msg_text = str(update.message.text).split()
        if len(msg_text) == 2:
            pair = msg_text[1].upper() + 'USDT'
            if pair in watchlist:
                watchlist.remove(pair)
                st.write_to_json_file(watchlist, watchlist_path)
                await update.message.reply_text(f'Removed {pair} from watchlist. New watchlist:\n' + str(watchlist))
            else:
                await update.message.reply_text(f'{pair} is not in watchlist')
        else:
            await update.message.reply_text("Sorry, invalid input.\nUsage example: /delwl BTC")
    except Exception as e:
        await update.message.reply_text(f'Failed to delete {pair}\n' + str(e))

def main():
    application = Application.builder().token(bot_token).build()

    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('tp', tp_command))
    application.add_handler(CommandHandler('getwl', get_watchlist))
    application.add_handler(CommandHandler('addwl', add_watchlist))
    application.add_handler(CommandHandler('delwl', del_watchlist))

    application.run_polling()

if __name__ == '__main__':
    main()
