// 全局变量
let cryptoData = [];
let sortConfig = {
    column: 'name',
    direction: 'asc'
};
let refreshInterval = null;
let isLoading = false;
let announcements = [];
let depositWithdrawInfo = {};
let arbitrageOpportunities = [];

// 交易所配置
const exchanges = ['binance', 'okx', 'mexc', 'gate', 'kucoin', 'bitget', 'bybit', 'htx'];
const exchangeNames = {
    'binance': 'Binance',
    'okx': 'OKX', 
    'mexc': 'MEXC',
    'gate': 'Gate',
    'kucoin': 'Kucoin',
    'bitget': 'Bitget',
    'bybit': 'Bybit',
    'htx': 'HTX'
};

// 模拟的交易所链信息
// 链ID: 1:ERC20, 2:TRC20, 3:BSC, 4:SOL, 5:BTC, 6:BTC-Lightning
const chainIdToName = { 1: 'ERC20', 2: 'TRC20', 3: 'BSC', 4: 'SOL', 5: 'BTC', 6: 'LN' };
const exchangeChainInfo = {
    'USDT': {
        'binance': { deposit: [1, 2, 3, 4], withdraw: [1, 2, 3, 4] },
        'okx':     { deposit: [1, 2, 3, 4], withdraw: [1, 2, 3, 4] },
        'gate':    { deposit: [1, 2, 3],    withdraw: [1, 2, 4] }, // Incompatible
        'bybit':   { deposit: [1, 2, 4],    withdraw: [1, 4] },
        'kucoin':  { deposit: [1, 2],       withdraw: [1, 2] },
        'mexc':    { deposit: [1, 2, 3],    withdraw: [1, 2, 3] },
        'htx':     { deposit: [1, 2, 3],    withdraw: [1, 2, 3] },
        'bitget':  { deposit: [1, 2, 4],    withdraw: [1, 2, 4] },
    },
    'ETH': {
        'binance': { deposit: [1, 3], withdraw: [1, 3] },
        'okx':     { deposit: [1, 3], withdraw: [1, 3] },
        'gate':    { deposit: [1],    withdraw: [3] },      // Incompatible
        'bybit':   { deposit: [1],    withdraw: [1] },
        'kucoin':  { deposit: [1],    withdraw: [1] },
        'mexc':    { deposit: [1, 3], withdraw: [1, 3] },
        'htx':     { deposit: [1, 3], withdraw: [1, 3] },
        'bitget':  { deposit: [1, 3], withdraw: [1, 3] },
    },
    'BTC': {
        'binance': { deposit: [5, 6], withdraw: [5, 6] },
        'okx':     { deposit: [5],    withdraw: [5, 6] },   // Partially incompatible
        'gate':    { deposit: [5],    withdraw: [5] },
        'bybit':   { deposit: [5],    withdraw: [5] },
        'kucoin':  { deposit: [5],    withdraw: [5] },
        'mexc':    { deposit: [5],    withdraw: [5] },
        'htx':     { deposit: [5],    withdraw: [5] },
        'bitget':  { deposit: [5],    withdraw: [5] },
    }
};

// 中文名称映射表
const chineseNameMap = {
    "btc": "比特币",
    "eth": "以太坊",
    "usdt": "泰达币",
    "bnb": "币安币",
    "sol": "索拉纳",
    "xrp": "瑞波币",
    "usdc": "美元币",
    "ada": "卡尔达诺",
    "doge": "狗狗币",
    "avax": "雪崩",
    "shib": "柴犬币",
    "dot": "波卡",
    "link": "链接",
    "trx": "波场",
    "bch": "比特币现金",
    "near": "近似协议",
    "ltc": "莱特币",
    "matic": "多边形",
    "atom": "宇宙",
    "etc": "以太坊经典",
    "xlm": "恒星币",
    "xmr": "门罗币",
    "fil": "文件币",
    "cro": "Cronos",
    "wbtc": "包装比特币",
    "algo": "阿尔格兰德",
    "vet": "唯链",
    "icp": "互联网计算机",
    "sand": "沙盒",
    "gala": "Gala",
    "axs": "Axie Infinity",
    "mana": "Decentraland",
    "kcs": "KuCoin Token",
    "ftt": "FTX Token",
    "egld": "MultiversX",
    "hnt": "Helium",
    "xtz": "Tezos",
    "grt": "The Graph",
    "mkr": "Maker",
    "aave": "Aave",
    "comp": "Compound",
    "snx": "Synthetix",
    "crv": "Curve DAO",
    "uni": "Uniswap",
    "sushi": "SushiSwap",
    "cake": "PancakeSwap",
    "1inch": "1inch",
    "gno": "灵知"
};


// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', () => {
    // 初始化事件监听器
    initEventListeners();
    
    // 初始化功能面板
    initFeaturePanels();
    
    // 请求通知权限
    requestNotificationPermission();
    
    // 首次加载数据
    fetchData();
    
    // 获取公告信息
    fetchAnnouncements();
    
    // 获取充提信息
    fetchDepositWithdrawInfo();
    
    // 默认设置30秒自动刷新
    setAutoRefresh(30);
});

// 请求通知权限
function requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission().then(permission => {
            if (permission === 'granted') {
                console.log('通知权限已获取');
            }
        });
    }
}

// 初始化所有事件监听器
function initEventListeners() {
    // 刷新按钮点击事件
    document.getElementById('refresh-btn').addEventListener('click', () => {
        fetchData();
    });
    
    // 自动刷新选择事件
    document.getElementById('auto-refresh').addEventListener('change', (e) => {
        const seconds = parseFloat(e.target.value);
        setAutoRefresh(seconds);
    });
    
    // 搜索功能
    document.getElementById('search-btn').addEventListener('click', filterData);
    document.getElementById('search-input').addEventListener('keyup', (e) => {
        if (e.key === 'Enter') {
            filterData();
        }
    });
    
    // 表头排序点击事件
    document.querySelectorAll('th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const column = th.getAttribute('data-sort');
            sortData(column);
        });
    });
}

// 初始化功能面板
function initFeaturePanels() {
    // 套利机会按钮
    document.getElementById('arbitrage-btn').addEventListener('click', () => {
        togglePanel('arbitrage-panel', 'arbitrage-btn');
    });
    
    // 公告监控按钮
    document.getElementById('announcements-btn').addEventListener('click', () => {
        togglePanel('announcements-panel', 'announcements-btn');
    });
    
    // 充提信息按钮
    document.getElementById('deposit-withdraw-btn').addEventListener('click', () => {
        togglePanel('deposit-withdraw-panel', 'deposit-withdraw-btn');
    });
}

