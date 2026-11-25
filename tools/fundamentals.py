"""Structured, source-linked fundamentals for DataBoard."""

import logging
import math
import re
import time
from statistics import median
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
from threading import Lock
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

LOG = logging.getLogger(__name__)
DATA_API = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
VALUE_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
F10 = "https://emweb.securities.eastmoney.com/PC_HSF10"
AMOUNTS = {
    "revenue": "TOTALOPERATEREVE",
    "profit": "PARENTNETPROFIT",
    "adjusted_profit": "KCFJCXSYJLR",
    "operating_cash": "NETCASH_OPERATE_PK",
}
RATIOS = {
    "roe": "ROEJQ",
    "gross_margin": "XSMLL",
    "net_interest_margin": "NET_INTEREST_MARGIN",
    "bad_loan_ratio": "NONPERLOAN",
    "provision_coverage": "BLDKBBL",
    "core_capital_ratio": "HXYJBCZL",
}
PEER_GROUPS = {
    "通信线缆及配套": ("002491", "600487", "600522", "601869"),
    "银行": ("601398", "601939", "601288", "600036", "601166"),
}
CSI_INDEX_CODES = {
    "中证银行": "399986", "沪深300": "000300", "中证500": "000905",
    "中证1000": "000852", "中证红利": "000922", "中证A500": "000510",
}
_cache = OrderedDict()
_cache_lock = Lock()
_request_locks = [Lock() for _ in range(32)]
_analysis_locks = [Lock() for _ in range(32)]
_detail_workers = ThreadPoolExecutor(max_workers=8, thread_name_prefix="fundamentals")


class FundamentalsUnavailable(Exception):
    """A required data source could not be loaded."""


def instrument_kind(symbol):
    market, code = symbol[:2], symbol[2:]
    if not re.fullmatch(r"[0-9]{6}", code):
        return "unsupported"
    if (market == "sh" and code.startswith(("50", "51", "52", "56", "58"))) or (
        market == "sz" and code.startswith(("15", "16", "18"))
    ):
        return "fund"
    if (market == "sh" and code.startswith("6")) or (market == "sz" and code.startswith(("00", "30"))):
        return "stock"
    if market == "bj" and code.startswith(("4", "8", "920")):
        return "stock"
    return "unsupported"


def _get(url, params=None, *, referer=None):
    headers = {"User-Agent": "Mozilla/5.0"}
    if referer:
        headers["Referer"] = referer
    try:
        response = requests.get(url, params=params, timeout=(4, 7), headers=headers)
    except (requests.ConnectionError, requests.Timeout):
        response = requests.get(url, params=params, timeout=(4, 7), headers=headers)
    response.raise_for_status()
    return response


def _table(report, query, *, size=10, sort=None, columns="ALL", valuation=False):
    params = {
        "reportName": report,
        "columns": columns,
        "filter": query,
        "pageSize": size,
        "source": "WEB" if valuation else "HSF10",
        "client": "WEB" if valuation else "PC",
    }
    if sort:
        params.update(sortColumns=sort, sortTypes="-1")
    result = _get(VALUE_API if valuation else DATA_API, params).json()
    if not result.get("success") and result.get("result") is None:
        # Eastmoney uses this code for a successful query with no rows.
        if result.get("code") == 9501:
            return []
        raise FundamentalsUnavailable(result.get("message") or report)
    return (result.get("result") or {}).get("data") or []


def _cached(key, ttl, loader):
    locks = _analysis_locks if key[0] == "analysis" else _request_locks
    with locks[hash(key) % len(locks)]:
        with _cache_lock:
            entry = _cache.get(key)
            if entry and time.monotonic() < entry[0]:
                _cache.move_to_end(key)
                return entry[1]
        value = loader()
        with _cache_lock:
            _cache[key] = (time.monotonic() + ttl, value)
            _cache.move_to_end(key)
            if len(_cache) > 256:
                _cache.popitem(last=False)
        return value


def _optional(loader, *args):
    try:
        return loader(*args)
    except (requests.RequestException, ValueError, FundamentalsUnavailable) as exc:
        LOG.info("Fundamentals source %s unavailable: %s", loader.__name__, exc)
        return None


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _delta(current, previous):
    return current - previous if current is not None and previous is not None else None


def _day(value):
    return str(value or "")[:10]


def _identifier(symbol):
    return f"{symbol[2:]}.{symbol[:2].upper()}"


