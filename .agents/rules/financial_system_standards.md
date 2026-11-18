---
trigger: always_on
description: Financial-grade engineering standards for US Stock Trading System
---

# 金融级系统研发与质量标准 (Mandatory)

本项目涉及真实资金、多券商账户对账、实时信号推送与持仓同步，所有代码改动必须严格遵守以下 5 项红线：

1. **全面严谨设计（Fail-Safe & Idempotency）**：
   - 任何外部 API（Tiger / Schwab / Futu / Supabase / Telegram / Feishu）调用失败、超时或返回非 200 时，**禁止静默降级覆盖真实状态**；发生鉴权或网络异常时，严禁触发 `CLOSED`/清零/删除现有持仓或历史记录。
   - 写库与推送操作必须具备幂等性校验与可观测告警（且告警正文需对 Markdown/JSON 特殊字符做安全转义）。
2. **深刻到位的测试覆盖**：
   - 每次修改或新增逻辑，必须同步补充边界条件、异常分支、Mock 故障注入与数据契约回归测试（`tests/test_v3_suite.py`），禁止只测 Happy Path。
   - 所有涉及资金、份额、净值、回撤、Token、账户归属的变更，提交前必须全量编译检查（`py_compile`）且测试 100% 通过。
3. **杜绝 Hard Coding**：
   - 严禁在 UI、对账或策略逻辑中写死账户余额、持仓股数、标的账户映射死表或环境路径；所有账户归属、余额、持仓与配置均以实时 API / 数据库事实源或环境变量为准。
4. **类型安全与序列化自查**：
   - 禁止对非明确数值列执行无差别 `pd.to_numeric(..., errors='coerce')`；任何字符串字段（如 `refresh_token`、`account`、`category`、`broker`）在云端/本地序列化与反序列化后必须原样保真。
   - 修改函数签名或字段时，必须全局检索所有调用方与云端同步载荷（SQLite 与 Supabase Schema 对齐）。
5. **严格的提交前 Review**：
   - 每次提交前逐行 `git diff` 自查作用域、变量拼写、SQL/REST 参数完整性、敏感凭据隔离（禁止将 Token 写入可提交的 `portfolio.db` 或日志输出）。
