"""분석용 정제 — 원본 64컬럼 → 분석 24컬럼.

[왜 따로 만드나]
`부산/부산_공고_직종분류.csv` 는 **원본 보존**이 원칙이라 가공값 옆에 사이트 원문을
함께 싣는다. 검증에는 좋지만 대시보드에 그대로 물리면 컬럼이 64개고, 같은 뜻의
값이 여러 표기로 흩어져 있어 집계가 안 된다.

  학력            34종 — `대학(2,3년)↑` `초대졸↑` `대졸(2~3년)~대졸(4년)` …
  고용형태표준     24종 — `계약직, 정규직` 처럼 복수값
  경력구분        `기타` 1,479건 — `관계없음` 758건이 여기 빠져 있었다
  급여최소/최대    `연봉 5,027~7,078만원` 이 최소=7078·최대=(빈칸) 으로 들어갔다

이 파일은 그것들을 **한 뜻 한 표기**로 접고, 분석에 안 쓰는 컬럼을 뺀다.

[프로젝트 목표에 맞춘 컬럼 선정]
주제는 "인재 배출과 기업 수요의 엇갈린 결 — 부산 청년 유출". 비교축이 셋이다.
  ① 무슨 일자리냐        직종대분류·중분류·직종명
  ② 청년이 갈 수 있냐    요구학력 · 경력요건 · 최소연차
  ③ 갈 만한 자리냐        고용형태 · 연봉환산 · 채용인원
여기에 지역(시군구)·수요강도(게재사이트수)·품질플래그를 붙였다.
담당업무·자격요건·우대사항·직무토큰·URL 목록·`원본_` 컬럼은 뺀다 — 원본에 있다.

실행:  python3 src/pipeline/refine.py
"""
import csv, re, sys, collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detail_join                                     # noqa: E402  split_pay

csv.field_size_limit(10 ** 9)
BASE = Path(__file__).resolve().parents[2]
SRC = BASE / "부산" / "부산_공고_직종분류.csv"
OUTDIR = BASE / "분석"
OUT = OUTDIR / "부산_공고_분석용.csv"
PIVOT = OUTDIR / "직종대분류_지표.csv"
CROSS = OUTDIR / "시군구_직종대분류.csv"

COLS = ["공고ID", "회사명", "공고제목",
        "직종대분류", "직종중분류코드", "직종코드", "직종명", "직종신뢰도",
        "직종추정코드", "직종추정명",
        "업종원문", "시군구",
        "고용형태", "고용형태복수", "요구학력", "경력요건", "최소연차",
        "급여형태", "연봉환산최소", "연봉환산최대",
        "채용인원", "채용인원구분", "마감구분", "게재사이트수",
        "부산확실도", "대표URL"]

# ---------------------------------------------------------------------------
# 학력 — 34종을 진입장벽 6단계로 접는다
# ---------------------------------------------------------------------------
# `고졸~대졸(4년)` 은 고졸도 받는다는 뜻이다. **범위는 하한**을 쓴다.
# 진입장벽을 보려는 것이므로 "최소 무엇을 요구하나" 가 답이어야 한다.
EDU_ORDER = ["학력무관", "중졸이하", "고졸", "전문대졸", "대학교졸", "석사이상"]
_EDU = [
    (r"학력\s*무관|무관", "학력무관"),
    (r"중졸|중학교|고등학교\s*미만", "중졸이하"),
    (r"고졸|고등학교", "고졸"),
    (r"초대졸|대학\(2,?3년\)|대졸\(2~?3년\)|전문대", "전문대졸"),
    (r"대학교\(4년\)|대졸\(4년\)|대졸", "대학교졸"),
    (r"석사|박사|대학원", "석사이상"),
]


def fold_edu(v):
    v = (v or "").strip()
    if not v:
        return "미기재"
    head = re.split(r"[~〜]", v)[0].strip() or v      # 범위면 하한
    # 부산일자리정보망은 `대학졸업(2,3년)이상` 처럼 `졸업` 을 끼워 적는다.
    # 떼면 `대학(2,3년)` 이 되어 다른 사이트 표기와 같아진다.
    head = head.replace("졸업", "")
    for pat, label in _EDU:
        if re.search(pat, head):
            return label
    return "미기재"


# ---------------------------------------------------------------------------
# 고용형태 — 복수값을 대표 하나 + 복수 플래그로
# ---------------------------------------------------------------------------
# `계약직, 정규직` 2,317건. 대표값만 남기면 안정성을 과대평가하게 되므로
# **복수 여부를 따로 남긴다.** 분석에서 애매한 건을 빼고 볼 수 있다.
EMP_ORDER = ["정규직", "계약직", "인턴", "파견", "프리랜서", "알바"]


def fold_emp(v):
    parts = [x.strip() for x in (v or "").split(",") if x.strip()]
    if not parts:
        return "미기재", ""
    picked = next((e for e in EMP_ORDER if e in parts), parts[0])
    return picked, "Y" if len(parts) > 1 else "N"


