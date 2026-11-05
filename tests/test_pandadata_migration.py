import ast
import datetime
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]

def functions(relative, names, **context):
    source=ast.parse((ROOT/relative).read_text(encoding="utf-8"))
    nodes=[ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0)]
    nodes.extend(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in names)
    namespace={"pd":pd,"datetime":datetime,"sys":sys,**context}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),relative,"exec"),namespace)
    return namespace

class MigrationTests(unittest.TestCase):
    def test_hk_industry_uses_hk_metadata(self):
        for path in ["agent-corporate-governance-scanner.py","scripts/agent-corporate-governance-scanner.py"]:
            sdk=Mock()
            sdk.get_stock_industry.side_effect=ValueError("A-share symbols required")
            sdk.get_hk_detail.return_value=pd.DataFrame([{"industry_group":"Banking Services"}])
            ns=functions(path,{"get_industry","get_market_type"},panda_data=sdk)
            self.assertEqual(ns["get_industry"]("0001.HK"),("Banking Services",""))
            sdk.get_stock_industry.assert_not_called()
            sdk.get_hk_detail.assert_called_once()

if __name__ == "__main__":
    unittest.main()
