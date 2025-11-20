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
        self.pos_history = []    # 记录每日持仓 (date, 每标的持仓数量)
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
        # 记录当日持仓
        try:
            cur_date = bt.num2date(self.datas[0].datetime[0]).date()
            pos_row = {'date': cur_date}
            for j, d in enumerate(self.datas):
                key = d._name or f'data{j}'
                pos_row[key] = self.getposition(d).size
            self.pos_history.append(pos_row)
        except Exception:
            pass

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

class VolumeSurgeUpStrategy(BaseMultiDataStrategy):
    """放量上涨策略
    买入条件(解释与假设):
      1) 当日涨幅 >= 2% 且 收盘价 >= 开盘价 (原文字 "上涨小于2%或收盘价小于开盘价" 视为排除条件，这里取反作为筛选)
      2) 当日成交额 >= 2e8 (2亿)
      3) 当日成交量 / 5日平均成交量 >= 2

    卖出条件(自定义假设):
      - 收盘价 < 开盘价 (转弱) 或 成交量/5日均量 < 1.2 (放量消失)

    若 5 日均量尚未形成 (前期样本不足)，跳过信号。
    若成交额缺失，使用 volume * close * 100 作为近似 (假设一手=100)。
    """
    params = (('vol_window', 20), ('vol_factor', 1.2))  # 继承仍会创建 vol_ma_map 供基础统计用

    def __init__(self):
        super().__init__()
        self.vol_ma5 = {}
        for d in self.datas:
            self.vol_ma5[d] = bt.indicators.SimpleMovingAverage(d.volume, period=5)  # type: ignore[attr-defined]

    def per_data_signal(self, data, i):
        # 前一日收盘是否可用
        if len(data.close) < 2:
            return False, False, False
        prev_close = data.close[-1]
        if prev_close == 0:
            return False, False, False
        pct_change = (data.close[0] - prev_close) / prev_close * 100.0
        # 成交额 (turnover)
        try:
            turnover = data.amount[0]
        except Exception:
            # 近似: volume * close * 100
            turnover = data.volume[0] * data.close[0] * 100.0
        vol_ma5_val = self.vol_ma5[data][0]
        if vol_ma5_val == 0:
            return False, False, False
        vol_ratio = data.volume[0] / vol_ma5_val
        increase_ok = (pct_change >= 2.0) and (data.close[0] >= data.open[0])
        turnover_ok = turnover >= 200_000_000.0
        vol_surge_ok = vol_ratio >= 2.0
        buy_sig = increase_ok and turnover_ok and vol_surge_ok
        # 卖出：价格转弱或放量消退
        sell_sig = (data.close[0] < data.open[0]) or (vol_ratio < 1.2)
        vol_ok = turnover_ok and vol_surge_ok
        return buy_sig, sell_sig, vol_ok

