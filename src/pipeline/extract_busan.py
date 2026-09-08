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
    """(부산여부, 판정근거, 확실도) — 확실도: 강 / 중 / 약

    [왜 등급을 나누는가]
    다지역 공고("서울, 경기, 대구, 경북, 부산, 경남")를 넣는 건 맞지만,
    "정말 부산에서 뽑는가" 는 따로 확인해야 한다. 지역 태그가 넓게 붙었을 뿐
    실제 근무지는 서울인 공고를 넣으면 부산 수요가 부풀려진다.

    → **상세페이지의 근무지주소를 정본으로 본다.**
       주소가 부산이면 확실하고, 주소가 있는데 부산이 아니면서 지역칸에도 부산이 없으면
       제목에 '부산' 이 있어도 부산 근무로 보지 않는다(보류로 뺀다).

    [실측 근거]
      · 잡코리아 부산 지역필터로 받은 3,319건 중 상세 근무지주소가 부산인 것 3,318건(99.97%)
        → 사이트 지역 필터는 믿을 만하다
      · 부산일자리정보망 상세 다지역 1,431건 중 1,357건이 부산 포함.
        나머지 74건도 "강서구,수영구" 처럼 부산 시군구만 적힌 것이라 실제로는 전부 부산
    """
    addr = r.get("상세주소") or ""
    region = r.get("지역원문") or ""
    sido = r.get("시도") or ""
    sgg = r.get("시군구") or ""
    title = r.get("공고제목") or ""
    multi = "," in region

    # ① 상세 근무지주소에 부산 — 가장 확실하다
    if "부산" in addr or any(g in addr for g in BUSAN_SGG if len(g) > 2):
        return True, "근무지주소=부산", "강"

    # ② 사이트가 부산으로 분류
    if sido == "부산":
        return True, "다지역(부산 포함)" if multi else "시도=부산", "강" if not multi else "중"
    if "부산" in region:
        return True, "다지역(부산 포함)" if multi else "지역원문=부산", "강" if not multi else "중"
    if sgg in BUSAN_SGG and not sido:
        return True, "부산 소속 시군구", "강"

    # ③ 부산광역시가 운영하는 지역 포털 — 지역 표기가 없어도 부산 공고다
    if r.get("사이트") == "부산일자리정보망":
        return True, "부산포털(지역미상)", "중"

    # ④ 제목에만 부산. 근무지주소가 이미 있는데 부산이 아니면 그 주소가 정본이다.
    if BUSAN_WORD.search(title):
        if addr:
            return False, "제목엔 부산이나 근무지주소가 타지역", "보류"
        return True, "제목에 부산 지명", "약"

    return False, "", ""

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
    conf = Counter()
    for r in rows:
        ok, reason, level = is_busan(r)
        if ok:
            r = dict(r); r["부산판정근거"] = reason; r["부산판정확실도"] = level
            busan.append(r); why[reason] += 1; conf[level] += 1
        elif level == "보류":
            # 제목엔 부산이 있으나 상세 근무지주소가 타지역인 공고.
            # 버리지 않고 따로 남겨 검토할 수 있게 한다.
            r = dict(r); r["부산판정근거"] = reason
            hold.append(r)

    print(f"입력 {len(rows):,}행 → 부산 {len(busan):,}행\n")
    print("판정 근거별")
    for k, v in why.most_common():
        print(f"   {k:26s}{v:8,}")
    print("\n확실도")
    for k in ("강", "중", "약"):
        if conf[k]:
            print(f"   {k:26s}{conf[k]:8,}")
    if hold:
        print(f"\n보류(제목엔 부산·근무지주소는 타지역) {len(hold):,}건 -> 부산_판정보류.csv")

    OUT.mkdir(exist_ok=True)

    # 통합키를 원본 행에도 채운다.
    #   `공고_정규화.csv` 의 통합키 칸은 비어 있다 — dedup 이 나중에 부여하고
    #   그 대응표는 `중복매핑.csv` 에 있다. 여기서 붙여 주지 않으면
    #   원본 파일의 통합키가 전부 빈칸이 되어 통합본과 조인할 수 없다.
    #   (병합 과정에서 값이 버려졌는지 검증하려다 이게 막혔다.)
    RANK = {"강": 0, "중": 1, "약": 2}
    key_of = {}
    mp = BUILD / "중복매핑.csv"
    if mp.exists():
        for r in csv.DictReader(open(mp, encoding="utf-8-sig")):
            key_of[(r["사이트"], r["공고URL"])] = r["통합키"]
    for r in busan:
        r["통합키"] = key_of.get((r["사이트"], r["공고URL"]), "")
    filled = sum(1 for r in busan if r["통합키"])
    print(f"  통합키 부여 {filled:,}/{len(busan):,}행")

    dump(OUT / "부산_공고_원본.csv", cols + ["부산판정근거", "부산판정확실도"], busan)
    if hold:
        dump(OUT / "부산_판정보류.csv", cols + ["부산판정근거"], hold)

    # 사이트별 요약
    by = Counter(r["사이트"] for r in busan)
    dump(OUT / "부산_사이트별.csv", ["사이트", "건수"],
         [{"사이트": s, "건수": n} for s, n in by.most_common()])
    print("\n사이트별 부산 공고")
    for s, n in by.most_common():
        print(f"   {s:<16}{n:>8,}")

    # 통합 마스터가 있으면 부산분만 골라낸다
    # [수정] 통합본은 원본과 **같은 판정**을 써야 한다.
    #   예전에는 여기서 "시도=부산 or 부산 시군구 or 부산일자리정보망" 이라는
    #   더 단순한 규칙을 따로 썼다. 그래서 근무지주소·다지역·제목으로 잡아낸 공고가
    #   원본에는 있는데 통합본에는 없는 불일치가 생겼다.
    #   → 원본에서 부산으로 판정된 행의 통합키를 모아 그걸로 거른다.
    #   판정근거·확실도는 그룹 안에서 가장 강한 것을 남긴다.
    #   통합키는 정규화 파일이 아니라 중복매핑에 있다(dedup 이 부여한다).
    best = {}
    for r in busan:
        k = r["통합키"]
        if not k:
            continue
        cur = best.get(k)
        if cur is None or RANK.get(r["부산판정확실도"], 9) < RANK.get(cur[1], 9):
            best[k] = (r["부산판정근거"], r["부산판정확실도"])

    m = BUILD / "공고_통합.csv"
    if m.exists():
        mrows = list(csv.DictReader(open(m, encoding="utf-8-sig")))
        mcols = (list(mrows[0].keys()) if mrows else []) + ["부산판정근거", "부산판정확실도"]
        mb = []
        for r in mrows:
            hit = best.get(r.get("통합키"))
            if not hit:
                continue
            r = dict(r); r["부산판정근거"], r["부산판정확실도"] = hit
            mb.append(r)
        dump(OUT / "부산_공고_통합.csv", mcols, mb)
        c = Counter(r["부산판정확실도"] for r in mb)
        print("  통합본 확실도  " + " / ".join(f"{k} {c[k]:,}" for k in ("강", "중", "약") if c[k]))

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
