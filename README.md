# 🚀 US Stock Trading Signal Dashboard (v2.29 Strategy)

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个基于美股与大类资产趋势择时、SGOV 闲置贴息与 JEPQ 高股息红利复利的**现代化半自动交易指挥台与信号管理系统**。

---

## 📊 策略表现一览 (v2.29 实盘表现 2022.05 ~ 2026.06)

* 🚀 **年化收益率 (CAGR)**：**31.75%**
* 🛡️ **最大回撤 (MaxDD)**：**-10.75%**
* 🎯 **夏普比率 (Sharpe)**：**2.267**
* ⚡ **索提诺比率 (Sortino)**：**3.023**
* 💰 **4年本利和 ($100k起)**：**$307,631.63** (+$207,631.63 净利润)

---

## 🏛️ 策略架构 (Portfolio Structure)

* **L0 现金流底仓 (60% NAV)**：100% 持有 `JEPQ` 高股息 ETF，开启 **DRIP 红利自动再投资**。
* **SGOV 闲置贴息池 (40% 初始 NAV)**：未建仓闲置资金 100% 自动持有 `SGOV` (0-3个月国债 ETF)，享年化 **~5.2% 无风险贴息**。建仓时优先卖出变现 SGOV。
* **跨资产多趋势层 (上限 55% NAV)**：
  * **美股类**：`SPY`, `QQQ`, `SOXX`, `QLD` (2x)，受 S5FI (45/55) 宽度闸门约束；
  * **非美股避险类**：`GLD` (黄金), `TLT` (美债), `DBC` (商品), `BITO` (比特币)，**豁免 S5FI**。

---

## 🖥️ 本地快速运行 (Local Quickstart)

```bash
# 1. 克隆仓库
git clone https://github.com/<YOUR_USERNAME>/US_Stock_Trading_Signal_Dashboard.git
cd US_Stock_Trading_Signal_Dashboard

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行每日盘后信号扫描
python run_daily_scan.py

# 4. 启动 Web 可视化指挥台
streamlit run app.py
```

---

## ☁️ Streamlit Cloud 免费一键部署 (Cloud Deployment)

1. 登录 [share.streamlit.io](https://share.streamlit.io/)；
2. 选择本 GitHub 仓库 `US_Stock_Trading_Signal_Dashboard`；
3. 选择主入口文件 `app.py`；
4. 点击 **[Deploy]** 即可在 1 分钟内获得专属公网网址！