class TarmacPlatformStrategy(BaseMultiDataStrategy):
    """停机坪形态策略 ("Tarmac" pattern)
    假设/解释:
      - 最近15日内第1步描述的"放量上涨"日在当前bar的前3个交易日 (即 index -3)。
      - 第2步: 紧接的下一个交易日 (index -2) 高开(open > 前一日收盘)、收阳(close > open)、实体占开盘的涨幅 < 3%( (close-open)/open < 3% )。
      - 第3步: 再后面连续两个交易日 (index -1, index 0) 也满足: 高开、收阳、实体 < 3%、当日涨幅在 0%~5% 内。
    原文“最近15日有涨幅大于9.5%”理解为形态基准日(第1天)涨幅 > 9.5%，且放量上涨 (volume/5日均量>=2 且 收盘>开盘)。
    买入时机: 第3个确认日(当前bar)满足所有条件则买入。
    卖出逻辑(假设): 若出现收盘价<开盘价 或 日内跌幅<-3% 或 日涨幅>6%(形态被打破) 则卖出。
    可后续参数化：surge_pct, body_pct_limit, confirm_max_pct, confirm_days。
    """
    params = (
        ('surge_pct', 9.5),          # 放量上涨日最低涨幅%
        ('surge_vol_ratio', 2.0),    # 放量倍率 (volume / ma5)
        ('body_pct_limit', 3.0),     # 每确认日实体(收-开)/开 < 3%
        ('confirm_max_pct', 5.0),    # 确认日涨幅上限
        ('exit_drop_pct', -3.0),     # 跌幅触发退出
        ('exit_spike_pct', 6.0),     # 异常大涨触发退出 (破形态)
    )

    def __init__(self):
        super().__init__()
        self.vol_ma5 = {}
        for d in self.datas:
            self.vol_ma5[d] = bt.indicators.SimpleMovingAverage(d.volume, period=5)  # type: ignore[attr-defined]

    def _daily_pct(self, data, offset=0):
        if len(data.close) < abs(offset) + 2:
            return None
        try:
            prev = data.close[offset-1]
            cur = data.close[offset]
            if prev == 0:
                return None
            return (cur - prev) / prev * 100.0
        except Exception:
            return None

    def per_data_signal(self, data, i):
        # 需要至少 4 根K线
        if len(data.close) < 4:
            return False, False, False
        # surge day = index -3
        surge_pct = self._daily_pct(data, -3)
        if surge_pct is None:
            return False, False, False
        # 5日均量与放量判断 (surge day)
        try:
            vol_ma5_surge = self.vol_ma5[data][-3]
        except Exception:
            vol_ma5_surge = 0
        if vol_ma5_surge == 0:
            return False, False, False
        vol_ratio_surge = data.volume[-3] / vol_ma5_surge
        # surge day conditions
        surge_ok = (
            surge_pct > self.p.surge_pct and
            data.close[-3] > data.open[-3] and
            vol_ratio_surge >= self.p.surge_vol_ratio
        )
        if not surge_ok:
            return False, False, False
        # 检查接下三个确认日 (index -2, -1, 0)
        for off in (-2, -1, 0):
            pct = self._daily_pct(data, off)
            if pct is None:
                return False, False, False
            body_pct = (data.close[off] - data.open[off]) / data.open[off] * 100.0 if data.open[off] != 0 else 0
            high_open = data.open[off] > data.close[off-1]
            cond = (
                high_open and
                data.close[off] > data.open[off] and
                body_pct < self.p.body_pct_limit and
                0.0 < pct <= self.p.confirm_max_pct
            )
            if not cond:
                return False, False, False
        # 若当前bar通过确认形态，构成买入
        buy_sig = True
        # 卖出逻辑
        today_pct = self._daily_pct(data, 0)
        sell_sig = False
        if today_pct is not None:
            if today_pct < self.p.exit_drop_pct or today_pct > self.p.exit_spike_pct or data.close[0] < data.open[0]:
                sell_sig = True
        # 将放量标识 vol_ok 简化为 surge day 的放量满足
        vol_ok = True
        return buy_sig, sell_sig, vol_ok

STRATEGY_MAP = {
    'MACD成交量': MacdVolumeStrategy,
    '均线交叉成交量': SmaCrossVolumeStrategy,
    '放量上涨': VolumeSurgeUpStrategy,
    '停机坪': TarmacPlatformStrategy,
}

DEFAULT_STRATEGY_NAME = 'MACD成交量'

