#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""程序入口
直接运行此脚本即可启动 GUI。
"""
from __future__ import annotations
import sys
import os
from PyQt6.QtWidgets import QApplication

# 兼容两种运行方式：
# 1) python -m src.main  -> 有包上下文 (__package__ 不为空)
# 2) python src/main.py  -> 无包上下文，需要调整 sys.path 并使用脚本导入
if __package__:
    from .gui import MainWindow  # 包方式
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if base_dir not in sys.path:
        sys.path.append(base_dir)
    from gui import MainWindow  # 脚本方式


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
