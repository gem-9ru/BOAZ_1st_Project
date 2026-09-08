"""발표용 산출물 생성 — ~/Downloads/부산_채용공고_final/

파이프라인을 다시 돌릴 때마다 CSV 와 설명 문서의 수치가 바뀐다.
손으로 고치면 반드시 어딘가 옛날 숫자가 남으므로 실측값으로 생성한다.

실행:  python3 src/make_deliverable.py
"""
import csv, collections, shutil, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = Path.home() / "Downloads" / "부산_채용공고_final"
SRC = BASE / "부산" / "부산_공고_통합.csv"


def pct(a, b):
    return f"{a * 100 // max(b, 1)}%"


def main():
    rows = list(csv.DictReader(SRC.open(encoding="utf-8-sig")))
    n = len(rows)
    fill = collections.Counter()
    for r in rows:
        for k, v in r.items():
            if (v or "").strip():
                fill[k] += 1

    site = collections.Counter(s.strip() for r in rows
                               for s in (r["게재사이트"] or "").split(",") if s.strip())
    sgg = collections.Counter(r["시군구"] for r in rows if r["시군구"])
    edu = collections.Counter((r.get("학력") or "미기재").strip() for r in rows)
    car = collections.Counter(r["경력구분"] for r in rows if r["경력구분"])
    ind = collections.Counter(r["업종"] for r in rows if r["업종"] and r["업종"] != "-")
    conf = collections.Counter(r.get("부산판정확실도", "") for r in rows)
    duty = collections.Counter()
    for r in rows:
        for x in (r["직무"] or "").split(","):
            x = x.strip()
            if x:
                duty[x] += 1
    hc = [int(r["채용인원"]) for r in rows if (r.get("채용인원") or "").isdigit()]
    job = collections.Counter(r["직종"] for r in rows if (r.get("직종") or "").strip())

    OUT.mkdir(parents=True, exist_ok=True)
    csv_name = f"부산_채용공고_{n}건.csv"
    for old in OUT.glob("부산_채용공고_*건.csv"):
        old.unlink()
    shutil.copy(SRC, OUT / csv_name)
    shutil.copy(BASE / "부산" / "부산_사이트별.csv", OUT / "사이트별_건수.csv")

    print(f"  -> {OUT}/{csv_name}  ({n:,}건, 컬럼 {len(rows[0])}개)")
    print(f"     확실도 " + " / ".join(f"{k} {conf[k]:,}" for k in ("강", "중", "약") if conf[k]))
    print(f"     담당업무 {pct(fill['담당업무'], n)}  직종 {pct(fill['직종'], n)}  "
          f"학력 {pct(fill['학력'], n)}  채용인원 {pct(fill['채용인원'], n)}")
    print(f"     채용인원 명시 {len(hc):,}건 합계 {sum(hc):,}명")
    print("\n  설명.md 에 넣을 값 —— 아래를 문서에 반영하세요")
    print("   사이트:", ", ".join(f"{k} {v:,}" for k, v in site.most_common(6)))
    print("   시군구:", ", ".join(f"{k} {v:,}" for k, v in sgg.most_common(5)))
    print("   업종  :", ", ".join(f"{k} {v:,}" for k, v in ind.most_common(5)))
    print("   직무  :", ", ".join(f"{k} {v:,}" for k, v in duty.most_common(8)))
    if job:
        print("   직종  :", ", ".join(f"{k} {v:,}" for k, v in job.most_common(6)))
    print("   학력  :", ", ".join(f"{k} {v:,}" for k, v in edu.most_common(6)))
    print("   경력  :", ", ".join(f"{k} {v:,}" for k, v in car.most_common(4)))


if __name__ == "__main__":
    main()