// 切换面板显示
function togglePanel(panelId, buttonId) {
    const panel = document.getElementById(panelId);
    const button = document.getElementById(buttonId);
    
    if (panel.style.display === 'none') {
        // 隐藏所有面板
        document.querySelectorAll('.feature-panel').forEach(p => p.style.display = 'none');
        document.querySelectorAll('.feature-btn').forEach(b => b.classList.remove('active'));
        
        // 显示当前面板
        panel.style.display = 'block';
        button.classList.add('active');
        
        // 更新面板内容
        updatePanelContent(panelId);
    } else {
        panel.style.display = 'none';
        button.classList.remove('active');
    }
}

// 更新面板内容
function updatePanelContent(panelId) {
    switch(panelId) {
        case 'arbitrage-panel':
            updateArbitragePanel();
            break;
        case 'announcements-panel':
            updateAnnouncementsPanel();
            break;
        case 'deposit-withdraw-panel':
            updateDepositWithdrawPanel();
            break;
    }
}

// 设置自动刷新
function setAutoRefresh(seconds) {
    // 清除现有的刷新间隔
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
    
    // 如果选择了自动刷新，设置新的间隔
    if (seconds > 0) {
        // 将字符串转换为数字
        const interval = parseFloat(seconds) * 1000;
        refreshInterval = setInterval(() => {
            fetchData();
        }, interval);
    }
}

// 从CoinGecko API获取数据并结合中文名称
async function fetchData() {
    if (isLoading) return;
    
    isLoading = true;
    showLoading(true);
    hideError();
    
    try {
        const response = await fetch('https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=150&page=1&sparkline=false');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const apiData = await response.json();
        
        // 使用API返回的数据作为基础，保证所有显示的货币都有价格
        cryptoData = apiData.map(crypto => {
            const symbolLower = crypto.symbol.toLowerCase();
            const basePrice = crypto.current_price;

            // 检查是否有中文名称，否则使用API提供的英文名称
            const name = chineseNameMap[symbolLower] || crypto.name;

            const variation = () => (Math.random() - 0.5) * basePrice * 0.02; // 最大±1%的差异
            const spreadVariation = () => basePrice * 0.001 * (Math.random() + 0.5); // 买卖价差

            const cryptoItem = {
                name: name,
                symbol: crypto.symbol.toUpperCase(),
                market_cap: crypto.market_cap,
                volume_24h: crypto.total_volume
            };

            // 为每个交易所生成买入价和卖出价
            exchanges.forEach(exchange => {
                const midPrice = basePrice + variation();
                const spread = spreadVariation();
                cryptoItem[exchange] = {
                    bid: midPrice - spread/2,  // 买入价
                    ask: midPrice + spread/2,  // 卖出价
                    mid: midPrice              // 中间价
                };
            });

            return cryptoItem;
        });
        
        // 计算套利机会
        calculateArbitrageOpportunities();
        
        // 更新表格
        updateTable();
        
        // 更新最后更新时间
        updateLastUpdateTime();
    } catch (error) {
        console.error('获取数据失败:', error);
        showError('获取价格数据失败，请稍后再试');
    } finally {
        isLoading = false;
        showLoading(false);
    }
}

// 更新表格数据
function updateTable() {
    const tableBody = document.getElementById('price-data');
    const searchInput = document.getElementById('search-input');
    const searchTerm = searchInput.value.trim().toLowerCase();
    
    // 过滤数据
    let filteredData = cryptoData;
    if (searchTerm) {
        filteredData = cryptoData.filter(crypto => 
            crypto.name.toLowerCase().includes(searchTerm) ||
            crypto.symbol.toLowerCase().includes(searchTerm)
        );
    }
    
    // 排序数据
    filteredData = sortDataByConfig(filteredData);
    
    // 清空表格
    tableBody.innerHTML = '';
    
    // 如果没有数据
    if (filteredData.length === 0) {
        const row = document.createElement('tr');
        row.innerHTML = `<td colspan="14" style="text-align: center;">没有找到匹配的数据</td>`;
        tableBody.appendChild(row);
        return;
    }
    
    // 填充表格
    filteredData.forEach(crypto => {
        const row = document.createElement('tr');
        
        // 计算最高和最低价格（使用中间价）
        const prices = exchanges.map(exchange => crypto[exchange] ? crypto[exchange].mid : null).filter(price => price !== null && isFinite(price));
        
        const maxPrice = prices.length > 0 ? Math.max(...prices) : 0;
        const minPrice = prices.length > 0 ? Math.min(...prices) : 0;
        const spread = maxPrice - minPrice;
        const spreadPercentage = (minPrice > 0) ? ((spread / minPrice) * 100).toFixed(2) : "0.00";
        
        // 计算套利机会
        const arbitrageInfo = calculateCryptoArbitrage(crypto);

        // 获取链信息
        let withdrawChains = [];
        let depositChains = [];
        let compatibleChains = [];
        if (arbitrageInfo) {
            const coinSymbol = crypto.symbol.split('/')[0]; // e.g., 'BTC' from 'BTC/USDT'
            const buyEx = arbitrageInfo.buyExchange.toLowerCase();
            const sellEx = arbitrageInfo.sellExchange.toLowerCase();

            const coinChainInfo = exchangeChainInfo[coinSymbol];
            if (coinChainInfo) {
                withdrawChains = coinChainInfo[buyEx] ? coinChainInfo[buyEx].withdraw : [];
                depositChains = coinChainInfo[sellEx] ? coinChainInfo[sellEx].deposit : [];
                if(withdrawChains && depositChains) {
                    compatibleChains = withdrawChains.filter(c => depositChains.includes(c));
                }
            }
        }
        
        // 创建单元格并添加高亮
        row.innerHTML = `
            <td>
                <div style="font-weight: bold;">${crypto.name}</div>
                <div style="color: #7f8c8d; font-size: 0.8rem;">${crypto.symbol}</div>
            </td>
            ${createBidAskCell(crypto.binance, maxPrice, minPrice)}
            ${createBidAskCell(crypto.okx, maxPrice, minPrice)}
            ${createBidAskCell(crypto.mexc, maxPrice, minPrice)}
            ${createBidAskCell(crypto.gate, maxPrice, minPrice)}
            ${createBidAskCell(crypto.kucoin, maxPrice, minPrice)}
            ${createBidAskCell(crypto.bitget, maxPrice, minPrice)}
            ${createBidAskCell(crypto.bybit, maxPrice, minPrice)}
            ${createBidAskCell(crypto.htx, maxPrice, minPrice)}
            <td class="price-spread">${spread > 0 ? spread.toFixed(6) : '0.00'} (${spreadPercentage}%)</td>
            ${createChainCell(withdrawChains)}
            ${createChainCell(depositChains)}
            ${createChainCompatibilityCell(compatibleChains)}
            ${createArbitrageCell(arbitrageInfo)}
        `;
        
        tableBody.appendChild(row);
    });
}

