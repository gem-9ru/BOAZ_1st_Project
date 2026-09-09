"""문서 수치를 산출물 실측값으로 동기화한다.

[왜 스크립트로 하나]
파이프라인을 고칠 때마다 25,244 → 25,245 처럼 전 수치가 움직인다. 문서 8개에
흩어진 숫자를 손으로 고치면 반드시 어딘가 옛 숫자가 남는다. 실제로 그렇게
남은 값이 여러 번 나왔고, 한 번은 오염된 전이 상태 값을 문서에 반영했다.

실행:  python3 src/sync_docs.py          동기화
       python3 src/sync_docs.py --check  검사만 (남은 옛 수치 보고)
"""
import csv, collections, re, sys
from pathlib import Path

csv.field_size_limit(10 ** 9)
BASE = Path(__file__).resolve().parent.parent
DOCS = ["README.md", "부산/README.md", "분석/README.md", "분석/수동분류/README.md",
        "build/README.md", "data/README.md"] + \
       [str(p.relative_to(BASE)) for p in sorted((BASE / "docs").glob("*.md"))]
EXTRA = [Path.home() / "Downloads" / "부산_채용공고_final" / "설명.md"]


def load(p):
    return list(csv.DictReader((BASE / p).open(encoding="utf-8-sig")))


def figures():
    r = load("부산/부산_공고_직종분류.csv")
    a = load("분석/부산_공고_분석용.csv")
    e = load("부산/직종분류_정확도.csv")
    n = len(r)
    f = {"공고": n,
         "세세분류": sum(1 for x in r if x["직종코드깊이"] == "6"),
         "대분류만": sum(1 for x in r if x["직종코드깊이"] == "1"),
         "미분류": sum(1 for x in r if x["직종코드깊이"] == "0"),
         "대분류부여": sum(1 for x in r if x["직종대분류코드"]),
         "직종종수": len({x["직종코드"] for x in r if x["직종코드"]}),
         "정답세트": len(e), "연봉명시": sum(1 for x in a if x["연봉환산최소"]),
         "13대분류부여": sum(1 for x in r if x["직종분류코드"]),
         "6자리보유": sum(1 for x in r if len(x["직종코드"]) == 6)}
    for k, v in [("강", "강"), ("중", "중"), ("약", "약")]:
        f["확실도_" + k] = sum(1 for x in r if x["직종코드확실도"] == v)
        f["부산_" + k] = sum(1 for x in r if x["부산판정확실도"] == v)
    f["확실도_강중"] = sum(1 for x in r if x["직종코드확실도"] in ("강", "중"))
    for k in ["고용24직접", "별칭일치", "학습사전", "상위합의"]:
        f["근거_" + k] = sum(1 for x in r if x["직종코드근거"] == k)
    for c in ["담당업무", "자격요건", "우대사항", "직무상세", "급여", "급여최소", "학력",
              "시군구", "회사명", "업종", "근무시간", "상세주소", "채용인원", "직종"]:
        f["채움_" + c] = 100 * sum(1 for x in r if (x.get(c) or "").strip()) / n
    hc = [int(x["채용인원"]) for x in r if (x["채용인원"] or "").isdigit()]
    f["인원명시"], f["인원합"] = len(hc), sum(hc)
    for k in ["별칭일치", "학습사전", "상위합의", "미분류"]:
        f["평가_" + k] = sum(1 for x in e if x["근거"] == k)
    sm = [x for x in e if x["근거"] in ("별칭일치", "학습사전")]
    f["평가_강중"] = len(sm)
    hit = collections.Counter()
    for x in e:
        p, t = x["예측코드"], x["정답코드"]
        for d, key in ((1, "대"), (2, "중"), (3, "소"), (4, "세"), (6, "세세")):
            if len(p) >= d:
                hit[key + "n"] += 1
                hit[key + "o"] += (p[:d] == t[:d])
    for key in ["대", "중", "소", "세", "세세"]:
        f["정확도_" + key] = 100 * hit[key + "o"] / max(hit[key + "n"], 1)
    tv = collections.Counter(x["정답코드"][:1] for x in e)
    pv = collections.Counter(x["예측코드"][:1] for x in e if x["예측코드"])
    m = sum(pv.values())
    f["TVD"] = 0.5 * sum(abs(100 * tv[k] / len(e) - 100 * pv[k] / m) for k in map(str, range(10)))
    er = [x for x in e if len(x["예측코드"]) == 6 and x["예측코드"] != x["정답코드"]]
    f["6자리오류"] = len(er)
    f["6자리오류_4자리일치"] = sum(1 for x in er if x["예측코드"][:4] == x["정답코드"][:4])
    return f


