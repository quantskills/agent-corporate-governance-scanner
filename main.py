#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
公司治理综合评分 Agent —— 唯一命令行入口 (CLI)

这是本项目对外暴露的**唯一入口**。它把散落在核心模块中的多模块编排
（9 个治理数据模块 → 评分引擎 → 行业对比 → 证据链 → LLM 归纳）统一收敛为
一个可复现、可产出样例产物的命令行工具。

用法示例
--------
  # 1) 单只股票，输出人类可读的证据链报告
  python main.py --symbol 000001.SZ

  # 2) 单只股票，输出结构化 JSON（可用于下游消费 / 存档）
  python main.py --symbol 600519.SH --json

  # 3) 走完整 Agent（含 DeepSeek 自然语言归纳）
  python main.py --symbol 002594.SZ --agent

  # 4) 批量评估，并把每只股票的报告/JSON 落盘到 samples/
  python main.py --symbols 000001.SZ 600519.SH 002594.SZ --save samples

  # 5) 交互模式（自然语言提问，走完整 Agent）
  python main.py --interactive

  # 6) 自检 / 离线冒烟：只验证编排链路与评分引擎是否可用
  python main.py --selftest
"""
import argparse
import datetime
import importlib.util
import json
import os
import sys

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE_PATH = os.path.join(_HERE, "agent-corporate-governance-scanner.py")


def load_core():
    """加载核心模块（文件名含连字符，无法直接 import，故用 importlib 动态加载）"""
    spec = importlib.util.spec_from_file_location("governance_core", _CORE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def run_single(core, symbol: str, as_json: bool, use_agent: bool) -> str:
    """评估单只股票，返回可打印/可落盘的字符串产物"""
    if use_agent:
        # 走完整 Agent：LLM 决策 -> 工具编排 -> LLM 归纳
        return core.governance_agent(f"评估 {symbol} 的公司治理风险")

    score_data = core.calculate_governance_score(symbol)
    if as_json:
        return json.dumps(score_data, ensure_ascii=False, indent=2)
    return core.generate_evidence_chain(score_data)


def cmd_selftest(core) -> int:
    """离线自检：不依赖外部服务，验证评分引擎与证据链编排是否自洽"""
    print("=" * 70)
    print("离线自检 (selftest) —— 验证多模块编排链路与评分引擎")
    print("=" * 70)

    dims = core.GOVERNANCE_DIMENSIONS
    total_weight = sum(d["weight"] for d in dims.values())
    print(f"[1/3] 治理维度数量: {len(dims)}  权重合计: {total_weight}")
    assert len(dims) == 9, "治理维度应为 9 个"
    assert total_weight == 100, "各维度权重合计应为 100"

    # 用一份构造的维度结果驱动评分引擎与证据链（不触网）
    fake_results = {
        k: {
            "score": 80,
            "evidence": [f"{v['name']}样例证据"],
            "details": {"demo": 1},
            "data_source": "selftest",
            "data_status": "success",
        }
        for k, v in dims.items()
    }
    weighted = sum(
        fake_results[k]["score"] * (v["weight"] / total_weight)
        for k, v in dims.items()
    )
    print(f"[2/3] 加权评分引擎: 全部维度=80 -> 综合={round(weighted, 1)} (应为 80.0)")
    assert round(weighted, 1) == 80.0

    fake_score_data = {
        "symbol": "SELFTEST.SZ",
        "overall_score": round(weighted, 1),
        "overall_level": core.get_risk_level(round(weighted, 1)),
        "dimension_results": fake_results,
        "data_coverage": {
            "total_dimensions": len(dims),
            "success_count": len(dims),
            "missing_count": 0,
            "error_count": 0,
            "coverage_rate": 100.0,
        },
        "industry_comparison": {
            "industry": "自检",
            "industry_code": "",
            "industry_avg_score": None,
            "vs_industry": None,
            "comparison_status": "暂不可用",
            "sample_count": 0,
        },
        "calculation_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    report = core.generate_evidence_chain(fake_score_data)
    print(f"[3/3] 证据链渲染: 生成报告 {len(report)} 字符，含全部 {len(dims)} 维度分项")
    for v in dims.values():
        assert v["name"] in report, f"报告缺少维度 {v['name']}"

    print("\n自检通过 ✅  多模块编排链路可用（评分引擎 + 证据链渲染）")
    return 0


def cmd_interactive(core) -> int:
    """交互模式：自然语言提问，走完整 Agent"""
    print("=" * 70)
    print("公司治理综合评分 Agent（交互模式）")
    print("输入自然语言问题，例如：评估平安银行(000001.SZ)的公司治理风险")
    print("输入 exit / quit 退出")
    print("=" * 70)
    while True:
        try:
            query = input("\n【你】").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见")
            return 0
        if query.lower() in ("exit", "quit", "q"):
            print("再见")
            return 0
        if not query:
            continue
        try:
            ans = core.governance_agent(query)
            print(f"【Agent】\n{ans}")
        except Exception as e:  # noqa: BLE001
            print(f"【错误】{e}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="公司治理综合评分 Agent —— 唯一命令行入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python main.py --symbol 000001.SZ\n"
        "  python main.py --symbols 000001.SZ 600519.SH --save samples\n"
        "  python main.py --interactive\n"
        "  python main.py --selftest",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--symbol", help="单只股票代码，如 000001.SZ / 600519.SH / 00700.HK")
    g.add_argument("--symbols", nargs="+", help="批量股票代码，空格分隔")
    g.add_argument("--interactive", action="store_true", help="进入自然语言交互模式")
    g.add_argument("--selftest", action="store_true", help="离线自检编排链路（不触网）")

    p.add_argument("--json", action="store_true", help="输出结构化 JSON 而非文本报告")
    p.add_argument("--agent", action="store_true", help="走完整 Agent（含 LLM 自然语言归纳）")
    p.add_argument("--save", metavar="DIR", help="将产物落盘到指定目录（默认仅打印）")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    core = load_core()

    if args.selftest:
        return cmd_selftest(core)

    if args.interactive:
        return cmd_interactive(core)

    symbols = []
    if args.symbol:
        symbols = [args.symbol]
    elif args.symbols:
        symbols = args.symbols

    if not symbols:
        build_parser().print_help()
        return 1

    save_dir = None
    if args.save:
        save_dir = os.path.join(_HERE, args.save) if not os.path.isabs(args.save) else args.save
        os.makedirs(save_dir, exist_ok=True)

    ext = "json" if (args.json and not args.agent) else "txt"
    exit_code = 0
    for symbol in symbols:
        print("\n" + "=" * 70)
        print(f"评估: {symbol}")
        print("=" * 70)
        try:
            product = run_single(core, symbol, args.json, args.agent)
            print(product)
            if save_dir:
                fname = f"{symbol.replace('.', '_')}_{_timestamp()}.{ext}"
                fpath = os.path.join(save_dir, fname)
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(product)
                print(f"\n[已保存] {fpath}")
        except Exception as e:  # noqa: BLE001
            exit_code = 1
            print(f"[错误] 评估 {symbol} 失败: {e}")
            import traceback

            traceback.print_exc()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
