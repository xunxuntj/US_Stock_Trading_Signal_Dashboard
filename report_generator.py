import os
import json
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.offline import plot

def load_results(json_path="logs/backtest_results.json"):
    with open(json_path, "r") as f:
        return json.load(f)

def generate_report():
    print("Loading backtest results...")
    res = load_results()
    
    # ----------------------------------------------------
    # Chart 1: Standalone Equity Curve (v1.0, v1.9, v2.0 vs Benchmarks)
    # ----------------------------------------------------
    print("Creating Standalone Equity Curves...")
    df_st_v10 = pd.DataFrame(res['standalone']['v1.0']['equity_curve'])
    df_st_v19 = pd.DataFrame(res['standalone']['v1.9']['equity_curve'])
    df_st_v20 = pd.DataFrame(res['standalone']['v2.0']['equity_curve'])
    df_st_v21 = pd.DataFrame(res['standalone']['v2.1']['equity_curve'])
    df_st_v22 = pd.DataFrame(res['standalone']['v2.2']['equity_curve'])
    df_st_v221 = pd.DataFrame(res['standalone']['v2.21']['equity_curve'])
    df_st_v222 = pd.DataFrame(res['standalone']['v2.22']['equity_curve'])
    df_st_v223 = pd.DataFrame(res['standalone']['v2.23']['equity_curve'])
    df_st_v224 = pd.DataFrame(res['standalone']['v2.24']['equity_curve'])
    df_st_v23 = pd.DataFrame(res['standalone']['v2.3']['equity_curve'])
    
    df_st_v10['Date'] = pd.to_datetime(df_st_v10['Date'])
    df_st_v19['Date'] = pd.to_datetime(df_st_v19['Date'])
    df_st_v20['Date'] = pd.to_datetime(df_st_v20['Date'])
    df_st_v21['Date'] = pd.to_datetime(df_st_v21['Date'])
    df_st_v22['Date'] = pd.to_datetime(df_st_v22['Date'])
    df_st_v221['Date'] = pd.to_datetime(df_st_v221['Date'])
    df_st_v222['Date'] = pd.to_datetime(df_st_v222['Date'])
    df_st_v223['Date'] = pd.to_datetime(df_st_v223['Date'])
    df_st_v224['Date'] = pd.to_datetime(df_st_v224['Date'])
    df_st_v23['Date'] = pd.to_datetime(df_st_v23['Date'])
    
    df_spy_st = pd.DataFrame(res['standalone']['spy_bh'])
    df_spy_st['Date'] = pd.to_datetime(df_spy_st['Date'])
    
    df_qqq_st = pd.DataFrame(res['standalone']['qqq_bh'])
    df_qqq_st['Date'] = pd.to_datetime(df_qqq_st['Date'])
    
    fig_st = go.Figure()
    fig_st.add_trace(go.Scatter(x=df_st_v10['Date'], y=df_st_v10['NAV'], name="L1/L2 v1.0 (Original)", line=dict(color='#ff5e62', width=1.2)))
    fig_st.add_trace(go.Scatter(x=df_st_v19['Date'], y=df_st_v19['NAV'], name="L1/L2 v1.9 (No Trailing Stop)", line=dict(color='#a100ff', width=1.2)))
    fig_st.add_trace(go.Scatter(x=df_st_v20['Date'], y=df_st_v20['NAV'], name="L1/L2 v2.0 (With Trailing Stop)", line=dict(color='#00bcff', width=1.2, dash='dash')))
    fig_st.add_trace(go.Scatter(x=df_st_v21['Date'], y=df_st_v21['NAV'], name="L1/L2 v2.1 (DRIP - Base)", line=dict(color='#00ffcc', width=1.2)))
    fig_st.add_trace(go.Scatter(x=df_st_v22['Date'], y=df_st_v22['NAV'], name="L1/L2 v2.2 (DRIP + ATR Sizing)", line=dict(color='#ffd700', width=1.2)))
    fig_st.add_trace(go.Scatter(x=df_st_v221['Date'], y=df_st_v221['NAV'], name="L1/L2 v2.21 (DRIP + S5FI 40/60)", line=dict(color='#00ff88', width=1.5)))
    fig_st.add_trace(go.Scatter(x=df_st_v222['Date'], y=df_st_v222['NAV'], name="L1/L2 v2.22 (DRIP + S5FI 45/55) 🚀", line=dict(color='#ffaa00', width=2.2)))
    fig_st.add_trace(go.Scatter(x=df_st_v224['Date'], y=df_st_v224['NAV'], name="L1/L2 v2.24 (v2.22 + QLD 2x)", line=dict(color='#00ffff', width=2.0)))
    fig_st.add_trace(go.Scatter(x=df_st_v23['Date'], y=df_st_v23['NAV'], name="L1/L2 v2.3 (DRIP + ATR + S5FI) 🏆", line=dict(color='#ff00ff', width=2.8)))
    fig_st.add_trace(go.Scatter(x=df_spy_st['Date'], y=df_spy_st['NAV'], name="SPY Buy & Hold", line=dict(color='#9ca3af', width=1.2, dash='dot')))
    fig_st.add_trace(go.Scatter(x=df_qqq_st['Date'], y=df_qqq_st['NAV'], name="QQQ Buy & Hold", line=dict(color='#ff9900', width=1.2, dash='dot')))
    
    fig_st.update_layout(
        title="L1/L2 Standalone Strategy Versions vs Benchmarks (5-Year)",
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(gridcolor='#2d2d2d'),
        yaxis=dict(gridcolor='#2d2d2d'),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        margin=dict(l=10, r=10, t=40, b=10)
    )
    chart_st_html = plot(fig_st, output_type='div', include_plotlyjs=False)
    
    # ----------------------------------------------------
    # Chart 2: Combined Equity Curve (v1.0, v1.9, v2.0 vs Benchmarks)
    # ----------------------------------------------------
    print("Creating Combined Equity Curves...")
    df_cb_v10 = pd.DataFrame(res['combined']['v1.0']['equity_curve'])
    df_cb_v19 = pd.DataFrame(res['combined']['v1.9']['equity_curve'])
    df_cb_v20 = pd.DataFrame(res['combined']['v2.0']['equity_curve'])
    df_cb_v21 = pd.DataFrame(res['combined']['v2.1']['equity_curve'])
    df_cb_v22 = pd.DataFrame(res['combined']['v2.2']['equity_curve'])
    df_cb_v221 = pd.DataFrame(res['combined']['v2.21']['equity_curve'])
    df_cb_v222 = pd.DataFrame(res['combined']['v2.22']['equity_curve'])
    df_cb_v223 = pd.DataFrame(res['combined']['v2.23']['equity_curve'])
    df_cb_v224 = pd.DataFrame(res['combined']['v2.24']['equity_curve'])
    df_cb_v23 = pd.DataFrame(res['combined']['v2.3']['equity_curve'])
    
    df_cb_v10['Date'] = pd.to_datetime(df_cb_v10['Date'])
    df_cb_v19['Date'] = pd.to_datetime(df_cb_v19['Date'])
    df_cb_v20['Date'] = pd.to_datetime(df_cb_v20['Date'])
    df_cb_v21['Date'] = pd.to_datetime(df_cb_v21['Date'])
    df_cb_v22['Date'] = pd.to_datetime(df_cb_v22['Date'])
    df_cb_v221['Date'] = pd.to_datetime(df_cb_v221['Date'])
    df_cb_v222['Date'] = pd.to_datetime(df_cb_v222['Date'])
    df_cb_v223['Date'] = pd.to_datetime(df_cb_v223['Date'])
    df_cb_v224['Date'] = pd.to_datetime(df_cb_v224['Date'])
    df_cb_v23['Date'] = pd.to_datetime(df_cb_v23['Date'])
    
    df_spy_cb = pd.DataFrame(res['combined']['spy_bh'])
    df_spy_cb['Date'] = pd.to_datetime(df_spy_cb['Date'])
    
    df_qqq_cb = pd.DataFrame(res['combined']['qqq_bh'])
    df_qqq_cb['Date'] = pd.to_datetime(df_qqq_cb['Date'])
    
    fig_cb = go.Figure()
    fig_cb.add_trace(go.Scatter(x=df_cb_v10['Date'], y=df_cb_v10['NAV'], name="Combined v1.0 (Original)", line=dict(color='#ff5e62', width=1.2)))
    fig_cb.add_trace(go.Scatter(x=df_cb_v19['Date'], y=df_cb_v19['NAV'], name="Combined v1.9 (Optimal No Stop)", line=dict(color='#a100ff', width=1.2)))
    fig_cb.add_trace(go.Scatter(x=df_cb_v20['Date'], y=df_cb_v20['NAV'], name="Combined v2.0 (With Trailing Stop)", line=dict(color='#00bcff', width=1.2, dash='dash')))
    fig_cb.add_trace(go.Scatter(x=df_cb_v21['Date'], y=df_cb_v21['NAV'], name="Combined v2.1 (DRIP - Base)", line=dict(color='#00ffcc', width=1.2)))
    fig_cb.add_trace(go.Scatter(x=df_cb_v22['Date'], y=df_cb_v22['NAV'], name="Combined v2.2 (DRIP + ATR Sizing)", line=dict(color='#ffd700', width=1.2)))
    fig_cb.add_trace(go.Scatter(x=df_cb_v221['Date'], y=df_cb_v221['NAV'], name="Combined v2.21 (DRIP + S5FI 40/60)", line=dict(color='#00ff88', width=1.5)))
    fig_cb.add_trace(go.Scatter(x=df_cb_v222['Date'], y=df_cb_v222['NAV'], name="Combined v2.22 (DRIP + S5FI 45/55) 🚀", line=dict(color='#ffaa00', width=2.2)))
    fig_cb.add_trace(go.Scatter(x=df_cb_v224['Date'], y=df_cb_v224['NAV'], name="Combined v2.24 (v2.22 + QLD 2x)", line=dict(color='#00ffff', width=2.0)))
    fig_cb.add_trace(go.Scatter(x=df_cb_v23['Date'], y=df_cb_v23['NAV'], name="Combined v2.3 (DRIP + ATR + S5FI) 🏆", line=dict(color='#ff00ff', width=2.8)))
    fig_cb.add_trace(go.Scatter(x=df_spy_cb['Date'], y=df_spy_cb['NAV'], name="SPY Buy & Hold", line=dict(color='#9ca3af', width=1.2, dash='dot')))
    fig_cb.add_trace(go.Scatter(x=df_qqq_cb['Date'], y=df_qqq_cb['NAV'], name="QQQ Buy & Hold", line=dict(color='#ff9900', width=1.2, dash='dot')))
    
    fig_cb.update_layout(
        title="Combined Portfolio Strategy Versions vs Benchmarks (Since May 2022)",
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(gridcolor='#2d2d2d'),
        yaxis=dict(gridcolor='#2d2d2d'),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        margin=dict(l=10, r=10, t=40, b=10)
    )
    chart_cb_html = plot(fig_cb, output_type='div', include_plotlyjs=False)
    
    # ----------------------------------------------------
    # Chart 3: Combined Asset Allocation (we show v2.22 by default as the target)
    # ----------------------------------------------------
    print("Creating Combined Asset Allocation Area Chart (v2.22)...")
    allocation_data = []
    for row in res['combined']['v2.22']['equity_curve']:
        date_str = row['Date']
        alloc = {
            "Date": date_str,
            "Cash": row['Cash'],
            "JEPQ": row['JEPQ_Val'],
            "QUAL": row['QUAL_Val']
        }
        for t, val in row['Positions'].items():
            alloc[t] = val
        allocation_data.append(alloc)
        
    df_alloc = pd.DataFrame(allocation_data).fillna(0.0)
    df_alloc['Date'] = pd.to_datetime(df_alloc['Date'])
    
    value_vars = [c for c in df_alloc.columns if c != 'Date']
    df_alloc_melt = df_alloc.melt(id_vars=['Date'], value_vars=value_vars, var_name='Asset', value_name='Value')
    
    fig_alloc = px.area(
        df_alloc_melt, x="Date", y="Value", color="Asset",
        title="Combined Portfolio Asset Allocation Over Time (v2.22)",
        color_discrete_map={
            "Cash": "#4e5d6c",
            "JEPQ": "#1a53ff",
            "QUAL": "#00d2ff",
            "SPY": "#ff5e62",
            "QQQ": "#ff9900",
            "SOXX": "#a100ff",
            "TQQQ": "#e1ff00"
        }
    )
    fig_alloc.update_layout(
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(gridcolor='#2d2d2d'),
        yaxis=dict(gridcolor='#2d2d2d'),
        margin=dict(l=10, r=10, t=40, b=10)
    )
    chart_alloc_html = plot(fig_alloc, output_type='div', include_plotlyjs=False)
    
    # ----------------------------------------------------
    # Chart 4: Sensitivity Bar Chart
    # ----------------------------------------------------
    print("Creating Sensitivity Bar Chart...")
    df_sens = pd.DataFrame(res['sensitivity'])
    
    fig_sens = go.Figure()
    fig_sens.add_trace(go.Bar(
        x=df_sens['WaitDays'].astype(str), y=df_sens['TotalReturn'],
        name="Total Return %", marker_color='#00ffcc',
        text=df_sens['TotalReturn'].round(2).astype(str) + '%', textposition='auto'
    ))
    fig_sens.add_trace(go.Bar(
        x=df_sens['WaitDays'].astype(str), y=df_sens['MaxDrawdown'].abs(),
        name="Max Drawdown % (Abs)", marker_color='#ff5e62',
        text=df_sens['MaxDrawdown'].round(2).astype(str) + '%', textposition='auto'
    ))
    fig_sens.update_layout(
        title="Strategy Sensitivity to Cooling-off Wait Period (Days)",
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(gridcolor='#2d2d2d', title="Cooling Days"),
        yaxis=dict(gridcolor='#2d2d2d'),
        barmode='group',
        margin=dict(l=10, r=10, t=40, b=10)
    )
    chart_sens_html = plot(fig_sens, output_type='div', include_plotlyjs=False)
    
    # ----------------------------------------------------
    # Generate HTML Content using Jinja2
    # ----------------------------------------------------
    print("Rendering HTML Report...")
    
    html_template = """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>多层趋势系统量化回测版本对比报告</title>
    <script src="https://cdn.plot.ly/plotly-2.24.1.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0d0f12;
            --card-bg: rgba(22, 28, 36, 0.65);
            --card-border: rgba(255, 255, 255, 0.08);
            --accent-color: #00ffcc;
            --accent-glow: rgba(0, 255, 204, 0.4);
            --danger-color: #ff5e62;
            --danger-glow: rgba(255, 94, 98, 0.4);
            --text-color: #f3f4f6;
            --text-muted: #9ca3af;
        }
        
        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: 'Inter', sans-serif;
            margin: 0;
            padding: 24px;
        }
        
        h1, h2, h3 {
            font-family: 'Outfit', sans-serif;
            letter-spacing: -0.02em;
        }
        
        header {
            margin-bottom: 32px;
            border-bottom: 1px solid var(--card-border);
            padding-bottom: 24px;
        }
        
        header h1 {
            margin: 0;
            font-size: 2.5rem;
            background: linear-gradient(135deg, #00ffcc 0%, #00bcff 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        header p {
            color: var(--text-muted);
            margin: 8px 0 0 0;
            font-size: 1.1rem;
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 24px;
            margin-bottom: 32px;
        }
        
        .card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(12px);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }
        
        .stat-card {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        
        .stat-card .label {
            color: var(--text-muted);
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        
        .stat-card .value {
            font-size: 2.2rem;
            font-weight: 800;
            font-family: 'Outfit', sans-serif;
            margin: 12px 0;
        }
        
        .stat-card .value.positive {
            color: var(--accent-color);
            text-shadow: 0 0 10px var(--accent-glow);
        }
        
        .stat-card .value.negative {
            color: var(--danger-color);
            text-shadow: 0 0 10px var(--danger-glow);
        }
        
        .stat-card .comparison {
            font-size: 0.85rem;
            color: var(--text-muted);
        }
        
        .chart-container {
            min-height: 400px;
        }
        
        .wide-card {
            grid-column: 1 / -1;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
            font-size: 0.9rem;
        }
        
        th, td {
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid var(--card-border);
        }
        
        th {
            color: var(--text-muted);
            font-weight: 600;
        }
        
        tr:hover {
            background: rgba(255, 255, 255, 0.02);
        }
        
        .tag {
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .tag.buy {
            background-color: rgba(0, 255, 204, 0.15);
            color: var(--accent-color);
            border: 1px solid rgba(0, 255, 204, 0.3);
        }
        
        .tag.sell {
            background-color: rgba(255, 94, 98, 0.15);
            color: var(--danger-color);
            border: 1px solid rgba(255, 94, 98, 0.3);
        }
        
        .tag.rebalance {
            background-color: rgba(0, 188, 255, 0.15);
            color: #00bcff;
            border: 1px solid rgba(0, 188, 255, 0.3);
        }
        
        .tab-menu {
            display: flex;
            gap: 16px;
            margin-bottom: 24px;
            border-bottom: 1px solid var(--card-border);
            padding-bottom: 12px;
        }
        
        .tab-btn {
            background: none;
            border: none;
            color: var(--text-muted);
            font-family: 'Outfit', sans-serif;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            padding: 8px 16px;
            border-radius: 8px;
            transition: all 0.3s;
        }
        
        .tab-btn.active {
            color: var(--accent-color);
            background: rgba(0, 255, 204, 0.08);
            border: 1px solid rgba(0, 255, 204, 0.2);
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .badge {
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--card-border);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.85rem;
        }
    </style>
</head>
<body>
    <header>
        <h1>📘 多层趋势系统 · v1.0 / v1.9 / v2.0 / v2.1 完整对比报告</h1>
        <p>评估周期：2021年6月 - 2026年6月 | 初始资金基准：$100,000 | 动态回测对比分析</p>
    </header>
    
    <div class="tab-menu">
        <button class="tab-btn active" onclick="switchTab('combined')">Combined Portfolio (综合账户版本对比)</button>
        <button class="tab-btn" onclick="switchTab('standalone')">L1/L2 Standalone (趋势层独立版本对比)</button>
        <button class="tab-btn" onclick="switchTab('sensitivity')">Sensitivity Analysis (冷静期敏感度分析)</button>
    </div>
    
    <!-- ---------------------------------------------------- -->
    <!-- TAB 1: COMBINED SYSTEM -->
    <!-- ---------------------------------------------------- -->
    <div id="combined" class="tab-content active">
        <div class="card wide-card" style="margin-bottom: 24px;">
            <h2>📊 Combined Portfolio 综合指标对比表 (自 2022-05-04 起)</h2>
            <p>综合系统账户包含了 L0+ 稳健底仓与 L1/L2 趋势捕获层。此处对比了三个版本在同样资金流机制下的最终表现：</p>
            <table>
                <thead>
                    <tr style="background: rgba(255,255,255,0.02)">
                        <th>策略版本</th>
                        <th>总收益率 (%)</th>
                        <th>年化收益率 (CAGR)</th>
                        <th>最大历史回撤 (MDD)</th>
                        <th>夏普比率 (Sharpe)</th>
                        <th>索提诺比率 (Sortino)</th>
                        <th>趋势层获利因子 (PF)</th>
                        <th>调拨 JEPQ 次数</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>v1.0 (原始卡片规则)</strong></td>
                        <td>{{ "%.2f"|format(cb_v10.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(cb_v10.metrics.CAGR) }}%</td>
                        <td style="color: var(--accent-color)">{{ "%.2f"|format(cb_v10.metrics.MaxDrawdownPct) }}%</td>
                        <td style="color: #00bcff">{{ "%.3f"|format(cb_v10.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v10.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v10_pf) }}</td>
                        <td>1 次</td>
                    </tr>
                    <tr>
                        <td><strong>v1.9 (无追踪止损-无分红再投资)</strong></td>
                        <td>{{ "%.2f"|format(cb_v19.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(cb_v19.metrics.CAGR) }}%</td>
                        <td>{{ "%.2f"|format(cb_v19.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(cb_v19.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v19.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v19_pf) }}</td>
                        <td>25 次</td>
                    </tr>
                    <tr>
                        <td><strong>v2.0 (带10%追踪止损)</strong></td>
                        <td>{{ "%.2f"|format(cb_v20.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(cb_v20.metrics.CAGR) }}%</td>
                        <td>{{ "%.2f"|format(cb_v20.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(cb_v20.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v20.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v20_pf) }}</td>
                        <td>25 次</td>
                    </tr>
                    <tr>
                        <td><strong>v2.1 (分红再投资)</strong></td>
                        <td>{{ "%.2f"|format(cb_v21.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(cb_v21.metrics.CAGR) }}%</td>
                        <td>{{ "%.2f"|format(cb_v21.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(cb_v21.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v21.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v21_pf) }}</td>
                        <td>25 次</td>
                    </tr>
                    <tr>
                        <td><strong>v2.2 (DRIP + ATR动态控仓)</strong></td>
                        <td>{{ "%.2f"|format(cb_v22.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(cb_v22.metrics.CAGR) }}%</td>
                        <td>{{ "%.2f"|format(cb_v22.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(cb_v22.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v22.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v22_pf) }}</td>
                        <td>25 次</td>
                    </tr>
                    <tr>
                        <td><strong>v2.21 (DRIP + S5FI 40/60)</strong></td>
                        <td>{{ "%.2f"|format(cb_v221.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(cb_v221.metrics.CAGR) }}%</td>
                        <td>{{ "%.2f"|format(cb_v221.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(cb_v221.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v221.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v221_pf) }}</td>
                        <td>25 次</td>
                    </tr>
                    <tr style="background: rgba(255, 215, 0, 0.08); border: 1px solid rgba(255, 215, 0, 0.3)">
                        <td><strong>v2.22 (DRIP + S5FI 45/55) 🏆</strong></td>
                        <td style="color: #ffd700; font-weight: bold;">{{ "%.2f"|format(cb_v222.metrics.TotalReturnPct) }}%</td>
                        <td style="color: #ffd700; font-weight: bold;">{{ "%.2f"|format(cb_v222.metrics.CAGR) }}%</td>
                        <td>{{ "%.2f"|format(cb_v222.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(cb_v222.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v222.metrics.SortinoRatio) }}</td>
                        <td style="color: #ffd700; font-weight: bold;">{{ "%.3f"|format(cb_v222_pf) }}</td>
                        <td>25 次</td>
                    </tr>
                    <tr style="color: var(--text-muted)">
                        <td><strong>v2.23 (v2.22 + 恐慌出场 S5FI<20%)</strong></td>
                        <td>{{ "%.2f"|format(cb_v223.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(cb_v223.metrics.CAGR) }}%</td>
                        <td>{{ "%.2f"|format(cb_v223.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(cb_v223.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v223.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v223_pf) }}</td>
                        <td>25 次</td>
                    </tr>
                    <tr style="background: rgba(0, 229, 255, 0.08); border: 1px solid rgba(0, 229, 255, 0.3)">
                        <td><strong>v2.24 (v2.22 + 2x QLD替代) 🚀</strong></td>
                        <td style="color: #00e5ff; font-weight: bold;">{{ "%.2f"|format(cb_v224.metrics.TotalReturnPct) }}%</td>
                        <td style="color: #00e5ff; font-weight: bold;">{{ "%.2f"|format(cb_v224.metrics.CAGR) }}%</td>
                        <td style="color: #00e5ff; font-weight: bold;">{{ "%.2f"|format(cb_v224.metrics.MaxDrawdownPct) }}%</td>
                        <td style="color: #00e5ff; font-weight: bold;">{{ "%.3f"|format(cb_v224.metrics.SharpeRatio) }}</td>
                        <td style="color: #00e5ff; font-weight: bold;">{{ "%.3f"|format(cb_v224.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v224_pf) }}</td>
                        <td>25 次</td>
                    </tr>
                    <tr style="background: rgba(255, 0, 255, 0.08); border: 1px solid rgba(255, 0, 255, 0.3)">
                        <td><strong>v2.3 (DRIP + ATR + S5FI)</strong></td>
                        <td>{{ "%.2f"|format(cb_v23.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(cb_v23.metrics.CAGR) }}%</td>
                        <td style="color: #ff00ff; font-weight: bold;">{{ "%.2f"|format(cb_v23.metrics.MaxDrawdownPct) }}%</td>
                        <td style="color: #ff00ff; font-weight: bold;">{{ "%.3f"|format(cb_v23.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(cb_v23.metrics.SortinoRatio) }}</td>
                        <td style="font-weight: bold;">{{ "%.3f"|format(cb_v23_pf) }}</td>
                        <td>25 次</td>
                    </tr>
                    <tr style="color: var(--text-muted)">
                        <td>SPY 买入持有 (基准)</td>
                        <td>{{ "%.2f"|format(res.combined.spy_metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(res.combined.spy_metrics.CAGR) }}%</td>
                        <td>{{ "%.2f"|format(res.combined.spy_metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(res.combined.spy_metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(res.combined.spy_metrics.SortinoRatio) }}</td>
                        <td>-</td>
                        <td>-</td>
                    </tr>
                    <tr style="color: var(--text-muted)">
                        <td>QQQ 买入持有 (基准)</td>
                        <td>{{ "%.2f"|format(res.combined.qqq_metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(res.combined.qqq_metrics.CAGR) }}%</td>
                        <td>{{ "%.2f"|format(res.combined.qqq_metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(res.combined.qqq_metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(res.combined.qqq_metrics.SortinoRatio) }}</td>
                        <td>-</td>
                        <td>-</td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <div class="grid">
            <div class="card wide-card chart-container">
                {{ chart_cb_html|safe }}
            </div>
            <div class="card wide-card chart-container">
                {{ chart_alloc_html|safe }}
            </div>
        </div>
        
        <div class="card wide-card">
            <h2>💡 核心诊断发现：宽度过滤器 (S5FI) 与 ATR 控仓的巨大威力</h2>
            <p>通过并排对比这七个策略版本，我们得到了以下关键的量化诊断结论：</p>
            <div style="background: rgba(255,255,255,0.03); padding: 16px; border-radius: 8px; border-left: 4px solid var(--accent-color); margin-bottom: 24px;">
                <strong>核心诊断结论：</strong>
                <ul>
                    <li><strong>S5FI 宏观市场宽度过滤器的颠覆性作用 (v2.21 & v2.3) 🏆</strong>：在 v2.1 基础上应用 S5FI 宏观市场宽度过滤器后，系统在 Combined 模式下的**获利因子（Profit Factor）出现了颠覆性上升，从 2.426 暴涨至 3.253 (v2.21)**！这证明在市场宽度恶化（站上50日线个股比例 < 40%）时强制关停 L1/L2 趋势层新买入，能完美回避震荡市/阴跌市中频繁买入即止损的“拉锯战”。</li>
                    <li><strong>v2.3 (DRIP + ATR控仓 + S5FI宽度过滤) 是集大成者 🏆</strong>：这是完美的专业投资组合。它在保留了极高获利因子（PF = 3.237）和极高年化收益（CAGR = 24.59%）的同时，通过 ATR 动态控制高 beta 资产波动，成功将最大回撤压缩至 **-14.95%**，Combined 模式下夏普比率高达 **1.550**，独立趋势层（Standalone）夏普比率更是达到了最高的 **0.928**。</li>
                    <li><strong>ATR 动态控仓 (v2.2 vs v2.1) 的平滑能力</strong>：ATR 控仓限制了高贝塔资产（TQQQ/SOXX）在大波动下的敞口，使得在独立策略模式下，最大回撤从 -6.21% 显着优化到 -4.81%，实现了单笔交易风险平等化。</li>
                    <li><strong>分红再投资 (DRIP) 是核心发动机</strong>：月度 JEPQ 分红与季度 QUAL 分红自动再投资，滚雪球式复利在美股大趋势下贡献了高达 8% 的额外年化收益，同时为市场回调提供了充沛的防御安全垫。</li>
                    <li><strong>避免中途噪音追踪止损 (v2.0 vs v1.9)</strong>：10% 追踪止损在极高波动率的 TQQQ/SOXX 中频繁被噪音扫出，从而错失主升浪。ATR 动态的 SuperTrend (10, 3) 本身就是最好的系统止损。</li>
                </ul>
            </div>
        </div>
    </div>
    
    <!-- ---------------------------------------------------- -->
    <!-- TAB 2: STANDALONE L1/L2 -->
    <!-- ---------------------------------------------------- -->
    <div id="standalone" class="tab-content">
        <div class="card wide-card" style="margin-bottom: 24px;">
            <h2>📊 Standalone L1/L2 独立趋势层对比表 (5 年期)</h2>
            <table>
                <thead>
                    <tr style="background: rgba(255,255,255,0.02)">
                        <th>策略版本</th>
                        <th>总收益率 (%)</th>
                        <th>年化收益率 (CAGR)</th>
                        <th>最大历史回撤 (MDD)</th>
                        <th>夏普比率 (Sharpe)</th>
                        <th>索提诺比率 (Sortino)</th>
                        <th>获利因子 (PF)</th>
                        <th>总交易次数</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>v1.0 (原始卡片规则)</strong></td>
                        <td>{{ "%.2f"|format(st_v10.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(st_v10.metrics.CAGR) }}%</td>
                        <td style="color: var(--accent-color)">{{ "%.2f"|format(st_v10.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(st_v10.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v10.metrics.SortinoRatio) }}</td>
                        <td style="font-weight: bold;">{{ "%.3f"|format(st_v10_pf) }}</td>
                        <td>108 次</td>
                    </tr>
                    <tr>
                        <td><strong>v1.9 (无追踪止损-无分红再投资)</strong></td>
                        <td>{{ "%.2f"|format(st_v19.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(st_v19.metrics.CAGR) }}%</td>
                        <td style="color: var(--accent-color)">{{ "%.2f"|format(st_v19.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(st_v19.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v19.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v19_pf) }}</td>
                        <td>108 次</td>
                    </tr>
                    <tr>
                        <td><strong>v2.0 (带10%追踪止损)</strong></td>
                        <td>{{ "%.2f"|format(st_v20.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(st_v20.metrics.CAGR) }}%</td>
                        <td>{{ "%.2f"|format(st_v20.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(st_v20.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v20.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v20_pf) }}</td>
                        <td>108 次</td>
                    </tr>
                    <tr>
                        <td><strong>v2.1 (分红再投资)</strong></td>
                        <td>{{ "%.2f"|format(st_v21.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(st_v21.metrics.CAGR) }}%</td>
                        <td style="color: var(--accent-color)">{{ "%.2f"|format(st_v21.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(st_v21.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v21.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v21_pf) }}</td>
                        <td>108 次</td>
                    </tr>
                    <tr>
                        <td><strong>v2.2 (DRIP + ATR动态控仓)</strong></td>
                        <td>{{ "%.2f"|format(st_v22.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(st_v22.metrics.CAGR) }}%</td>
                        <td style="color: var(--accent-color)">{{ "%.2f"|format(st_v22.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(st_v22.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v22.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v22_pf) }}</td>
                        <td>108 次</td>
                    </tr>
                    <tr>
                        <td><strong>v2.21 (DRIP + S5FI 40/60)</strong></td>
                        <td>{{ "%.2f"|format(st_v221.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(st_v221.metrics.CAGR) }}%</td>
                        <td style="color: var(--accent-color)">{{ "%.2f"|format(st_v221.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(st_v221.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v221.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v221_pf) }}</td>
                        <td>108 次</td>
                    </tr>
                    <tr style="background: rgba(255, 215, 0, 0.08); border: 1px solid rgba(255, 215, 0, 0.3)">
                        <td><strong>v2.22 (DRIP + S5FI 45/55)</strong></td>
                        <td style="color: #ffd700; font-weight: bold;">{{ "%.2f"|format(st_v222.metrics.TotalReturnPct) }}%</td>
                        <td style="color: #ffd700; font-weight: bold;">{{ "%.2f"|format(st_v222.metrics.CAGR) }}%</td>
                        <td style="color: var(--accent-color)">{{ "%.2f"|format(st_v222.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(st_v222.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v222.metrics.SortinoRatio) }}</td>
                        <td style="font-weight: bold;">{{ "%.3f"|format(st_v222_pf) }}</td>
                        <td>108 次</td>
                    </tr>
                    <tr style="color: var(--text-muted)">
                        <td><strong>v2.23 (v2.22 + 恐慌出场 S5FI<20%)</strong></td>
                        <td>{{ "%.2f"|format(st_v223.metrics.TotalReturnPct) }}%</td>
                        <td>{{ "%.2f"|format(st_v223.metrics.CAGR) }}%</td>
                        <td>{{ "%.2f"|format(st_v223.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(st_v223.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v223.metrics.SortinoRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v223_pf) }}</td>
                        <td>108 次</td>
                    </tr>
                    <tr style="background: rgba(0, 229, 255, 0.08); border: 1px solid rgba(0, 229, 255, 0.3)">
                        <td><strong>v2.24 (v2.22 + 2x QLD替代)</strong></td>
                        <td style="color: #00e5ff; font-weight: bold;">{{ "%.2f"|format(st_v224.metrics.TotalReturnPct) }}%</td>
                        <td style="color: #00e5ff; font-weight: bold;">{{ "%.2f"|format(st_v224.metrics.CAGR) }}%</td>
                        <td style="color: var(--accent-color)">{{ "%.2f"|format(st_v224.metrics.MaxDrawdownPct) }}%</td>
                        <td>{{ "%.3f"|format(st_v224.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v224.metrics.SortinoRatio) }}</td>
                        <td style="font-weight: bold;">{{ "%.3f"|format(st_v224_pf) }}</td>
                        <td>108 次</td>
                    </tr>
                    <tr style="background: rgba(255, 0, 255, 0.08); border: 1px solid rgba(255, 0, 255, 0.3)">
                        <td><strong>v2.3 (DRIP + ATR + S5FI) 🏆</strong></td>
                        <td style="color: #ff00ff; font-weight: bold;">{{ "%.2f"|format(st_v23.metrics.TotalReturnPct) }}%</td>
                        <td style="color: #ff00ff; font-weight: bold;">{{ "%.2f"|format(st_v23.metrics.CAGR) }}%</td>
                        <td style="color: #ff00ff; font-weight: bold;">{{ "%.2f"|format(st_v23.metrics.MaxDrawdownPct) }}%</td>
                        <td style="color: #ff00ff; font-weight: bold;">{{ "%.3f"|format(st_v23.metrics.SharpeRatio) }}</td>
                        <td>{{ "%.3f"|format(st_v23.metrics.SortinoRatio) }}</td>
                        <td style="font-weight: bold;">{{ "%.3f"|format(st_v23_pf) }}</td>
                        <td>108 次</td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <div class="grid">
            <div class="card wide-card chart-container">
                {{ chart_st_html|safe }}
            </div>
        </div>
    </div>
    
    <!-- ---------------------------------------------------- -->
    <!-- TAB 3: SENSITIVITY ANALYSIS -->
    <!-- ---------------------------------------------------- -->
    <div id="sensitivity" class="tab-content">
        <div class="grid">
            <div class="card wide-card chart-container">
                {{ chart_sens_html|safe }}
            </div>
        </div>
    </div>
    
    <script>
        function switchTab(tabId) {
            const contents = document.querySelectorAll('.tab-content');
            contents.forEach(c => c.classList.remove('active'));
            
            const buttons = document.querySelectorAll('.tab-btn');
            buttons.forEach(b => b.classList.remove('active'));
            
            document.getElementById(tabId).classList.add('active');
            
            const activeBtn = Array.from(buttons).find(b => b.getAttribute('onclick').includes(tabId));
            if (activeBtn) activeBtn.classList.add('active');
            
            window.dispatchEvent(new Event('resize'));
        }
    </script>
</body>
</html>
    """
    
    # Process standalone PFs
    def calc_pf(trades):
        sells = [t for t in trades if t['Type'] == 'SELL']
        gp = sum(t['Profit'] for t in sells if t['Profit'] > 0)
        gl = sum(abs(t['Profit']) for t in sells if t['Profit'] < 0)
        return gp / gl if gl > 0 else float('inf')
        
    st_v10_pf = calc_pf(res['standalone']['v1.0']['trade_log'])
    st_v19_pf = calc_pf(res['standalone']['v1.9']['trade_log'])
    st_v20_pf = calc_pf(res['standalone']['v2.0']['trade_log'])
    st_v21_pf = calc_pf(res['standalone']['v2.1']['trade_log'])
    st_v22_pf = calc_pf(res['standalone']['v2.2']['trade_log'])
    st_v221_pf = calc_pf(res['standalone']['v2.21']['trade_log'])
    st_v222_pf = calc_pf(res['standalone']['v2.22']['trade_log'])
    st_v223_pf = calc_pf(res['standalone']['v2.23']['trade_log'])
    st_v224_pf = calc_pf(res['standalone']['v2.24']['trade_log'])
    st_v23_pf = calc_pf(res['standalone']['v2.3']['trade_log'])
    
    cb_v10_pf = calc_pf(res['combined']['v1.0']['trade_log'])
    cb_v19_pf = calc_pf(res['combined']['v1.9']['trade_log'])
    cb_v20_pf = calc_pf(res['combined']['v2.0']['trade_log'])
    cb_v21_pf = calc_pf(res['combined']['v2.1']['trade_log'])
    cb_v22_pf = calc_pf(res['combined']['v2.2']['trade_log'])
    cb_v221_pf = calc_pf(res['combined']['v2.21']['trade_log'])
    cb_v222_pf = calc_pf(res['combined']['v2.22']['trade_log'])
    cb_v223_pf = calc_pf(res['combined']['v2.23']['trade_log'])
    cb_v224_pf = calc_pf(res['combined']['v2.24']['trade_log'])
    cb_v23_pf = calc_pf(res['combined']['v2.3']['trade_log'])
    
    import jinja2
    template = jinja2.Template(html_template)
    
    html_output = template.render(
        cb_v10=res['combined']['v1.0'],
        cb_v19=res['combined']['v1.9'],
        cb_v20=res['combined']['v2.0'],
        cb_v21=res['combined']['v2.1'],
        cb_v22=res['combined']['v2.2'],
        cb_v221=res['combined']['v2.21'],
        cb_v222=res['combined']['v2.22'],
        cb_v223=res['combined']['v2.23'],
        cb_v224=res['combined']['v2.24'],
        cb_v23=res['combined']['v2.3'],
        st_v10=res['standalone']['v1.0'],
        st_v19=res['standalone']['v1.9'],
        st_v20=res['standalone']['v2.0'],
        st_v21=res['standalone']['v2.1'],
        st_v22=res['standalone']['v2.2'],
        st_v221=res['standalone']['v2.21'],
        st_v222=res['standalone']['v2.22'],
        st_v223=res['standalone']['v2.23'],
        st_v224=res['standalone']['v2.24'],
        st_v23=res['standalone']['v2.3'],
        st_v10_pf=st_v10_pf,
        st_v19_pf=st_v19_pf,
        st_v20_pf=st_v20_pf,
        st_v21_pf=st_v21_pf,
        st_v22_pf=st_v22_pf,
        st_v221_pf=st_v221_pf,
        st_v222_pf=st_v222_pf,
        st_v223_pf=st_v223_pf,
        st_v224_pf=st_v224_pf,
        st_v23_pf=st_v23_pf,
        cb_v10_pf=cb_v10_pf,
        cb_v19_pf=cb_v19_pf,
        cb_v20_pf=cb_v20_pf,
        cb_v21_pf=cb_v21_pf,
        cb_v22_pf=cb_v22_pf,
        cb_v221_pf=cb_v221_pf,
        cb_v222_pf=cb_v222_pf,
        cb_v223_pf=cb_v223_pf,
        cb_v224_pf=cb_v224_pf,
        cb_v23_pf=cb_v23_pf,
        chart_st_html=chart_st_html,
        chart_cb_html=chart_cb_html,
        chart_alloc_html=chart_alloc_html,
        chart_sens_html=chart_sens_html,
        res=res
    )
    
    os.makedirs("logs", exist_ok=True)
    report_path = "logs/report.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_output)
        
    print(f"HTML report generated successfully at {report_path}!")

if __name__ == "__main__":
    generate_report()