def _report_rows(symbol):
    return _cached(("reports", symbol), 1800, lambda: _table(
        "RPT_F10_FINANCE_MAINFINADATA", f'(SECUCODE="{_identifier(symbol)}")',
        size=12, sort="REPORT_DATE",
    ))


def _report(row):
    return {
        "period": _day(row.get("REPORT_DATE")),
        "announced": _day(row.get("NOTICE_DATE")),
        "currency": row.get("CURRENCY"),
        **{key: _number(row.get(field)) for key, field in (AMOUNTS | RATIOS).items()},
    }


def _quarters(reports):
    previous_ends = {"06-30": "03-31", "09-30": "06-30", "12-31": "09-30"}

    def single_quarter(period):
        report = reports.get(period, {})
        predecessor = previous_ends.get(period[5:])
        previous = reports.get(period[:5] + predecessor, {}) if predecessor else None
        comparable = previous is not None and _same_basis(report, previous)
        return {
            key: _delta(report.get(key), previous.get(key)) if comparable
            else report.get(key) if previous is None else None
            for key in AMOUNTS
        }

    return [
        {"period": period, "currency": reports[period].get("currency"), **single_quarter(period),
         "prior": single_quarter(f"{int(period[:4]) - 1}{period[4:]}")}
        for period in sorted(reports)[-4:]
    ]


def _same_basis(first, second):
    return bool(first.get("currency") and first.get("currency") == second.get("currency"))


def _report_findings(current, prior, kind):
    profit = _delta(current["profit"], prior.get("profit"))
    adjusted = _delta(current["adjusted_profit"], prior.get("adjusted_profit"))
    cash = _delta(current["operating_cash"], prior.get("operating_cash"))
    findings = []
    unit = f"亿 {current['currency']}"
    if profit is not None and adjusted is not None and profit > 0 > adjusted:
        findings.append(f"累计归母净利润同比增加 {profit / 1e8:,.2f} {unit}，扣非归母净利润同比减少 {-adjusted / 1e8:,.2f} {unit}")
    if kind == "stock" and adjusted is not None and cash is not None and adjusted > 0 > cash:
        findings.append(f"累计扣非归母净利润同比增加 {adjusted / 1e8:,.2f} {unit}，经营现金流净额同比减少 {-cash / 1e8:,.2f} {unit}")
    if kind == "bank":
        for field, label in (("net_interest_margin", "净息差"), ("bad_loan_ratio", "不良贷款率"),
                             ("provision_coverage", "拨备覆盖率"), ("core_capital_ratio", "核心一级资本充足率")):
            change = _delta(current[field], prior.get(field))
            if change is not None and round(change, 2):
                direction = "上升" if change > 0 else "下降"
                findings.append(f"{label}同比{direction} {abs(change):.2f} 个百分点，至 {current[field]:.2f}%")
    return findings


def _profit_observation(current, prior):
    profit, prior_profit = current["profit"], prior.get("profit")
    if profit is None or prior_profit is None:
        return ""
    if prior_profit < 0 <= profit:
        return "归母净利润同比扭亏"
    if profit < 0 <= prior_profit:
        return "归母净利润同比转亏"
    change = "增加" if profit > prior_profit else "减少" if profit < prior_profit else "持平"
    amount = abs(profit - prior_profit) / 1e8
    return f"累计归母净利润同比{change} {amount:,.2f} 亿 {current['currency']}" if amount else "累计归母净利润同比持平"


def _valuations(query, size):
    return _table(
        "RPT_VALUEANALYSIS_DET", query, size=size, sort="TRADE_DATE", valuation=True,
        columns="SECURITY_CODE,SECURITY_NAME_ABBR,TRADE_DATE,CLOSE_PRICE,TOTAL_MARKET_CAP,PE_TTM,PB_MRQ",
    )


def _valuation_row(row):
    return {
        "code": row.get("SECURITY_CODE"), "name": row.get("SECURITY_NAME_ABBR"),
        "date": _day(row.get("TRADE_DATE")), "price": _number(row.get("CLOSE_PRICE")),
        "market_cap": _number(row.get("TOTAL_MARKET_CAP")),
        "pe": _number(row.get("PE_TTM")), "pb": _number(row.get("PB_MRQ")),
    }