// 创建链信息单元格
function createChainCell(chains) {
    if (!chains || chains.length === 0) return '<td>-</td>';
    const html = chains.map(chainId => {
        const name = chainIdToName[chainId] || 'Unknown';
        return `<span class="chain-badge chain-${name.toLowerCase()}">${name}</span>`;
    }).join(' ');
    return `<td>${html}</td>`;
}

// 创建链兼容性单元格
function createChainCompatibilityCell(compatibleChains) {
    if (!compatibleChains) return '<td>-</td>';
    if (compatibleChains.length > 0) {
        return `<td class="chain-compatible-yes"><i class="fas fa-check-circle"></i> 是</td>`;
    } else {
        return `<td class="chain-compatible-no"><i class="fas fa-times-circle"></i> 否</td>`;
    }
}

// 创建买卖价格单元格HTML
function createBidAskCell(priceData, maxPrice, minPrice) {
    if (!priceData || !priceData.bid || !priceData.ask) {
        return '<td>-</td>';
    }
    
    let className = '';
    const midPrice = priceData.mid;
    
    if (midPrice === maxPrice) {
        className = 'price-highest';
    } else if (midPrice === minPrice) {
        className = 'price-lowest';
    }
    
    return `<td class="${className}">
        <div class="bid-ask-prices">
            <div class="bid-price">买: ${priceData.bid.toFixed(6)}</div>
            <div class="ask-price">卖: ${priceData.ask.toFixed(6)}</div>
        </div>
    </td>`;
}

// 创建套利机会单元格
function createArbitrageCell(arbitrageInfo) {
    if (!arbitrageInfo || arbitrageInfo.profit <= 0) {
        return '<td class="arbitrage-cell">-</td>';
    }

    const profitPercentage = arbitrageInfo.profitPercentage.toFixed(2);
    let className = 'arbitrage-cell';

    if (arbitrageInfo.profitPercentage > 2) {
        className += ' high-opportunity';
    } else if (arbitrageInfo.profitPercentage > 0.5) {
        className += ' opportunity';
    }

    const buyExName = exchangeNames[arbitrageInfo.buyExchange] || arbitrageInfo.buyExchange;
    const sellExName = exchangeNames[arbitrageInfo.sellExchange] || arbitrageInfo.sellExchange;

    const tooltipText = `买入: ${buyExName} @ ${arbitrageInfo.buyPrice.toFixed(6)}<br>卖出: ${sellExName} @ ${arbitrageInfo.sellPrice.toFixed(6)}<br>利润: $${arbitrageInfo.profit.toFixed(6)}`;

    return `<td class="${className} tooltip">
        <div>${profitPercentage}%</div>
        <small>${buyExName} → ${sellExName}</small>
        <span class="tooltiptext">${tooltipText}</span>
    </td>`;
}

// 计算单个货币的套利机会
function calculateCryptoArbitrage(crypto) {
    let bestBuy = null;
    let bestSell = null;
    let maxProfit = -Infinity;

    // 找到最低买入价和最高卖出价
    exchanges.forEach(buyExchange => {
        exchanges.forEach(sellExchange => {
            if (buyExchange !== sellExchange && crypto[buyExchange] && crypto[sellExchange]) {
                const buyPrice = crypto[buyExchange].ask; // 在买入交易所的卖出价
                const sellPrice = crypto[sellExchange].bid; // 在卖出交易所的买入价
                const profit = sellPrice - buyPrice;
                
                if (profit > maxProfit) {
                    maxProfit = profit;
                    bestBuy = buyExchange;
                    bestSell = sellExchange;
                }
            }
        });
    });
    
    if (maxProfit > 0 && bestBuy && bestSell) {
        const buyPrice = crypto[bestBuy].ask;
        const profitPercentage = (maxProfit / buyPrice) * 100;
        
        return {
            profit: maxProfit,
            profitPercentage: profitPercentage,
            buyExchange: bestBuy,
            sellExchange: bestSell,
            buyPrice: buyPrice,
            sellPrice: crypto[bestSell].bid
        };
    }
    
    return null;
}

// 计算所有套利机会
function calculateArbitrageOpportunities() {
    arbitrageOpportunities = [];
    
    cryptoData.forEach(crypto => {
        const arbitrageInfo = calculateCryptoArbitrage(crypto);
        if (arbitrageInfo && arbitrageInfo.profitPercentage > 0.1) { // 只显示利润超过0.1%的机会
            arbitrageOpportunities.push({
                symbol: crypto.symbol,
                name: crypto.name,
                volume_24h: crypto.volume_24h,
                ...arbitrageInfo
            });
        }
    });
    
    // 按利润率排序
    arbitrageOpportunities.sort((a, b) => b.profitPercentage - a.profitPercentage);
}

// 创建价格单元格HTML，添加高亮（保留原函数用于兼容）
function createPriceCell(price, maxPrice, minPrice) {
    if (price === null || !isFinite(price)) {
        return '<td>-</td>';
    }
    
    let className = '';
    if (price === maxPrice && maxPrice !== minPrice) {
        className = 'price-high';
    } else if (price === minPrice && maxPrice !== minPrice) {
        className = 'price-low';
    }
    
    return `<td class="${className}">${parseFloat(price).toFixed(6)}</td>`;
}

// 根据搜索框过滤数据
function filterData() {
    updateTable();
}

// 排序数据
function sortData(column) {
    // 如果点击的是当前排序列，则切换排序方向
    if (sortConfig.column === column) {
        sortConfig.direction = sortConfig.direction === 'asc' ? 'desc' : 'asc';
    } else {
        sortConfig.column = column;
        sortConfig.direction = 'asc';
    }
    
    // 更新表头样式
    updateSortIndicators();
    
    // 更新表格
    updateTable();
}

