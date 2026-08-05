# -*- coding: utf-8 -*-
"""
公司治理评分 Agent —— 离线单元测试

这些测试**不触网**：它们通过 monkeypatch 把 9 个取数函数替换为桩数据，
从而验证「多模块编排 → 评分引擎 → 行业对比 → 证据链渲染」这条主链路的正确性，
以及入口 main.py 的加载与自检。

运行：
    python -m pytest tests -v
或（无 pytest 时）：
    python tests/test_governance.py
"""
import importlib.util
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_CORE_PATH = os.path.join(_ROOT, "agent-corporate-governance-scanner.py")

sys.path.insert(0, _ROOT)


def load_core():
    spec = importlib.util.spec_from_file_location("governance_core_test", _CORE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = load_core()


def _fake_dim(score, status="success"):
    return {
        "score": score,
        "evidence": ["桩证据"],
        "details": {"k": 1},
        "data_source": "test",
        "data_status": status,
    }


# ---------- 1. 维度定义与权重 ----------

def test_dimensions_count_and_weight():
    assert len(core.GOVERNANCE_DIMENSIONS) == 9
    total = sum(d["weight"] for d in core.GOVERNANCE_DIMENSIONS.values())
    assert total == 100, f"权重合计应为 100, 实为 {total}"


# ---------- 2. 风险等级映射 ----------

def test_risk_levels():
    assert "优" in core.get_risk_level(90)
    assert "良" in core.get_risk_level(78)
    assert "中" in core.get_risk_level(60)
    assert "差" in core.get_risk_level(45)
    assert "极差" in core.get_risk_level(30)


# ---------- 3. 市场类型判断 ----------

def test_market_type():
    assert core.get_market_type("000001.SZ") == "cn"
    assert core.get_market_type("600519.SH") == "cn"
    assert core.get_market_type("00700.HK") == "hk"


# ---------- 4. 加权评分引擎（全 80 分 -> 综合 80.0）----------

def _patch_all_dims(monkeypatch, score):
    fetchers = [
        "fetch_audit_opinion", "fetch_litigation", "fetch_related_party_transactions",
        "fetch_guarantee", "fetch_contract_risk", "fetch_intermediary_info",
        "fetch_equity_nature", "fetch_violation_records", "fetch_stock_acquisition",
    ]
    for name in fetchers:
        monkeypatch.setattr(core, name, lambda s, sc=score: _fake_dim(sc))
    # 禁用外部登录与行业对比
    monkeypatch.setattr(core, "ensure_panda_data", lambda: None)
    monkeypatch.setattr(core, "get_industry", lambda s: ("测试行业", ""))
    core.SCORE_CACHE.clear()
    core.FULL_REPORT_CACHE.clear()


def test_weighted_score_engine(monkeypatch):
    _patch_all_dims(monkeypatch, 80)
    result = core.calculate_governance_score("TEST.SZ")
    assert result["overall_score"] == 80.0
    assert result["overall_level"] == core.get_risk_level(80.0)
    assert result["data_coverage"]["success_count"] == 9
    assert result["data_coverage"]["coverage_rate"] == 100.0


def test_weighted_score_low(monkeypatch):
    _patch_all_dims(monkeypatch, 30)
    result = core.calculate_governance_score("LOW.SZ")
    assert result["overall_score"] == 30.0
    assert "极差" in result["overall_level"]


# ---------- 5. 证据链渲染包含所有维度 ----------

def test_evidence_chain_contains_all_dims(monkeypatch):
    _patch_all_dims(monkeypatch, 70)
    result = core.calculate_governance_score("EV.SZ")
    report = core.generate_evidence_chain(result)
    assert "公司治理综合评分报告" in report
    for dim in core.GOVERNANCE_DIMENSIONS.values():
        assert dim["name"] in report
    assert "EV.SZ" in report


# ---------- 6. JSON 可序列化（回归：related_party 曾产生 NaN）----------

def test_result_is_json_serializable(monkeypatch):
    _patch_all_dims(monkeypatch, 75)
    result = core.calculate_governance_score("JSON.SZ")
    dumped = json.dumps(result, ensure_ascii=False)  # 若含 NaN 会产出非法 JSON
    reparsed = json.loads(dumped)
    assert reparsed["symbol"] == "JSON.SZ"


# ---------- 7. 入口 main.py 可加载且自检通过 ----------

def test_main_selftest():
    spec = importlib.util.spec_from_file_location("main_entry", os.path.join(_ROOT, "main.py"))
    main_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_mod)
    rc = main_mod.main(["--selftest"])
    assert rc == 0


if __name__ == "__main__":
    # 简易 runner（无 pytest 时）
    class _MP:
        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, value):
            old = getattr(obj, name)
            self._undo.append((obj, name, old))
            setattr(obj, name, value)

        def undo(self):
            for obj, name, old in reversed(self._undo):
                setattr(obj, name, old)
            self._undo.clear()

    passed = failed = 0
    for fname, fn in sorted(globals().items()):
        if not fname.startswith("test_") or not callable(fn):
            continue
        mp = _MP()
        try:
            if fn.__code__.co_argcount == 1:
                fn(mp)
            else:
                fn()
            print(f"PASS  {fname}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {fname}: {e}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {fname}: {e}")
            failed += 1
        finally:
            mp.undo()

    print(f"\n结果: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
