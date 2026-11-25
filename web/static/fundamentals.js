(() => {
    const scope = document.getElementById("fundamental-scope");
    const overview = document.getElementById("fundamental-overview");
    const detail = document.getElementById("fundamental-detail");
    const search = document.getElementById("fundamental-search");
    const queryInput = document.getElementById("fundamental-query");
    const matches = document.getElementById("fundamental-matches");
    const labels = {
        revenue: "营业收入", profit: "归母净利润", adjusted_profit: "扣非归母净利润",
        operating_cash: "经营现金流净额", roe: "加权平均 ROE", gross_margin: "毛利率",
        net_interest_margin: "净息差", bad_loan_ratio: "不良贷款率",
        provision_coverage: "拨备覆盖率", core_capital_ratio: "核心一级资本充足率",
    };
    const amountKeys = ["revenue", "profit", "adjusted_profit", "operating_cash"];
    let overviewVersion = 0;
    let detailVersion = 0;
    let searchVersion = 0;
    let selected = "";
    const escape = escHtml;
    const number = (value, suffix = "") => Number.isFinite(value) ? `${value.toFixed(2)}${suffix}` : "—";
    const amount = value => number(Number.isFinite(value) ? value / 1e8 : null);
    const multiple = value => value > 0 ? number(value, " 倍") : "—";
    const signed = (value, suffix) => `${value > 0 ? "+" : ""}${number(value, suffix)}`;
    const period = date => date ? date : "—";
    const symbolKey = (code, market) => `${market.toLowerCase()}:${code}`;

    async function read(url, timeout = 35000) {
        const response = await fetchWithTimeout(url, {}, timeout);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "暂时无法获取数据，请稍后重试");
        return data;
    }

    function analysisUrl(code, market, summary = false) {
        const params = new URLSearchParams({ market });
        if (summary) params.set("view", "summary");
        return `/api/fundamentals/${encodeURIComponent(code)}?${params}`;
    }

    function table(title, columns, rows) {
        return `<div class="fundamental-table-wrap" tabindex="0" role="region" aria-label="${escape(title)}">
            <table class="fundamental-table">
            <thead><tr>${columns.map(column => `<th scope="col">${escape(column)}</th>`).join("")}</tr></thead>
            <tbody>${rows.map(row => `<tr>${row.map((value, i) =>
                i === 0 ? `<th scope="row">${value}</th>` : `<td>${value}</td>`).join("")}</tr>`).join("")}</tbody>
            </table></div>`;
    }

    function panel(title, content) {
        return `<section class="card"><h3>${escape(title)}</h3>${content}</section>`;
    }

    function meta(text) {
        return `<p class="fundamental-meta">${escape(text)}</p>`;
    }

    function sourceLinks(entries) {
        return `<p class="fundamental-sources fundamental-meta">${entries.filter(([, url]) => url)
            .map(([label, url]) => `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(label)}</a>`)
            .join("")}</p>`;
    }

    function assetButton(item) {
        const code = safeSecurityCode(item.code);
        const market = safeMarket(item.market);
        const current = symbolKey(code, market) === selected;
        return `<button type="button" class="fundamental-ticker" data-code="${code}" data-market="${market}" aria-current="${current}">${escape(item.name || code)} <small>${market.toUpperCase()}${code}</small></button>`;
    }

    function markSelected() {
        for (const button of [overview, matches].flatMap(node => [...node.querySelectorAll("[data-code]")])) {
            button.setAttribute("aria-current", String(symbolKey(button.dataset.code, button.dataset.market) === selected));
        }
    }

    window.loadFundamentalOverview = async function () {
        const version = ++overviewVersion;
        const category = scope.value;
        overview.innerHTML = meta("正在读取标的");
        try {
            const data = await read("/api/fundamentals");
            if (version !== overviewVersion) return;
            const assets = data.items.filter(item => item[category]);
            if (!assets.length) {
                overview.innerHTML = meta(category === "held" ? "暂无持仓，可按代码或简称查询。" : "暂无自选，可按代码或简称查询。");
                return;
            }
            overview.innerHTML = table("标的基本面概览", ["标的", "报告期", "主要变化"],
                assets.map(item => [assetButton(item), "—", '<span class="fundamental-note">正在查询</span>']));
            const rows = [...overview.querySelectorAll("tbody tr")];
            let next = 0;
            async function worker() {
                while (version === overviewVersion && next < assets.length) {
                    const index = next++;
                    const item = assets[index];
                    const cells = rows[index].querySelectorAll("td");
                    try {
                        const result = await read(analysisUrl(item.code, item.market, true));
                        cells[0].textContent = period(result.period);
                        cells[1].textContent = result.observation;
                        const button = rows[index].querySelector("button");
                        if (result.name) button.firstChild.textContent = `${result.name} `;
                    } catch {
                        cells[1].textContent = "暂时无法获取，点击标的重试";
                    }
                }
            }
            await Promise.all(Array.from({ length: Math.min(3, assets.length) }, worker));
        } catch (error) {
            if (version === overviewVersion) overview.innerHTML = meta(error.message);
        }
    };

    function comparison(key, current, previous) {
        if (!Number.isFinite(current) || !Number.isFinite(previous)) return "—";
        if (!amountKeys.includes(key)) return signed(current - previous, " 个百分点");
        const isProfit = key === "profit" || key === "adjusted_profit";
        if (current > 0 && previous < 0) return isProfit ? "扭亏" : "由负转正";
        if (current < 0 && previous > 0) return isProfit ? "转亏" : "转负";
        if (previous <= 0 || (isProfit && previous < Math.abs(current - previous))) {
            return signed((current - previous) / 1e8, " 亿");
        }
        return signed((current / previous - 1) * 100, "%");
    }

    function reportCards(data) {
        const { current, prior, quarters, sources, quality, business } = data;
        const bank = data.kind === "bank";
        const keys = bank
            ? ["revenue", "profit", "adjusted_profit", "roe", "net_interest_margin", "bad_loan_ratio", "provision_coverage", "core_capital_ratio"]
            : [...amountKeys, "roe", "gross_margin"];
        const currency = current.currency === "CNY" ? "人民币亿元" : `亿 ${current.currency || "（财报币种）"}`;
        const financials = table("最新财报与同期对比", ["指标", current.period, prior.period || "上年同期", "同比变化"],
            keys.map(key => {
                const format = amountKeys.includes(key) ? amount : value => number(value, "%");
                return [labels[key], format(current[key]), format(prior[key]), comparison(key, current[key], prior[key])];
            }));
        const trendKeys = bank ? amountKeys.slice(0, 3) : amountKeys;
        const trends = table("近四季走势", ["单季", ...trendKeys.map(key => labels[key]), "扣非净利润同比"],
            quarters.map(row => [`${row.period.slice(0, 4)} Q${Number(row.period.slice(5, 7)) / 3}`,
                 ...trendKeys.map(key => amount(row[key])),
                 comparison("adjusted_profit", row.adjusted_profit, row.prior?.adjusted_profit)]));
        const date = current.announced ? ` · 公告日 ${current.announced}` : "";
        const header = `<p class="fundamental-observation"><strong>${escape(data.observation)}</strong></p>
            ${meta(`报告期 ${current.period}${date}${data.industry ? ` · ${data.industry}` : ""}`)}`;
        const reports = panel("财报与同比", header + financials + meta(`金额单位为${currency}。`)
            + (data.basis_notes || []).map(meta).join("")
            + sourceLinks([["本期财报原文", sources.report], ["公司公告 · 巨潮资讯", sources.filings],
                ["财务数据 · 东方财富", sources.financial],
                ...(data.basis_notices || []).map(item => [item.title, item.url])]));
        const quarterCard = panel("近四季走势", trends + meta(`金额单位为${currency}。部分单季值由累计值相减。`));
        const products = business?.products?.length ? panel("主营业务",
            meta(`分产品数据截至 ${business.period}。金额单位为${currency}。`)
            + table("主营业务构成", ["产品", "收入", "收入占比", "收入同比", "毛利率"],
                business.products.map(item => [escape(item.name), amount(item.revenue), number(item.share, "%"),
                    Number.isFinite(item.yoy) ? signed(item.yoy, "%") : "—", number(item.margin, "%")]))
            + sourceLinks([["主营业务数据 · 东方财富", sources.business]]))
            : bank ? "" : panel("主营业务", meta("暂无可用的分产品数据。")
                + sourceLinks([["主营业务数据 · 东方财富", sources.business]]));
        const cash = bank ? "" : panel("盈利质量",
            table("盈利质量指标", ["指标", "本期"], [
                ["非经常性损益净额", amount(quality.nonrecurring)],
                ["购建长期资产支出", amount(quality.capex)],
                ["经营现金流净额减购建长期资产支出", amount(quality.cash_after_capex)],
                ["期末应收账款", amount(quality.receivables)],
                ["应收账款同比", Number.isFinite(quality.receivables_change) ? signed(quality.receivables_change, "%") : "—"],
            ]) + meta(`金额单位为${currency}。`));
        return reports + quarterCard + `<div class="fundamental-grid">${products}${cash}</div>`;
    }

    function valuationCard(data) {
        const valuation = data.valuation;
        if (!valuation) return panel("估值与同行", meta("暂时无法获取收盘估值。"));
        const peers = valuation.peers;
        const companies = [{ ...valuation, name: data.name }, ...peers];
        const rows = companies.map(row => [escape(`${row.name || ""} ${row.code}`), number(row.price, " 元"),
            row.pe < 0 ? "亏损" : multiple(row.pe), multiple(row.pb), number(row.roe, "%")]);
        const roeHeading = valuation.roe_period ? `加权 ROE（截至 ${valuation.roe_period}）` : "加权 ROE";
        const rankings = Object.entries(valuation.percentiles).map(([key, entry]) =>
            `${key === "pe" ? "PE" : "PB"} ${number(entry.value, "%")}（${entry.samples} 个交易日）`);
        const ranks = rankings.length
            ? `近 260 个交易日内的历史分位（仅用对应指标为正的历史样本）${rankings.join("、")}`
            : "有效历史样本不足，暂缺估值分位。";
        const cap = valuation.market_cap ? ` · 总市值 ${amount(valuation.market_cap)} 亿元` : "";
        const stats = valuation.peer_stats;
        const sample = stats ? `所列同行有效 ${stats.field === "pb" ? "PB" : "PE"} 样本 ${stats.count} 家` : "";
        const peerRange = stats?.median != null
            ? `${sample} · 中位数 ${multiple(stats.median)} · 区间 ${multiple(stats.low)}–${multiple(stats.high)}`
            : sample;
        return panel("估值与同行", meta(`${valuation.date} 收盘${cap}${data.industry ? ` · ${data.industry}` : ""}`)
            + table("同日估值对比", ["标的", "收盘价", "PE（TTM）", "PB", roeHeading], rows)
            + (valuation.adjusted_pe ? meta(`按最近四季扣非归母净利润计算，滚动 PE 为 ${multiple(valuation.adjusted_pe)}。`) : "")
            + meta(ranks) + meta(peers.length ? "同行基于业务相近或同一细分行业选取。" : "当前没有可用的同日同行估值。")
            + (peerRange ? meta(peerRange) : "")
            + sourceLinks([["收盘估值 · 东方财富", data.sources.valuation]]));
    }

    function reportAnalysisCard(data) {
        const { current, prior, quality, quarters, business } = data;
        const findings = [...data.findings];
        const last = quarters.at(-1);
        if (last?.adjusted_profit != null && last.prior?.adjusted_profit != null
            && last.adjusted_profit !== last.prior.adjusted_profit) {
            const now = last.adjusted_profit;
            const before = last.prior.adjusted_profit;
            const change = before < 0 && now > 0 ? "同比扭亏"
                : before >= 0 && now < 0 ? "同比转亏"
                : now > before ? "同比增加" : "同比减少";
            const currency = current.currency === "CNY" ? "元" : ` ${current.currency}`;
            const priorTwo = quarters.slice(-3, -1);
            const quarterIndex = row => Number(row.period.slice(0, 4)) * 4 + Number(row.period.slice(5, 7)) / 3;
            let trend = "";
            if (priorTwo.length === 2 && priorTwo.every(row => Number.isFinite(row.adjusted_profit))
                && quarterIndex(last) - quarterIndex(priorTwo[0]) === 2
                && quarterIndex(last) - quarterIndex(priorTwo[1]) === 1
                && priorTwo.every(row => row.currency === last.currency)) {
                const [earlier, recent] = priorTwo.map(row => row.adjusted_profit);
                if ((now < before && earlier < recent && recent < now)
                    || (now > before && earlier > recent && recent > now)) {
                    trend = `近三季依次为 ${amount(earlier)}、${amount(recent)}、${amount(now)} 亿${currency}。`;
                }
            }
            findings.push(`本季扣非归母净利润${change}，由上年同季的 ${amount(before)} 亿${currency}变为 ${amount(now)} 亿${currency}。${trend}`);
        }
        const products = business?.products?.filter(item => item.increase > 0)
            .sort((a, b) => b.increase - a.increase) || [];
        if (products.length) {
            const named = products.slice(0, 2).map(item => Number.isFinite(item.yoy)
                ? `${item.name}（收入同比 ${signed(item.yoy, "%")}）` : item.name);
            findings.push(`${named.join("、")}是 ${business.period} 已披露产品中收入增量较大的项目。`);
        }
        if (data.kind === "stock" && current.operating_cash != null
            && prior.operating_cash != null && current.operating_cash < prior.operating_cash
            && quality.receivables_change > 0) {
            findings.push(`累计经营现金流净额同比减少，同期应收账款增加 ${signed(quality.receivables_change, "%")}。`);
        }
        const observations = findings.length
            ? panel("本期财报解读", `<ul class="fundamental-notes">${findings.map(item => `<li>${escape(item)}</li>`).join("")}</ul>`)
            : "";
        const events = data.events?.length
            ? panel("近期相关公告", data.events.map(event => sourceLinks([[`${event.date} · ${event.title}`, event.url]])).join(""))
            : "";
        return observations + events;
    }

    function fundCards(data) {
        const fund = data.fund;
        const positions = fund.holdings || [];
        const index = fund.index_valuation;
        const tracking = fund.tracking_performance;
        const summary = [fund.tracking ? `跟踪标的 ${fund.tracking}` : "", fund.fund_type]
            .filter(Boolean).join(" · ");
        return panel("基金与跟踪标的", meta(summary || "暂无跟踪标的资料。")
            + (fund.management_fee ? meta(`管理费率 ${fund.management_fee}`) : "")
            + (fund.custody_fee ? meta(`托管费率 ${fund.custody_fee}`) : "")
            + sourceLinks([["基金公告 · 巨潮资讯", data.sources.filings], ["基金资料 · 天天基金", data.sources.profile]]))
            + (fund.tracking ? panel("跟踪表现", tracking
                ? meta(`${tracking.start} 至 ${tracking.end}，基金收益 ${signed(tracking.fund_return, "%")}，跟踪指数收益 ${signed(tracking.index_return, "%")}，相差 ${signed(tracking.difference, " 个百分点")}。`)
                    + sourceLinks([["基金与指数收益走势 · 天天基金", tracking.source]])
                : meta("暂无可核验的同区间基金与跟踪指数收益。")) : "")
            + panel("披露持仓", positions.length
                ? meta(`持仓截至 ${fund.holdings_period}${fund.concentration != null ? ` · 前十大持仓合计 ${number(fund.concentration, "%")}` : ""}`)
                    + table("主要持仓", ["证券", "占基金净值"], positions.map(row => [escape(row.name), number(row.weight, "%")]))
                    + sourceLinks([["持仓数据 · 天天基金", data.sources.holdings]])
                : meta("暂时无法获取带日期的披露持仓。"))
            + panel("跟踪指数估值", index
                ? meta(`${index.date} · ${index.name} · 市盈率（中证口径 1）${multiple(index.pe)}`)
                    + sourceLinks([["指数估值 · 指数编制机构", index.source]])
                : meta("暂无可核验的指数估值。"));
    }

    window.openFundamental = async function (code, market = "", name = "") {
        ++searchVersion;
        const version = ++detailVersion;
        selected = symbolKey(code, market);
        showTab(6);
        markSelected();
        detail.innerHTML = panel("基本面详情", meta(`正在加载 ${name || code} 的数据`));
        try {
            const data = await read(analysisUrl(code, market), 50000);
            if (version !== detailVersion) return;
            selected = symbolKey(code, data.market);
            markSelected();
            const heading = `${data.name || name || code} · ${data.market.toUpperCase()}${code}`;
            if (data.kind === "unsupported") {
                detail.innerHTML = panel(heading, meta(data.observation));
                return;
            }
            const content = data.kind === "fund" ? fundCards(data)
                : reportCards(data) + valuationCard(data) + reportAnalysisCard(data);
            detail.innerHTML = `<h2 class="fundamental-observation">${escape(heading)}</h2>${content}`;
        } catch (error) {
            if (version !== detailVersion) return;
            detail.innerHTML = panel("基本面详情", meta(error.message)
                + '<button type="button" class="quick-btn">重试</button>');
            detail.querySelector("button").onclick = () => openFundamental(code, market, name);
        }
    };

    scope.addEventListener("change", () => loadFundamentalOverview());
    for (const container of [overview, matches]) {
        container.addEventListener("click", event => {
            const button = event.target.closest("button[data-code]");
            if (button) {
                openFundamental(button.dataset.code, button.dataset.market);
                detail.focus();
            }
        });
    }
    search.addEventListener("submit", async event => {
        event.preventDefault();
        const query = queryInput.value.trim();
        const version = ++searchVersion;
        if (!query) return;
        const code = /^(?:(sh|sz|bj|hk)[.:]?)?(\d{5,6})(?:[.:](sh|sz|bj|hk))?$/i.exec(query);
        if (code) {
            matches.textContent = "";
            openFundamental(code[2], (code[1] || code[3] || "").toLowerCase());
            detail.focus();
            return;
        }
        matches.innerHTML = meta("正在查询证券");
        try {
            const data = await read(`/api/stock/search?q=${encodeURIComponent(query)}`);
            if (version !== searchVersion) return;
            const options = data.results.filter(item => item.type !== "ZS" && item.type !== "GP-B" && safeMarket(item.market) !== "hk");
            if (options.length === 1) {
                matches.textContent = "";
                openFundamental(options[0].code, safeMarket(options[0].market), options[0].name);
                detail.focus();
            } else {
                matches.innerHTML = options.length ? `<div class="fundamental-matches">${options.map(assetButton).join("")}</div>`
                    : meta("未找到支持的证券，请试试证券代码。");
            }
        } catch (error) {
            if (version === searchVersion) matches.innerHTML = meta(error.message);
        }
    });
})();