// 根据当前排序配置排序数据
function sortDataByConfig(data) {
    return [...data].sort((a, b) => {
        let valueA, valueB;

        if (sortConfig.column === 'name') {
            valueA = a.name;
            valueB = b.name;
        } else if (sortConfig.column === 'spread') {
            const getMidPrice = (crypto, exchange) => crypto[exchange] ? crypto[exchange].mid : null;

            const pricesA = exchanges
                .map(ex => getMidPrice(a, ex))
                .filter(price => price !== null && isFinite(price));

            const pricesB = exchanges
                .map(ex => getMidPrice(b, ex))
                .filter(price => price !== null && isFinite(price));

            valueA = pricesA.length > 1 ? Math.max(...pricesA) - Math.min(...pricesA) : 0;
            valueB = pricesB.length > 1 ? Math.max(...pricesB) - Math.min(...pricesB) : 0;
        } else {
            // 对于交易所价格列
            const priceA = a[sortConfig.column] ? a[sortConfig.column].mid : null;
            const priceB = b[sortConfig.column] ? b[sortConfig.column].mid : null;

            valueA = priceA === null || !isFinite(priceA) ? -Infinity : priceA;
            valueB = priceB === null || !isFinite(priceB) ? -Infinity : priceB;
        }

        // 比较
        if (valueA < valueB) {
            return sortConfig.direction === 'asc' ? -1 : 1;
        }
        if (valueA > valueB) {
            return sortConfig.direction === 'asc' ? 1 : -1;
        }
        return 0;
    });
}

// 更新排序指示器
function updateSortIndicators() {
    // 移除所有排序类
    document.querySelectorAll('th.sortable').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
    });
    
    // 添加当前排序类
    const currentTh = document.querySelector(`th[data-sort="${sortConfig.column}"]`);
    if (currentTh) {
        currentTh.classList.add(`sort-${sortConfig.direction}`);
    }
}

// 显示/隐藏加载指示器
function showLoading(show) {
    document.getElementById('loading-indicator').style.display = show ? 'flex' : 'none';
}

// 显示错误消息
function showError(message) {
    const errorElement = document.getElementById('error-message');
    const errorTextElement = document.getElementById('error-text');
    
    errorTextElement.textContent = message;
    errorElement.style.display = 'flex';
}

// 隐藏错误消息
function hideError() {
    document.getElementById('error-message').style.display = 'none';
}

// 更新最后更新时间
function updateLastUpdateTime() {
    const now = new Date();
    const timeString = now.toLocaleTimeString('zh-CN');
    document.getElementById('last-update-time').textContent = timeString;
}

// 获取交易所公告
async function fetchAnnouncements() {
    try {
        // 模拟公告数据（实际应用中需要调用各交易所的API）
        announcements = [
            {
                exchange: 'Binance',
                title: 'Binance将上线新币种XYZ',
                content: 'Binance将于2024年1月15日上线XYZ/USDT交易对',
                date: new Date(Date.now() - 2 * 60 * 60 * 1000), // 2小时前
                type: 'new_listing',
                isNew: true
            },
            {
                exchange: 'OKX',
                title: 'OKX系统维护通知',
                content: 'OKX将于今晚22:00-23:00进行系统维护',
                date: new Date(Date.now() - 4 * 60 * 60 * 1000), // 4小时前
                type: 'maintenance',
                isNew: false
            },
            {
                exchange: 'Gate',
                title: 'Gate新增ABC币种交易',
                content: 'Gate.io新增ABC/USDT交易对，现已开放交易',
                date: new Date(Date.now() - 6 * 60 * 60 * 1000), // 6小时前
                type: 'new_listing',
                isNew: true
            }
        ];
        
        // 检查新上币提醒
        checkNewListingAlerts();
    } catch (error) {
        console.error('获取公告失败:', error);
    }
}

// 检查新上币提醒
function checkNewListingAlerts() {
    const newListings = announcements.filter(ann => ann.type === 'new_listing' && ann.isNew);
    
    if (newListings.length > 0) {
        // 显示新上币提醒
        showNewListingNotification(newListings);
    }
}

// 显示新上币通知
function showNewListingNotification(listings) {
    listings.forEach(listing => {
        if (Notification.permission === 'granted') {
            new Notification(`${listing.exchange} 新上币提醒`, {
                body: listing.title,
                icon: '/favicon.ico'
            });
        } else {
            // 在页面上显示提醒
            const alertDiv = document.createElement('div');
            alertDiv.className = 'new-listing-alert';
            alertDiv.innerHTML = `
                <div class="alert alert-warning">
                    <strong>新上币提醒:</strong> ${listing.exchange} - ${listing.title}
                    <button onclick="this.parentElement.parentElement.remove()" class="close-btn">×</button>
                </div>
            `;
            document.body.insertBefore(alertDiv, document.body.firstChild);
            
            // 5秒后自动消失
            setTimeout(() => {
                if (alertDiv.parentElement) {
                    alertDiv.remove();
                }
            }, 5000);
        }
    });
}

// 获取充值提现信息
async function fetchDepositWithdrawInfo() {
    try {
        // 模拟充提信息数据
        depositWithdrawInfo = {
            'BTC': {
                networks: [
                    { name: 'Bitcoin', symbol: 'BTC', depositFee: 0, withdrawFee: 0.0005, minWithdraw: 0.001 },
                    { name: 'Lightning Network', symbol: 'BTC-Lightning', depositFee: 0, withdrawFee: 0.000001, minWithdraw: 0.00001 }
                ]
            },
            'ETH': {
                networks: [
                    { name: 'Ethereum', symbol: 'ETH', depositFee: 0, withdrawFee: 0.005, minWithdraw: 0.01 },
                    { name: 'Arbitrum', symbol: 'ETH-ARBITRUM', depositFee: 0, withdrawFee: 0.0001, minWithdraw: 0.001 }
                ]
            },
            'USDT': {
                networks: [
                    { name: 'Ethereum (ERC20)', symbol: 'USDT-ERC20', depositFee: 0, withdrawFee: 15, minWithdraw: 20 },
                    { name: 'Tron (TRC20)', symbol: 'USDT-TRC20', depositFee: 0, withdrawFee: 1, minWithdraw: 10 },
                    { name: 'BSC (BEP20)', symbol: 'USDT-BEP20', depositFee: 0, withdrawFee: 0.8, minWithdraw: 10 }
                ]
            }
        };
    } catch (error) {
        console.error('获取充提信息失败:', error);
    }
}

