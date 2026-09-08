"""JSON-LD 누락 필드 보강 — 학력·급여·상세주소만 다시 받는다.

[배경]
`common.parse_jobposting_ld` 가 schema.org JobPosting 에서 8개 필드만 뽑고
아래를 버리고 있었다(파서는 고쳤지만 이미 수집한 데이터는 그대로다).

    educationRequirements  학력      표본 3/3 존재
    baseSalary             급여      표본 1/3 존재
    description            "근무지는 부산 동구 중앙대로 197 (초량동)이며" → 상세주소
    datePosted             게시일

[범위] **부산 최종 산출물에서 학력·급여·상세주소가 빈 공고만.** 755건.
전량(13.6만)을 다시 받을 이유가 없다. 목표가 부산이고 나머지는 이미 채워져 있다.

    기대 회수  학력 약 640건 · 급여 약 180건 · 상세주소 최대 830건
    소요      2req/s 기준 약 6분

[산출] data/잡코리아_LD상세.csv — 파일명이 `*상세.csv` 라 detail_join 이 자동으로
공고URL 로 붙인다. 목록 사이트로는 안 읽힌다(normalize 가 공고제목 컬럼을 요구).

실행:  python3 src/jobkorea_ld_backfill.py
       python3 src/pipeline/normalize.py && ... (이후 파이프라인 재실행)
"""
import csv, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Site, parse_jobposting_ld, fetch_many, DATA   # noqa: E402

csv.field_size_limit(10 ** 9)
BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "부산" / "부산_공고_직종분류.csv"
OUT = DATA / "잡코리아_LD상세.csv"
COLS = ["공고URL", "학력", "급여", "업종", "모집인원", "근무시간", "상세주소", "게시일", "수집시각"]
GI = re.compile(r"jobkorea\.co\.kr/Recruit/GI_Read/\d+")
LD_SITES = {"잡코리아", "리멤버커리어", "건설워커", "미디어잡"}


def targets():
    urls = []
    seen = set()
    for r in csv.DictReader(SRC.open(encoding="utf-8-sig")):
        sites = {s.strip() for s in (r["게재사이트"] or "").split(",")}
        if not (LD_SITES & sites):
            continue
        if all((r[c] or "").strip() for c in ("학력", "급여", "상세주소")):
            continue
        for u in (r["전체URL"] or r["대표URL"] or "").split("|"):
            u = u.strip().split("?")[0]
            if GI.search(u) and u not in seen:
                seen.add(u); urls.append(u); break
    return urls


def main():
    urls = targets()
    print(f"대상 {len(urls):,}건 (부산 최종에서 학력·급여·상세주소가 빈 공고)")
    site = Site("잡코리아LD", "https://www.jobkorea.co.kr", delay=0.5)
    rows = []

    def parse(u, r):
        d = parse_jobposting_ld(u, r)
        if not d:
            return None
        rec = {c: d.get(c, "") for c in COLS}
        rec["공고URL"] = u
        # 하나라도 얻은 게 있어야 저장한다
        return rec if any(rec[c] for c in COLS if c not in ("공고URL", "수집시각")) else None

    for rec in fetch_many(site, urls, parse, workers=2, per_sec=2.0, label="LD보강"):
        if rec:
            rows.append(rec)
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    fill = {c: sum(1 for r in rows if r[c]) for c in COLS[1:-1]}
    print(f"-> {OUT.name} ({len(rows):,}건)")
    print("   " + " · ".join(f"{c} {v:,}" for c, v in fill.items()))


if __name__ == "__main__":
    main()
