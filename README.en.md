# Corporate Governance Scoring Agent

**简体中文** | English

> A-share corporate governance risk scoring agent: 9-dimension scoring (0-100) with evidence chains. LLM-orchestrated + PandaData-driven.

![type](https://img.shields.io/badge/type-agent-blue)
![license](https://img.shields.io/badge/license-GPLv3-blue)

---

## What This Is

This agent scores A-share listed companies on corporate governance across 9 dimensions:

- Audit Opinion (15%) — financial reporting reliability
- Litigation Risk (15%) — legal compliance
- Related Party Transactions (12%) — related-party dealing risks
- Guarantee Risk (12%) — contingent liabilities from external guarantees
- Contract Risk (8%) — major contract disputes
- Intermediary Quality (8%) — auditor/underwriter quality
- Equity Nature (10%) — ownership structure independence
- Violation Records (15%) — regulatory penalties
- Stock Acquisition (5%) — equity ownership changes

## Quick Start

```bash
pip install openai python-dotenv panda_data
```

Configure `.env`:

```env
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
PANDA_DATA_USERNAME=your_phone
PANDA_DATA_PASSWORD=your_password
```

Run:

```bash
python scripts/agent-corporate-governance-scanner.py
```

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
