# ⏰ 外部 Cronjob 定时触发设置指南 (External Cronjob Guide)

由于 GitHub 原生的 `schedule` (Actions 定时任务) 存在高峰期严重延迟或偶尔漏触发的已知限制，推荐使用以下两种**外部 Cronjob 触发方式**，实现秒级准时、100% 稳定的每日信号扫描。

---

## 方案 A：外部 Cron 秒级触发 GitHub Action (推荐 🌟)

**核心原理**：在您的外部服务器、群晖 NAS、个人 PC 或免费 Cron 服务上，定时向 GitHub 发送 API 请求。GitHub Actions 接收到 `workflow_dispatch` 后，**会立即在云端分配虚拟机毫秒级响应并运行**，彻底避免了 Actions 内部定时器的延迟。

### 1. 极简 `curl` 命令行触发 (适合 Linux / macOS Cron / NAS)

在您的外部服务器/NAS 上执行 `crontab -e`，添加如下 Cron 条目（美东盘后 16:30，即北京时间次晨 04:30 / 夏令时 04:30）：

```bash
# 北京时间 周二至周六 早上 04:30 执行 (对应美股 Mon-Fri 盘后)
30 4 * * 2-6 curl -X POST -H "Accept: application/vnd.github+json" -H "Authorization: Bearer YOUR_GITHUB_PAT" -H "X-GitHub-Api-Version: 2022-11-28" https://api.github.com/repos/xunxuntj/US_Stock_Trading_Signal_Dashboard/actions/workflows/daily_scan.yml/dispatches -d '{"ref":"main"}'
```

*(注：请将 `YOUR_GITHUB_PAT` 替换为您在 GitHub `Settings -> Developer Settings -> Personal Access Tokens` 生成的个人令牌)*

### 2. Python 触发脚本

```bash
# 外部 Python 定时脚本调用
python3 trigger_github_action.py --token YOUR_GITHUB_PAT --branch main
```

---

## 方案 B：外部服务器 / NAS 本地直接运行并自动 Push

**核心原理**：在您自己的 Linux 服务器 / 群晖 NAS / 树莓派上直接运行 `run_external_cron_scan.sh`，脚本会自动：
1. `git pull --rebase`（拉取网页端最新数据，保证数据防覆盖安全）；
2. 运行 `download_data.py` 和 `run_daily_scan.py`；
3. 自动 Commit & Push 最新的 `portfolio.db` 和 `data/` 到 GitHub。

### 部署步骤：
1. 赋予执行权限：
   ```bash
   chmod +x run_external_cron_scan.sh
   ```
2. 添加 Linux Crontab：
   ```bash
   # 北京时间 周二至周六 早上 04:30 自动本地运行并 Sync 到 GitHub
   30 4 * * 2-6 /bin/bash /path/to/US_Stock_Trading_Signal_Dashboard/run_external_cron_scan.sh >> /path/to/cron.log 2>&1
   ```

---

## 💡 免费第三方 Cron 触发服务推荐 (无需自备服务器)

如果您不想维护自己的服务器，可以使用以下免费秒级 Cron 网页服务来触发 **方案 A 的 URL**：
1. **[cron-job.org](https://cron-job.org/)** (支持 HTTP Header & POST body，免费无限次)
2. **[EasyCron](https://www.easycron.com/)**
3. **[Pipedream](https://pipedream.com/)** / **[Make.com](https://www.make.com/)**
