"""跨模块共享的异常类型（独立成模块以避免循环导入）。"""

from __future__ import annotations


class Cancelled(Exception):
    """用户主动取消：Ctrl-R 回退返回 / Ctrl-C / EOF。

    在流程中向上抛出，由 Transaction 捕获并回退已应用的改动。
    """


class SaveExit(Cancelled):
    """用户按 esc：保存/确认返回——保留本层改动，退回上一级。

    是 Cancelled 的子类：只关心「返回」这件事的调用方一个 `except Cancelled`
    就能同时接住两种按键；需要区分「保存返回」与「回退返回」时，把
    `except SaveExit` 写在前面单独处理，再用 `except Cancelled` 兜底。
    """