def _valuation(symbol):
    code = symbol[2:]
    rows = _cached(("valuation", code), 900, lambda: _valuations(f'(SECURITY_CODE="{code}")', 260))
    if not rows:
        return None
    current = _valuation_row(rows[0])
    history = [_valuation_row(row) for row in rows[1:]]
    current["percentiles"] = {}
    for field in ("pe", "pb"):
        valid = [row[field] for row in history if row[field] is not None and row[field] > 0]
        value = current[field]
        if len(valid) >= 60 and value is not None and value > 0:
            rank = sum(item < value for item in valid) + sum(item == value for item in valid) / 2
            current["percentiles"][field] = {"value": rank / len(valid) * 100, "samples": len(valid)}
    cash_market = current["market_cap"]
    current["market_cap"] = cash_market if cash_market and cash_market > 0 else None
    return current


def _profile(symbol):
    rows = _table(
        "RPT_F10_ORG_BASICINFO", f'(SECUCODE="{_identifier(symbol)}")', size=1,
        columns="BOARD_CODE_BK_3LEVEL,BOARD_NAME_3LEVEL,MAIN_BUSINESS",
    )
    return rows[0] if rows else {}


def _peer_rows(profile, kind, code, valuation_date):
    group = "银行" if kind == "bank" else profile.get("BOARD_NAME_3LEVEL")
    symbols = [item for item in PEER_GROUPS.get(group, ()) if item != code]
    board = profile.get("BOARD_CODE_BK_3LEVEL") or ""
    if not symbols and re.fullmatch(r"BK[0-9]+", board):
        matches = _table(
            "RPT_F10_ORG_BASICINFO", f'(BOARD_CODE_BK_3LEVEL="{board}")(SECURITY_TYPE="A股")',
            size=20, sort="LISTING_DATE", columns="SECURITY_CODE",
        )
        symbols = [row["SECURITY_CODE"] for row in matches
                   if re.fullmatch(r"[0-9]{6}", row.get("SECURITY_CODE") or "")
                   and row["SECURITY_CODE"] != code]
    if not symbols or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valuation_date):
        return []
    codes = ",".join(f'"{item}"' for item in symbols)
    rows = _valuations(f"(SECURITY_CODE in ({codes}))(TRADE_DATE='{valuation_date}')", len(symbols))
    indexed = {row["SECURITY_CODE"]: _valuation_row(row) for row in rows}
    return [indexed[item] for item in symbols if item in indexed]


def _peer_roes(peers, period):
    codes = sorted({row["code"] for row in peers if re.fullmatch(r"[0-9]{6}", row["code"] or "")})
    if not codes:
        return {}
    code_filter = ",".join(f'"{code}"' for code in codes)
    rows = _table(
        "RPT_F10_FINANCE_MAINFINADATA",
        f"(SECURITY_CODE in ({code_filter}))(REPORT_DATE='{period}')",
        size=len(codes), columns="SECURITY_CODE,REPORT_DATE,ROEJQ",
    )
    return {row["SECURITY_CODE"]: _number(row.get(RATIOS["roe"])) for row in rows
            if row.get("SECURITY_CODE") in codes and _day(row.get("REPORT_DATE")) == period}


def _business(symbol):
    rows = _get(f"{F10}/BusinessAnalysis/PageAjax", {"code": symbol.upper()}).json().get("zygcfx") or []
    rows = [row for row in rows if str(row.get("MAINOP_TYPE")) == "2" and row.get("ITEM_NAME")]
    latest = max((_day(row.get("REPORT_DATE")) for row in rows), default="")
    previous = f"{int(latest[:4]) - 1}{latest[4:]}" if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", latest) else ""
    prior_rows = {row["ITEM_NAME"]: row for row in rows if _day(row["REPORT_DATE"]) == previous}
    products = []
    for row in rows:
        if _day(row.get("REPORT_DATE")) != latest:
            continue
        name = row["ITEM_NAME"]
        revenue = _number(row.get("MAIN_BUSINESS_INCOME"))
        prior_revenue = _number(prior_rows.get(name, {}).get("MAIN_BUSINESS_INCOME"))
        share = _number(row.get("MBI_RATIO"))
        margin = _number(row.get("GROSS_RPOFIT_RATIO"))
        products.append({
            "name": name, "revenue": revenue,
            "share": share * 100 if share is not None else None,
            "margin": margin * 100 if margin is not None else None,
            "yoy": (revenue / prior_revenue - 1) * 100 if revenue is not None and prior_revenue else None,
            "increase": _delta(revenue, prior_revenue),
        })
    return {"period": latest, "products": sorted(products, key=lambda item: item["revenue"] or 0, reverse=True)[:8]}


