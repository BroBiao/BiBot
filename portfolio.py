# !/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import datetime as dt
import pandas as pd
import numpy as np
from config import Config


class Portfolio(object):

    def __init__(self):
        self.file_path = Config.PF_PATH
        self.fee_rate = Config.FEES_RATE
        if not os.path.exists(self.file_path):
            columns = ['OpenTime', 'Side', 'Pair', 'Amount', 'Status', 'OpenPrice', 'ClosePrice', 'SL', 'TP', 'PnL']
            self.portfolio = pd.DataFrame(columns=columns, dtype=float)
        else:
            self.portfolio = pd.read_csv(self.file_path, index_col=0)

    def save(self):
        self.portfolio.to_csv(self.file_path)

    def get_all(self):
        return self.portfolio

    def get_open(self):
        open_pos = self.portfolio[self.portfolio['Status'] == 'Open']
        return open_pos

    def get_total_pnl(self):
        total_pnl = self.portfolio['PnL'].sum()
        return total_pnl

    def open(self, time, side, pair, amount, price, sl, tp):
        pos_info = [time, side, pair, amount, 'Open', price, np.nan, sl, tp, 0.0]
        self.portfolio.loc[len(self.portfolio)] = pos_info

    def close(self, pair, price):
        pos_index = self.portfolio.index[(self.portfolio['Pair'] == pair) & (self.portfolio['Status'] == 'Open')]
        self.portfolio.loc[pos_index, 'Status'] = 'Close'
        self.portfolio.loc[pos_index, 'ClosePrice'] = price
        open_price = self.portfolio.loc[pos_index, 'OpenPrice']
        amount = self.portfolio.loc[pos_index, 'Amount']
        fee = price * amount * self.fee_rate
        side = self.portfolio.loc[pos_index, 'Side'].values[-1]
        if side == 'LONG':
            pnl = (price - open_price) * amount - fee
        elif side == 'SHORT':
            pnl = (open_price - price) * amount - fee
        else:
            raise Exception('Unable close position, undefined side')
        self.portfolio.loc[pos_index, 'PnL'] = pnl
        return pnl.iloc[0]    # convert pandas series to float


## for test purpose
# por = Portfolio()
# now = dt.datetime.now().strftime('%m/%d %H:%M:%S')
# por.open(now, 'LONG', 'BTCUSDT', 1.0, 40000.0, 39000.0, 41000.0)
# por.open(now, 'LONG', 'ETHUSDT', 1.0, 2300.0, 2000.0, 2600.0)
# por.open(now, 'SHORT', 'LTCUSDT', 1.0, 200.0, 200.0, 260.0)
# print(por.get_all().to_string())
# por.close('BTCUSDT', 40500.0)
# print(por.get_all().to_string())
# print(por.get_open()['Pair'].to_list())
# print(por.get_total_pnl())
# por.save()
# os.remove('./portfolio.csv')
