import datetime as dt
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class BacktestResult:
    performance: List[Dict[str, Any]] = field(default_factory=list)  # {'date','strategy_nav','benchmark_nav'}
    positions: List[Dict[str, Any]] = field(default_factory=list)    # {'code','name','weight'}
    trades: List[Dict[str, Any]] = field(default_factory=list)       # {'code','name','buy_price','sell_price','pnl','pnl_cash','buy_date','sell_date','hold_days','ret_pct'}
    rebalance_signals: List[Dict[str, Any]] = field(default_factory=list)  # {'signal_date','code','action','start_weight','target_weight'}


def load_sample_result(start_date: dt.date, end_date: dt.date) -> BacktestResult:
    """根据选择的日期范围生成示例净值与记录。真实接入时替换为回测结果。"""
    if end_date < start_date:
        # 返回空结果用于界面提示
        return BacktestResult()

    # 生成每日净值（策略假设高增长，基准低增长）
    perf: List[Dict[str, Any]] = []
    strat_nav = 1.0
    bench_nav = 1.0
    days = (end_date - start_date).days + 1
    for i in range(days):
        date = start_date + dt.timedelta(days=i)
        # 简单趋势：策略日增长 0.5%，基准 0.05%
        if i > 0:
            strat_nav *= 1 + 0.005
            bench_nav *= 1 + 0.0005
        perf.append({'date': date, 'strategy_nav': strat_nav, 'benchmark_nav': bench_nav})

    today = dt.date.today()
    positions = [{'code': '513290.SH', 'name': '纳指生物科技ETF', 'weight': 1.0}] if days > 0 else []

    # 仅生成范围尾部附近的示例交易
    trades: List[Dict[str, Any]] = []
    if days >= 10:
        trades.append({
            'code': '515790.SH', 'name': '新能源ETF', 'buy_price': 1.055, 'sell_price': 1.102,
            'pnl': 0.047, 'pnl_cash': 123456.78, 'buy_date': end_date - dt.timedelta(days=9),
            'sell_date': end_date - dt.timedelta(days=4), 'hold_days': 5, 'ret_pct': 0.0447
        })
        trades.append({
            'code': '513290.SH', 'name': '纳指生物科技ETF', 'buy_price': 1.435, 'sell_price': 1.495,
            'pnl': 0.06, 'pnl_cash': 234567.89, 'buy_date': end_date - dt.timedelta(days=20),
            'sell_date': end_date - dt.timedelta(days=1), 'hold_days': 19, 'ret_pct': 0.0418
        })

    signals: List[Dict[str, Any]] = []
    for i in range(min(15, days)):
        d = end_date - dt.timedelta(days=i+1)
        if d < start_date:
            break
        signals.append({
            'signal_date': d,
            'code': '513290.SH' if i % 2 else '515790.SH',
            'action': '开仓' if i % 2 else '平仓',
            'start_weight': 99.0 if i % 2 == 0 else 0.0,
            'target_weight': 0.0 if i % 2 == 0 else 100.0,
        })

    return BacktestResult(performance=perf, positions=positions, trades=trades, rebalance_signals=signals)