# ---------------------------------------------------------------------------
# 급여 — 형태가 다른 값을 연봉(만원)으로 환산
# ---------------------------------------------------------------------------
# 시급 10,320원 과 연봉 3,000만원 을 한 축에 놓을 수 없으면 급여 비교가 안 된다.
# 월 소정근로 209시간 · 월 22일 기준으로 연 환산한다.
#   시급 ×209×12   일급 ×22×12   주급 ×52   월급 ×12   연봉 ×1
# `회사내규`·`협의`·`면접후결정`·`건별` 은 금액이 없어 빈칸으로 남긴다.
PAY_MULT = {"연봉": 1, "월급": 12, "주급": 52, "일급": 264, "시급": 2508}
_PAY_WON = {"시급", "일급"}          # 이 둘만 원 단위로 저장돼 있다


def to_annual(kind, v):
    if kind not in PAY_MULT or not v:
        return ""
    n = int(v) * PAY_MULT[kind]
    if kind in _PAY_WON:
        n //= 10000
    # 연봉 500만원 미만·5억 초과는 파싱 실패로 본다(월급 칸에 시급이 오는 등)
    return str(n) if 500 <= n <= 50000 else ""


CAREER = {"무관", "신입", "경력"}

# 업종 칸에 공고 제목이 들어온 행이 있다(건설워커 파싱).
#   "2026년 건축/안전/토목/경영/BIM 경력사원 모집"
# `기타 사업지원 서비스업` 같은 정상 값을 지우지 않도록 좁게 잡는다.
_IND_JUNK = re.compile(r"모집|채용\s*공고|구인|^\[")


def clean_industry(v):
    v = (v or "").strip()
    if not v or v == "-" or _IND_JUNK.search(v):
        return ""
    return v

# ---------------------------------------------------------------------------
# 시군구 — 부산 16개 구·군으로 제한
# ---------------------------------------------------------------------------
# 원본에는 103종이 들어 있다. 두 가지가 섞여서다.
#   ① `진구` 237건 — `부산진구` 가 잘려 들어왔다
#   ② `대구` 93 · `김해시` 89 · `강남구` 64 … — 다지역 공고의 대표 근무지가
#      타지역으로 잡힌 것. 공고 자체는 부산 판정을 통과했지만 **어느 구인지는 모른다**
# 지역 차트를 그리려면 17종(16구군 + 미상)이어야 한다. 타지역 값은 미상으로 접는다.
BUSAN_SGG = {"중구", "서구", "동구", "영도구", "부산진구", "동래구", "남구", "북구",
             "해운대구", "사하구", "금정구", "강서구", "연제구", "수영구", "사상구", "기장군"}


def fold_sgg(v):
    v = (v or "").strip()
    if v == "진구":
        return "부산진구"
    return v if v in BUSAN_SGG else "미상"


def main():
    rows = list(csv.DictReader(SRC.open(encoding="utf-8-sig")))
    OUTDIR.mkdir(exist_ok=True)
    out, st = [], collections.Counter()

    for r in rows:
        # 급여 — 원문에서 다시 쪼갠다(고친 split_pay 로).
        kind, lo, hi = detail_join.split_pay(r.get("급여"))
        if kind != r.get("급여형태") or lo != r.get("급여최소"):
            st["급여_재파싱"] += 1
        alo, ahi = to_annual(kind, lo), to_annual(kind, hi)

        # 경력 — `기타` 는 원문에서 다시 판정한다.
        car = (r.get("경력구분") or "").strip()
        if car not in CAREER:
            from normalize import norm_career
            car, yrs = norm_career(r.get("원본_경력"))
            st["경력_재판정"] += 1
        else:
            yrs = r.get("최소연차") or ""
        car = car if car in CAREER else "미기재"

        emp, emp_multi = fold_emp(r.get("고용형태표준"))
        edu = fold_edu(r.get("학력"))
        dl = (r.get("마감구분") or "").strip()
        dl = {"기한": "기한", "상시": "상시"}.get(dl, "미기재")

        out.append({
            "공고ID": r["통합키"], "회사명": r["회사명"], "공고제목": r["공고제목"],
            "직종대분류": r["직종대분류명"] or "미분류",
            "직종중분류코드": r["직종중분류코드"],
            "직종코드": r["직종코드"], "직종명": r["직종명"],
            "직종신뢰도": r["직종코드확실도"],
            # `약` 등급 참고값. 홀드아웃 실측 세세분류 7% · 중분류 42%.
            # 집계에 쓰면 안 된다 — 눈으로 훑을 때만 쓴다.
            "직종추정코드": r.get("직종추정코드", ""),
            "직종추정명": r.get("직종추정명", ""),
            "업종원문": clean_industry(r["업종"]),
            "시군구": fold_sgg(r["시군구"]),
            "고용형태": emp, "고용형태복수": emp_multi,
            "요구학력": edu, "경력요건": car, "최소연차": yrs,
            "급여형태": kind or "미기재",
            "연봉환산최소": alo, "연봉환산최대": ahi,
            "채용인원": r["채용인원"], "채용인원구분": r["채용인원구분"],
            "마감구분": dl, "게재사이트수": r["게재사이트수"],
            "부산확실도": r["부산판정확실도"], "대표URL": r["대표URL"],
        })

    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader(); w.writerows(out)

    n = len(out)
    print(f"{OUT.relative_to(BASE)}  {n:,}건 · {len(COLS)}컬럼")
    print(f"  급여 재파싱 {st['급여_재파싱']:,}건 · 경력 재판정 {st['경력_재판정']:,}건")
    for c in ["직종대분류", "요구학력", "경력요건", "고용형태", "급여형태", "마감구분", "시군구"]:
        k = collections.Counter(x[c] for x in out)
        print(f"\n  {c} ({len(k)}종)")
        for v, m in k.most_common():
            print(f"     {m:>6,}  {100*m/n:5.1f}%  {v}")
    make_pivot(out)
    make_cross(out)
    ann = [int(x["연봉환산최소"]) for x in out if x["연봉환산최소"]]
    ann.sort()
    print(f"\n  연봉환산최소 {len(ann):,}건 ({100*len(ann)/n:.0f}%)  "
          f"중앙값 {ann[len(ann)//2]:,}만원  "
          f"25% {ann[len(ann)//4]:,}  75% {ann[3*len(ann)//4]:,}")
    return out