def counts():
    """행수·컬럼수는 파일에서 직접 센다. 문서에 손으로 적어 두면 반드시 어긋난다."""
    c = {}
    for rel in ["build/공고_정규화.csv", "build/공고_통합.csv", "build/중복매핑.csv",
                "부산/부산_공고_원본.csv", "부산/부산_공고_통합.csv",
                "부산/부산_판정보류.csv", "부산/부산_직종별_집계.csv",
                "부산/부산_직종대분류_집계.csv", "부산/부산_공고_직종분류.csv",
                "분석/부산_공고_분석용.csv"]:
        p = BASE / rel
        if not p.exists():          # build/ 는 .gitignore — 없으면 건너뛴다
            continue
        with p.open(encoding="utf-8-sig") as f:
            rd = csv.reader(f)
            head = next(rd)
            c[rel] = (sum(1 for _ in rd), len(head))
    return c


# 줄 단위 인라인 수치 동기화.
#   (그 줄에 이게 있으면, 이 패턴의 숫자를, 이 값으로)
# 파일명·라벨을 앵커로 잡아 우연히 같은 숫자를 건드리지 않게 한다.
def inline_rules(f, c):
    R = []

    def add(anchor, pat, val, skip=None):
        R.append((anchor, re.compile(pat), str(val), skip))

    def rows(rel):
        return f"{c[rel][0]:,}" if rel in c else None

    def cols(rel):
        return c[rel][1] if rel in c else None

    # 파이프라인 단계 — "정규화 227,214행 → 중복병합 161,351건"
    if rows("build/공고_정규화.csv"):
        add("정규화", r"(?<=정규화 )[\d,]+(?=행)", rows("build/공고_정규화.csv"))
        add("공고_정규화.csv", r"[\d,]+(?=행)", rows("build/공고_정규화.csv"))
    if rows("build/공고_통합.csv"):
        add("중복병합", r"(?<=중복병합 )[\d,]+(?=건)", rows("build/공고_통합.csv"))
        # `부산/부산_공고_통합.csv` 도 이름이 겹친다 — 그 줄은 건드리지 않는다
        add("공고_통합.csv", r"[\d,]+(?=건)", rows("build/공고_통합.csv"),
            skip="부산_공고_통합")
    if rows("build/중복매핑.csv"):
        add("중복매핑.csv", r"[\d,]+(?=행)", rows("build/중복매핑.csv"))
    if rows("부산/부산_공고_원본.csv"):
        add("부산_공고_원본.csv", r"[\d,]+(?=행| \|)", rows("부산/부산_공고_원본.csv"))
        add("결과: 원본", r"(?<=결과: 원본 )[\d,]+(?=행)", rows("부산/부산_공고_원본.csv"))
    if rows("부산/부산_직종별_집계.csv"):
        add("부산_직종별_집계.csv", r"[\d,]+(?=종| \|)", rows("부산/부산_직종별_집계.csv"))

    # 컬럼수 — 줄에 파일명이 있으면 그 줄의 `N컬럼` 을 고친다
    for rel, key in [("부산/부산_공고_직종분류.csv", "부산_공고_직종분류.csv"),
                     ("분석/부산_공고_분석용.csv", "부산_공고_분석용.csv"),
                     ("부산/부산_공고_통합.csv", "부산_공고_통합.csv")]:
        if cols(rel):
            add(key, r"\d+(?=컬럼)", cols(rel))

    # 직종 분류 현황 — "세세분류까지 8,670건(34.5%) · 대분류까지 24,383건(97.0%)"
    # 건수와 백분율을 함께 갈아야 한다. 하나만 고치면 더 헷갈린다.
    add("세세분류까지", r"(?<=세세분류까지 )[\d,]+(?=건)", f"{f['세세분류']:,}")
    add("세세분류까지", r"(?<=건\()[\d.]+(?=%\))", f"{100*f['세세분류']/f['공고']:.1f}")
    add("대분류까지", r"(?<=대분류까지 )[\d,]+(?=건)", f"{f['13대분류부여']:,}")
    add("대분류까지", r"(?<=건\()[\d.]+(?=%\)\*\*)", f"{100*f['13대분류부여']/f['공고']:.1f}")
    add("총변동거리", r"(?<=\*\*)[\d.]+(?=%p)", f"{f['TVD']:.1f}")
    return R


