#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回测执行模块 (多标的 + 可选策略)
支持传入多个 DataFrame 与策略名称。
"""
from __future__ import annotations
import backtrader as bt
import pandas as pd
from typing import Dict, Any, Tuple, List

try:
    from .strategy import STRATEGY_MAP, DEFAULT_STRATEGY_NAME
except ImportError:
    from strategy import STRATEGY_MAP, DEFAULT_STRATEGY_NAME  # type: ignore


class PandasDataExt(bt.feeds.PandasData):
    lines = ('amount',)
    params = (('amount', 'amount'),)


def run_backtest(dfs: List[pd.DataFrame], strategy_name: str | None = None, display_names: List[str] | None = None, log_cb=None) -> Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame, bt.Strategy]:
    if log_cb:
        log_cb("初始化回测引擎 ...")
    cerebro = bt.Cerebro()
    if strategy_name is None:
        strategy_name = DEFAULT_STRATEGY_NAME
    strategy_cls = STRATEGY_MAP.get(strategy_name, STRATEGY_MAP[DEFAULT_STRATEGY_NAME])
    cerebro.addstrategy(strategy_cls)
    cerebro.broker.set_cash(100000.0)

    for i, df in enumerate(dfs):
        data = df.copy()
        data.set_index('date', inplace=True)
        feed = PandasDataExt(dataname=data)  # type: ignore[arg-type]
        name = display_names[i] if display_names and i < len(display_names) else f'data{i}'
        cerebro.adddata(feed, name=name)

    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='timereturn')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')

    if log_cb:
        log_cb("开始运行回测 ...")
    result = cerebro.run()
    strat = result[0]

    final_value = cerebro.broker.getvalue()
    initial_cash = 100000.0
    total_return = (final_value - initial_cash) / initial_cash

    ref_df = dfs[0]
    num_days = (ref_df['date'].iloc[-1] - ref_df['date'].iloc[0]).days
    annual_return = (1 + total_return) ** (365.0 / num_days) - 1 if num_days > 0 else 0.0

    dd = strat.analyzers.drawdown.get_analysis()
    max_drawdown = dd.max.drawdown if hasattr(dd.max, 'drawdown') else dd.get('max', {}).get('drawdown', 0.0)

    trades = getattr(strat, 'trades', 0)
    wins = getattr(strat, 'wins', 0)
    win_rate = wins / trades if trades > 0 else 0.0

    # 交易明细 DataFrame
    trade_records = getattr(strat, 'trade_records', [])
    if trade_records:
        trades_df = pd.DataFrame(trade_records)
        trades_df.sort_values('exit_date', inplace=True)
    else:
        trades_df = pd.DataFrame(columns=['symbol','entry_date','exit_date','entry_price','exit_price','size','pnl_pct','holding_days'])

    returns_dict = strat.analyzers.timereturn.get_analysis()
    equity_list = []
    value = initial_cash
    for dt, r in returns_dict.items():
        value *= (1 + r)
        equity_list.append({'date': dt, 'value': value})
    equity_curve_df = pd.DataFrame(equity_list)
    if equity_curve_df.empty:
        equity_curve_df = pd.DataFrame({'date': ref_df['date'], 'value': initial_cash})

    base = ref_df[['date', 'close']].copy()
    base['benchmark'] = initial_cash * base['close'] / base['close'].iloc[0]
    equity_curve_df = pd.merge(equity_curve_df, base[['date', 'benchmark']], on='date', how='right')
    equity_curve_df['value'] = equity_curve_df['value'].ffill()

    metrics = {
        '总收益率': total_return,
        '年化收益率': annual_return,
        '交易次数': trades,
        '胜率': win_rate,
        '最大回撤(%)': max_drawdown,
        '最终资产': final_value,
        '策略': strategy_name,
        '标的数量': len(dfs),
    }
    if log_cb:
        log_cb("回测完成。")
    return metrics, equity_curve_df, trades_df, strat

__all__ = ['run_backtest']
