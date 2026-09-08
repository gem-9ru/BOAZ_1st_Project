"""체크포인트(JSONL) → CSV 내보내기.

수집이 중간에 끊기면 CSV 가 안 써진다. Site.save() 는 정상 종료 시점에만 부르기 때문이다.
사람인 상세가 IP 차단으로 끊겼을 때 5,670건이 체크포인트에만 남았다.
파이프라인은 체크포인트도 읽지만(detail_join), 배포용 데이터는 CSV 로 있어야 한다.

실행:  python3 src/flush_ckpt.py 사람인_직무상세
       python3 src/flush_ckpt.py            (인자 없으면 CSV 가 없는 것만 전부)
"""
import csv, glob, json, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA, LOGS = BASE / "data", BASE / "logs"


def flush(name):
    src = LOGS / f"{name}.ckpt.jsonl"
    if not src.exists():
        print(f"  {name}: 체크포인트 없음"); return 0
    rows, bad = [], 0
    with src.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                bad += 1          # 중단 시점에 잘린 마지막 줄
    if not rows:
        print(f"  {name}: 비어 있음"); return 0
    cols = list(dict.fromkeys(k for r in rows for k in r))
    out = DATA / f"{name}.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    print(f"  {name}: {len(rows):,}건 -> {out.name}" + (f" (손상 {bad}줄 무시)" if bad else ""))
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for n in sys.argv[1:]:
            flush(n)
    else:
        for p in sorted(glob.glob(str(LOGS / "*.ckpt.jsonl"))):
            name = Path(p).stem.replace(".ckpt", "")
            if not (DATA / f"{name}.csv").exists():
                flush(name)