def apply_inline(line, rules):
    for anchor, pat, val, skip in rules:
        if anchor in line and not (skip and skip in line):
            line = pat.sub(val, line, count=1)
    return line


def rows_pivot():
    out = {}
    for r in load("분석/직종대분류_지표.csv"):
        if r["직종대분류"] == "미분류":
            continue
        out[r["직종대분류"]] = (f"{int(r['공고수']):,}", r["비중"], r["대졸이상요구율"],
                              r["신입가능율"], r["정규직율"],
                              f"{int(r['연봉중앙값']):,}", r["연봉명시율"])
    return out


def rows_major():
    out = {}
    for r in load("부산/부산_직종대분류_집계.csv"):
        if r["대분류명"] == "미분류":
            continue
        out[r["대분류명"]] = (f"{int(r['부산공고수']):,}", r["비중"])
    return out


# 근거·미분류사유 표는 이름이 문서마다 다르게 적혀 있어서(`별칭일치` / `공식 명칭·별칭
# 일치`) 별칭을 함께 등록한다. 4칸 / 3칸 표 모두 이름을 키로 건수·비중을 갈아 준다.
BASIS_ALIAS = {
    "고용24 직접": "고용24직접",
    "공식 명칭·별칭 일치": "별칭일치",
    "정답에서 학습한 사전": "학습사전",
    "후보 분포 표결": "상위합의",
    "제목·담당업무 추천 1순위": "추천1순위",
    "사람이 분류표를 보고 붙임": "수동분류(공고)",
}


def rows_basis():
    """근거 → (건수, 비중). 문서 표기·내부 표기 양쪽을 키로 넣는다."""
    r = load("부산/부산_공고_직종분류.csv")
    n = len(r)
    c = collections.Counter(x["직종코드근거"] or "미분류" for x in r)
    out = {k: (f"{v:,}", f"{100 * v / n:.1f}%") for k, v in c.items()}
    for doc, key in BASIS_ALIAS.items():
        if key in out:
            out[doc] = out[key]
    return out


def rows_reason():
    """미분류사유 → 건수. 사유 문장은 `사유 — 설명` 꼴이라 앞쪽만 쓴다."""
    r = load("부산/부산_공고_직종분류.csv")
    c = collections.Counter(x["직종미분류사유"].split(" —")[0]
                            for x in r if x["직종미분류사유"])
    return {k: f"{v:,}" for k, v in c.items()}


# 확실도 표는 자동 동기화하지 않는다. `강`·`중`·`약` 이라는 이름을 직종코드확실도 ·
# 부산판정확실도 · 평가 등급별 표가 모두 쓰는데, 건수는 서로 다르기 때문이다.
# 이름을 키로 갈면 엉뚱한 표를 덮는다(실제로 부산판정 23,683 을 7,211 로 덮었다).


