"""A-share trading calendar used by the scheduler and desktop monitor."""

import logging
import threading
from datetime import time
from functools import lru_cache
from time import monotonic
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


_calendar_refresh_lock = threading.Lock()
_calendar_result = (None, None)
_calendar_retry_at = 0


def cached_trading_day(day):
    """Return the verified status, or None while the calendar is unavailable."""
    global _calendar_retry_at
    if day.weekday() >= 5:
        return False
    result_day, result = _calendar_result
    if result_day == day:
        return result

    def refresh():
        global _calendar_result
        try:
            _calendar_result = (day, day in _trading_dates(day))
        except Exception as exc:
            logging.getLogger(__name__).warning("无法确认 %s 是否开市，持仓按工作日时段刷新：%s", day, exc)
        finally:
            _calendar_refresh_lock.release()

    if _calendar_refresh_lock.acquire(blocking=False):
        if monotonic() >= _calendar_retry_at and _calendar_result[0] != day:
            _calendar_retry_at = monotonic() + 300
            threading.Thread(target=refresh, daemon=True).start()
        else:
            _calendar_refresh_lock.release()
    return None
