# 公司治理综合评分 Agent

**简体中文** | [English](README.en.md)

> A 股上市公司治理风险评分 Agent：9 维度打分（0-100）+ 逐项证据链。LLM 编排 + PandaData 数据驱动。

![type](https://img.shields.io/badge/type-agent-blue)
![license](https://img.shields.io/badge/license-GPLv3-blue)

---

## 这是什么

本 Agent 对 A 股上市公司进行公司治理综合评分，覆盖 9 个核心维度：

| 维度 | 权重 | 数据来源 |
|------|------|----------|
| 审计意见 | 15% | `panda_data.get_audit_opinion` |
| 诉讼风险 | 15% | `panda_data.get_litigation` |
| 关联交易 | 12% | `panda_data.get_related_party_transaction` |
| 担保风险 | 12% | `panda_data.get_guarantee` |
| 合同风险 | 8% | `panda_data.get_major_contract` |
| 中介机构 | 8% | `panda_data.get_intermediary` |
| 股权性质 | 10% | `panda_data.get_stock_basic` |
| 违规记录 | 15% | `panda_data.get_violation` |
| 举牌收购 | 5% | `panda_data.get_stock_acquisition` |

## 工作流程

```
用户输入 → LLM 意图理解 → PandaData 数据获取 → 逐维度评分+证据 → 加权汇总 → LLM 报告生成
```

## 快速开始

### 前置依赖

```bash
pip install openai python-dotenv panda_data
```

### 配置

创建 `.env` 文件：

```env
# LLM API（默认 DeepSeek，也支持 OpenAI 兼容接口）
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat

# PandaData
PANDA_DATA_USERNAME=86手机号
PANDA_DATA_PASSWORD=密码
```

### 运行

```bash
python scripts/agent-corporate-governance-scanner.py
```

内置测试用例：
- 评估平安银行(000001.SZ)的公司治理风险
- 贵州茅台(600519.SH)的治理评分是多少？
- 比亚迪(002594.SZ)的治理风险评估

### 作为模块使用

```python
from agent_corporate_governance_scanner import governance_agent

result = governance_agent("评估平安银行(000001.SZ)的公司治理风险")
print(result)
```

## 目录结构

```
agent-corporate-governance-scanner/
├── SKILL.md                              # 技能定义
├── scripts/
│   └── agent-corporate-governance-scanner.py  # Agent 主脚本
├── references/
│   └── source_boundary.md                # 外部数据边界
├── agents/
│   └── openai.yaml                       # Agent 配置
├── README.md
└── LICENSE
```

## 核心约束

| 约束 | 说明 |
| --- | --- |
| 只用 PandaData 数据 | 所有数据来自 panda_data SDK |
| 只述不荐 | 输出研究结构与事实归纳，不构成任何投资建议 |
| A 股为主 | 当前仅支持 A 股上市公司 |

---

## ⚠️ 免责声明

本仓库仅作研究方法层面的整理，非官方、不隶属任何被研究对象，不验证任何收益声明，不构成任何投资建议。

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).

## QUANTSKILLS 社群

<div align="center">
  <img src="https://raw.githubusercontent.com/quantskills/.github/main/profile/assets/pandaai-community-qr.jpg" alt="PandaAI 社群二维码" width="220">
  <br>
  <sub>扫码加入 PandaAI 社群，交流 QUANTSKILLS 技能、Agent 工作流与量化研究实践。</sub>
</div>