def _med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else ""


def make_pivot(out):
    """직종대분류별 핵심 지표. 대시보드의 기준 표다.

    [비율의 분모에 주의]
    `대졸이상요구` 는 학력을 **밝힌 공고** 기준이다. 전체를 분모로 쓰면
    미기재 28% 가 '대졸을 안 요구한다' 로 잘못 세어진다.
    분모 건수를 `학력명시` 컬럼으로 함께 실어 검산할 수 있게 했다.
    """
    g = collections.defaultdict(list)
    for r in out:
        g[r["직종대분류"]].append(r)
    tot = sum(1 for r in out if r["직종대분류"] != "미분류")
    rows = []
    for k, v in g.items():
        edu = [r for r in v if r["요구학력"] != "미기재"]
        deg = [r for r in edu if r["요구학력"] in ("전문대졸", "대학교졸", "석사이상")]
        car = [r for r in v if r["경력요건"] != "미기재"]
        new = [r for r in car if r["경력요건"] in ("무관", "신입")]
        emp = [r for r in v if r["고용형태"] != "미기재"]
        reg = [r for r in emp if r["고용형태"] == "정규직"]
        pay = [int(r["연봉환산최소"]) for r in v if r["연봉환산최소"]]
        hc = [int(r["채용인원"]) for r in v if (r["채용인원"] or "").isdigit()]
        rows.append({
            "직종대분류": k, "공고수": len(v),
            "비중": "" if k == "미분류" else f"{100*len(v)/tot:.1f}%",
            "채용인원합": sum(hc),
            "학력명시": len(edu),
            "대졸이상요구율": f"{100*len(deg)/len(edu):.1f}%" if edu else "",
            "경력명시": len(car),
            "신입가능율": f"{100*len(new)/len(car):.1f}%" if car else "",
            "정규직율": f"{100*len(reg)/len(emp):.1f}%" if emp else "",
            "연봉명시": len(pay),
            "연봉명시율": f"{100*len(pay)/len(v):.1f}%",
            "연봉중앙값": _med(pay),
        })
    rows.sort(key=lambda r: (r["직종대분류"] == "미분류", -r["공고수"]))
    with PIVOT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"\n{PIVOT.relative_to(BASE)}  {len(rows)}행")
    print(f"  {'직종대분류':<32}{'공고수':>7}{'비중':>7}{'대졸요구':>9}{'신입가능':>9}"
          f"{'정규직':>8}{'연봉중앙':>9}{'연봉명시':>9}")
    for r in rows:
        print(f"  {r['직종대분류'][:30]:<32}{r['공고수']:>7,}{r['비중']:>7}"
              f"{r['대졸이상요구율']:>9}{r['신입가능율']:>9}{r['정규직율']:>8}"
              f"{str(r['연봉중앙값']):>9}{r['연봉명시율']:>9}")


def make_cross(out):
    """시군구 × 직종대분류 교차표. 지역별로 어떤 일자리가 몰려 있는지."""
    maj = [r["직종대분류"] for r in out]
    order = [k for k, _ in collections.Counter(maj).most_common() if k != "미분류"]
    g = collections.defaultdict(collections.Counter)
    for r in out:
        g[r["시군구"]][r["직종대분류"]] += 1
    rows = sorted(g.items(), key=lambda x: -sum(x[1].values()))
    with CROSS.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["시군구", "공고수"] + order + ["미분류"])
        for sgg, c in rows:
            w.writerow([sgg, sum(c.values())] + [c[k] for k in order] + [c["미분류"]])
    print(f"\n{CROSS.relative_to(BASE)}  {len(rows)}행 × {len(order)+3}컬럼")


if __name__ == "__main__":
    main()