def sync(check=False):
    f = figures()
    c = counts()
    inl = inline_rules(f, c)
    piv, maj = rows_pivot(), rows_major()
    bas, rsn = rows_basis(), rows_reason()
    n = f["공고"]
    # 표 행은 이름을 키로 통째로 교체한다. 개별 숫자를 찾아 고치는 것보다 안전하다.
    changed = 0
    for rel in DOCS + [str(p) for p in EXTRA if p.exists()]:
        p = Path(rel) if Path(rel).is_absolute() else BASE / rel
        if not p.exists():
            continue
        lines = p.read_text().splitlines()
        out = []
        for line in lines:
            m = re.match(r"^\| ([^|]+?) \|(?:[^|]*\|){7}\s*$", line)
            if m and m.group(1).strip() in piv:
                line = f"| {m.group(1).strip()} | " + " | ".join(piv[m.group(1).strip()]) + " |"
            else:
                m3 = re.match(r"^\| ([^|]+?) \| ([\d,]+) \| ([\d.]+%) \|\s*$", line)
                if m3 and m3.group(1).strip() in maj:
                    v = maj[m3.group(1).strip()]
                    line = f"| {m3.group(1).strip()} | {v[0]} | {v[1]} |"
            # 근거 표 — `| 이름 | 건수 | 비중 | 깊이 |`
            m4 = re.match(r"^\| ([^|]+?) \| ([\d,]+) \| ([\d.]+%) \|([^|]*)\|\s*$", line)
            if m4 and m4.group(1).strip() in bas:
                v = bas[m4.group(1).strip()]
                line = f"| {m4.group(1).strip()} | {v[0]} | {v[1]} |{m4.group(4)}|"
            # 미분류사유 표 — `| `사유` | 건수 | 뜻 |`
            m5 = re.match(r"^\| `([^`]+)` \| ([\d,]+) \|([^|]*)\|\s*$", line)
            if m5 and m5.group(1) in rsn:
                line = f"| `{m5.group(1)}` | {rsn[m5.group(1)]} |{m5.group(3)}|"
            line = apply_inline(line, inl)
            out.append(line)
        new = "\n".join(out) + "\n"
        if new != p.read_text():
            changed += 1
            if not check:
                p.write_text(new)
    print(f"{'검사' if check else '동기화'}: 표 갱신 필요 문서 {changed}개")
    print("\n=== 현재 실측값 (문서에 이 숫자가 들어가야 한다) ===")
    print(f"  공고 {n:,} · 정답세트 {f['정답세트']:,} · 직종 {f['직종종수']:,}종")
    print(f"  세세분류 {f['세세분류']:,}({100*f['세세분류']/n:.1f}%) · "
          f"대분류만 {f['대분류만']:,}({100*f['대분류만']/n:.1f}%) · "
          f"미분류 {f['미분류']:,}({100*f['미분류']/n:.1f}%)")
    print(f"  대분류 부여 {f['대분류부여']:,}({100*f['대분류부여']/n:.1f}%)")
    print(f"  직종확실도 강 {f['확실도_강']:,} / 중 {f['확실도_중']:,} / 약 {f['확실도_약']:,}")
    print(f"  부산판정   강 {f['부산_강']:,} / 중 {f['부산_중']:,} / 약 {f['부산_약']:,}")
    print("  근거 " + " / ".join(f"{k.split('_')[1]} {v:,}" for k, v in f.items()
                                if k.startswith("근거_")))
    print("  채움 " + " · ".join(f"{k.split('_')[1]} {v:.1f}%" for k, v in f.items()
                                if k.startswith("채움_")))
    print(f"  채용인원 명시 {f['인원명시']:,}건 합계 {f['인원합']:,}명")
    print("  평가 " + " / ".join(f"{k.split('_')[1]} {v:,}" for k, v in f.items()
                                if k.startswith("평가_")))
    print("  정확도 " + " · ".join(f"{k.split('_')[1]}분류 {v:.1f}%" for k, v in f.items()
                                 if k.startswith("정확도_")))
    print(f"  TVD {f['TVD']:.1f}%p · 6자리오류 {f['6자리오류']:,} 중 4자리일치 "
          f"{f['6자리오류_4자리일치']:,}")
    print(f"  연봉명시 {f['연봉명시']:,}({100*f['연봉명시']/n:.0f}%)")


if __name__ == "__main__":
    sync(check="--check" in sys.argv)
