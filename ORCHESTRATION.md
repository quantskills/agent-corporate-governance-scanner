# 多模块编排证据 (Orchestration Evidence)

本文件记录本 Agent「多模块编排」的完整调用链路，并附**真实运行**截取作为证据。
所有数据均来自 `PandaData` 真实接口 + `DeepSeek` 真实 LLM 调用，运行记录见
[`samples/`](./samples) 目录。

---

## 1. 编排总览

用户查询进入唯一入口 [`main.py`](./main.py) 后，经过如下 5 层编排：

```
用户查询 / --symbol
      │
      ▼
[入口层] main.py  ──►  governance_agent()            # 交互 / Agent 模式
      │                     │
      │                     ▼
      │              [决策层] DeepSeek LLM  ──► 输出 Action:calculate_governance_score|{...}
      │                     │
      ▼                     ▼
[编排层] calculate_governance_score(symbol)          # 核心编排函数
      │
      ├─► ensure_panda_data()          # 惰性登录 PandaData（一次）
      │
      ├─► [数据层] 9 个取数模块（治理维度）
      │      ①fetch_audit_opinion          → panda_data.get_audit_opinion
      │      ②fetch_litigation             → get_stock_financial_event / market_event
      │      ③fetch_related_party_transactions → get_stock_rela_party_trans
      │      ④fetch_guarantee              → get_top_holders (质押) / financial_event
      │      ⑤fetch_contract_risk          → get_stock_market_event
      │      ⑥fetch_intermediary_info      → get_stock_intermediary_information
      │      ⑦fetch_equity_nature          → get_top_holders / shareholder_holding
      │      ⑧fetch_violation_records      → get_stock_status_change
      │      ⑨fetch_stock_acquisition      → get_stock_shareholder_change / top_holders
      │
      ├─► [评分引擎] 按 GOVERNANCE_DIMENSIONS 权重加权求和 → overall_score
      │
      ├─► [行业对比] get_industry → get_industry_constituents
      │            └─ ThreadPoolExecutor(max_workers=5) 并发对 ≤10 家同业
      │               调用 calculate_dimension_scores() → 行业平均分
      │
      ▼
[渲染层] generate_evidence_chain(score_data)         # 逐项证据链报告
      │
      ▼
[归纳层] DeepSeek LLM  ──► 自然语言总体评价（--agent / 交互模式）
```

对应源码位置：

| 层 | 函数 | 文件:行 |
|----|------|---------|
| 入口 | `main()` / `run_single()` | `main.py` |
| 决策/归纳 | `governance_agent()` / `llm_call()` | `agent-corporate-governance-scanner.py` |
| 编排 | `calculate_governance_score()` | `agent-corporate-governance-scanner.py:611` |
| 数据 | `fetch_*`（9 个） | `agent-corporate-governance-scanner.py:139-570` |
| 评分引擎 | 权重加权段 | `agent-corporate-governance-scanner.py:632-639` |
| 行业对比 | `get_industry_constituents` + 线程池 | `agent-corporate-governance-scanner.py:650-673` |
| 渲染 | `generate_evidence_chain()` | `agent-corporate-governance-scanner.py:721` |

---

## 2. 权重编排表（评分引擎输入）

9 个模块权重合计 = 100（由 `tests/test_governance.py::test_dimensions_count_and_weight` 守护）：

| 维度 | key | 权重 |
|------|-----|------|
| 审计意见 | audit_opinion | 15 |
| 诉讼风险 | litigation | 15 |
| 违规记录 | violation | 15 |
| 关联交易 | related_party | 12 |
| 担保风险 | guarantee | 12 |
| 股权性质 | equity_nature | 10 |
| 合同风险 | contract | 8 |
| 中介机构 | intermediary | 8 |
| 举牌收购 | stock_acquisition | 5 |

---

## 3. 真实运行证据

### 3.1 平安银行 000001.SZ

- 命令：`python main.py --symbol 000001.SZ`
- 完整记录：[`samples/RUN_RECORD_000001_SZ.log`](./samples/RUN_RECORD_000001_SZ.log)
- 结构化产物：[`samples/000001_SZ_20260805_232443.json`](./samples/000001_SZ_20260805_232443.json)

真实数据要点（证明各模块真的取到了数据，而非默认值）：

- **综合评分 78.6 / 100（良 · 中低风险），数据覆盖率 66.7% (6/9)**
- 行业对比：银行，行业平均 79.6 分（基于 **10 家同业公司并发评分**），相对 -1.0
- ③关联交易：真实取到 **21 笔**，含「中国平安保险(集团)、平安养老、陆金所、平安证券」等关联方
- ⑥中介机构：真实识别审计所为 **安永华明（EY，国际四大）** → 92 分
- ⑦股权性质：真实前十大股东 **中国平安集团 49.56%**、平安人寿 6.11%、香港中央结算 2.94%

### 3.2 贵州茅台 600519.SH

- 命令：`python main.py --symbol 600519.SH`
- 完整记录：[`samples/RUN_RECORD_600519_SH.log`](./samples/RUN_RECORD_600519_SH.log)
- 文本报告产物：[`samples/600519_SH_20260805_232451.txt`](./samples/600519_SH_20260805_232451.txt)

真实数据要点：

- **综合评分 79.2 / 100（良 · 中低风险）**，行业「食品饮料」平均 79.9（10 家同业）
- ③关联交易：真实取到茅台集团及营销公司关联方，`total_amount = 0.02` 亿元
- ⑥中介机构：真实识别审计所为 **天健会计师事务所（非四大）** → 72 分
- ⑦股权性质：真实第一大股东 **茅台集团 54.40%**、贵州省国资 4.55%

---

## 4. 真实运行中发现并修复的问题（证据驱动）

| 问题 | 现象（真实运行） | 修复 |
|------|------------------|------|
| 关联交易金额 NaN | 000001.SZ 首次运行 `total_amount: nan`，导致 JSON 非法 | `fetch_related_party_transactions` 增加 NaN 过滤（`amount == amount`），修复后 `total_amount: 0.28` |
| import 即触发登录 | 无法离线测试 / 离线自检 | 将 `OpenAI` 客户端与 `panda_data.init_token` 改为惰性初始化（`get_client()` / `ensure_panda_data()`） |
| 凭证缓存写入失败 | 部分环境 `PermissionError: user.json` | `ensure_panda_data()` 容忍持久化失败，内存 token 仍可用 |

回归测试见 `tests/test_governance.py::test_result_is_json_serializable`。

---

## 5. 复现方式

```bash
# 离线验证编排链路（不触网）
python main.py --selftest
python tests/test_governance.py

# 真实运行（需在 .env 填入 DeepSeek + PandaData 凭证）
python main.py --symbol 000001.SZ --save samples
python make_run_record.py 000001.SZ 600519.SH
```
