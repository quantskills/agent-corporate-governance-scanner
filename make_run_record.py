# -*- coding: utf-8 -*-
"""
真实运行记录器：以子进程方式调用唯一入口 main.py，把**完整 stdout/stderr**
逐字节落盘为运行记录（避免 PowerShell 对重定向 UTF-8 流的截断）。

用法：
    python make_run_record.py 000001.SZ 600519.SH
产物：
    samples/RUN_RECORD_<symbol>.log
"""
import datetime
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "samples")
os.makedirs(SAMPLES, exist_ok=True)


def record(symbol: str) -> int:
    log_path = os.path.join(SAMPLES, f"RUN_RECORD_{symbol.replace('.', '_')}.log")
    cmd = [sys.executable, os.path.join(HERE, "main.py"), "--symbol", symbol]
    header = (
        "=" * 78 + "\n"
        f"真实运行记录 (real run record)\n"
        f"命令      : python main.py --symbol {symbol}\n"
        f"开始时间  : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Python    : {sys.version.split()[0]}\n"
        + "=" * 78 + "\n\n"
    )
    proc = subprocess.run(cmd, cwd=HERE, capture_output=True)
    out = proc.stdout.decode("utf-8", errors="replace")
    err = proc.stderr.decode("utf-8", errors="replace")
    footer = (
        "\n" + "=" * 78 + "\n"
        f"退出码    : {proc.returncode}\n"
        f"结束时间  : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        + "=" * 78 + "\n"
    )
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(out)
        if err.strip():
            f.write("\n----- STDERR -----\n")
            f.write(err)
        f.write(footer)
    print(f"[记录已保存] {log_path}  (exit={proc.returncode}, {len(out)} chars stdout)")
    return proc.returncode


if __name__ == "__main__":
    symbols = sys.argv[1:] or ["000001.SZ"]
    rc = 0
    for s in symbols:
        rc |= record(s)
    sys.exit(rc)
