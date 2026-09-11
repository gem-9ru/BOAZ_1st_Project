"""부산 수집 진행 현황 — 목표 대비 퍼센트.

실행:  bash 진행상황.sh        한 번 출력
       bash 진행상황.sh -w     5초마다 갱신
"""
import csv, json, subprocess, sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA, LOGS = BASE / "data", BASE / "logs"

# (표시명, 종류, 파일이름, 목표, 목표근거, 이 작업을 돌리는 프로세스)
JOBS = [
    ("사람인 부산 목록",     "csv",  "사람인부산",             13946, "사이트 표기", "saramin_busan"),
    ("잡코리아 부산 목록",   "csv",  "잡코리아부산",            8660, "사이트 표기", "jobkorea_busan"),
    ("커리어 부산 목록",     "csv",  "커리어부산",              5072, "목록 실측(패널 5,209는 누적)", "career_busan"),
    ("부산장애인 목록",      "csv",  "부산장애인일자리정보망",      124, "전수",      "busanjob4u"),
    ("널스케이프 부산",      "csv",  "널스케이프부산",             49, "사이트 표기", "nurscape_busan"),
    ("부산일자리정보망 상세", "ckpt", "부산일자리정보망_상세",     25326, "해외채용 제외", "busanjob_detail"),
    ("잡코리아 상세",       "ckpt", "잡코리아_직무상세",         8200, "목록−알바몬",  "duty_detail 잡코리아"),
    ("커리어 상세",         "ckpt", "커리어_직무상세",           5070, "부산 목록",   "duty_detail 커리어"),
    ("사람인 상세",         "ckpt", "사람인_직무상세",           5670, "IP 차단으로 중단", "duty_detail 사람인"),
    ("고용24 인증번호",     "ckpt", "고용24_인증번호",           4214, "잡코리아 워크넷분", "work24_detail"),
    ("고용24 상세",        "ckpt", "고용24_상세",              4214, "1단계 결과",  "work24_detail"),
]

RUNNING = ("busanjob_detail", "duty_detail", "jobkorea_busan", "saramin_busan",
           "career_busan", "nurscape_busan", "work24_detail", "busanjob4u", "busansidae")


def count(kind, name):
    p = (LOGS / f"{name}.ckpt.jsonl") if kind == "ckpt" else (DATA / f"{name}.csv")
    if not p.exists():
        return 0
    with p.open("rb") as f:
        n = sum(1 for _ in f)
    return n if kind == "ckpt" else max(n - 1, 0)


def procs():
    try:
        out = subprocess.run(["pgrep", "-fl", "|".join(RUNNING)],
                             capture_output=True, text=True).stdout
    except Exception:
        return []
    live = []
    for line in out.splitlines():
        for r in RUNNING:
            if r + ".py" in line:
                arg = line.split(r + ".py")[-1].strip().split(">")[0].strip()
                live.append(f"{r}{(' ' + arg) if arg else ''}")
                break
    return live


def bar(pct, w=22):
    f = int(w * min(pct, 100) / 100)
    return "█" * f + "·" * (w - f)


def render():
    live = procs()
    L = ["", f"  부산 수집 현황                    {time.strftime('%H:%M:%S')}",
         "  " + "=" * 74]
    done = tgt = 0
    for label, kind, name, target, why, proc in JOBS:
        n = count(kind, name)
        pct = n / target * 100 if target else 0
        done += min(n, target); tgt += target
        # 어떤 프로세스가 이 작업을 돌리는지 JOBS 에 못박아 둔다.
        # 이름 일부만 맞춰보면 "고용24 인증번호"(work24_detail)처럼 라벨과 프로세스명이
        # 달라 실행 중인데도 '중단' 으로 잘못 나온다.
        running = any(proc in p for p in live)
        if pct >= 99.5:
            state = "완료"
        elif running:
            state = "진행"
        elif n == 0:
            state = "대기"
        else:
            state = "중단"
        mark = "▶" if state == "진행" else (" " if state == "완료" else "·")
        L.append(f"  {mark} {label:<17}{bar(pct)} {pct:5.1f}%  {n:>6,}/{target:>6,}  {state}  {why}")
    L.append("  " + "-" * 74)
    L.append(f"    {'전체':<17}{bar(done / tgt * 100)} {done / tgt * 100:5.1f}%  {done:>6,}/{tgt:>6,}")
    L.append("")
    L.append("  실행 중: " + (", ".join(live) if live else "없음"))
    L.append("")
    return "\n".join(L)


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
