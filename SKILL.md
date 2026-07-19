---
name: agent-corporate-governance-scanner
description: "公司治理综合评分 Agent。对 A 股上市公司进行 9 维度治理风险打分（0-100）并生成逐项证据链：审计意见、诉讼风险、关联交易、担保风险、合同风险、中介机构、股权性质、违规记录、举牌收购。LLM 编排 + PandaData 数据驱动。"
quantSkills:
  organization: https://github.com/quantskills
  repository: quantskills/agent-corporate-governance-scanner
  repository_url: https://github.com/quantskills/agent-corporate-governance-scanner
  project_type: agent
  collection: governance
  license: GPL-3.0
  category: agent
  tags: [quant, governance, risk, scoring, agent, llm, 诉讼, 关联交易, 担保, 审计, 公司治理]
  platforms: [claude-code, codex, openclaw]
  language: zh
  status: stable
  validation_level: verified
  maintainer_type: community
  requires: [OPENAI_API_KEY, PANDA_DATA_USERNAME, PANDA_DATA_PASSWORD]
  summary_zh: 公司治理综合评分 Agent，9维度治理风险打分+证据链
  summary_en: Corporate governance scoring agent with 9-dimension risk scoring and evidence chains
---

# 公司治理综合评分 Agent

## 适用场景

1. 用户需要评估某只 A 股上市公司的公司治理风险
2. 用户需要了解某公司在诉讼、关联交易、担保、违规等维度的治理表现
3. 用户需要生成公司治理综合评分报告（0-100 分 + 逐项证据链）

## Agent 架构

### 编排维度（9 项）

| 维度 | 权重 | 说明 |
|------|------|------|
| 审计意见 | 15% | 审计意见类型反映财务报告可靠性 |
| 诉讼风险 | 15% | 法律诉讼事件反映公司合规风险 |
| 关联交易 | 12% | 关联方交易可能存在利益输送 |
| 担保风险 | 12% | 对外担保可能带来或有负债 |
| 合同风险 | 8% | 重大合同纠纷反映经营风险 |
| 中介机构 | 8% | 审计/承销机构资质影响信息质量 |
| 股权性质 | 10% | 股权结构影响治理独立性 |
| 违规记录 | 15% | 监管处罚反映合规状况 |
| 举牌收购 | 5% | 股权变动可能影响公司稳定性 |

### 工作流程

```
用户输入股票代码
  → LLM 理解意图，选择治理维度
  → PandaData 获取各维度原始数据
  → 逐维度评分（0-100）+ 证据提取
  → 加权汇总 → 综合治理评分
  → LLM 生成自然语言报告
```

### LLM 编排

- 模型：DeepSeek Chat（可通过 .env 切换）
- 职责：意图理解、工具选择、证据综合、报告生成
- 工具集：9 个维度数据获取函数 + 1 个综合评分函数

## 输入数据

| 数据 | 来源接口 | 说明 |
|------|----------|------|
| 审计意见 | `panda_data.get_audit_opinion` | 最近 8 个季度 |
| 诉讼 | `panda_data.get_litigation` | 诉讼公告 |
| 关联交易 | `panda_data.get_related_party_transaction` | 关联交易明细 |
| 担保 | `panda_data.get_guarantee` | 对外担保 |
| 重大合同 | `panda_data.get_major_contract` | 合同公告 |
| 中介机构 | `panda_data.get_intermediary` | 审计/承销机构 |
| 股权性质 | `panda_data.get_stock_basic` | 股权结构 |
| 违规记录 | `panda_data.get_violation` | 监管处罚 |
| 举牌收购 | `panda_data.get_stock_acquisition` | 股权变动 |

## 输出结果

### 综合评分

| 字段 | 类型 | 说明 |
|------|------|------|
| overall_score | float | 综合治理评分 0-100（越高越好） |
| risk_level | str | low / medium / high |
| dimensions | dict | 各维度得分 + 证据链 |
| report | str | LLM 生成的自然语言报告 |

### 风险等级

- `low`：score >= 80（治理良好）
- `medium`：60 <= score < 80（治理一般）
- `high`：score < 60（治理风险较高）

## 使用方式

### 前置依赖

```bash
pip install openai python-dotenv panda_data
```

### 认证

需要两套认证：

**1. LLM API（默认 DeepSeek）**

```env
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

**2. PandaData**

```env
PANDA_DATA_USERNAME=86手机号
PANDA_DATA_PASSWORD=密码
```

### 运行

```bash
# 直接运行（内置测试用例）
python scripts/agent-corporate-governance-scanner.py

# 或作为模块导入
from agent_corporate_governance_scanner import governance_agent
result = governance_agent("评估平安银行(000001.SZ)的公司治理风险")
```

## 目录结构

```
agent-corporate-governance-scanner/
├── SKILL.md
├── scripts/
│   └── agent-corporate-governance-scanner.py   # Agent 主脚本
├── references/
│   └── source_boundary.md                       # 外部数据边界
├── agents/
│   └── openai.yaml                              # Agent 配置
├── README.md
└── LICENSE
```

## References

Use `references/source_boundary.md`.
