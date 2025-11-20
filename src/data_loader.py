#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据获取模块
负责通过 akshare 下载指定股票的前复权日线数据，并标准化字段。
"""
from __future__ import annotations
import akshare as ak
import pandas as pd
from typing import Callable

# 映射：展示名称 -> akshare symbol（不含交易所后缀）
DISPLAY_TO_SYMBOL = {
    "金地集团（600383.SH)": "600383",
    "金地集团（600383.SH)": "600383",  # 兼容可能的全角括号输入
    "金地集团（600383.SH）": "600383",
    "分众传媒（002027.SZ)": "002027",
    "分众传媒（002027.SZ)": "002027",
    "分众传媒（002027.SZ）": "002027",
}
# 规范化 GUI 下拉项（用于回测内部处理）
NORMALIZED_OPTIONS = [
    "金地集团（600383.SH）",
    "分众传媒（002027.SZ）"
]


def get_stock_data(display_name: str, start: str, end: str, log_cb: Callable[[str], None] | None = None) -> pd.DataFrame:
    """获取 A 股前复权日线数据。

    参数:
        display_name: GUI 下拉框展示名称，如 "金地集团（600383.SH）"。
        start: 起始日期，格式 YYYY-MM-DD
        end: 截止日期，格式 YYYY-MM-DD
        log_cb: 日志回调函数，用于 GUI 实时输出
    返回:
        标准化后的 DataFrame，包含: date, open, high, low, close, volume, amount
    异常:
        抛出 RuntimeError 以便线程捕获并通知 GUI
    """
    try:
        if log_cb:
            log_cb(f"正在获取数据: {display_name} ({start} ~ {end}) 前复权日线 ...")
        symbol_raw = DISPLAY_TO_SYMBOL.get(display_name, None)
        if not symbol_raw:
            raise RuntimeError(f"无法识别的股票名称: {display_name}")

        # akshare 日期格式为 YYYYMMDD
        start_fmt = start.replace('-', '')
        end_fmt = end.replace('-', '')

        # 调用 akshare 接口
        df = ak.stock_zh_a_hist(symbol=symbol_raw, period="daily", start_date=start_fmt, end_date=end_fmt, adjust="qfq")
        if df is None or df.empty:
            raise RuntimeError("获取数据为空，可能是网络异常或日期范围无数据")

        # 标准化字段
        df = df.rename(columns={
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount',
        })
        # 处理类型与顺序
        df['date'] = pd.to_datetime(df['date'])
        df = df[['date', 'open', 'high', 'low', 'close', 'volume', 'amount']].sort_values('date').reset_index(drop=True)

        # 缺失值处理
        missing = df.isna().sum().sum()
        if missing > 0:
            if log_cb:
                log_cb(f"发现 {missing} 个缺失值，已用前向填充处理")
            # 使用 ffill 填充缺失值，兼容类型检查
            df.ffill(inplace=True)
            df.fillna(0, inplace=True)

        if log_cb:
            log_cb(f"数据获取成功，共 {len(df)} 行。")
        return df
    except Exception as e:
        raise RuntimeError(f"数据获取失败: {e}") from e


def compute_macd(df: pd.DataFrame) -> pd.DataFrame:
    """计算 MACD 指标列并添加到 DataFrame (DIF, DEA, MACD_HIST)。"""
    fast_ema = df['close'].ewm(span=12, adjust=False).mean()
    slow_ema = df['close'].ewm(span=26, adjust=False).mean()
    dif = fast_ema - slow_ema
    dea = dif.ewm(span=9, adjust=False).mean()
    hist = dif - dea
    df['DIF'] = dif
    df['DEA'] = dea
    df['MACD_HIST'] = hist
    return df

__all__ = [
    'get_stock_data', 'compute_macd', 'NORMALIZED_OPTIONS', 'get_generic_hist'
]

def get_generic_hist(symbol: str, start: str, end: str) -> pd.DataFrame:
    """通用代码历史数据获取 (股票/ETF 兼容尝试)

    参数:
        symbol: 形如 513580.SH / 510300.SH / 600383.SH / 159819.SZ 等
        start, end: YYYYMMDD 或 YYYY-MM-DD (自动去除 '-')
    返回: DataFrame[date, open, high, low, close, volume, amount]

    逻辑:
        1. 去掉交易所后缀 (.SH / .SZ)
        2. 优先尝试 ETF 接口 fund_etf_hist_em
        3. 失败则回退 stock_zh_a_hist (若是股票)
    """
    import re
    import akshare as ak
    s_clean = symbol.upper().strip()
    s_clean = re.sub(r"\.SH$|\.SZ$", "", s_clean)
    start_fmt = start.replace('-', '')
    end_fmt = end.replace('-', '')
    df = None
    # 尝试 ETF
    try:
        df = ak.fund_etf_hist_em(symbol=s_clean)
        if df is not None and not df.empty:
            df = df.rename(columns={'日期': 'date', '开盘': 'open', '收盘': 'close', '最高': 'high', '最低': 'low', '成交量': 'volume', '成交额': 'amount'})
    except Exception:
        df = None
    # 若为空再尝试 A 股股票日线
    if df is None or df.empty:
        try:
            df = ak.stock_zh_a_hist(symbol=s_clean, period='daily', start_date=start_fmt, end_date=end_fmt, adjust='qfq')
            if df is not None and not df.empty:
                df = df.rename(columns={'日期': 'date', '开盘': 'open', '收盘': 'close', '最高': 'high', '最低': 'low', '成交量': 'volume', '成交额': 'amount'})
        except Exception:
            df = None
    if df is None or df.empty:
        raise RuntimeError(f"无法获取数据: {symbol}")
    df['date'] = pd.to_datetime(df['date'])
    df = df[['date', 'open', 'high', 'low', 'close', 'volume', 'amount']].sort_values('date').reset_index(drop=True)
    return df
