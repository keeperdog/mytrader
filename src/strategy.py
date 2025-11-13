#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backtrader 策略模块
提供可选择的多种基础策略：
1) MACD + 成交量放大 (MacdVolumeStrategy)
2) 均线交叉 + 成交量过滤 (SmaCrossVolumeStrategy)

并支持多标的：对每个 data 单独进行信号判断与下单，统计汇总交易次数与胜率。
"""
from __future__ import annotations
import backtrader as bt

class BaseMultiDataStrategy(bt.Strategy):
    """多标的基础策略父类，封装统计逻辑。
    子类只需实现 per_data_signal(data, i) 返回 (buy_signal, sell_signal, volume_ok)。

    说明: 原先在 __init__ 中使用 dict comprehension 创建指标时出现 NameError(self) 异常，
    可能与运行环境或代码缩进解析有关。这里改为分步初始化，避免在 comprehension 中引用 self，
    并延后指标生成，提升兼容性与可读性。
    """
    params = (('vol_window', 20), ('vol_factor', 1.2))

    def __init__(self):
        self.trades = 0
        self.wins = 0
        self.last_buy_price = {}
        self.last_buy_date = {}
        self.vol_ma_map = {}
        self.trade_records = []  # 记录每笔交易明细
        for d in self.datas:
            self.last_buy_price[d] = None
            self.last_buy_date[d] = None
            self.vol_ma_map[d] = bt.indicators.SimpleMovingAverage(d.volume, period=self.p.vol_window)  # type: ignore[attr-defined]

    def per_data_signal(self, data, i):  # 子类覆盖
        return False, False, False

    def next(self):
        for i, d in enumerate(self.datas):
            buy_sig, sell_sig, vol_ok = self.per_data_signal(d, i)
            pos = self.getposition(d)
            if not pos:
                if buy_sig and vol_ok:
                    # 简化：每标的平分资金 (1 / N)
                    self.order_target_percent(data=d, target=1.0/len(self.datas))
                    self.last_buy_price[d] = d.close[0]
                    self.last_buy_date[d] = bt.num2date(d.datetime[0]).date()
            else:
                if sell_sig:
                    self.order_target_percent(data=d, target=0.0)
                    self.trades += 1
                    if self.last_buy_price[d] is not None and d.close[0] > self.last_buy_price[d]:
                        self.wins += 1
                    # 记录交易
                    entry_price = self.last_buy_price[d]
                    exit_price = d.close[0]
                    entry_date = self.last_buy_date[d]
                    exit_date = bt.num2date(d.datetime[0]).date()
                    pnl_pct = (exit_price - entry_price) / entry_price if entry_price else 0.0
                    holding_days = (exit_date - entry_date).days if entry_date else 0
                    self.trade_records.append({
                        'symbol': d._name or f'data{i}',
                        'entry_date': entry_date,
                        'exit_date': exit_date,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'size': pos.size,
                        'pnl_pct': pnl_pct,
                        'holding_days': holding_days,
                    })
                    self.last_buy_price[d] = None
                    self.last_buy_date[d] = None

    def stop(self):
        # 统计未平仓
        for d in self.datas:
            pos = self.getposition(d)
            if pos and self.last_buy_price[d] is not None:
                self.trades += 1
                if d.close[0] > self.last_buy_price[d]:
                    self.wins += 1
                # 记录强制平仓（以最后一个 bar 收盘价计算）
                exit_date = bt.num2date(d.datetime[0]).date()
                entry_price = self.last_buy_price[d]
                exit_price = d.close[0]
                entry_date = self.last_buy_date[d]
                pnl_pct = (exit_price - entry_price) / entry_price if entry_price else 0.0
                holding_days = (exit_date - entry_date).days if entry_date else 0
                self.trade_records.append({
                    'symbol': d._name or 'unknown',
                    'entry_date': entry_date,
                    'exit_date': exit_date,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'size': pos.size,
                    'pnl_pct': pnl_pct,
                    'holding_days': holding_days,
                })

class MacdVolumeStrategy(BaseMultiDataStrategy):
    def __init__(self):
        super().__init__()
        self.macd_map = {}
        for d in self.datas:
            self.macd_map[d] = bt.indicators.MACD(d.close)  # type: ignore[attr-defined]

    def per_data_signal(self, data, i):
        macd = self.macd_map[data]
        vol_ma = self.vol_ma_map[data]
        buy_cross = macd.macd[0] > macd.signal[0] and macd.macd[-1] <= macd.signal[-1]
        sell_cross = macd.macd[0] < macd.signal[0] and macd.macd[-1] >= macd.signal[-1]
        vol_ok = data.volume[0] > vol_ma[0] * self.p.vol_factor
        return buy_cross, sell_cross, vol_ok

class SmaCrossVolumeStrategy(BaseMultiDataStrategy):
    params = (('short', 10), ('long', 30), ('vol_window', 20), ('vol_factor', 1.2))

    def __init__(self):
        super().__init__()
        self.sma_short = {}
        self.sma_long = {}
        for d in self.datas:
            self.sma_short[d] = bt.indicators.SimpleMovingAverage(d.close, period=self.p.short)  # type: ignore[attr-defined]
            self.sma_long[d] = bt.indicators.SimpleMovingAverage(d.close, period=self.p.long)  # type: ignore[attr-defined]

    def per_data_signal(self, data, i):
        short = self.sma_short[data]
        long = self.sma_long[data]
        vol_ma = self.vol_ma_map[data]
        buy_cross = short[0] > long[0] and short[-1] <= long[-1]
        sell_cross = short[0] < long[0] and short[-1] >= long[-1]
        vol_ok = data.volume[0] > vol_ma[0] * self.p.vol_factor
        return buy_cross, sell_cross, vol_ok

STRATEGY_MAP = {
    'MACD成交量': MacdVolumeStrategy,
    '均线交叉成交量': SmaCrossVolumeStrategy,
}

DEFAULT_STRATEGY_NAME = 'MACD成交量'

__all__ = ['MacdVolumeStrategy', 'SmaCrossVolumeStrategy', 'STRATEGY_MAP', 'DEFAULT_STRATEGY_NAME']
