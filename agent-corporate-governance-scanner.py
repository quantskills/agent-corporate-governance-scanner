"""
公司治理综合评分 Agent - 治理风险 0-100 打分 + 逐项证据链
编排维度：诉讼/关联/担保/合同/中介/股权性质/违规/举牌/审计意见
"""
import sys
import os
import json
import datetime
import time
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from openai import OpenAI
from dotenv import load_dotenv
import panda_data

SCORE_CACHE = {}
FULL_REPORT_CACHE = {}
CACHE_EXPIRE_SECONDS = 3600
FULL_REPORT_CACHE_SECONDS = 300

load_dotenv()

# ============ LLM 配置 ============

MODEL = os.getenv("OPENAI_MODEL", "deepseek-chat")

_client = None


def get_client() -> OpenAI:
    """惰性创建 OpenAI 客户端，避免在离线/测试环境下 import 即失败"""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
        )
    return _client


# ============ PandaData 初始化 ============

_panda_inited = False


def ensure_panda_data() -> None:
    """惰性登录 PandaData，只在首次真正取数时执行一次"""
    global _panda_inited
    if _panda_inited:
        return
    try:
        panda_data.init_token(
            username=os.getenv("PANDA_DATA_USERNAME"),
            password=os.getenv("PANDA_DATA_PASSWORD"),
        )
    except PermissionError:
        # 某些环境下 panda_data 无法把凭证缓存写入安装目录（user.json），
        # 但内存中的 token 通常已获取成功；此处容忍持久化失败，继续取数。
        pass
    _panda_inited = True

# ============ 治理维度定义 ============

GOVERNANCE_DIMENSIONS = {
    "audit_opinion": {"name": "审计意见", "weight": 15, "description": "审计意见类型反映财务报告可靠性"},
    "litigation": {"name": "诉讼风险", "weight": 15, "description": "法律诉讼事件反映公司合规风险"},
    "related_party": {"name": "关联交易", "weight": 12, "description": "关联方交易可能存在利益输送"},
    "guarantee": {"name": "担保风险", "weight": 12, "description": "对外担保可能带来或有负债"},
    "contract": {"name": "合同风险", "weight": 8, "description": "重大合同纠纷反映经营风险"},
    "intermediary": {"name": "中介机构", "weight": 8, "description": "审计/承销机构资质影响信息质量"},
    "equity_nature": {"name": "股权性质", "weight": 10, "description": "股权结构影响治理独立性"},
    "violation": {"name": "违规记录", "weight": 15, "description": "监管处罚反映合规状况"},
    "stock_acquisition": {"name": "举牌收购", "weight": 5, "description": "股权变动可能影响公司稳定性"},
}

INDUSTRY_BASELINE = {}

# ============ 数据获取辅助函数 ============

def get_market_type(symbol: str) -> str:
    """判断股票市场类型"""
    if symbol.endswith(".SH"):
        return "cn"
    elif symbol.endswith(".SZ"):
        return "cn"
    elif symbol.endswith(".HK"):
        return "hk"
    return "cn"


def get_industry(symbol: str) -> tuple:
    """Return the market-specific documented industry name and code."""
    try:
        if get_market_type(symbol) == "hk":
            df = panda_data.get_hk_detail(symbol=[symbol], fields=["industry_group"])
            if df is not None and not df.empty:
                return str(df.iloc[0].get("industry_group", "")), ""
        else:
            df = panda_data.get_stock_industry(stock_symbol=[symbol])
            if df is not None and not df.empty:
                return str(df.iloc[0].get("industry_name", "")), str(df.iloc[0].get("industry_code", ""))
        return "其他", ""
    except Exception:
        return "其他", ""