def _statement(symbol, statement, periods):
    data = _get(f"{F10}/NewFinanceAnalysis/{statement}AjaxNew", {
        "code": symbol.upper(), "companyType": 4, "reportDateType": 0,
        "reportType": 1, "dates": ",".join(periods),
    }).json()
    return {_day(row.get("REPORT_DATE")): row for row in data.get("data") or []}


def _disclosure(symbol):
    return "https://www.cninfo.com.cn/new/fulltextSearch?" + urlencode({"keyWord": symbol[2:]})


def _notices(symbol, announced):
    code = symbol[2:]
    response = _get("https://np-anotice-stock.eastmoney.com/api/security/ann", {
        "sr": -1, "page_size": 30, "page_index": 1, "ann_type": "A",
        "client_source": "web", "stock_list": code, "f_node": 0, "s_node": 0,
    }).json()
    filings = (response.get("data") or {}).get("list") or []
    report_url = None
    events = []
    basis_notices = []
    for filing in filings:
        ident = filing.get("art_code") or ""
        if not re.fullmatch(r"AN[0-9]+", ident):
            continue
        title = (filing.get("title_ch") or filing.get("title") or "").strip()
        title = re.split(r"[:：]", title, maxsplit=1)[-1].strip()
        date = _day(filing.get("notice_date"))
        url = f"https://data.eastmoney.com/notices/detail/{code}/{ident}.html"
        if not report_url and date == announced and re.search(r"(季度报告|半年度报告|年度报告)(全文)?$", title):
            report_url = url
        if re.search(r"(收购|增购|减值|重大合同|业绩预告|业绩快报|利润分配|监管措施|立案)", title) and "董事会" not in title:
            events.append({"title": title, "date": date, "url": url})
        if re.search(r"会计差错更正|财务报表重述|合并范围变更|同一控制下企业合并", title):
            basis_notices.append({"title": title, "date": date, "url": url})
    return {"report": report_url, "events": events[:3], "basis_notices": basis_notices}


