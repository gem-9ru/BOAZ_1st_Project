# -*- coding: utf-8 -*-
"""크롤링 진행 상황 요약.

주의: 상세 수집형 크롤러(잡코리아·리멤버)는 CSV 를 마지막에 한 번 쓰기 때문에
      진행 중에는 CSV 행수가 실제 수집량과 다르다. 실시간 수치는 체크포인트(JSONL)를 봐야 한다.
"""
import glob, os, re, subprocess, time
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
os.chdir(BASE)

SCRIPT2SITE = {"jobkorea": "잡코리아", "remember": "리멤버커리어", "jobplanet": "잡플래닛",
               "wanted": "원티드", "catch": "캐치", "jasoseol": "자소설닷컴", "jumpit": "점핏",
               "linkareer": "링커리어", "worker": "건설워커", "gamejob": "게임잡",
               "mediajob": "미디어잡", "joballio": "잡알리오", "nurscape": "널스케이프",
               "career": "커리어"}
# 사이트가 밝힌 전체 규모 (수집 목표)
TARGET = {"잡코리아": 108009, "리멤버커리어": 13502, "잡플래닛": 56139,
          "잡알리오": 2054}

def _etime_sec(s):
    """macOS ps 의 etime 형식 [[dd-]hh:]mm:ss 를 초로 변환."""
    days = 0
    if "-" in s:
        d, s = s.split("-", 1)
        days = int(d)
    parts = [int(x) for x in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, sec = parts
    return days * 86400 + h * 3600 + m * 60 + sec


def running_procs():
    """실행 중인 크롤러 목록.

    주의: macOS 의 ps 에는 etimes(초 단위) 키워드가 없다. etime 을 써야 한다.
          etimes 를 쓰면 ps 가 통째로 실패해서 '실행 중 0개' 로 잘못 보고했었다.
    """
    out = {}
    try:
        ps = subprocess.run(["ps", "-eo", "pid,etime,command"],
                            capture_output=True, text=True).stdout
    except Exception:
        return out
    for line in ps.splitlines():
        if "status.py" in line:
            continue
        m = re.search(r"^\s*(\d+)\s+([\d:\-]+)\s+.*python3\s+(?:\S*/)?(\w+)\.py", line)
        if m and m.group(3) in SCRIPT2SITE:
            try:
                out[SCRIPT2SITE[m.group(3)]] = (m.group(1), _etime_sec(m.group(2)))
            except ValueError:
                out[SCRIPT2SITE[m.group(3)]] = (m.group(1), 0)
    return out

def csv_rows(p):
    try:
        with open(p, encoding="utf-8-sig") as f:
            return max(sum(1 for _ in f) - 1, 0)
    except OSError:
        return 0

def hhmm(sec):
    if sec <= 0 or sec > 86400 * 3:
        return "-"
    return str(timedelta(seconds=int(sec))).rsplit(".")[0]

def main():
    run = running_procs()
    print("=" * 72)
    print(f"  크롤링 상태      {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 72)
    print(f"\n▶ 실행 중: {len(run)}개" + ("" if run else "   (모두 완료 또는 중단)"))
    for s, (pid, et) in sorted(run.items()):
        print(f"    {s:<12} PID {pid:<8} 경과 {hhmm(et)}")

    print(f"\n▶ 사이트별\n    {'사이트':<13}{'수집':>9}{'목표':>10}{'진행률':>8}  {'남은시간':>9}  상태")
    print("    " + "-" * 60)
    total_rows = 0
    for site in sorted(set(SCRIPT2SITE.values())):
        ck = Path(f"logs/{site}.ckpt.jsonl")
        csvp = Path(f"data/{site}.csv")
        if not ck.exists() and not csvp.exists():
            continue
        # 진행 중에는 체크포인트가 실시간, 완료 후에는 CSV 가 정본
        live = sum(1 for _ in open(ck, encoding="utf-8")) if ck.exists() else 0
        rows = csv_rows(csvp)
        got = max(live, rows) if site in run else (rows or live)
        total_rows += rows or got
        tgt = TARGET.get(site, 0)
        pct = f"{100*got/tgt:5.1f}%" if tgt else "    -"
        eta = "-"
        if site in run and tgt and got:
            rate = got / max(run[site][1], 1)
            eta = hhmm((tgt - got) / rate) if rate > 0 else "-"
        state = "수집중" if site in run else "완료"
        print(f"    {site:<13}{got:>9,}{tgt:>10,}{pct:>8}  {eta:>9}  {state}")
    print("    " + "-" * 60)
    print(f"    {'CSV 합계':<13}{total_rows:>9,}")

    built = Path("build/공고_통합.csv")
    if built.exists():
        n = csv_rows(built)
        t = datetime.fromtimestamp(built.stat().st_mtime)
        stale = " (원본이 갱신됨 - 파이프라인 재실행 필요)" if any(
            Path(p).stat().st_mtime > built.stat().st_mtime for p in glob.glob("data/*.csv")) else ""
        print(f"\n▶ 통합 결과   {n:,}건   {t:%m-%d %H:%M} 생성{stale}")
    print()

if __name__ == "__main__":
    main()
