import os
import datetime as dt
import wx
import wx.adv as adv
from typing import Optional
from dataclasses import dataclass

from gui.data_models import BacktestResult, load_sample_result

# Matplotlib 嵌入并设置中文字体
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib
import matplotlib.dates as mdates
import mplcursors
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
matplotlib.rcParams['axes.unicode_minus'] = False


@dataclass
class StrategyConfig:
    name: str
    file_path: str


class PerformancePanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.figure = Figure(figsize=(5, 4))
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvas(self, -1, self.figure)
        vbox.Add(self.canvas, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(vbox)

    def update(self, result: BacktestResult):
        self.ax.clear()
        if not result.performance:
            self.ax.text(0.5, 0.5, '暂无绩效数据', ha='center', va='center', fontsize=12)
            self.canvas.draw()
            return

        dates = [p['date'] for p in result.performance]
        strat = [p['strategy_nav'] for p in result.performance]
        bench = [p['benchmark_nav'] for p in result.performance]
        line_strat, = self.ax.plot(dates, strat, label='策略')
        line_bench, = self.ax.plot(dates, bench, label='基准')
        self.ax.set_title('策略与基准表现对比')
        self.ax.legend()
        self.figure.tight_layout()

        # 设置悬停提示：显示日期 + 两条曲线的相对百分比（相对首日）
        base_strat = strat[0]
        base_bench = bench[0]
        lines = [line_strat, line_bench]
        # 清除旧 cursor 避免重复事件
        if hasattr(self, 'cursor') and self.cursor:
            try:
                self.cursor.disconnect('add')
            except Exception:
                pass
        self.cursor = mplcursors.cursor(lines, hover=True)

        def _fmt(sel):
            line = sel.artist
            x = sel.target[0]
            xdata = line.get_xdata()
            # 将 xdata 转为 matplotlib 的数值（float days）以便比较
            try:
                xnums = mdates.date2num(xdata)
            except Exception:
                # 如果 xdata 已经是数值，直接使用
                xnums = xdata
            # 找最近点索引（比较数值）
            idx = min(range(len(xnums)), key=lambda i: abs(xnums[i] - x))
            # 获取对应日期并格式化
            try:
                date_dt = mdates.num2date(xnums[idx]).date()
            except Exception:
                # 兜底：如果原始 dates 列表可用，直接取
                date_dt = dates[idx]
            pct_strat = (strat[idx] / base_strat - 1) * 100
            pct_bench = (bench[idx] / base_bench - 1) * 100
            text = f"{date_dt:%Y-%m-%d}\n策略  {pct_strat:.1f}%\n基准  {pct_bench:.1f}%"
            sel.annotation.set_text(text)
            sel.annotation.get_bbox_patch().set(fc='#ffffff', alpha=0.9)
            sel.annotation.arrow_patch.set(visible=False)

        self.cursor.connect('add', _fmt)
        self.canvas.draw()


class SimpleListPanel(wx.Panel):
    def __init__(self, parent, columns):
        super().__init__(parent)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        for i, col in enumerate(columns):
            self.list.InsertColumn(i, col)
        vbox.Add(self.list, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(vbox)

    def reset(self):
        self.list.DeleteAllItems()

    def append_row(self, values):
        idx = self.list.InsertItem(self.list.GetItemCount(), str(values[0]))
        for i, val in enumerate(values[1:], start=1):
            self.list.SetItem(idx, i, str(val))

    def set_column_widths(self):
        for i in range(self.list.GetColumnCount()):
            self.list.SetColumnWidth(i, wx.LIST_AUTOSIZE_USEHEADER)


class MainFrame(wx.Frame):
    def __init__(self, parent: Optional[wx.Window], title: str):
        super().__init__(parent, title=title, size=(1400, 820))
        self.result: Optional[BacktestResult] = None
        self._build_ui()

    # -------------- UI 构建 --------------
    def _build_ui(self):
        panel = wx.Panel(self)
        hbox = wx.BoxSizer(wx.HORIZONTAL)

        left_panel = self._build_left(panel)
        hbox.Add(left_panel, 0, wx.EXPAND | wx.ALL, 0)

        self.nb = wx.Notebook(panel)
        self.performance_panel = PerformancePanel(self.nb)
        self.positions_panel = SimpleListPanel(self.nb, ['代码', '名称', '仓位%'])
        self.trades_panel = SimpleListPanel(self.nb, ['代码', '名称', '买入价', '卖出价', '盈亏', '盈亏(现金)', '买入日', '卖出日', '持仓天数', '收益率%'])
        self.signals_panel = SimpleListPanel(self.nb, ['信号日期', '代码', '操作类型', '起始仓位%', '目标仓位%'])
        self.nb.AddPage(self.performance_panel, '历史表现')
        self.nb.AddPage(self.positions_panel, '当前持仓')
        self.nb.AddPage(self.trades_panel, '历史交易')
        self.nb.AddPage(self.signals_panel, '调仓信号')
        hbox.Add(self.nb, 1, wx.EXPAND | wx.ALL, 0)

        bottom_log = self._build_log(panel)

        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(hbox, 1, wx.EXPAND)
        vbox.Add(bottom_log, 0, wx.EXPAND)
        panel.SetSizer(vbox)

        self._build_menu()

    def _build_menu(self):
        menubar = wx.MenuBar()
        backtest_menu = wx.Menu()
        item_run = backtest_menu.Append(wx.ID_ANY, '本地策略回测')
        self.Bind(wx.EVT_MENU, self.on_start_backtest, item_run)
        menubar.Append(backtest_menu, '回测')
        self.SetMenuBar(menubar)

    def _build_left(self, parent):
        panel = wx.Panel(parent, size=(340, -1))
        vbox = wx.BoxSizer(wx.VERTICAL)

        # 策略选择
        st_box = wx.StaticBox(panel, label='策略选择')
        st_sizer = wx.StaticBoxSizer(st_box, wx.VERTICAL)
        self.strategy_choice = wx.ComboBox(panel, choices=self._load_strategies(), style=wx.CB_READONLY)
        st_sizer.Add(self.strategy_choice, 0, wx.EXPAND | wx.ALL, 5)
        btn_dir = wx.Button(panel, label='策略目录')
        btn_edit = wx.Button(panel, label='编辑策略')
        st_btn_h = wx.BoxSizer(wx.HORIZONTAL)
        st_btn_h.Add(btn_dir, 1, wx.ALL, 2)
        st_btn_h.Add(btn_edit, 1, wx.ALL, 2)
        st_sizer.Add(st_btn_h, 0, wx.EXPAND)
        vbox.Add(st_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # 回测日期范围
        date_box = wx.StaticBox(panel, label='回测日期范围')
        date_sizer = wx.StaticBoxSizer(date_box, wx.VERTICAL)
        today = wx.DateTime.Now()
        start_def = today - wx.DateSpan(years=7)  # 默认7年前
        self.start_picker = adv.DatePickerCtrl(panel, dt=start_def)
        self.end_picker = adv.DatePickerCtrl(panel, dt=today)
        date_grid = wx.FlexGridSizer(cols=2, vgap=4, hgap=4)
        date_grid.Add(wx.StaticText(panel, label='开始日期:'), 0, wx.ALIGN_CENTER_VERTICAL)
        date_grid.Add(self.start_picker, 1, wx.EXPAND)
        date_grid.Add(wx.StaticText(panel, label='结束日期:'), 0, wx.ALIGN_CENTER_VERTICAL)
        date_grid.Add(self.end_picker, 1, wx.EXPAND)
        date_sizer.Add(date_grid, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(date_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # 基准
        bench_box = wx.StaticBox(panel, label='基准指数')
        bench_sizer = wx.StaticBoxSizer(bench_box, wx.VERTICAL)
        self.benchmark_choice = wx.ComboBox(panel, choices=['沪深300', '中证500', '上证50'], style=wx.CB_READONLY)
        bench_sizer.Add(self.benchmark_choice, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(bench_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # 操作按钮
        btn_h = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_start = wx.Button(panel, label='启动回测')
        self.btn_stop = wx.Button(panel, label='停止回测')
        self.btn_stop.Disable()
        btn_h.Add(self.btn_start, 1, wx.ALL, 5)
        btn_h.Add(self.btn_stop, 1, wx.ALL, 5)
        vbox.Add(btn_h, 0, wx.EXPAND)

        self.btn_start.Bind(wx.EVT_BUTTON, self.on_start_backtest)
        self.btn_stop.Bind(wx.EVT_BUTTON, self.on_stop_backtest)

        panel.SetSizer(vbox)
        return panel

    def _build_log(self, parent):
        log_panel = wx.Panel(parent, size=(-1, 160))
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.log_ctrl = wx.TextCtrl(log_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
        vbox.Add(self.log_ctrl, 1, wx.EXPAND | wx.ALL, 4)
        btn_h = wx.BoxSizer(wx.HORIZONTAL)
        btn_clear = wx.Button(log_panel, label='清空日志')
        btn_save = wx.Button(log_panel, label='保存日志')
        btn_h.Add(btn_clear, 0, wx.ALL, 4)
        btn_h.Add(btn_save, 0, wx.ALL, 4)
        vbox.Add(btn_h, 0, wx.ALIGN_RIGHT)
        btn_clear.Bind(wx.EVT_BUTTON, lambda e: self.log_ctrl.SetValue(''))
        btn_save.Bind(wx.EVT_BUTTON, self.on_save_log)
        log_panel.SetSizer(vbox)
        return log_panel

    # -------------- 数据与事件 --------------
    def _load_strategies(self):
        path = os.path.join(os.getcwd(), 'tasks')
        names = []
        if os.path.isdir(path):
            for f in os.listdir(path):
                if f.endswith('.toml'):
                    names.append(os.path.splitext(f)[0])
        return names or ['示例策略']

    def log(self, text: str):
        self.log_ctrl.AppendText(text + '\n')

    def _wxdate_to_pydate(self, wxdate: wx.DateTime) -> dt.date:
        return dt.date(wxdate.GetYear(), wxdate.GetMonth() + 1, wxdate.GetDay())

    def on_start_backtest(self, event):
        start_py = self._wxdate_to_pydate(self.start_picker.GetValue())
        end_py = self._wxdate_to_pydate(self.end_picker.GetValue())
        self.log(f'开始回测: 日期范围 {start_py} ~ {end_py} ...')
        self.btn_start.Disable()
        self.btn_stop.Enable()
        # 加载示例数据（真实回测替换此调用）
        self.result = load_sample_result(start_py, end_py)
        if not self.result.performance:
            self.log('日期范围无效或无数据。')
        self.update_views()
        self.log('回测完成 (示例示意)。')
        self.btn_start.Enable()
        self.btn_stop.Disable()

    def on_stop_backtest(self, event):
        self.log('停止回测请求（示例中无真实线程）')
        self.btn_start.Enable()
        self.btn_stop.Disable()

    def update_views(self):
        if not self.result:
            return
        # 绩效
        self.performance_panel.update(self.result)
        # 当前持仓
        self.positions_panel.reset()
        for pos in self.result.positions:
            self.positions_panel.append_row([
                pos['code'], pos['name'], f"{pos['weight']*100:.2f}%"
            ])
        self.positions_panel.set_column_widths()
        # 历史交易
        self.trades_panel.reset()
        for t in self.result.trades:
            self.trades_panel.append_row([
                t['code'], t['name'], t['buy_price'], t['sell_price'], f"{t['pnl']:.4f}", f"{t['pnl_cash']:.2f}",
                t['buy_date'], t['sell_date'], t['hold_days'], f"{t['ret_pct']*100:.2f}"
            ])
        self.trades_panel.set_column_widths()
        # 调仓信号
        self.signals_panel.reset()
        for s in self.result.rebalance_signals:
            self.signals_panel.append_row([
                s['signal_date'], s['code'], s['action'], f"{s['start_weight']*100:.1f}", f"{s['target_weight']*100:.1f}"
            ])
        self.signals_panel.set_column_widths()

    def on_save_log(self, event):
        with wx.FileDialog(self, '保存日志', wildcard='Text files (*.txt)|*.txt', style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return
            path = dlg.GetPath()
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.log_ctrl.GetValue())
            self.log(f'日志已保存到: {path}')