// 更新套利面板
function updateArbitragePanel() {
    const container = document.getElementById('arbitrage-opportunities');

    if (arbitrageOpportunities.length === 0) {
        container.innerHTML = '<p class="text-center">暂无高于0.1%的套利机会</p>';
        return;
    }

    const opportunitiesHtml = arbitrageOpportunities.slice(0, 15).map(opp => {
        const profitLevel = opp.profitPercentage > 2 ? 'high' : opp.profitPercentage > 1 ? 'medium' : 'low';
        
        return `
            <div class="opportunity-card" data-profit-level="${profitLevel}">
                <div class="opportunity-header">
                    <div class="opportunity-coin">
                        <i class="fas fa-coins"></i>
                        <strong>${opp.name} (${opp.symbol})</strong>
                    </div>
                    <div class="opportunity-profit-badge profit-${profitLevel}">
                        +${opp.profitPercentage.toFixed(2)}%
                    </div>
                </div>
                <div class="opportunity-body">
                    <div class="opportunity-path">
                        <div class="exchange-box">
                            <span class="exchange-name">${exchangeNames[opp.buyExchange] || opp.buyExchange}</span>
                            <span class="action-label">Buy At</span>
                            <span class="price-label">$${opp.buyPrice.toFixed(6)}</span>
                        </div>
                        <div class="arrow"><i class="fas fa-long-arrow-alt-right"></i></div>
                        <div class="exchange-box">
                            <span class="exchange-name">${exchangeNames[opp.sellExchange] || opp.sellExchange}</span>
                            <span class="action-label">Sell At</span>
                            <span class="price-label">$${opp.sellPrice.toFixed(6)}</span>
                        </div>
                    </div>
                    <div class="opportunity-details">
                        <div>
                            <i class="fas fa-calculator"></i>
                            <strong>利润:</strong>
                            <span>$${opp.profit.toFixed(6)} / per unit</span>
                        </div>
                        <div>
                            <i class="fas fa-chart-bar"></i>
                            <strong>24h Volume:</strong>
                            <span>$${opp.volume_24h ? opp.volume_24h.toLocaleString('en-US', { maximumFractionDigits: 0 }) : 'N/A'}</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = `
        <div class="panel-controls">
            <p>Top 15 opportunities (sorted by profit %)</p>
        </div>
        <div class="opportunities-grid">
            ${opportunitiesHtml}
        </div>
    `;
}

// 更新公告面板
function updateAnnouncementsPanel() {
    const container = document.getElementById('announcements-list');
    
    if (announcements.length === 0) {
        container.innerHTML = '<p>暂无公告信息</p>';
        return;
    }
    
    const html = announcements.map(ann => {
        return `
            <div class="announcement-item ${ann.type === 'new_listing' ? 'new-listing' : ''}">
                <div class="d-flex justify-content-between">
                    <strong>${ann.exchange}</strong>
                    <span class="announcement-date">${ann.date.toLocaleString('zh-CN')}</span>
                </div>
                <h5>${ann.title}</h5>
                <p>${ann.content}</p>
                ${ann.isNew ? '<span class="badge badge-warning">新</span>' : ''}
            </div>
        `;
    }).join('');
    
    container.innerHTML = html;
}

// 更新充提信息面板
function updateDepositWithdrawPanel() {
    const container = document.getElementById('deposit-withdraw-info');
    
    if (Object.keys(depositWithdrawInfo).length === 0) {
        container.innerHTML = '<p>暂无充提信息</p>';
        return;
    }
    
    const html = Object.entries(depositWithdrawInfo).map(([symbol, info]) => {
        const networksHtml = info.networks.map(network => {
            return `
                <div class="network-info">
                    <span><strong>${network.name}</strong></span>
                    <span>提现费: ${network.withdrawFee} ${symbol}</span>
                </div>
                <div class="fee-info">
                    充值费: ${network.depositFee} ${symbol} | 
                    最小提现: ${network.minWithdraw} ${symbol}
                </div>
            `;
        }).join('');
        
        return `
            <div class="deposit-withdraw-item">
                <h5>${symbol}</h5>
                ${networksHtml}
            </div>
        `;
    }).join('');
    
    container.innerHTML = html;
}

// 生成模拟数据
function getMockData() {
    // 常见加密货币列表
    const cryptos = [
        { name: '比特币', symbol: 'BTC/USDT' },
        { name: '以太坊', symbol: 'ETH/USDT' },
        { name: '币安币', symbol: 'BNB/USDT' },
        { name: '瑞波币', symbol: 'XRP/USDT' },
        { name: '索拉纳', symbol: 'SOL/USDT' },
        { name: '卡尔达诺', symbol: 'ADA/USDT' },
        { name: '狗狗币', symbol: 'DOGE/USDT' },
        { name: '波卡', symbol: 'DOT/USDT' },
        { name: '莱特币', symbol: 'LTC/USDT' },
        { name: '雪崩', symbol: 'AVAX/USDT' },
        { name: '链接', symbol: 'LINK/USDT' },
        { name: '波场', symbol: 'TRX/USDT' },
        { name: '近似协议', symbol: 'NEAR/USDT' },
        { name: '柚子', symbol: 'EOS/USDT' },
        { name: '沙盒', symbol: 'SAND/USDT' },
        { name: '宇宙', symbol: 'ATOM/USDT' },
        { name: '多边形', symbol: 'MATIC/USDT' },
        { name: '阿尔格兰德', symbol: 'ALGO/USDT' },
        { name: '基本注意力通证', symbol: 'BAT/USDT' },
        { name: '恒星币', symbol: 'XLM/USDT' },
        { name: '柴犬币', symbol: 'SHIB/USDT' },
        { name: '去中心化财经', symbol: 'DEFI/USDT' },
        { name: '流量币', symbol: 'FIL/USDT' },
        { name: '艾达币', symbol: 'ADA/USDT' },
        { name: '达世币', symbol: 'DASH/USDT' },
        { name: '门罗币', symbol: 'XMR/USDT' },
        { name: '泰达币', symbol: 'USDT/USD' },
        { name: '美元币', symbol: 'USDC/USD' },
        { name: '币圈币', symbol: 'BNB/USDT' },
        { name: '以太坊经典', symbol: 'ETC/USDT' },
        { name: '比特币现金', symbol: 'BCH/USDT' },
        { name: '兹卡什', symbol: 'ZEC/USDT' },
        { name: '埃欧塔', symbol: 'IOTA/USDT' },
        { name: '图灵币', symbol: 'TRB/USDT' },
        { name: '阿童木', symbol: 'ATOM/USDT' },
        { name: '1英寸', symbol: '1INCH/USDT' },
        { name: '雷达币', symbol: 'RUNE/USDT' },
        { name: '合成代币', symbol: 'SNX/USDT' },
        { name: '复合币', symbol: 'COMP/USDT' },
        { name: '曲线DAO代币', symbol: 'CRV/USDT' },
        { name: '去中心化交易所', symbol: 'DEX/USDT' },
        { name: '非同质化代币', symbol: 'NFT/USDT' },
        { name: '元宇宙币', symbol: 'META/USDT' },
        { name: '人工智能币', symbol: 'AI/USDT' },
        { name: '游戏代币', symbol: 'GAME/USDT' },
        { name: '隐私币', symbol: 'PRIV/USDT' },
        { name: '绿色能源币', symbol: 'GREEN/USDT' },
        { name: '医疗健康币', symbol: 'HEALTH/USDT' },
        { name: '供应链币', symbol: 'SUPPLY/USDT' },
        { name: '身份验证币', symbol: 'ID/USDT' },
        { name: '预言机币', symbol: 'ORACLE/USDT' },
        { name: '存储币', symbol: 'STORAGE/USDT' },
        { name: '互联网币', symbol: 'WEB3/USDT' },
        { name: '社交媒体币', symbol: 'SOCIAL/USDT' },
        { name: '音乐币', symbol: 'MUSIC/USDT' },
        { name: '艺术币', symbol: 'ART/USDT' },
        { name: '体育币', symbol: 'SPORTS/USDT' },
        { name: '旅游币', symbol: 'TRAVEL/USDT' },
        { name: '教育币', symbol: 'EDU/USDT' },
        { name: '金融科技币', symbol: 'FINTECH/USDT' },
        { name: '保险币', symbol: 'INSUR/USDT' },
        { name: '法律币', symbol: 'LEGAL/USDT' },
        { name: '房地产币', symbol: 'REALESTATE/USDT' },
        { name: '慈善币', symbol: 'CHARITY/USDT' },
        { name: '农业币', symbol: 'AGRI/USDT' },
        { name: '零知识证明币', symbol: 'ZK/USDT' },
        { name: '区块链安全币', symbol: 'SECURITY/USDT' },
        { name: '去中心化自治组织', symbol: 'DAO/USDT' },
        { name: '去中心化身份', symbol: 'DID/USDT' },
        { name: '去中心化金融', symbol: 'DEFI2/USDT' },
        { name: '去中心化存储', symbol: 'DSTORAGE/USDT' },
        { name: '去中心化计算', symbol: 'DCOMPUTE/USDT' },
        { name: '去中心化保险', symbol: 'DINSURANCE/USDT' },
        { name: '去中心化借贷', symbol: 'DLENDING/USDT' },
        { name: '去中心化交易', symbol: 'DTRADING/USDT' },
        { name: '去中心化预测', symbol: 'DPREDICTION/USDT' },
        { name: '去中心化社交', symbol: 'DSOCIAL/USDT' },
        { name: '去中心化游戏', symbol: 'DGAMING/USDT' },
        { name: '去中心化艺术', symbol: 'DART/USDT' },
        { name: '去中心化音乐', symbol: 'DMUSIC/USDT' },
        { name: '去中心化视频', symbol: 'DVIDEO/USDT' },
        { name: '去中心化内容', symbol: 'DCONTENT/USDT' },
        { name: '去中心化广告', symbol: 'DAD/USDT' },
        { name: '去中心化市场', symbol: 'DMARKET/USDT' },
        { name: '去中心化旅游', symbol: 'DTRAVEL/USDT' },
        { name: '去中心化医疗', symbol: 'DHEALTH/USDT' },
        { name: '去中心化教育', symbol: 'DEDU/USDT' },
        { name: '去中心化能源', symbol: 'DENERGY/USDT' },
        { name: '去中心化供应链', symbol: 'DSUPPLY/USDT' },
        { name: '去中心化物联网', symbol: 'DIOT/USDT' },
        { name: '去中心化人工智能', symbol: 'DAI/USDT' },
        { name: '去中心化元宇宙', symbol: 'DMETA/USDT' },
        { name: '去中心化虚拟现实', symbol: 'DVR/USDT' },
        { name: '去中心化增强现实', symbol: 'DAR/USDT' },
        { name: '跨链协议', symbol: 'CROSS/USDT' },
        { name: '闪电网络', symbol: 'LIGHTNING/USDT' },
        { name: '量子抗性', symbol: 'QUANTUM/USDT' },
        { name: '碳中和币', symbol: 'CARBON/USDT' },
        { name: '数据隐私', symbol: 'PRIVACY/USDT' },
        { name: '智能合约平台', symbol: 'SMART/USDT' },
        { name: '去中心化云存储', symbol: 'DCLOUD/USDT' },
        { name: '去中心化域名', symbol: 'DDNS/USDT' },
        { name: '去中心化通信', symbol: 'DCOMM/USDT' },
        { name: '去中心化身份验证', symbol: 'DAUTH/USDT' },
        { name: '去中心化投票', symbol: 'DVOTE/USDT' },
        { name: '去中心化治理', symbol: 'DGOV/USDT' },
        { name: '去中心化审计', symbol: 'DAUDIT/USDT' },
        { name: '去中心化法律', symbol: 'DLAW/USDT' },
        { name: '去中心化名誉', symbol: 'DREP/USDT' },
        { name: '去中心化数据分析', symbol: 'DDATA/USDT' },
        { name: '去中心化预言机', symbol: 'DORACLE/USDT' },
        { name: '去中心化交叉链', symbol: 'DCROSS/USDT' },
        { name: '去中心化流动性', symbol: 'DLIQUIDITY/USDT' }
    ];
    
    // 为每个加密货币生成随机价格
    return cryptos.map(crypto => {
        // 生成基础价格
        let basePrice;
        switch (crypto.symbol) {
            case 'BTC/USDT':
                basePrice = 50000 + Math.random() * 5000;
                break;
            case 'ETH/USDT':
                basePrice = 3000 + Math.random() * 300;
                break;
            case 'BNB/USDT':
                basePrice = 400 + Math.random() * 40;
                break;
            case 'XRP/USDT':
                basePrice = 0.5 + Math.random() * 0.05;
                break;
            case 'SOL/USDT':
                basePrice = 100 + Math.random() * 10;
                break;
            case 'ADA/USDT':
                basePrice = 0.4 + Math.random() * 0.04;
                break;
            case 'DOGE/USDT':
                basePrice = 0.08 + Math.random() * 0.008;
                break;
            case 'DOT/USDT':
                basePrice = 6 + Math.random() * 0.6;
                break;
            case 'LTC/USDT':
                basePrice = 70 + Math.random() * 7;
                break;
            case 'AVAX/USDT':
                basePrice = 30 + Math.random() * 3;
                break;
            case 'LINK/USDT':
                basePrice = 15 + Math.random() * 1.5;
                break;
            case 'TRX/USDT':
                basePrice = 0.1 + Math.random() * 0.01;
                break;
            case 'NEAR/USDT':
                basePrice = 4 + Math.random() * 0.4;
                break;
            case 'EOS/USDT':
                basePrice = 0.7 + Math.random() * 0.07;
                break;
            case 'SAND/USDT':
                basePrice = 0.5 + Math.random() * 0.05;
                break;
            case 'ATOM/USDT':
                basePrice = 8 + Math.random() * 0.8;
                break;
            case 'MATIC/USDT':
                basePrice = 0.8 + Math.random() * 0.08;
                break;
            case 'ALGO/USDT':
                basePrice = 0.15 + Math.random() * 0.015;
                break;
            case 'BAT/USDT':
                basePrice = 0.25 + Math.random() * 0.025;
                break;
            case 'XLM/USDT':
                basePrice = 0.12 + Math.random() * 0.012;
                break;
            case 'SHIB/USDT':
                basePrice = 0.00001 + Math.random() * 0.000001;
                break;
            case 'DEFI/USDT':
                basePrice = 500 + Math.random() * 50;
                break;
            case 'FIL/USDT':
                basePrice = 4 + Math.random() * 0.4;
                break;
            case 'DASH/USDT':
                basePrice = 40 + Math.random() * 4;
                break;
            case 'XMR/USDT':
                basePrice = 160 + Math.random() * 16;
                break;
            case 'USDT/USD':
                basePrice = 0.999 + Math.random() * 0.002;
                break;
            case 'USDC/USD':
                basePrice = 0.998 + Math.random() * 0.004;
                break;
            case 'ETC/USDT':
                basePrice = 18 + Math.random() * 1.8;
                break;
            case 'BCH/USDT':
                basePrice = 230 + Math.random() * 23;
                break;
            case 'ZEC/USDT':
                basePrice = 30 + Math.random() * 3;
                break;
            case 'IOTA/USDT':
                basePrice = 0.2 + Math.random() * 0.02;
                break;
            case 'TRB/USDT':
                basePrice = 25 + Math.random() * 2.5;
                break;
            case '1INCH/USDT':
                basePrice = 0.35 + Math.random() * 0.035;
                break;
            case 'RUNE/USDT':
                basePrice = 4.5 + Math.random() * 0.45;
                break;
            case 'SNX/USDT':
                basePrice = 2.5 + Math.random() * 0.25;
                break;
            case 'COMP/USDT':
                basePrice = 45 + Math.random() * 4.5;
                break;
            case 'CRV/USDT':
                basePrice = 0.6 + Math.random() * 0.06;
                break;
            case 'DEX/USDT':
                basePrice = 120 + Math.random() * 12;
                break;
            case 'CROSS/USDT':
                basePrice = 85 + Math.random() * 8.5;
                break;
            case 'LIGHTNING/USDT':
                basePrice = 65 + Math.random() * 6.5;
                break;
            case 'QUANTUM/USDT':
                basePrice = 110 + Math.random() * 11;
                break;
            case 'CARBON/USDT':
                basePrice = 25 + Math.random() * 2.5;
                break;
            case 'PRIVACY/USDT':
                basePrice = 45 + Math.random() * 4.5;
                break;
            case 'SMART/USDT':
                basePrice = 75 + Math.random() * 7.5;
                break;
            case 'DCLOUD/USDT':
                basePrice = 55 + Math.random() * 5.5;
                break;
            case 'DDNS/USDT':
                basePrice = 30 + Math.random() * 3;
                break;
            case 'DCOMM/USDT':
                basePrice = 40 + Math.random() * 4;
                break;
            case 'DAUTH/USDT':
                basePrice = 35 + Math.random() * 3.5;
                break;
            case 'DVOTE/USDT':
                basePrice = 20 + Math.random() * 2;
                break;
            case 'DGOV/USDT':
                basePrice = 50 + Math.random() * 5;
                break;
            case 'DAUDIT/USDT':
                basePrice = 45 + Math.random() * 4.5;
                break;
            case 'DLAW/USDT':
                basePrice = 60 + Math.random() * 6;
                break;
            case 'DREP/USDT':
                basePrice = 25 + Math.random() * 2.5;
                break;
            case 'DDATA/USDT':
                basePrice = 70 + Math.random() * 7;
                break;
            case 'DORACLE/USDT':
                basePrice = 80 + Math.random() * 8;
                break;
            case 'DCROSS/USDT':
                basePrice = 90 + Math.random() * 9;
                break;
            case 'DLIQUIDITY/USDT':
                basePrice = 65 + Math.random() * 6.5;
                break;
            case 'NFT/USDT':
                basePrice = 180 + Math.random() * 18;
                break;
            case 'META/USDT':
                basePrice = 250 + Math.random() * 25;
                break;
            case 'AI/USDT':
                basePrice = 300 + Math.random() * 30;
                break;
            case 'GAME/USDT':
                basePrice = 75 + Math.random() * 7.5;
                break;
            case 'PRIV/USDT':
                basePrice = 90 + Math.random() * 9;
                break;
            case 'GREEN/USDT':
                basePrice = 45 + Math.random() * 4.5;
                break;
            case 'HEALTH/USDT':
                basePrice = 60 + Math.random() * 6;
                break;
            case 'SUPPLY/USDT':
                basePrice = 35 + Math.random() * 3.5;
                break;
            case 'ID/USDT':
                basePrice = 20 + Math.random() * 2;
                break;
            case 'ORACLE/USDT':
                basePrice = 110 + Math.random() * 11;
                break;
            case 'STORAGE/USDT':
                basePrice = 40 + Math.random() * 4;
                break;
            case 'WEB3/USDT':
                basePrice = 150 + Math.random() * 15;
                break;
            case 'SOCIAL/USDT':
                basePrice = 85 + Math.random() * 8.5;
                break;
            case 'MUSIC/USDT':
                basePrice = 30 + Math.random() * 3;
                break;
            case 'ART/USDT':
                basePrice = 55 + Math.random() * 5.5;
                break;
            case 'SPORTS/USDT':
                basePrice = 25 + Math.random() * 2.5;
                break;
            case 'TRAVEL/USDT':
                basePrice = 15 + Math.random() * 1.5;
                break;
            case 'EDU/USDT':
                basePrice = 10 + Math.random() * 1;
                break;
            case 'FINTECH/USDT':
                basePrice = 95 + Math.random() * 9.5;
                break;
            case 'INSUR/USDT':
                basePrice = 50 + Math.random() * 5;
                break;
            case 'LEGAL/USDT':
                basePrice = 40 + Math.random() * 4;
                break;
            case 'REALESTATE/USDT':
                basePrice = 70 + Math.random() * 7;
                break;
            case 'CHARITY/USDT':
                basePrice = 5 + Math.random() * 0.5;
                break;
            case 'AGRI/USDT':
                basePrice = 20 + Math.random() * 2;
                break;
            case 'ZK/USDT':
                basePrice = 200 + Math.random() * 20;
                break;
            case 'SECURITY/USDT':
                basePrice = 120 + Math.random() * 12;
                break;
            case 'DAO/USDT':
                basePrice = 80 + Math.random() * 8;
                break;
            case 'DID/USDT':
                basePrice = 45 + Math.random() * 4.5;
                break;
            case 'DEFI2/USDT':
                basePrice = 150 + Math.random() * 15;
                break;
            case 'DSTORAGE/USDT':
                basePrice = 65 + Math.random() * 6.5;
                break;
            case 'DCOMPUTE/USDT':
                basePrice = 85 + Math.random() * 8.5;
                break;
            case 'DINSURANCE/USDT':
                basePrice = 55 + Math.random() * 5.5;
                break;
            case 'DLENDING/USDT':
                basePrice = 75 + Math.random() * 7.5;
                break;
            case 'DTRADING/USDT':
                basePrice = 95 + Math.random() * 9.5;
                break;
            case 'DPREDICTION/USDT':
                basePrice = 40 + Math.random() * 4;
                break;
            case 'DSOCIAL/USDT':
                basePrice = 60 + Math.random() * 6;
                break;
            case 'DGAMING/USDT':
                basePrice = 70 + Math.random() * 7;
                break;
            case 'DART/USDT':
                basePrice = 50 + Math.random() * 5;
                break;
            case 'DMUSIC/USDT':
                basePrice = 35 + Math.random() * 3.5;
                break;
            case 'DVIDEO/USDT':
                basePrice = 65 + Math.random() * 6.5;
                break;
            case 'DCONTENT/USDT':
                basePrice = 45 + Math.random() * 4.5;
                break;
            case 'DAD/USDT':
                basePrice = 30 + Math.random() * 3;
                break;
            case 'DMARKET/USDT':
                basePrice = 55 + Math.random() * 5.5;
                break;
            case 'DTRAVEL/USDT':
                basePrice = 25 + Math.random() * 2.5;
                break;
            case 'DHEALTH/USDT':
                basePrice = 70 + Math.random() * 7;
                break;
            case 'DEDU/USDT':
                basePrice = 20 + Math.random() * 2;
                break;
            case 'DENERGY/USDT':
                basePrice = 60 + Math.random() * 6;
                break;
            case 'DSUPPLY/USDT':
                basePrice = 40 + Math.random() * 4;
                break;
            case 'DIOT/USDT':
                basePrice = 80 + Math.random() * 8;
                break;
            case 'DAI/USDT':
                basePrice = 180 + Math.random() * 18;
                break;
            case 'DMETA/USDT':
                basePrice = 160 + Math.random() * 16;
                break;
            case 'DVR/USDT':
                basePrice = 90 + Math.random() * 9;
                break;
            case 'DAR/USDT':
                basePrice = 75 + Math.random() * 7.5;
                break;
            case 'SAND/USDT':
                basePrice = 0.5 + Math.random() * 0.05;
                break;
            case 'ATOM/USDT':
                basePrice = 10 + Math.random() * 1;
                break;
            case 'MATIC/USDT':
                basePrice = 0.8 + Math.random() * 0.08;
                break;
            case 'ALGO/USDT':
                basePrice = 0.15 + Math.random() * 0.015;
                break;
            case 'BAT/USDT':
                basePrice = 0.25 + Math.random() * 0.025;
                break;
            case 'XLM/USDT':
                basePrice = 0.12 + Math.random() * 0.012;
                break;
            case 'SHIB/USDT':
                basePrice = 0.00001 + Math.random() * 0.000001;
                break;
            case 'FIL/USDT':
                basePrice = 5 + Math.random() * 0.5;
                break;
            case 'DASH/USDT':
                basePrice = 35 + Math.random() * 3.5;
                break;
            case 'XMR/USDT':
                basePrice = 160 + Math.random() * 16;
                break;
            case 'USDT/USD':
                basePrice = 1 + (Math.random() - 0.5) * 0.01;
                break;
            case 'USDC/USD':
                basePrice = 1 + (Math.random() - 0.5) * 0.005;
                break;
            case 'ETC/USDT':
                basePrice = 20 + Math.random() * 2;
                break;
            case 'BCH/USDT':
                basePrice = 250 + Math.random() * 25;
                break;
            case 'ZEC/USDT':
                basePrice = 30 + Math.random() * 3;
                break;
            case 'IOTA/USDT':
                basePrice = 0.2 + Math.random() * 0.02;
                break;
            case 'TRB/USDT':
                basePrice = 40 + Math.random() * 4;
                break;
            case '1INCH/USDT':
                basePrice = 0.4 + Math.random() * 0.04;
                break;
            case 'RUNE/USDT':
                basePrice = 5 + Math.random() * 0.5;
                break;
            case 'SNX/USDT':
                basePrice = 3 + Math.random() * 0.3;
                break;
            case 'COMP/USDT':
                basePrice = 50 + Math.random() * 5;
                break;
            case 'CRV/USDT':
                basePrice = 0.6 + Math.random() * 0.06;
                break;
            case 'DEFI/USDT':
                basePrice = 1200 + Math.random() * 120;
                break;
            default:
                basePrice = 1 + Math.random() * 100;
        }
        
        // 为每个交易所生成略有差异的价格
        const variation = () => (Math.random() - 0.5) * basePrice * 0.02; // 最大±1%的差异
        
        return {
            name: crypto.name,
            symbol: crypto.symbol,
            binance: basePrice + variation(),
            okx: basePrice + variation(),
            mexc: basePrice + variation(),
            gate: basePrice + variation(),
            kucoin: basePrice + variation(),
            bitget: basePrice + variation(),
            bybit: basePrice + variation(),
            htx: basePrice + variation()
        };
    });
}

// 实际API调用示例（注释掉，因为需要后端支持）
/*
async function fetchBinancePrice(symbol) {
    try {
        const response = await fetch(`https://api.binance.com/api/v3/ticker/price?symbol=${symbol}`);
        const data = await response.json();
        return parseFloat(data.price);
    } catch (error) {
        console.error('Binance API error:', error);
        return null;
    }
}

async function fetchOkxPrice(symbol) {
    try {
        const response = await fetch(`https://www.okx.com/api/v5/market/ticker?instId=${symbol}`);
        const data = await response.json();
        return parseFloat(data.data[0].last);
    } catch (error) {
        console.error('OKX API error:', error);
        return null;
    }
}

// 其他交易所的API调用函数...
*/

// 注意：在实际应用中，应该使用后端服务来聚合各交易所的数据
// 这样可以避免跨域问题，并且可以隐藏API密钥等敏感信息
// 前端只需要调用自己的后端API即可