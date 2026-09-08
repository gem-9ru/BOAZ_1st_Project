"""사이트별 수집 결과 표를 CSV/로그 실측값으로 출력한다(수기 오기 방지). 표준출력."""
import csv, glob, json, os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA, LOGS = BASE / "data", BASE / "logs"
COLS = ["회사명", "공고제목", "직무", "경력", "고용형태", "지역", "기술스택", "마감일"]

def stats(p):
    with open(p, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return 0, {}
    fill = {c: round(100 * sum(1 for r in rows if (r.get(c) or "").strip()) / len(rows))
            for c in COLS}
    return len(rows), fill

def main():
    lines = ["| 사이트 | 수집 건수 | 파일 | 채움률(회사/제목/직무/경력/고용형태/지역/스택/마감) |",
             "|---|---:|---|---|"]
    total = 0
    rows = []
    for p in sorted(glob.glob(str(DATA / "*.csv"))):
        name = Path(p).stem
        n, fill = stats(p)
        total += n
        rows.append((n, name, fill))
    for n, name, fill in sorted(rows, key=lambda x: -x[0]):
        pct = " / ".join(f"{fill.get(c,0)}%" for c in COLS)
        lines.append(f"| {name} | {n:,} | `data/{name}.csv` | {pct} |")
    lines.append(f"| **합계** | **{total:,}** | | |")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
