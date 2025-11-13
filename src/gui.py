#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GUI 模块
构建 PyQt6 主窗口，包含：
  顶部操作区（股票选择、日期范围、开始回测按钮）
  中间 Tab 区（图表 + 指标表格）
  底部日志区
使用 QThread 运行回测避免界面卡顿。
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QMainWindow, QApplication, QVBoxLayout, QHBoxLayout,
    QComboBox, QDateEdit, QPushButton, QTabWidget, QTextEdit, QTableWidget,
    QTableWidgetItem, QLabel, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate
from PyQt6.QtGui import QIcon, QColor, QKeySequence, QShortcut
import traceback
import pandas as pd
import matplotlib
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
try:
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
except Exception:  # fallback for backend differences
    try:
        from matplotlib.backends.backend_qt import NavigationToolbar2QT as NavigationToolbar
    except Exception:
        NavigationToolbar = None
from matplotlib import patches
import mplcursors

# 全局字体设置：尝试使用系统可用中文字体，解决中文显示乱码问题
try:
    from matplotlib import font_manager as _fm
    _candidates = ["PingFang SC", "Songti SC", "Heiti SC", "SimHei", "Microsoft YaHei", "WenQuanYi Micro Hei"]
    _available = {f.name for f in _fm.fontManager.ttflist}
    for _fname in _candidates:
        if _fname in _available:
            matplotlib.rcParams['font.family'] = _fname
            break
    # 避免负号显示成乱码或方块
    matplotlib.rcParams['axes.unicode_minus'] = False
except Exception:
    pass

# 兼容包/脚本双运行模式的导入
try:
    from .data_loader import get_stock_data, compute_macd, NORMALIZED_OPTIONS
    from .backtest import run_backtest
    from .strategy import STRATEGY_MAP, DEFAULT_STRATEGY_NAME
except ImportError:
    from data_loader import get_stock_data, compute_macd, NORMALIZED_OPTIONS  # type: ignore
    from backtest import run_backtest  # type: ignore
    from strategy import STRATEGY_MAP, DEFAULT_STRATEGY_NAME  # type: ignore

class BacktestWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict, pd.DataFrame, pd.DataFrame, list)  # metrics, equity_curve, trades, list_of_ohlc_dfs
    error = pyqtSignal(str)

    def __init__(self, display_names: list[str], start_date: str, end_date: str, strategy_name: str):
        super().__init__()
        self.display_names = display_names
        self.start_date_str = start_date
        self.end_date_str = end_date
        self.strategy_name = strategy_name

    def run(self):
        try:
            self.progress.emit(5, "线程启动")
            self.progress.emit(10, "开始获取数据 ...")
            dfs = []
            for name in self.display_names:
                self.progress.emit(10, f"获取数据 {name} ...")
                df = get_stock_data(name, self.start_date_str, self.end_date_str, log_cb=lambda m: self.progress.emit(15, m))
                df = compute_macd(df)
                dfs.append(df)
            self.progress.emit(40, "执行回测 ...")
            metrics, equity_curve_df, trades_df, strat = run_backtest(dfs, strategy_name=self.strategy_name, display_names=self.display_names, log_cb=lambda m: self.progress.emit(70, m))
            self.progress.emit(90, "准备图表数据 ...")
            # 保留所有 ohlc dfs，UI 可选择主图标的
            ohlc_list = [d.copy() for d in dfs]
            self.progress.emit(100, "完成")
            self.finished.emit(metrics, equity_curve_df, trades_df, ohlc_list)
        except Exception as e:
            err = f"回测线程异常: {e}\n{traceback.format_exc()}"
            self.error.emit(err)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("量化回测 MVP")
        self.resize(1200, 800)
        self.worker: BacktestWorker | None = None
        self._init_ui()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 顶部操作区
        top_bar = QHBoxLayout()
        self.stock_list = QListWidget()
        self.stock_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        for opt in NORMALIZED_OPTIONS:
            self.stock_list.addItem(QListWidgetItem(opt))
        for i in range(self.stock_list.count()):
            item = self.stock_list.item(i)
            if item is not None:
                item.setSelected(True)

        # 主图标的选择（回测完成后填充）
        self.primary_label = QLabel("主图:")
        self.primary_combo = QComboBox()
        self.primary_combo.setEnabled(False)
        self.primary_combo.currentIndexChanged.connect(self.on_primary_changed)

        self.strategy_combo = QComboBox()
        for name in STRATEGY_MAP.keys():
            self.strategy_combo.addItem(name)
        self.strategy_combo.setCurrentText(DEFAULT_STRATEGY_NAME)

        self.start_date = QDateEdit()
        self.start_date.setDisplayFormat('yyyy-MM-dd')
        self.start_date.setDate(QDate(2025, 1, 1))
        self.end_date = QDateEdit()
        self.end_date.setDisplayFormat('yyyy-MM-dd')
        self.end_date.setDate(QDate.currentDate())

        self.run_btn = QPushButton("开始回测")
        self.run_btn.setStyleSheet("background-color: orange; font-weight: bold; padding:6px 16px;")
        self.run_btn.clicked.connect(self.start_backtest)

        self.refresh_btn = QPushButton("刷新策略")
        self.refresh_btn.clicked.connect(self.refresh_strategy)
        self.reload_btn = QPushButton("重载应用")
        self.reload_btn.clicked.connect(self.reload_app)
        self.exit_btn = QPushButton("退出")
        self.exit_btn.clicked.connect(self.close)

        top_bar.addWidget(QLabel("标的(多选):"))
        top_bar.addWidget(self.stock_list)
        top_bar.addWidget(self.primary_label)
        top_bar.addWidget(self.primary_combo)
        top_bar.addWidget(QLabel("策略:"))
        top_bar.addWidget(self.strategy_combo)
        top_bar.addWidget(QLabel("开始日期:"))
        top_bar.addWidget(self.start_date)
        top_bar.addWidget(QLabel("结束日期:"))
        top_bar.addWidget(self.end_date)
        top_bar.addWidget(self.run_btn)
        top_bar.addWidget(self.refresh_btn)
        top_bar.addWidget(self.reload_btn)
        top_bar.addWidget(self.exit_btn)
        top_bar.addStretch(1)
        main_layout.addLayout(top_bar)

        # 快捷键 Ctrl+Q 退出
        self._quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        self._quit_shortcut.activated.connect(self.close)

        # Tabs
        self.tabs = QTabWidget()
        self.chart_tab = QWidget()       # K线/指示 (保留)
        self.equity_tab = QWidget()      # 收益曲线 + 指标（合并在同一Tab）
        self.trades_tab = QWidget()      # 交易明细
        self.tabs.addTab(self.chart_tab, "图表区")
        self.tabs.addTab(self.equity_tab, "收益&指标")
        self.tabs.addTab(self.trades_tab, "交易明细")
        main_layout.addWidget(self.tabs, stretch=1)

        chart_layout = QVBoxLayout(self.chart_tab)
        self.fig = Figure(figsize=(8, 5))
        self.canvas = FigureCanvas(self.fig)
        chart_layout.addWidget(self.canvas)
        # 添加 Matplotlib 工具栏，支持放大/缩小/平移/保存
        try:
            toolbar = NavigationToolbar(self.canvas, self)
            chart_layout.addWidget(toolbar)
        except Exception:
            pass

        # 收益曲线 + 指标在同一 Tab
        equity_layout = QHBoxLayout(self.equity_tab)
        # 左侧：收益曲线
        left_box = QVBoxLayout()
        self.equity_fig = Figure(figsize=(8,5))
        self.equity_canvas = FigureCanvas(self.equity_fig)
        left_box.addWidget(self.equity_canvas)
        equity_layout.addLayout(left_box, stretch=4)
        # 右侧：指标表
        right_box = QVBoxLayout()
        right_box.addWidget(QLabel("统计指标"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["指标", "数值", "单位"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        right_box.addWidget(self.table)
        side = QWidget()
        side.setLayout(right_box)
        side.setMinimumWidth(300)
        equity_layout.addWidget(side, stretch=0)

        trades_layout = QVBoxLayout(self.trades_tab)
        self.trades_table = QTableWidget(0, 8)
        self.trades_table.setHorizontalHeaderLabels(['标的','买入日期','卖出日期','买入价','卖出价','数量','收益率(%)','持仓天数'])
        self.trades_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trades_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        trades_layout.addWidget(self.trades_table)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background:#111;color:#0f0;font-family:Monaco;font-size:12px")
        self.log_text.setMinimumHeight(160)
        main_layout.addWidget(self.log_text)

    # 追加日志
    def log(self, msg: str):
        self.log_text.append(msg)

    def start_backtest(self):
        if self.worker and self.worker.isRunning():
            return
        selected = [item.text() for item in self.stock_list.selectedItems()]
        if not selected:
            self.log("未选择标的，已取消。")
            return
        start_str = self.start_date.date().toString('yyyy-MM-dd')
        end_str = self.end_date.date().toString('yyyy-MM-dd')
        strat_name = self.strategy_combo.currentText()
        self.log(f"启动回测: {','.join(selected)} 策略={strat_name} {start_str} ~ {end_str}")
        self.run_btn.setEnabled(False)
        # 记录本次选择，供图表标注用
        self.last_selected_names = selected
        self.worker = BacktestWorker(selected, start_str, end_str, strat_name)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_progress(self, pct: int, text: str):
        self.log(f"[{pct}%] {text}")

    def on_error(self, err: str):
        self.log(f"错误: {err}")
        self.run_btn.setEnabled(True)

    def on_finished(self, metrics: dict, equity_curve: pd.DataFrame, trades_df: pd.DataFrame, ohlc_list: list):
        self.log("回测完成，更新界面 ...")
        self.run_btn.setEnabled(True)
        self.update_table(metrics)
        # ohlc_list is aligned with display_names order
        names = getattr(self.worker, 'display_names', [])
        self.ohlc_map = {name: df for name, df in zip(names, ohlc_list)}
        # enable primary selector and populate
        self.primary_combo.clear()
        for name in names:
            self.primary_combo.addItem(name)
        self.primary_combo.setEnabled(True)
        self.primary_combo.setCurrentIndex(0)
        # store trades for hover matching
        self.last_trades_df = trades_df.copy() if trades_df is not None else pd.DataFrame()
        # draw initial chart using first symbol
        primary_df = ohlc_list[0] if ohlc_list else pd.DataFrame()
        self.update_charts(primary_df, trades_df)
        self.update_equity_chart(equity_curve, trades_df)
        self.update_trades_table(trades_df)

    def on_primary_changed(self, index: int):
        try:
            name = self.primary_combo.currentText()
            df = getattr(self, 'ohlc_map', {}).get(name)
            if df is not None:
                trades = getattr(self, 'last_trades_df', pd.DataFrame())
                self.update_charts(df, trades)
        except Exception:
            pass

    def refresh_strategy(self):
        """热更新策略映射：尝试 reload 模块并刷新下拉框。"""
        self.log("尝试刷新策略模块 ...")
        import importlib, sys
        module_names = ["src.strategy", "strategy"]
        loaded_mod = None
        for name in module_names:
            if name in sys.modules:
                try:
                    loaded_mod = importlib.reload(sys.modules[name])
                    break
                except Exception as e:
                    self.log(f"模块 {name} reload 失败: {e}")
        if loaded_mod is None:
            # 尚未加载，尝试导入
            for name in module_names:
                try:
                    loaded_mod = importlib.import_module(name)
                    break
                except Exception as e:
                    self.log(f"模块 {name} 导入失败: {e}")
        if loaded_mod is None:
            self.log("刷新策略失败：未找到策略模块。")
            return
        try:
            new_map = getattr(loaded_mod, "STRATEGY_MAP", None)
            default_name = getattr(loaded_mod, "DEFAULT_STRATEGY_NAME", None)
            if not new_map:
                self.log("策略映射为空或不存在。")
                return
            current = self.strategy_combo.currentText()
            self.strategy_combo.clear()
            for name in new_map.keys():
                self.strategy_combo.addItem(name)
            # 尝试保持原选择
            if current in new_map:
                self.strategy_combo.setCurrentText(current)
            elif default_name:
                self.strategy_combo.setCurrentText(default_name)
            self.log(f"策略刷新完成，共 {len(new_map)} 条。")
        except Exception as e:
            self.log(f"刷新策略内部出错: {e}")

    def update_table(self, metrics: dict):
        self.table.setRowCount(0)
        for k, v in metrics.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            unit = "%" if "率" in k or "回撤" in k else ("元" if "资产" in k else "")
            self.table.setItem(row, 0, QTableWidgetItem(k))
            if isinstance(v, float):
                if unit == "%":
                    show_v = f"{v*100:.2f}"
                else:
                    show_v = f"{v:.2f}"
            else:
                show_v = str(v)
            self.table.setItem(row, 1, QTableWidgetItem(show_v))
            self.table.setItem(row, 2, QTableWidgetItem(unit))
        self.table.resizeColumnsToContents()

    def update_charts(self, ohlc_df: pd.DataFrame, trades_df: pd.DataFrame):
        """绘制 K 线，标注买卖点；中间展示 MACD 柱状图；底部展示 Vol 柱。支持滚轮缩放；悬停显示中文 OHLC。"""
        self.fig.clear()
        gs = self.fig.add_gridspec(3, 1, height_ratios=[3, 1, 1], hspace=0.06)
        ax_price = self.fig.add_subplot(gs[0])
        ax_macd = self.fig.add_subplot(gs[1], sharex=ax_price)  # 中间：MACD 柱
        ax_vol = self.fig.add_subplot(gs[2], sharex=ax_price)   # 底部：Vol 柱

        ax_price.set_title("K线")
        # 绘制蜡烛
        width = 0.6
        for pos, (idx, row) in enumerate(ohlc_df.iterrows()):
            o = float(row['open']); c = float(row['close']); h = float(row['high']); l = float(row['low'])
            color = 'red' if c >= o else 'green'
            ax_price.plot([pos, pos], [l, h], color=color, linewidth=1)
            ax_price.add_patch(patches.Rectangle((pos - width/2, min(o, c)), width,
                                                 abs(c - o), color=color, alpha=0.6))
        ax_price.set_xlim(-1, len(ohlc_df))
        ax_price.tick_params(axis='x', labelbottom=False)

        # 买卖点标注（仅第一标的）
        # 买卖点标注（仅当前主图标的）+ hover 展示交易信息
        try:
            primary_combo = getattr(self, 'primary_combo', None)
            first_name = primary_combo.currentText() if primary_combo is not None else None
            if first_name and not trades_df.empty and 'symbol' in trades_df.columns:
                pos_map = {pd.Timestamp(d): i for i, d in enumerate(ohlc_df['date'])}
                sub = trades_df[trades_df['symbol'] == first_name].copy()
                buy_x, buy_y, buy_txt = [], [], []
                sell_x, sell_y, sell_txt = [], [], []
                for _, t in sub.iterrows():
                    entry_date = pd.to_datetime(t.get('entry_date')) if pd.notna(t.get('entry_date')) else None
                    exit_date = pd.to_datetime(t.get('exit_date')) if pd.notna(t.get('exit_date')) else None
                    size = t.get('size', '')
                    if entry_date is not None and entry_date in pos_map:
                        i_buy = pos_map[entry_date]
                        buy_x.append(i_buy)
                        buy_y.append(float(ohlc_df['close'].iloc[i_buy]))
                        ep = t.get('entry_price', None)
                        buy_txt.append(f"买入 {first_name}\n日期:{entry_date.date()}\n价格:{ep:.2f} 数量:{size}" if ep is not None else f"买入 {first_name}\n日期:{entry_date.date()} 数量:{size}")
                    if exit_date is not None and exit_date in pos_map:
                        i_sell = pos_map[exit_date]
                        sell_x.append(i_sell)
                        sell_y.append(float(ohlc_df['close'].iloc[i_sell]))
                        xp = t.get('exit_price', None)
                        pnl = t.get('pnl_pct', None)
                        pnl_txt = f" 收益:{pnl*100:.2f}%" if pnl is not None else ""
                        sell_txt.append(f"卖出 {first_name}\n日期:{exit_date.date()}\n价格:{xp:.2f}{pnl_txt}" if xp is not None else f"卖出 {first_name}\n日期:{exit_date.date()}{pnl_txt}")
                if buy_x:
                    buy_sc = ax_price.scatter(buy_x, buy_y, marker='^', color='#2ca02c', s=50, zorder=5)
                    try:
                        cur = mplcursors.cursor(buy_sc, hover=True)
                        @cur.connect("add")
                        def _on_buy(sel):
                            idx = int(getattr(sel, 'index', 0) or 0)
                            idx = max(0, min(idx, len(buy_txt)-1))
                            sel.annotation.set(text=buy_txt[idx])
                    except Exception:
                        pass
                if sell_x:
                    sell_sc = ax_price.scatter(sell_x, sell_y, marker='v', color='#d64f4f', s=50, zorder=5)
                    try:
                        cur2 = mplcursors.cursor(sell_sc, hover=True)
                        @cur2.connect("add")
                        def _on_sell(sel):
                            idx = int(getattr(sel, 'index', 0) or 0)
                            idx = max(0, min(idx, len(sell_txt)-1))
                            sel.annotation.set(text=sell_txt[idx])
                    except Exception:
                        pass
        except Exception:
            pass

        # MACD 柱状图 (中间)
        hist = ohlc_df['MACD_HIST'] if 'MACD_HIST' in ohlc_df.columns else (ohlc_df['DIF'] - ohlc_df['DEA'])
        x = range(len(ohlc_df))
        colors = ['#d64f4f' if v >= 0 else '#2ca02c' for v in hist]
        ax_macd.bar(x, hist, color=colors, width=0.8, alpha=0.8)
        ax_macd.axhline(0, color='#888', linewidth=0.8)
        ax_macd.set_ylabel('MACD')

        # Vol 柱状图 (底部)
        vol = ohlc_df['volume']
        up_colors = ['#d64f4f' if (ohlc_df['close'].iloc[i] >= ohlc_df['open'].iloc[i]) else '#2ca02c' for i in range(len(ohlc_df))]
        ax_vol.bar(range(len(ohlc_df)), vol, color=up_colors, width=0.8, alpha=0.8)
        ax_vol.set_ylabel('Vol')

        # X 轴日期（在最底部显示）
        step = max(len(ohlc_df)//20, 1)
        show_dates = [d.strftime('%Y-%m-%d') for d in ohlc_df['date']]
        ax_vol.set_xticks(range(0, len(ohlc_df), step))
        ax_vol.set_xticklabels([show_dates[i] for i in range(0, len(ohlc_df), step)], rotation=45, fontsize=8)

        # Hover：在 K 线上增加一条透明线以支持悬停（中文 OHLC）
        try:
            import numpy as np
            x_idx = np.arange(len(ohlc_df))
            y_close = ohlc_df['close'].to_numpy()
            line_close, = ax_price.plot(x_idx, y_close, alpha=0)
            cursor = mplcursors.cursor([line_close], hover=True)
            @cursor.connect("add")
            def on_add(sel):
                xvals = line_close.get_xdata(); yvals = line_close.get_ydata()
                idx = getattr(sel, 'index', None)
                try:
                    idx = int(round(idx)) if idx is not None else None
                except Exception:
                    idx = None
                n = len(x_idx)
                if idx is None or idx < 0 or idx >= n:
                    try:
                        tx = float(sel.target[0]) if hasattr(sel, 'target') else float(x_idx[-1])
                    except Exception:
                        tx = float(n-1)
                    xv = np.asarray(xvals, dtype=float)
                    idx = int(np.argmin(np.abs(xv - tx)))
                d = ohlc_df['date'].iloc[idx]
                o = ohlc_df['open'].iloc[idx]; h = ohlc_df['high'].iloc[idx]; l = ohlc_df['low'].iloc[idx]; c = ohlc_df['close'].iloc[idx]
                sel.annotation.set(text=f"{pd.to_datetime(d).date()}\n开:{o:.2f} 高:{h:.2f} 低:{l:.2f} 收:{c:.2f}")
        except Exception:
            pass

        # 滚轮缩放（以鼠标位置为中心）
        try:
            if hasattr(self, '_scroll_cid') and self._scroll_cid:
                self.canvas.mpl_disconnect(self._scroll_cid)
            def _on_scroll(event):
                if event.inaxes not in (ax_price, ax_macd, ax_vol):
                    return
                import numpy as np
                cur_axes = ax_price
                xmin, xmax = cur_axes.get_xlim()
                xdata = event.xdata if event.xdata is not None else (xmin + xmax)/2
                span = (xmax - xmin)
                if event.button == 'up':
                    scale = 0.8
                elif event.button == 'down':
                    scale = 1.25
                else:
                    scale = 1.0
                new_span = max(5, span * scale)
                left = xdata - new_span/2
                right = xdata + new_span/2
                cur_axes.set_xlim(left, right)
                self.canvas.draw_idle()
            self._scroll_cid = self.canvas.mpl_connect('scroll_event', _on_scroll)
        except Exception:
            pass

        self.fig.tight_layout()
        self.canvas.draw()

    def update_equity_chart(self, equity_curve: pd.DataFrame, trades_df: pd.DataFrame):
        self.equity_fig.clear()
        ax = self.equity_fig.add_subplot(1,1,1)
        ax.set_title("策略收益曲线")
        ax.plot(equity_curve['date'], equity_curve['value'], label='净值', color='orange')
        ax.grid(alpha=0.3)
        self.equity_fig.autofmt_xdate()
        # Hover
        try:
            cursor = mplcursors.cursor(ax.lines, hover=True)
            @cursor.connect("add")
            def on_add(sel):
                import numpy as np
                line = sel.artist
                x, y = line.get_data()
                # sel.index 可能是浮点或异常值，做鲁棒处理
                idx = getattr(sel, 'index', None)
                try:
                    idx = int(round(idx)) if idx is not None else None
                except Exception:
                    idx = None
                # 趋近最近点
                if idx is None or idx < 0 or idx >= len(x):
                    try:
                        tx = sel.target[0]
                        idx = int(np.argmin(np.abs(np.asarray(x) - tx)))
                    except Exception:
                        idx = max(0, min(len(x)-1, 0))
                d = pd.to_datetime(x[idx])
                initial_val = float(equity_curve['value'].iloc[0]) if not equity_curve.empty else 1.0
                val = float(y[idx])
                pct = (val / initial_val - 1.0) * 100
                # 当日买卖点（匹配 entry_date / exit_date）
                hover_date = d.date()
                buys = []
                sells = []
                if not trades_df.empty:
                    # entry_date / exit_date 在 trade_records 中是 date 对象
                    buys = trades_df[trades_df['entry_date'] == hover_date]['symbol'].tolist()
                    sells = trades_df[trades_df['exit_date'] == hover_date]['symbol'].tolist()
                buys_txt = ("买:" + ",".join(buys)) if buys else ""
                sells_txt = ("卖:" + ",".join(sells)) if sells else ""
                trade_txt = (buys_txt + (" " if buys_txt and sells_txt else "") + sells_txt).strip()
                if trade_txt:
                    sel.annotation.set(text=f"{hover_date}\n净值:{val:.2f}\n收益:{pct:.2f}%\n{trade_txt}")
                else:
                    sel.annotation.set(text=f"{hover_date}\n净值:{val:.2f}\n收益:{pct:.2f}%")
        except Exception:
            pass
        self.equity_fig.tight_layout()
        self.equity_canvas.draw()

    def update_trades_table(self, trades_df: pd.DataFrame):
        self.trades_table.setRowCount(0)
        if trades_df.empty:
            return
        for _, row in trades_df.iterrows():
            r = self.trades_table.rowCount()
            self.trades_table.insertRow(r)
            vals = [
                row.get('symbol',''),
                str(row.get('entry_date','')),
                str(row.get('exit_date','')),
                f"{row.get('entry_price',0):.2f}" if row.get('entry_price') else '',
                f"{row.get('exit_price',0):.2f}" if row.get('exit_price') else '',
                str(row.get('size','')),
                f"{row.get('pnl_pct',0)*100:.2f}" if row.get('pnl_pct') is not None else '',
                str(row.get('holding_days','')),
            ]
            for c,val in enumerate(vals):
                self.trades_table.setItem(r,c,QTableWidgetItem(val))
        self.trades_table.resizeColumnsToContents()

    def reload_app(self):
        self.log("重载应用: 重新加载模块并重建界面 ...")
        import importlib, sys
        mods = ['strategy','data_loader','backtest','src.strategy','src.data_loader','src.backtest']
        for m in mods:
            if m in sys.modules:
                try:
                    importlib.reload(sys.modules[m])
                    self.log(f"模块 {m} 重载成功")
                except Exception as e:
                    self.log(f"模块 {m} 重载失败: {e}")
        # 重新构建界面
        old = self.centralWidget()
        if old:
            old.deleteLater()
        self._init_ui()
        self.log("重载完成。")

__all__ = ['MainWindow']