def get_last_n_years_dates(n: int = 1) -> tuple:
    """获取最近n年的日期范围"""
    end_date = datetime.datetime.now().strftime("%Y%m%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=n*365)).strftime("%Y%m%d")
    return start_date, end_date

def get_last_n_quarters(n: int = 4) -> tuple:
    """获取最近n个季度的范围"""
    now = datetime.datetime.now()
    end_year = now.year
    end_quarter = (now.month - 1) // 3 + 1
    
    start_month = now.month - (n - 1) * 3
    start_year = end_year
    
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    
    start_quarter = (start_month - 1) // 3 + 1
    
    end_quarter_str = f"{end_year}q{end_quarter}"
    start_quarter_str = f"{start_year}q{start_quarter}"
    
    return start_quarter_str, end_quarter_str

# ============ 治理数据获取工具 ============

def fetch_audit_opinion(symbol: str) -> Dict:
    """获取审计意见数据"""
    try:
        market = get_market_type(symbol)
        start_q, end_q = get_last_n_quarters(8)
        df = panda_data.get_audit_opinion(symbol, start_quarter=start_q, end_quarter=end_q, market=market)
        
        if df is None or df.empty:
            return {"score": 75, "evidence": ["暂无审计意见数据，按行业平均评估"], "details": {}, "data_source": "panda_data.get_audit_opinion", "data_status": "missing"}
        
        opinions = []
        risk_count = 0
        standard_count = 0
        
        for _, row in df.iterrows():
            opinion = str(row.get("audit_opinion", ""))
            if opinion:
                opinions.append(opinion)
                if "标准无保留" in opinion or "无保留意见" in opinion:
                    standard_count += 1
                elif "保留" in opinion or "否定" in opinion or "无法表示" in opinion:
                    risk_count += 1
        
        if risk_count > 0:
            score = max(0, 80 - risk_count * 20)
            evidence = [f"发现{risk_count}项非标准审计意见"] + opinions[-3:]
        else:
            score = 95
            evidence = [f"最近{len(opinions)}次审计均为标准无保留意见"]
        
        return {"score": score, "evidence": evidence, "details": {"opinion_count": len(opinions), "standard_count": standard_count, "risk_count": risk_count}, 
                "data_source": "panda_data.get_audit_opinion", "data_status": "success"}
    except Exception as e:
        return {"score": 70, "evidence": [f"获取审计意见异常: {str(e)[:50]}"], "details": {}, 
                "data_source": "panda_data.get_audit_opinion", "data_status": "error"}


def fetch_litigation(symbol: str) -> Dict:
    """获取诉讼风险数据"""
    try:
        start_date, end_date = get_last_n_years_dates(2)
        market = get_market_type(symbol)
        
        litigation_events = []
        
        if market == "hk":
            df_fin = panda_data.get_stock_financial_event(symbol, start_date, end_date)
            df_mkt = panda_data.get_stock_market_event(symbol, start_date, end_date)
            
            if df_fin is not None and not df_fin.empty:
                for _, row in df_fin.iterrows():
                    event_type = str(row.get("event_type", ""))
                    event_desc = str(row.get("event_desc", ""))
                    event_date = str(row.get("event_date", ""))
                    if "诉讼" in event_type or "诉讼" in event_desc or "仲裁" in event_desc or "纠纷" in event_desc:
                        litigation_events.append(f"{event_date}: {event_desc[:50]}")
            
            if df_mkt is not None and not df_mkt.empty:
                for _, row in df_mkt.iterrows():
                    event_type = str(row.get("event_type", ""))
                    event_desc = str(row.get("event_desc", ""))
                    event_date = str(row.get("event_date", ""))
                    if "诉讼" in event_type or "诉讼" in event_desc or "仲裁" in event_desc or "纠纷" in event_desc:
                        litigation_events.append(f"{event_date}: {event_desc[:50]}")
        
        if len(litigation_events) == 0:
            if market == "hk":
                return {"score": 90, "evidence": ["近2年无诉讼/仲裁/纠纷事件记录"], "details": {"event_count": 0}, 
                        "data_source": "panda_data.get_stock_financial_event + get_stock_market_event", "data_status": "success"}
            else:
                return {"score": 75, "evidence": ["PandaData未提供A股诉讼专用接口，无法获取直接数据", "评分基于行业中性默认值，建议结合公司公告进一步核实"], "details": {"event_count": 0}, 
                        "data_source": "无专用接口", "data_status": "no_direct_data"}
        
        score = max(0, 90 - len(litigation_events) * 8)
        return {"score": score, "evidence": litigation_events[:5], "details": {"event_count": len(litigation_events)}, 
                "data_source": "panda_data.get_stock_financial_event + get_stock_market_event", "data_status": "success"}
    except Exception as e:
        return {"score": 75, "evidence": [f"获取诉讼数据异常: {str(e)[:50]}", "评分基于行业中性默认值"], "details": {}, 
                "data_source": "panda_data.get_stock_financial_event", "data_status": "error"}


def fetch_related_party_transactions(symbol: str) -> Dict:
    """获取关联交易数据"""
    try:
        start_date, end_date = get_last_n_years_dates(2)
        market = get_market_type(symbol)
        
        if market == "cn":
            df = panda_data.get_stock_rela_party_trans(symbol, start_date, end_date)
        else:
            df = panda_data.get_stock_market_event(symbol, start_date, end_date)
        
        related_events = []
        total_amount = 0
        
        if df is not None and not df.empty:
            if market == "cn":
                for _, row in df.iterrows():
                    info_date = str(row.get("info_date", ""))
                    party_name = str(row.get("party_name", ""))
                    relation = str(row.get("relation", ""))
                    try:
                        amount = float(row.get("amount", 0))
                    except (TypeError, ValueError):
                        amount = 0.0
                    if amount == amount:  # 过滤 NaN（NaN != NaN）
                        total_amount += amount
                    related_events.append(f"{info_date}: {party_name}({relation})")
            else:
                for _, row in df.iterrows():
                    event_type = str(row.get("event_type", ""))
                    event_desc = str(row.get("event_desc", ""))
                    event_date = str(row.get("event_date", ""))
                    if "关联" in event_type or "关联" in event_desc:
                        related_events.append(f"{event_date}: {event_desc[:50]}")
        
        if len(related_events) == 0:
            return {"score": 85, "evidence": ["近2年无重大关联交易披露"], "details": {"transaction_count": 0, "total_amount": 0}, 
                    "data_source": "panda_data.get_stock_rela_party_trans", "data_status": "success"}
        
        score = max(0, 85 - min(len(related_events), 10) * 3)
        evidence = related_events[:5]
        if total_amount > 0:
            evidence.append(f"关联交易总金额: {total_amount/100000000:.2f}亿元")
        
        return {"score": score, "evidence": evidence, "details": {"transaction_count": len(related_events), "total_amount": round(total_amount/100000000, 2)}, 
                "data_source": "panda_data.get_stock_rela_party_trans", "data_status": "success"}
    except Exception as e:
        return {"score": 70, "evidence": [f"获取关联交易数据异常: {str(e)[:50]}"], "details": {}, 
                "data_source": "panda_data.get_stock_rela_party_trans", "data_status": "error"}


def fetch_guarantee(symbol: str) -> Dict:
    """获取担保风险数据（间接评估）"""
    try:
        start_date, end_date = get_last_n_years_dates(2)
        start_q, end_q = get_last_n_quarters(8)
        market = get_market_type(symbol)
        
        guarantee_events = []
        pledge_events = []
        pledge_count = 0
        
        if market == "hk":
            df_fin = panda_data.get_stock_financial_event(symbol, start_date, end_date)
            df_mkt = panda_data.get_stock_market_event(symbol, start_date, end_date)
            
            if df_fin is not None and not df_fin.empty:
                for _, row in df_fin.iterrows():
                    event_type = str(row.get("event_type", ""))
                    event_desc = str(row.get("event_desc", ""))
                    event_date = str(row.get("event_date", ""))
                    if "担保" in event_type or "担保" in event_desc or "抵押" in event_desc:
                        guarantee_events.append(f"{event_date}: {event_desc[:50]}")
            
            if df_mkt is not None and not df_mkt.empty:
                for _, row in df_mkt.iterrows():
                    event_type = str(row.get("event_type", ""))
                    event_desc = str(row.get("event_desc", ""))
                    event_date = str(row.get("event_date", ""))
                    if "担保" in event_type or "担保" in event_desc:
                        guarantee_events.append(f"{event_date}: {event_desc[:50]}")
        else:
            df_top = panda_data.get_top_holders(symbol, start_date, end_date, start_rank=1, end_rank=10, market="cn")
            if df_top is not None and not df_top.empty:
                seen_holders = set()
                for _, row in df_top.iterrows():
                    holder_name = str(row.get("holder_name", "")) if "holder_name" in df_top.columns else str(row.get("holder", ""))
                    if holder_name in seen_holders:
                        continue
                    seen_holders.add(holder_name)
                    
                    pledge_info = str(row.get("pledge", ""))
                    if pledge_info and pledge_info.lower() != "nan" and pledge_info != "None" and pledge_info != "none":
                        pledge_count += 1
                        pledge_events.append(f"{str(row.get('date', ''))}: {holder_name}存在股权质押")
        
        if len(guarantee_events) == 0 and len(pledge_events) == 0:
            if market == "hk":
                return {"score": 88, "evidence": ["近2年无对外担保/股权质押事件记录"], "details": {"guarantee_count": 0, "pledge_count": 0}, 
                        "data_source": "panda_data.get_stock_financial_event + get_stock_market_event", "data_status": "success"}
            else:
                return {"score": 78, "evidence": ["PandaData未提供A股担保专用接口，无法获取对外担保金额数据", "评分基于行业中性默认值，建议结合公司公告进一步核实"], "details": {"guarantee_count": 0, "pledge_count": 0}, 
                        "data_source": "无专用接口", "data_status": "no_direct_data"}
        
        score = max(0, 88 - len(guarantee_events) * 5 - pledge_count * 3)
        evidence = guarantee_events[:3] + pledge_events[:2]
        if market != "hk":
            evidence.append("注：PandaData无A股担保专用接口，股权质押数据来自股东持股信息")
        
        return {"score": score, "evidence": evidence, "details": {"guarantee_count": len(guarantee_events), "pledge_count": pledge_count}, 
                "data_source": "panda_data.get_top_holders", "data_status": "success"}
    except Exception as e:
        return {"score": 75, "evidence": [f"获取担保数据异常: {str(e)[:50]}", "评分基于行业中性默认值"], "details": {}, 
                "data_source": "panda_data.get_top_holders", "data_status": "error"}


def fetch_contract_risk(symbol: str) -> Dict:
    """获取合同风险数据"""
    try:
        start_date, end_date = get_last_n_years_dates(2)
        market = get_market_type(symbol)
        
        contract_events = []
        
        if market == "hk":
            df = panda_data.get_stock_market_event(symbol, start_date, end_date)
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    event_type = str(row.get("event_type", ""))
                    event_desc = str(row.get("event_desc", ""))
                    event_date = str(row.get("event_date", ""))
                    if "合同" in event_type or "合同" in event_desc or "协议" in event_desc:
                        contract_events.append(f"{event_date}: {event_desc[:50]}")
        
        if len(contract_events) == 0:
            if market == "hk":
                return {"score": 88, "evidence": ["近2年无重大合同纠纷记录"], "details": {"contract_count": 0}, 
                        "data_source": "panda_data.get_stock_market_event", "data_status": "success"}
            else:
                return {"score": 75, "evidence": ["PandaData未提供A股合同专用接口，无法获取直接数据", "评分基于行业中性默认值，建议结合公司公告进一步核实"], "details": {"contract_count": 0}, 
                        "data_source": "无专用接口", "data_status": "no_direct_data"}
        
        score = max(0, 88 - min(len(contract_events), 10) * 3)
        return {"score": score, "evidence": contract_events[:5], "details": {"contract_count": len(contract_events)}, 
                "data_source": "panda_data.get_stock_market_event", "data_status": "success"}
    except Exception as e:
        return {"score": 75, "evidence": [f"获取合同数据异常: {str(e)[:50]}", "评分基于行业中性默认值"], "details": {}, 
                "data_source": "panda_data.get_stock_market_event", "data_status": "error"}


def fetch_intermediary_info(symbol: str) -> Dict:
    """获取中介机构信息"""
    try:
        start_date, end_date = get_last_n_years_dates(2)
        market = get_market_type(symbol)
        
        df = panda_data.get_stock_intermediary_information(start_date, end_date, symbol)
        
        if df is None or df.empty:
            return {"score": 75, "evidence": ["暂无中介机构数据，按行业平均评估"], "details": {}, 
                    "data_source": "panda_data.get_stock_intermediary_information", "data_status": "missing"}
        
        intermediaries = []
        auditors = []
        
        for _, row in df.iterrows():
            name = str(row.get("intermediary_name", ""))
            category = str(row.get("intermediary_category", ""))
            intermediaries.append(f"{category}: {name}")
            if "审计" in category or "会计师" in name:
                auditors.append(name)
        
        big4_firms = ["普华永道", "德勤", "毕马威", "安永", "PwC", "Deloitte", "KPMG", "EY"]
        has_big4 = any(firm.lower() in ' '.join(auditors).lower() for firm in big4_firms)
        
        if has_big4:
            score = 92
            evidence = ["审计机构为国际四大会计师事务所"] + auditors[:2]
        else:
            score = 72
            evidence = ["审计机构非国际四大"] + auditors[:2]
        
        return {"score": score, "evidence": evidence, "details": {"intermediary_count": len(intermediaries), "auditor_count": len(auditors), "has_big4": has_big4}, 
                "data_source": "panda_data.get_stock_intermediary_information", "data_status": "success"}
    except Exception as e:
        return {"score": 70, "evidence": [f"获取中介机构数据异常: {str(e)[:50]}"], "details": {}, 
                "data_source": "panda_data.get_stock_intermediary_information", "data_status": "error"}


def fetch_equity_nature(symbol: str) -> Dict:
    """获取股权性质数据"""
    try:
        start_date, end_date = get_last_n_years_dates(1)
        market = get_market_type(symbol)
        
        if market == "cn":
            df = panda_data.get_top_holders(symbol, start_date, end_date, start_rank=1, end_rank=10, market="cn")
        else:
            df = panda_data.get_stock_shareholder_holding(symbol, start_date, end_date)
        
        if df is None or df.empty:
            return {"score": 72, "evidence": ["暂无股东持股数据，按行业平均评估"], "details": {}, 
                    "data_source": "panda_data.get_top_holders", "data_status": "missing"}
        
        top_holders = []
        total_ratio = 0
        has_institutional = False
        has_foreign = False
        pledge_count = 0
        pledge_holders = set()
        seen_holders = set()
        
        latest_date = df['date'].max() if 'date' in df.columns else None
        
        for _, row in df.iterrows():
            if latest_date and 'date' in df.columns and str(row['date']) != str(latest_date):
                continue
                
            holder_name = str(row.get("holder_name", "")) if "holder_name" in df.columns else str(row.get("holder", ""))
            
            if holder_name in seen_holders:
                continue
            seen_holders.add(holder_name)
            
            holding_ratio = float(row.get("hold_percent_total", 0)) if "hold_percent_total" in df.columns else float(row.get("holding_ratio", 0))
            holder_type = str(row.get("holder_type", ""))
            holder_attr = str(row.get("holder_attr", ""))
            pledge_info = str(row.get("pledge", ""))
            
            total_ratio += holding_ratio
            
            if "外资" in holder_type or "foreign" in holder_type.lower():
                has_foreign = True
            if "机构" in holder_attr or "证券" in holder_attr:
                has_institutional = True
            if pledge_info and pledge_info.lower() != "nan" and pledge_info != "None" and pledge_info != "none":
                if holder_name not in pledge_holders:
                    pledge_count += 1
                    pledge_holders.add(holder_name)
            
            if len(top_holders) < 5:
                top_holders.append(f"{holder_name}: {holding_ratio:.2f}%")
        
        total_ratio = min(total_ratio, 100)
        
        if total_ratio >= 60:
            score = 65
            evidence = ["股权集中度较高，可能影响治理独立性"]
        elif total_ratio >= 40:
            score = 75
            evidence = ["股权集中度适中"]
        else:
            score = 82
            evidence = ["股权分散度较好"]
        
        if has_institutional:
            evidence.append("机构投资者参与度较高")
        if has_foreign:
            evidence.append("外资股东持股")
        if pledge_count > 0:
            evidence.append(f"存在{pledge_count}位股东质押")
        
        evidence += top_holders[:3]
        
        return {"score": score, "evidence": evidence, "details": {"top10_ratio_sum": round(total_ratio, 2), "has_institutional": has_institutional, "has_foreign": has_foreign, "pledge_count": pledge_count}, 
                "data_source": "panda_data.get_top_holders", "data_status": "success"}
    except Exception as e:
        return {"score": 70, "evidence": [f"获取股权数据异常: {str(e)[:50]}"], "details": {}, 
                "data_source": "panda_data.get_top_holders", "data_status": "error"}


def fetch_violation_records(symbol: str) -> Dict:
    """获取违规记录数据"""
    try:
        start_date, end_date = get_last_n_years_dates(2)
        market = get_market_type(symbol)
        
        violation_events = []
        
        df_status = panda_data.get_stock_status_change(symbol, start_date, end_date)
        if df_status is not None and not df_status.empty:
            for _, row in df_status.iterrows():
                event_type = str(row.get("event_type", ""))
                event_desc = str(row.get("event_desc", ""))
                event_date = str(row.get("event_date", ""))
                if any(keyword in event_type or keyword in event_desc for keyword in ["处罚", "违规", "警示", "监管", "谴责", "停牌"]):
                    violation_events.append(f"{event_date}: {event_desc[:50]}")
        
        if market == "hk":
            df_fin = panda_data.get_stock_financial_event(symbol, start_date, end_date)
            df_mkt = panda_data.get_stock_market_event(symbol, start_date, end_date)
            for df in [df_fin, df_mkt]:
                if df is None or df.empty:
                    continue
                for _, row in df.iterrows():
                    event_type = str(row.get("event_type", ""))
                    event_desc = str(row.get("event_desc", ""))
                    event_date = str(row.get("event_date", ""))
                    if any(keyword in event_type or keyword in event_desc for keyword in ["处罚", "违规", "警示", "监管", "谴责", "停牌"]):
                        violation_events.append(f"{event_date}: {event_desc[:50]}")
        
        if len(violation_events) == 0:
            return {"score": 88, "evidence": ["近2年无违规处罚/监管警示记录"], "details": {"violation_count": 0}, 
                    "data_source": "panda_data.get_stock_status_change", "data_status": "success"}
        
        score = max(0, 88 - len(violation_events) * 10)
        return {"score": score, "evidence": violation_events[:5], "details": {"violation_count": len(violation_events)}, 
                "data_source": "panda_data.get_stock_status_change", "data_status": "success"}
    except Exception as e:
        return {"score": 75, "evidence": [f"获取违规记录异常: {str(e)[:50]}"], "details": {}, 
                "data_source": "panda_data.get_stock_status_change", "data_status": "error"}


def fetch_stock_acquisition(symbol: str) -> Dict:
    """获取举牌收购数据"""
    try:
        start_date, end_date = get_last_n_years_dates(2)
        market = get_market_type(symbol)
        
        acquisition_events = []
        
        if market == "hk":
            df = panda_data.get_stock_market_event(symbol, start_date, end_date)
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    event_type = str(row.get("event_type", ""))
                    event_desc = str(row.get("event_desc", ""))
                    event_date = str(row.get("event_date", ""))
                    if "举牌" in event_type or "举牌" in event_desc or "收购" in event_desc:
                        acquisition_events.append(f"{event_date}: {event_desc[:50]}")
        else:
            df_shareholder = panda_data.get_stock_shareholder_change(symbol, start_date, end_date)
            df_top = panda_data.get_top_holders(symbol, start_date, end_date, start_rank=1, end_rank=10, market="cn")
            
            if df_shareholder is not None and not df_shareholder.empty:
                for _, row in df_shareholder.head(5).iterrows():
                    change_date = str(row.get("change_date", ""))
                    change_type = str(row.get("change_type", ""))
                    acquisition_events.append(f"{change_date}: 股东变更({change_type})")
            
            if df_top is not None and not df_top.empty:
                recent_date = df_top['date'].max() if 'date' in df_top.columns else ""
                acquisition_events.append(f"{recent_date}: 前十大股东持股变动数据更新")
        
        if len(acquisition_events) == 0:
            return {"score": 88, "evidence": ["近2年无举牌收购/重大股权变更事件"], "details": {"acquisition_count": 0}, 
                    "data_source": "panda_data.get_stock_shareholder_change + get_top_holders", "data_status": "success"}
        
        score = max(50, 88 - len(acquisition_events) * 6)
        return {"score": score, "evidence": acquisition_events[:3], "details": {"acquisition_count": len(acquisition_events)}, 
                "data_source": "panda_data.get_stock_shareholder_change + get_top_holders", "data_status": "success"}
    except Exception as e:
        return {"score": 75, "evidence": [f"获取举牌收购数据异常: {str(e)[:50]}"], "details": {}, 
                "data_source": "panda_data.get_stock_shareholder_change", "data_status": "error"}


# ============ 评分引擎 ============

def calculate_dimension_scores(symbol: str) -> float:
    """仅计算股票的治理综合评分（用于行业对比）"""
    now = time.time()

    if symbol in SCORE_CACHE:
        cached = SCORE_CACHE[symbol]
        if now - cached["timestamp"] < CACHE_EXPIRE_SECONDS:
            return cached["score"]

    try:
        ensure_panda_data()
        dimension_results = {}
        dimension_results["audit_opinion"] = fetch_audit_opinion(symbol)
        dimension_results["litigation"] = fetch_litigation(symbol)
        dimension_results["related_party"] = fetch_related_party_transactions(symbol)
        dimension_results["guarantee"] = fetch_guarantee(symbol)
        dimension_results["contract"] = fetch_contract_risk(symbol)
        dimension_results["intermediary"] = fetch_intermediary_info(symbol)
        dimension_results["equity_nature"] = fetch_equity_nature(symbol)
        dimension_results["violation"] = fetch_violation_records(symbol)
        dimension_results["stock_acquisition"] = fetch_stock_acquisition(symbol)
        
        total_weight = sum(d["weight"] for d in GOVERNANCE_DIMENSIONS.values())
        weighted_score = 0
        
        for dim_key, dim_config in GOVERNANCE_DIMENSIONS.items():
            dim_result = dimension_results[dim_key]
            weighted_score += dim_result["score"] * (dim_config["weight"] / total_weight)
        
        score = round(weighted_score, 1)
        SCORE_CACHE[symbol] = {"score": score, "timestamp": now}
        return score
    except Exception:
        return None


def calculate_governance_score(symbol: str) -> Dict:
    """计算公司治理综合评分"""
    now = time.time()
    
    if symbol in FULL_REPORT_CACHE:
        cached = FULL_REPORT_CACHE[symbol]
        if now - cached["timestamp"] < FULL_REPORT_CACHE_SECONDS:
            return cached["result"]

    ensure_panda_data()
    dimension_results = {}

    dimension_results["audit_opinion"] = fetch_audit_opinion(symbol)
    dimension_results["litigation"] = fetch_litigation(symbol)
    dimension_results["related_party"] = fetch_related_party_transactions(symbol)
    dimension_results["guarantee"] = fetch_guarantee(symbol)
    dimension_results["contract"] = fetch_contract_risk(symbol)
    dimension_results["intermediary"] = fetch_intermediary_info(symbol)
    dimension_results["equity_nature"] = fetch_equity_nature(symbol)
    dimension_results["violation"] = fetch_violation_records(symbol)
    dimension_results["stock_acquisition"] = fetch_stock_acquisition(symbol)
    
    total_weight = sum(d["weight"] for d in GOVERNANCE_DIMENSIONS.values())
    weighted_score = 0
    
    for dim_key, dim_config in GOVERNANCE_DIMENSIONS.items():
        dim_result = dimension_results[dim_key]
        weighted_score += dim_result["score"] * (dim_config["weight"] / total_weight)
    
    overall_score = round(weighted_score, 1)
    
    success_count = sum(1 for r in dimension_results.values() if r["data_status"] == "success")
    missing_count = sum(1 for r in dimension_results.values() if r["data_status"] == "missing")
    error_count = sum(1 for r in dimension_results.values() if r["data_status"] == "error")
    
    industry_name, industry_code = get_industry(symbol)
    
    industry_avg_score = None
    sample_count = 0
    
    if industry_code:
        try:
            df_constituents = panda_data.get_industry_constituents(industry_code)
            if df_constituents is not None and not df_constituents.empty:
                peer_symbols = df_constituents['stock_symbol'].tolist()
                peer_symbols = [s for s in peer_symbols if s != symbol][:10]
                
                if peer_symbols:
                    scores = []
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        future_to_symbol = {executor.submit(calculate_dimension_scores, peer): peer for peer in peer_symbols}
                        for future in as_completed(future_to_symbol):
                            try:
                                result = future.result()
                                if result:
                                    scores.append(result)
                            except Exception:
                                continue
                    
                    if scores:
                        industry_avg_score = round(sum(scores) / len(scores), 1)
                        sample_count = len(scores)
        except Exception:
            pass
    
    vs_industry = round(overall_score - industry_avg_score, 1) if industry_avg_score is not None else None
    comparison_status = f"基于{sample_count}家同业公司" if industry_avg_score is not None else "暂不可用"
    
    industry_comparison = {
        "industry": industry_name,
        "industry_code": industry_code,
        "industry_avg_score": industry_avg_score,
        "vs_industry": vs_industry,
        "comparison_status": comparison_status,
        "sample_count": sample_count
    }
    
    result = {
        "symbol": symbol,
        "overall_score": overall_score,
        "overall_level": get_risk_level(overall_score),
        "dimension_results": dimension_results,
        "data_coverage": {
            "total_dimensions": len(GOVERNANCE_DIMENSIONS),
            "success_count": success_count,
            "missing_count": missing_count,
            "error_count": error_count,
            "coverage_rate": round(success_count / len(GOVERNANCE_DIMENSIONS) * 100, 1)
        },
        "industry_comparison": industry_comparison,
        "calculation_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    FULL_REPORT_CACHE[symbol] = {"result": result, "timestamp": now}
    return result


def get_risk_level(score: float) -> str:
    """根据分数获取风险等级"""
    if score >= 85:
        return "优 (低风险)"
    elif score >= 70:
        return "良 (中低风险)"
    elif score >= 55:
        return "中 (中风险)"
    elif score >= 40:
        return "差 (高风险)"
    else:
        return "极差 (极高风险)"


def generate_evidence_chain(score_data: Dict) -> str:
    """生成逐项证据链报告"""
    report = f"【公司治理综合评分报告】\n"
    report += "=" * 70 + "\n\n"
    report += f"股票代码：{score_data['symbol']}\n"
    report += f"综合评分：{score_data['overall_score']} / 100\n"
    report += f"风险等级：{score_data['overall_level']}\n"
    report += f"数据覆盖率：{score_data['data_coverage']['coverage_rate']}% ({score_data['data_coverage']['success_count']}/{score_data['data_coverage']['total_dimensions']})\n"
    
    if "industry_comparison" in score_data:
        ic = score_data["industry_comparison"]
        if ic["industry_avg_score"] is not None:
            vs_sign = "+" if ic["vs_industry"] > 0 else ""
            report += f"行业归属：{ic['industry']}（行业平均 {ic['industry_avg_score']}分，相对{vs_sign}{ic['vs_industry']}分，基于{ic['sample_count']}家同业公司）\n"
        else:
            report += f"行业归属：{ic['industry']}（行业对比暂不可用）\n"
    
    report += f"评估日期：{score_data['calculation_date']}\n\n"
    
    report += "【分项评分详情】\n"
    report += "-" * 70 + "\n\n"
    
    for dim_key, dim_config in GOVERNANCE_DIMENSIONS.items():
        dim_result = score_data["dimension_results"][dim_key]
        score = dim_result["score"]
        weight = dim_config["weight"]
        status = dim_result.get("data_status", "unknown")
        source = dim_result.get("data_source", "")
        
        status_icon = "✅" if status == "success" else "⚠️" if status == "missing" else "❌"
        
        report += f"{status_icon} {dim_config['name']}（权重 {weight}%）：{score}/100\n"
        report += f"   说明：{dim_config['description']}\n"
        report += f"   数据源：{source}\n"
        report += f"   证据链：\n"
        for i, evidence in enumerate(dim_result["evidence"], 1):
            report += f"     {i}. {evidence}\n"
        
        if dim_result["details"]:
            details_str = ", ".join(f"{k}: {v}" for k, v in dim_result["details"].items())
            report += f"   详情：{details_str}\n"
        
        report += "\n"
    
    report += "-" * 70 + "\n"
    report += f"合计评分：{score_data['overall_score']} / 100\n"
    report += f"风险等级：{score_data['overall_level']}\n"
    report += "-" * 70 + "\n"
    
    return report


# ============ Agent 工具定义 ============

tools = {
    "calculate_governance_score": calculate_governance_score,
    "generate_evidence_chain": generate_evidence_chain,
}

# ============ 系统提示词 ============

system_prompt = """
你是一个专业的公司治理风险评估助手，拥有以下工具：

1. calculate_governance_score(symbol) - 计算公司治理综合评分（包含9个维度数据）
   - symbol: 股票代码（如 000001.SZ、600000.SH、00700.HK）

2. generate_evidence_chain(score_data) - 生成治理评分证据链报告
   - score_data: calculate_governance_score返回的评分数据

规则：
1. 用户询问公司治理、风险评估、评分等问题时，必须调用工具查询
2. 输出格式：Action:工具名|{"参数名":值}
   示例：Action:calculate_governance_score|{"symbol":"000001.SZ"}
3. 不需要工具时，直接输出 Answer:回答内容
4. 只能二选一输出，不要多余文字，不要解释思考过程
"""


def llm_call(prompt: str, sys_prompt: str) -> str:
    """调用 DeepSeek API"""
    resp = get_client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )
    return resp.choices[0].message.content.strip()


def governance_agent(user_query: str) -> str:
    """公司治理评分 Agent"""
    output = llm_call(user_query, system_prompt)

    if output.startswith("Answer:"):
        return output.replace("Answer:", "").strip()

    if output.startswith("Action:"):
        action_part = output.replace("Action:", "").strip()
        try:
            tool_name, args_str = action_part.split("|", 1)
            tool_name = tool_name.strip()
            args = json.loads(args_str)
        except:
            return f"解析工具调用失败: {output}"

        tool_func = tools.get(tool_name)
        if tool_func:
            try:
                tool_result = tool_func(**args)
            except Exception as e:
                return f"工具执行失败: {str(e)}"
        else:
            return f"工具 {tool_name} 不存在"

        if tool_name == "calculate_governance_score":
            evidence_chain = generate_evidence_chain(tool_result)
            final_prompt = (
                f"用户问题：{user_query}\n"
                f"工具返回结果：{evidence_chain}\n"
                f"根据工具结果整理自然语言回答，直接输出 Answer:回答内容"
            )
            final_ans = llm_call(final_prompt, system_prompt)
            return final_ans.replace("Answer:", "").strip()
        else:
            return str(tool_result)

    return output



# ============ 入口 ============

if __name__ == "__main__":
    print("=" * 70)
    print("公司治理综合评分 Agent（DeepSeek API | PandaData）")
    print("=" * 70)

    test_cases = [
        "评估平安银行(000001.SZ)的公司治理风险",
        "贵州茅台(600519.SH)的治理评分是多少？",
        "比亚迪(002594.SZ)的治理风险评估",
    ]

    for q in test_cases:
        print(f"\n【用户】{q}")
        try:
            ans = governance_agent(q)
            print(f"【Agent】\n{ans}")
        except Exception as e:
            print(f"【错误】{e}")
            import traceback
            traceback.print_exc()