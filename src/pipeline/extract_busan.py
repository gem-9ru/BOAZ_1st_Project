# -*- coding: utf-8 -*-
"""부산 지역 채용공고 추출.

입력: ../../build/공고_정규화.csv, 공고_통합.csv (있으면)
출력: ../../부산/  폴더
        부산_공고_통합.csv    중복 제거된 부산 공고 (있을 때)
        부산_공고_원본.csv    사이트별 원본 행
        부산_사이트별.csv     사이트별 건수 요약
        부산_판정보류.csv     부산 여부가 불확실해 제외한 행 (검토용)

[판정 기준] 확실한 것만 부산으로 넣고, 애매한 것은 보류 파일로 뺀다.
  1) 시도 == '부산'                                        → 부산 (단일지역)
  2) 지역원문에 '부산' 이 포함                                 → 부산 (다지역 공고 포함)
  3) 시군구가 부산 소속 구/군                                  → 부산 (정규화에서 이미 복원됨)
  4) 공고제목·상세주소에 부산 지명                              → 부산 (지역칸이 본사 주소인 공고)
     "[부산] 건강코디네이터 채용", "부산/대구 지역영업관리" 처럼
     실제 근무지는 부산인데 지역 칸에는 본사(서울·경남)가 적힌 공고가 있다.
     사이트별 전수 대조에서 잡코리아 196건, 잡알리오 26건, 커리어 16건 등이 이 유형이었다.
     자소설닷컴은 원본에 지역 필드 자체가 없어 이 규칙으로만 잡힌다(31건).
  5) 부산일자리정보망인데 지역 미상                              → 부산
     처음엔 "사람인 제휴 데이터라 타 지역이 섞인다" 며 보류했으나,
     부산광역시가 운영하는 지역 포털이고 게시 목적 자체가 부산 구인·구직 연결이므로
     지역 표기가 없는 건도 부산으로 본다(사용자 판단).
     판정근거 컬럼에 '부산포털(지역미상)' 으로 남겨 나중에 구분할 수 있게 한다.
"""
import csv, re
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
BUILD, OUT = BASE / "build", BASE / "부산"
BUSAN_SGG = {"강서구", "금정구", "기장군", "남구", "동구", "동래구", "부산진구", "북구",
             "사상구", "사하구", "서구", "수영구", "연제구", "영도구", "중구", "해운대구"}

# 제목에서 부산을 판정할 때 쓰는 지명.
# '기장' 은 '세무기장', '사상' 은 '사상 최대' 처럼 다른 뜻으로 훨씬 자주 쓰여서 넣지 않는다.
# '남구·동구·중구·서구·북구' 도 다른 광역시에 같은 이름이 있어 제외한다.
BUSAN_WORD = re.compile(
    r"부산|해운대|센텀시티|센텀|광안리|남포동|자갈치|서면역|"
    r"동래구|금정구|연제구|수영구|영도구|사하구|부산진구|기장군|사상구")

def is_busan(r):
    if r.get("시도") == "부산":
        return True, "시도=부산"
    if "부산" in (r.get("지역원문") or ""):
        return True, "지역원문에 부산 포함"
    if (r.get("시군구") or "") in BUSAN_SGG and not r.get("시도"):
        return True, "부산 소속 시군구"
    if BUSAN_WORD.search((r.get("공고제목") or "") + " " + (r.get("상세주소") or "")):
        return True, "제목·주소에 부산 지명"
    if r.get("사이트") == "부산일자리정보망":
        return True, "부산포털(지역미상)"
    return False, ""

def dump(path, cols, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    print(f"  -> {path.relative_to(BASE)} ({len(rows):,}행)")

def main():
    src = BUILD / "공고_정규화.csv"
    rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
    cols = list(rows[0].keys()) if rows else []
    busan, hold = [], []
    why = Counter()
    for r in rows:
        ok, reason = is_busan(r)
        if ok:
            r = dict(r); r["부산판정근거"] = reason
            busan.append(r); why[reason] += 1

    print(f"입력 {len(rows):,}행 → 부산 {len(busan):,}행\n")
    print("판정 근거별")
    for k, v in why.most_common():
        print(f"   {k:22s}{v:8,}")

    OUT.mkdir(exist_ok=True)
    dump(OUT / "부산_공고_원본.csv", cols + ["부산판정근거"], busan)
    if hold:
        dump(OUT / "부산_판정보류.csv", cols, hold)

    # 사이트별 요약
    by = Counter(r["사이트"] for r in busan)
    dump(OUT / "부산_사이트별.csv", ["사이트", "건수"],
         [{"사이트": s, "건수": n} for s, n in by.most_common()])
    print("\n사이트별 부산 공고")
    for s, n in by.most_common():
        print(f"   {s:<16}{n:>8,}")

    # 통합 마스터가 있으면 부산분만 골라낸다
    m = BUILD / "공고_통합.csv"
    if m.exists():
        mrows = list(csv.DictReader(open(m, encoding="utf-8-sig")))
        mcols = list(mrows[0].keys()) if mrows else []
        mb = [r for r in mrows
              if r.get("시도") == "부산"
              or (r.get("시군구") in BUSAN_SGG and not r.get("시도"))
              or "부산일자리정보망" in (r.get("게재사이트") or "")]
        dump(OUT / "부산_공고_통합.csv", mcols, mb)

    # 직무 상위
    duty = Counter()
    for r in busan:
        for d in (r.get("직무") or "").split(","):
            d = d.strip()
            if d:
                duty[d] += 1
    print("\n부산 공고 직무 상위 15")
    for d, n in duty.most_common(15):
        print(f"   {d:<20}{n:>7,}")

if __name__ == "__main__":
    main()
