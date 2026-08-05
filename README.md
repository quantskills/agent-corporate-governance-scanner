# 公司治理综合评分 Agent（Corporate Governance Scanner）

> 输入一个股票代码，输出 **0–100 的治理风险评分 + 逐项证据链 + 行业对比**。
> 数据来自 **PandaData** 真实接口，自然语言归纳来自 **DeepSeek** LLM。

本 Agent 编排 9 个治理维度（诉讼 / 关联交易 / 担保 / 合同 / 中介机构 /
股权性质 / 违规 / 举牌收购 / 审计意见），按权重加权得到综合治理评分，并给出
每一项的数据源与证据链，可选与同行业公司做横向对比。

---

## 目录结构

```
agent-corporate-governance-scanner/
├── main.py                                # ★ 唯一入口（CLI）
├── agent-corporate-governance-scanner.py  # 核心：9 维取数 + 评分引擎 + 证据链 + Agent
├── make_run_record.py                     # 真实运行记录器（落盘完整 stdout）
├── .env                                    # 凭证配置（需自行填写）
├── README.md
├── ORCHESTRATION.md                        # 多模块编排证据 + 真实运行截取
├── tests/
│   └── test_governance.py                 # 离线单元测试（不触网）
└── samples/                                # 样例产物 & 真实运行记录
    ├── 000001_SZ_*.json                    # 平安银行 结构化评分
    ├── 600519_SH_*.txt                     # 贵州茅台 证据链报告
    ├── RUN_RECORD_000001_SZ.log            # 真实运行记录
    ├── RUN_RECORD_600519_SH.log
    └── test_run_result.txt                 # 测试运行结果
```

---

## 安装

```bash
pip install openai python-dotenv panda_data
```

要求 Python 3.9+（开发验证于 3.12.10）。

## 配置凭证（.env）

在项目根目录的 [.env](./.env) 中填写：

```ini
OPENAI_API_KEY=你的DeepSeekKey
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat

PANDA_DATA_USERNAME=你的PandaData账号(手机号)
PANDA_DATA_PASSWORD=你的PandaData密码
```

> 未填凭证时，仍可运行 `--selftest` 与单元测试（它们不触网）。

---

## 唯一入口用法（main.py）

所有功能都从 [main.py](./main.py) 进入：

```bash
# 1) 单只股票 → 人类可读的证据链报告
python main.py --symbol 000001.SZ

# 2) 单只股票 → 结构化 JSON（便于存档 / 下游消费）
python main.py --symbol 600519.SH --json

# 3) 走完整 Agent（含 DeepSeek 自然语言总体评价）
python main.py --symbol 002594.SZ --agent

# 4) 批量评估并落盘到 samples/
python main.py --symbols 000001.SZ 600519.SH 002594.SZ --save samples

# 5) 交互模式（自然语言提问）
python main.py --interactive

# 6) 离线自检：验证编排链路与评分引擎（不触网）
python main.py --selftest
```

支持的股票代码：A 股 `.SH` / `.SZ`，港股 `.HK`（如 `00700.HK`）。

### 参数说明

| 参数 | 说明 |
|------|------|
| `--symbol S` | 单只股票代码 |
| `--symbols S1 S2 ...` | 批量股票代码 |
| `--interactive` | 自然语言交互模式 |
| `--selftest` | 离线自检编排链路（不触网） |
| `--json` | 输出结构化 JSON 而非文本报告 |
| `--agent` | 走完整 Agent（含 LLM 归纳） |
| `--save DIR` | 将产物落盘到指定目录 |

---

## 输出说明

**文本报告**（默认）包含：综合评分、风险等级、数据覆盖率、行业对比，以及 9 个维度
逐项的分数 / 权重 / 数据源 / 证据链 / 详情。

**JSON 产物**（`--json`）为结构化对象，主要字段：

| 字段 | 含义 |
|------|------|
| `overall_score` / `overall_level` | 综合评分 / 风险等级 |
| `dimension_results.<dim>` | 每维度的 `score` / `evidence` / `details` / `data_source` / `data_status` |
| `data_coverage` | 成功 / 缺失 / 异常维度计数与覆盖率 |
| `industry_comparison` | 行业名称、行业平均分、相对差、同业样本数 |

### 风险等级映射

| 分数 | 等级 |
|------|------|
| ≥85 | 优（低风险） |
| 70–84 | 良（中低风险） |
| 55–69 | 中（中风险） |
| 40–54 | 差（高风险） |
| <40 | 极差（极高风险） |

---

## 样例产物

| 产物 | 内容 |
|------|------|
| [samples/000001_SZ_*.json](./samples) | 平安银行治理评分 78.6，含 21 笔真实关联交易、平安集团 49.56% 持股 |
| [samples/600519_SH_*.txt](./samples) | 贵州茅台治理评分 79.2，含茅台集团 54.40% 持股、天健审计 |
| [samples/RUN_RECORD_*.log](./samples) | 两只股票的**真实运行记录**（完整 stdout） |
| [samples/test_run_result.txt](./samples/test_run_result.txt) | 单元测试运行结果（8 passed） |

多模块编排链路与真实运行证据详见 [ORCHESTRATION.md](./ORCHESTRATION.md)。

---

## 测试

无需 pytest 亦可运行（内置简易 runner）：

```bash
python tests/test_governance.py
# 或（若已安装 pytest）
python -m pytest tests -v
```

覆盖：维度/权重校验、风险等级映射、市场类型判断、加权评分引擎、证据链渲染、
JSON 可序列化回归（NaN 修复）、入口自检。

---

## 说明与已知限制

- PandaData **未提供 A 股诉讼 / 担保 / 合同的专用接口**，这些维度在 A 股上使用
  行业中性默认值并在证据链中明确标注（`data_status = no_direct_data`），建议结合
  公司公告核实；港股则通过财务/市场事件接口取数。
- 评分含缓存：综合报告缓存 5 分钟，单股评分缓存 1 小时（用于行业对比并发提速）。
- LLM 归纳（`--agent` / 交互模式）会消耗 DeepSeek 额度；`--symbol`（默认）与
  `--json` 不调用 LLM，只做取数 + 评分 + 证据链。
