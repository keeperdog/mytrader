# 量化回测 MVP (PyQt6 + Backtrader + Akshare)

## 功能概述

最小可行版本，通过 GUI 选择股票与日期范围，运行基于 MACD 金叉 + 成交量放大 的示例策略，输出：

- 图表：K 线 + MACD + 信号、策略收益 vs 基准收益
- 指标：总收益率、年化收益率、交易次数、胜率、最大回撤、最终资产
- 日志：实时显示数据获取、回测进度及错误信息

## 安装依赖（Conda 环境 mytrader）

```bash
conda activate mytrader
# 若尚未安装或需要升级 pip
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 运行

```bash
conda activate mytrader
# 推荐方式（包运行，避免相对导入问题）
python -m src.main
# 若使用脚本直接运行也已兼容：
python src/main.py
```

若出现 `ImportError: attempted relative import with no known parent package` 说明使用脚本方式但旧版本 `main.py` 未包含兼容逻辑，已在当前版本修复；如仍异常，可强制使用模块方式运行：

```bash
python -m src.main
```

## 操作步骤

1. 启动后顶部选择标的（默认金地集团）与日期范围（默认 2020-01-01 ~ 2025-01-01）。
2. 点击“开始回测”按钮，按钮置灰表示进行中，底部日志滚动输出状态。
3. 完成后：
   - “图表区”显示两幅图；支持鼠标悬停查看收益曲线数值。
   - “数据区”显示指标表格，可选中复制。
4. 再次修改参数后重新点击“开始回测”即可重复测试。

## 策略逻辑

- 买入：MACD DIF 上穿 DEA (金叉) 且当日成交量 > 近 20 日均量 \* 1.2 → 满仓。
- 卖出：MACD DIF 下穿 DEA (死叉) → 清仓。
- 初始资金：100000 元；不计手续费与滑点。

## 修改扩展

- 新增标的：编辑 `data_loader.py` 中 `NORMALIZED_OPTIONS` 与映射字典。
- 策略调参：在 `strategy.py` 中修改 `vol_window`、`vol_factor` 或新增条件。
- 增加指标：在 `backtest.py` 中扩展分析器 / 计算逻辑，再在 GUI `update_table` 中展示。

## 常见问题

- 数据为空：检查网络或日期范围；日志会提示“获取数据为空”。
- GUI 卡顿：确认未在主线程做耗时操作；回测在 QThread 中执行。
- 悬停无提示：可能 `mplcursors` 安装失败，重新 `pip install mplcursors`。

## 免责声明

示例策略仅用于教学演示，不构成投资建议。请谨慎使用及扩展。