def _stock_analysis(symbol, summary):
    rows = _report_rows(symbol)
    if not rows:
        return {"kind": "unsupported", "observation": "暂无该标的的 A 股公司财报"}
    reports = {_day(row["REPORT_DATE"]): _report(row) for row in reversed(rows) if row.get("REPORT_DATE")}
    if not reports:
        raise FundamentalsUnavailable("财报缺少报告期")
    latest = max(reports)
    current = reports[latest]
    prior = reports.get(f"{int(latest[:4]) - 1}{latest[4:]}", {})
    if prior and not _same_basis(current, prior):
        prior = {"period": prior["period"]}
    kind = "bank" if rows[0].get("ORG_TYPE") == "银行" else "stock"
    findings = _report_findings(current, prior, kind)
    result = {
        "kind": kind, "name": rows[0].get("SECURITY_NAME_ABBR"), "period": latest,
        "observation": findings[0] if findings else (
            _profit_observation(current, prior) or "暂无上年同期利润数据"
        ),
    }
    if summary:
        return result

    jobs = {
        "profile": (_profile, symbol), "valuation": (_valuation, symbol),
        "notices": (_notices, symbol, current["announced"]),
    }
    if kind == "stock":
        jobs.update(
            business=(_business, symbol),
            balance=(_statement, symbol, "zcfzb", [latest, f"{int(latest[:4]) - 1}{latest[4:]}"]),
            cash=(_statement, symbol, "xjllb", [latest]),
        )
    futures = {key: _detail_workers.submit(_optional, *job) for key, job in jobs.items()}
    data = {key: future.result() for key, future in futures.items()}
    profile = data["profile"] or {}
    valuation = data["valuation"]
    if valuation:
        year_end = reports.get(f"{int(latest[:4]) - 1}-12-31", {})
        adjusted = current["adjusted_profit"]
        if not latest.endswith("12-31"):
            previous_tail = (_delta(year_end.get("adjusted_profit"), prior.get("adjusted_profit"))
                             if _same_basis(current, year_end) else None)
            adjusted = adjusted + previous_tail if adjusted is not None and previous_tail is not None else None
        cap = valuation["market_cap"]
        valuation["adjusted_pe"] = (
            cap / adjusted if cap and adjusted and adjusted > 0 and current["currency"] in ("CNY", "人民币")
            and current["announced"] and valuation["date"] > current["announced"] else None
        )
        valuation["peers"] = _optional(_peer_rows, profile, kind, symbol[2:], valuation["date"]) or []
        valuation["roe"] = current["roe"]
        valuation["roe_period"] = latest
        peer_roes = _optional(_peer_roes, valuation["peers"], latest) or {}
        for peer in valuation["peers"]:
            peer["roe"] = peer_roes.get(peer["code"])
        field = "pb" if kind == "bank" else "pe"
        sample = [row[field] for row in valuation["peers"] if row[field] is not None and row[field] > 0]
        valuation["peer_stats"] = {
            "field": field, "count": len(sample),
            "median": median(sample) if len(sample) >= 3 else None,
            "low": min(sample) if len(sample) >= 3 else None,
            "high": max(sample) if len(sample) >= 3 else None,
        }

    balances = data.get("balance") or {}
    balance = balances.get(latest, {})
    start = balances.get(f"{int(latest[:4]) - 1}{latest[4:]}", {})
    cash = (data.get("cash") or {}).get(latest, {})
    notices = data["notices"] or {}
    quarters = _quarters(reports)
    for quarter in quarters:
        baseline = reports.get(f"{int(quarter['period'][:4]) - 1}{quarter['period'][4:]}", {})
        if not _same_basis(reports[quarter["period"]], baseline):
            quarter["prior"] = {}
    basis_notes = []
    if prior and not prior.get("currency"):
        basis_notes.append("本期与上年同期的财报币种不同或缺失，未计算累计同比。")
    if any(row["adjusted_profit"] is None or row["prior"].get("adjusted_profit") is None for row in quarters):
        basis_notes.append("部分单季扣非利润或同比缺少同币种的累计报表或上年同季数据。")
    if notices.get("basis_notices"):
        basis_notes.append("近期公告涉及财报更正、重述或合并口径。请结合公告核对相关报告期的可比性。")
    receivables = _number(balance.get("ACCOUNTS_RECE"))
    start_receivables = _number(start.get("ACCOUNTS_RECE"))
    capex = _number(cash.get("CONSTRUCT_LONG_ASSET"))
    result.update(
        current=current, prior=prior, findings=findings, quarters=quarters, business=data.get("business"),
        basis_notes=basis_notes, basis_notices=notices.get("basis_notices", []),
        industry=profile.get("BOARD_NAME_3LEVEL"), valuation=valuation, events=notices.get("events", []),
        quality={
            "capex": capex, "cash_after_capex": _delta(current["operating_cash"], capex),
            "receivables": receivables,
            "receivables_change": (receivables / start_receivables - 1) * 100
            if receivables is not None and start_receivables else None,
            "nonrecurring": _delta(current["profit"], current["adjusted_profit"]),
        },
        sources={
            "filings": _disclosure(symbol),
            "report": notices.get("report"),
            "financial": f"{F10}/NewFinanceAnalysis/Index?type=web&code={symbol.upper()}",
            "business": f"{F10}/BusinessAnalysis/Index?type=web&code={symbol.upper()}",
            "valuation": f"https://data.eastmoney.com/gzfx/detail/{symbol[2:]}.html",
        },
    )
    return result


def _fund_profile(code):
    response = _get(f"https://fundf10.eastmoney.com/jbgk_{code}.html")
    document = BeautifulSoup(response.content, "html.parser")
    data = {}
    for header in document.find_all("th"):
        value = header.find_next_sibling("td")
        if value:
            data[header.get_text(strip=True)] = value.get_text(" ", strip=True)
    if not data.get("基金简称"):
        raise FundamentalsUnavailable("基金档案缺少基金简称")
    return data


def _fund_holdings(code):
    response = _get(f"https://fund.eastmoney.com/{code}.html")
    document = BeautifulSoup(response.content, "html.parser")
    for table in document.find_all("table"):
        headers = [cell.get_text(strip=True) for cell in table.select("th")]
        if headers[:2] != ["股票名称", "持仓占比"]:
            continue
        period = ""
        for container in list(table.parents)[:5]:
            match = re.search(r"持仓截止日期\s*[:：]\s*(\d{4}-\d{2}-\d{2})", container.get_text(" ", strip=True))
            if match:
                period = match.group(1)
                break
        holdings = []
        for row in table.select("tr"):
            cells = row.select("td")
            if len(cells) < 2:
                continue
            weight = _number(cells[1].get_text(strip=True).removesuffix("%"))
            if weight is not None:
                holdings.append({"name": cells[0].get_text(strip=True), "weight": weight})
        if holdings and period:
            return {"holdings_period": period, "holdings": holdings[:10],
                    "concentration": sum(item["weight"] for item in holdings[:10]) if len(holdings) >= 10 else None}
    return {}