class MidCapRotationStrategy(bt.Strategy):
    """中规模轮动策略 (示例实现)
    参数来源: 用户给出的配置
    逻辑:
      - 计算 ROC(period) = close / close[-period] - 1
      - 买入条件: roc(period) > buy_thr (任意满足 buy 条件列表计数>=buy_at_least_count)
      - 卖出条件: roc(period) < sell_thr_low 或 roc(period) > sell_thr_high (卖出条件列表满足>=sell_at_least_count)
      - 每个 rebal_days 日进行一次轮动 (period = RunDaily, period_days=1 -> 每日)
      - 排序: 按 roc(period) DESC，选 topK (去掉 dropN 前N个后再选 topK)
      - 权重: 等权 (WeighEqually)
    简化:
      - 不额外考虑手续费滑点，此处留给 broker 配置
      - 若样本不足 (len < roc_period+1) 则该标的跳过当前 bar 计算
    输出:
      - trade_records (与其它策略一致)
      - pos_history (每日持仓快照)
    """
    params = dict(
        roc_period=21,
        buy_conditions=(0.05,),          # 表示 roc > 0.05 (可扩展多个条件 OR)
        buy_at_least_count=1,
        sell_conditions_low=(-0.06,),    # roc < -0.06 OR
        sell_conditions_high=(0.20,),    # roc > 0.20 OR
        sell_at_least_count=1,
        topK=2,
        dropN=0,
        rebalance_days=1,                # 每 N 天轮动
    )

    def __init__(self):
        self.day_counter = 0
        self.trade_records = []
        self.pos_history = []
        # 保存最近买入价用于胜率统计 (简化)
        self.last_buy_price = {d: None for d in self.datas}
        self.last_buy_date = {d: None for d in self.datas}
        self.trades = 0
        self.wins = 0

    def _roc(self, data, period):
        if len(data.close) <= period:
            return None
        prev = data.close[-period]
        cur = data.close[0]
        if prev == 0:
            return None
        return cur / prev - 1.0

    def next(self):
        self.day_counter += 1
        current_date = bt.num2date(self.datas[0].datetime[0]).date()

        # 计算所有标的 ROC
        roc_map = {}
        for d in self.datas:
            roc_val = self._roc(d, self.p.roc_period)
            if roc_val is not None:
                roc_map[d] = roc_val

        # 卖出检查 (逐标的)
        for d in list(self.datas):
            pos = self.getposition(d)
            if pos.size == 0:
                continue
            roc_val = roc_map.get(d, None)
            if roc_val is None:
                continue
            sell_hits = 0
            for low_thr in self.p.sell_conditions_low:
                if roc_val < low_thr:
                    sell_hits += 1; break
            for high_thr in self.p.sell_conditions_high:
                if roc_val > high_thr:
                    sell_hits += 1; break
            if sell_hits >= self.p.sell_at_least_count:
                self.order_target_percent(d, 0.0)
                entry_price = self.last_buy_price.get(d)
                exit_price = d.close[0]
                entry_date = self.last_buy_date.get(d)
                exit_date = current_date
                pnl_pct = (exit_price - entry_price)/entry_price if entry_price else 0.0
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
                self.trades += 1
                if entry_price is not None and exit_price > entry_price:
                    self.wins += 1
                self.last_buy_price[d] = None
                self.last_buy_date[d] = None

        # 轮动买入 (按 rebalance_days)
        if self.day_counter % self.p.rebalance_days == 0 and roc_map:
            # 构建买入候选列表
            candidates = []
            for d, roc_val in roc_map.items():
                buy_hits = sum(1 for cond in self.p.buy_conditions if roc_val > cond)
                if buy_hits >= self.p.buy_at_least_count:
                    candidates.append((d, roc_val))
            # 排序 & 选 topK
            candidates.sort(key=lambda x: x[1], reverse=True)
            if self.p.dropN > 0:
                candidates = candidates[self.p.dropN:]
            target = [c[0] for c in candidates[: self.p.topK]]
            target_set = set(target)
            # 当前持仓集合
            held_set = {d for d in self.datas if self.getposition(d).size > 0}
            # 卸载不在目标内的持仓
            for d in held_set - target_set:
                self.order_target_percent(d, 0.0)
                pos = self.getposition(d)
                entry_price = self.last_buy_price.get(d)
                exit_price = d.close[0]
                entry_date = self.last_buy_date.get(d)
                exit_date = current_date
                pnl_pct = (exit_price - entry_price)/entry_price if entry_price else 0.0
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
                self.trades += 1
                if entry_price is not None and exit_price > entry_price:
                    self.wins += 1
                self.last_buy_price[d] = None
                self.last_buy_date[d] = None
            # 买入新的目标
            if target:
                weight = 1.0 / len(target)
                for d in target:
                    if self.getposition(d).size == 0:
                        self.order_target_percent(d, weight)
                        self.last_buy_price[d] = d.close[0]
                        self.last_buy_date[d] = current_date

        # 记录持仓快照
        snapshot = {'date': current_date}
        for d in self.datas:
            snapshot[d._name or 'unknown'] = self.getposition(d).size
        self.pos_history.append(snapshot)

    def stop(self):
        # 强制平仓剩余持仓（统计）
        current_date = bt.num2date(self.datas[0].datetime[0]).date() if self.datas else None
        for d in self.datas:
            pos = self.getposition(d)
            if pos.size > 0 and self.last_buy_price.get(d) is not None:
                exit_price = d.close[0]
                entry_price = self.last_buy_price[d]
                entry_date = self.last_buy_date[d]
                exit_date = current_date
                pnl_pct = (exit_price - entry_price)/entry_price if entry_price else 0.0
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
                self.trades += 1
                if entry_price is not None and exit_price > entry_price:
                    self.wins += 1

STRATEGY_MAP['中规模轮动'] = MidCapRotationStrategy

__all__ = ['MacdVolumeStrategy', 'SmaCrossVolumeStrategy', 'VolumeSurgeUpStrategy', 'TarmacPlatformStrategy', 'MidCapRotationStrategy', 'STRATEGY_MAP', 'DEFAULT_STRATEGY_NAME']
