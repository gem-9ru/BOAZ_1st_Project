"""부산 수집 진행 현황 — 목표 대비 퍼센트.

실행:  python3 src/busan_status.py          한 번 출력
       python3 src/busan_status.py -w       5초마다 갱신
"""
import csv, json, os, subprocess, sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA, LOGS = BASE / "data", BASE / "logs"

# (표시명, 종류, 파일, 목표건수, 목표근거)
JOBS = [
    ("부산일자리정보망 상세", "ckpt", "부산일자리정보망_상세", 25895, "목록 전건"),
    ("사람인 상세",          "ckpt", "사람인_직무상세",       13946, "부산 목록"),
    ("잡코리아 부산 목록",    "csv",  "잡코리아부산",           8660, "사이트 표기"),
    ("잡코리아 상세",        "ckpt", "잡코리아_직무상세",       8199, "목록−알바몬"),
    ("커리어 부산 목록",      "csv",  "커리어부산",             5209, "사이트 표기"),
    ("커리어 상세",          "ckpt", "커리어_직무상세",         5070, "부산 목록"),
    ("사람인 부산 목록",      "csv",  "사람인부산",            13946, "사이트 표기"),
    ("널스케이프 부산",       "csv",  "널스케이프부산",            49, "사이트 표기"),
]

RUNNING = ("busanjob_detail", "duty_detail", "jobkorea_busan",
           "saramin_busan", "career_busan", "nurscape_busan")


def count(kind, name):
    if kind == "ckpt":
        p = LOGS / f"{name}.ckpt.jsonl"
        if not p.exists():
            return 0
        with p.open("rb") as f:
            return sum(1 for _ in f)
    p = DATA / f"{name}.csv"
    if not p.exists():
        return 0
    with p.open("rb") as f:
        return max(sum(1 for _ in f) - 1, 0)


def procs():
    try:
        out = subprocess.run(["pgrep", "-fl", "|".join(RUNNING)],
                             capture_output=True, text=True).stdout
    except Exception:
        return []
    live = []
    for line in out.splitlines():
        for r in RUNNING:
            if r in line:
                arg = line.split(r + ".py")[-1].strip()
                live.append(f"{r}{(' ' + arg) if arg else ''}")
                break
    return live


def bar(pct, width=24):
    fill = int(width * min(pct, 100) / 100)
    return "█" * fill + "·" * (width - fill)


def render():
    live = procs()
    out = []
    out.append(f"부산 수집 현황   {time.strftime('%H:%M:%S')}")
    out.append("=" * 74)
    done_all = tgt_all = 0
    for label, kind, name, target, why in JOBS:
        n = count(kind, name)
        pct = n / target * 100 if target else 0
        done_all += min(n, target); tgt_all += target
        mark = "▶" if any(name.split("_")[0][:4] in p or label[:3] in p for p in live) else " "
        state = "완료" if pct >= 99.5 else ("대기" if n == 0 else "진행")
        out.append(f"{mark} {label:20}{bar(pct)} {pct:5.1f}%  {n:>7,}/{target:>7,}  {state}  {why}")
    out.append("-" * 74)
    out.append(f"  {'전체':20}{bar(done_all/tgt_all*100)} "
               f"{done_all/tgt_all*100:5.1f}%  {done_all:>7,}/{tgt_all:>7,}")
    out.append("")
    out.append(f"실행 중 {len(live)}개: " + (", ".join(live) if live else "없음"))
    return "\n".join(out)


if __name__ == "__main__":
    if "-w" in sys.argv:
        try:
            while True:
                print("\033[2J\033[H" + render(), flush=True)
                time.sleep(5)
        except KeyboardInterrupt:
            pass
    else:
        print(render())