def _index_valuation(name):
    code = CSI_INDEX_CODES.get(name.removesuffix("指数"))
    if not code:
        return None
    import pandas as pd
    from xlrd import XLRDError

    url = f"https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/indicator/{code}indicator.xls"
    raw = _get(url).content
    try:
        frame = pd.read_excel(BytesIO(raw), engine="xlrd")
    except XLRDError as exc:
        raise FundamentalsUnavailable("指数估值文件无法解析") from exc
    if frame.shape[1] != 10:
        raise FundamentalsUnavailable("指数估值文件字段不匹配")
    measurements = []
    for raw_date, *_, pe, _pe2, _yield1, _yield2 in frame.itertuples(index=False, name=None):
        try:
            date = datetime.strptime(str(raw_date), "%Y%m%d").date().isoformat()
        except ValueError:
            continue
        pe = _number(pe)
        if pe is not None and pe > 0:
            measurements.append((date, pe))
    if not measurements:
        return None
    date, pe = max(measurements)
    return {"name": name, "date": date, "pe": pe, "source": url}


def _tracking_performance(code, tracking):
    name = tracking.removesuffix("指数")
    index_code = CSI_INDEX_CODES.get(name)
    if not index_code:
        return None
    url = "https://api.fund.eastmoney.com/pinzhong/LJSYLZS"
    payload = _get(url, {"fundCode": code, "indexcode": index_code, "type": "q"},
                   referer="https://fund.eastmoney.com/").json()
    series = payload.get("Data") or []
    if len(series) < 2:
        return None
    benchmark = next((item for item in series[1:]
                      if str(item.get("name", "")).removesuffix("指数") == name), None)
    if benchmark is None:
        return None
    china_time = timezone(timedelta(hours=8))

    def by_day(points):
        result = {}
        for point in points:
            if not isinstance(point, list) or len(point) < 2:
                continue
            timestamp, value = map(_number, point[:2])
            if timestamp is not None and value is not None and value > -100:
                date = datetime.fromtimestamp(timestamp / 1000, china_time).date().isoformat()
                result[date] = 1 + value / 100
        return result

    fund = by_day(series[0].get("data") or [])
    index = by_day(benchmark.get("data") or [])
    common = sorted(fund.keys() & index.keys())
    if len(common) < 2:
        return None
    start, end = common[0], common[-1]
    fund_return = (fund[end] / fund[start] - 1) * 100
    index_return = (index[end] / index[start] - 1) * 100
    return {"start": start, "end": end, "fund_return": fund_return, "index_return": index_return,
            "difference": fund_return - index_return, "source": f"https://fund.eastmoney.com/{code}.html"}


def _fund_analysis(symbol, summary):
    code = symbol[2:]
    profile = _cached(("fund", code), 1800, lambda: _fund_profile(code))
    tracking = profile.get("跟踪标的", "").strip("- —")
    fund_type = profile.get("基金类型")
    scale = profile.get("净资产规模", "")
    period = re.search(r"(\d{4})年(\d{2})月(\d{2})日", scale)
    result = {
        "kind": "fund", "name": profile["基金简称"],
        "period": "-".join(period.groups()) if period else None,
        "observation": f"跟踪 {tracking}" if tracking else "暂无跟踪标的资料",
    }
    if summary:
        return result
    positions = _detail_workers.submit(_optional, _fund_holdings, code)
    performance = _detail_workers.submit(_optional, _tracking_performance, code, tracking)
    index = _optional(_index_valuation, tracking)
    result.update(
        fund={"tracking": tracking, "fund_type": fund_type, "index_valuation": index,
              "tracking_performance": performance.result(),
              "management_fee": profile.get("管理费率"), "custody_fee": profile.get("托管费率"),
              **(positions.result() or {})},
        sources={
            "filings": _disclosure(symbol),
            "profile": f"https://fundf10.eastmoney.com/jbgk_{code}.html",
            "holdings": f"https://fund.eastmoney.com/{code}.html",
        },
    )
    return result


def analyze(symbol, summary=False):
    kind = instrument_kind(symbol)
    if kind == "unsupported":
        return {"kind": kind, "observation": "该标的暂不支持基本面分析"}
    loader = _fund_analysis if kind == "fund" else _stock_analysis
    try:
        return _cached(("analysis", symbol, summary), 300, lambda: loader(symbol, summary))
    except (requests.RequestException, ValueError, FundamentalsUnavailable) as exc:
        LOG.info("Fundamentals for %s unavailable: %s", symbol, exc)
        raise FundamentalsUnavailable("暂时无法获取基本面数据，请稍后重试") from exc
