"""A-share trading calendar used by the scheduler and desktop monitor."""

import logging
from datetime import time
from functools import lru_cache
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo("Asia/Shanghai")
RISK_CHECK_TIMES = (
    time(9, 30), time(10), time(10, 30), time(11), time(11, 30),
    time(13), time(13, 30), time(14), time(14, 30), time(15),
)


@lru_cache(maxsize=1)
def _trading_dates(as_of):
    import akshare as ak

    # AKShare renamed the calendar function in newer releases.
    fetch = getattr(ak, "calendar_trade_date_hist_sina", None)
    if fetch is None:
        fetch = ak.tool_trade_date_hist_sina
    dates = frozenset(fetch()["trade_date"])
    if not dates or max(dates).year < as_of.year:
        raise ValueError("交易日历未覆盖当前年份")
    return dates


def is_trading_day(day):
    if day.weekday() >= 5:
        return False
    try:
        return day in _trading_dates(day)
    except Exception as exc:
        logging.getLogger(__name__).warning("无法确认 %s 是否开市，跳过自动任务：%s", day, exc)
        return False
