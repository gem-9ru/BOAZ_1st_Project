"""미분류 공고 수동 분류 — 작업 시트 생성 · 적용.

    python3 src/pipeline/keco_manual.py sheet    작업 시트 만들기
    python3 src/pipeline/keco_manual.py apply    채운 시트 검증 + 반영

[왜 손으로 붙이나]
자동 분류는 공식 명칭 1,130개와의 **문자열 대조**로만 한다. 그래서 KECO 어휘에
없는 실무 관용어가 통째로 빠진다. `생산직`(KECO 는 `~원` 을 쓴다) · `병동`·`원무과`
(부서·근무공간) · `피부관리사`·`수의테크니션`(분류표에 없는 신직종).
사람이 분류표를 보고 붙이면 이게 해결된다. 규칙으로 흉내내려면 손 사전이 필요한데,
그럴 거면 처음부터 사람이 붙이는 쪽이 정확하고 근거도 남는다.

[작업 단위를 둘로 나눈 이유]
미분류 3,854건을 한 줄씩 보면 오래 걸린다. 그런데 직무 토큰은 반복된다.
    상위  50개 토큰 → 1,381건 (35.8%)
    상위 300개 토큰 → 1,969건 (51.1%)
그래서 **토큰 시트로 절반을 걷고, 토큰으로 안 걸리는 것만 공고 단위로** 본다.
토큰이 아예 없는 공고(1,152건)는 제목밖에 단서가 없어 처음부터 공고 단위다.

[입력 규칙]
`직종코드` 칸에 아래 중 아무 자릿수나 적으면 된다. 확실한 만큼만 적으면 된다.
    6자리 550102   세세분류 — 재가 요양보호사
    4자리 5501     세분류
    3자리 550      소분류
    2자리 55       중분류
    1자리 5        대분류 — 미용·여행·숙박·음식·경비·돌봄·청소
비우면 미분류로 남는다. `x` 를 적으면 "분류 불가" 로 확정한다(빈칸과 구분하려면).

[우선순위]
수동분류는 **자동이 미분류로 남긴 공고에만** 적용된다. 이미 코드가 붙은 공고를
덮어쓰지 않으므로, 시트를 채워도 기존 정확도가 나빠질 일은 없다.
공고 시트가 토큰 시트보다 우선한다(그 공고를 직접 보고 붙인 것이므로).
"""
import csv, sys, collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keco_v2 import Master, tokens, norm, core_of     # noqa: E402

csv.field_size_limit(10 ** 9)
BASE = Path(__file__).resolve().parents[2]
SRC = BASE / "부산" / "부산_공고_직종분류.csv"
WORK = BASE / "분석" / "수동분류"
REF = WORK / "0_직종코드_분류표.csv"
TOKSHEET = WORK / "1_토큰_분류.csv"
JOBSHEET = WORK / "2_공고_분류.csv"
# 채운 결과는 여기로 옮겨 커밋한다 — 파이프라인을 다시 돌려도 작업이 살아 있게
STORE_TOK = BASE / "data" / "keco" / "수동분류_토큰.csv"
STORE_JOB = BASE / "data" / "keco" / "수동분류_공고.csv"

TOP_TOKENS = 300


# ---------------------------------------------------------------------------
def _bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def suggest(tok, cores, k=3):
    """분류표에서 글자가 가장 많이 겹치는 명칭 k개. 후보를 훑는 시간을 줄여 준다.

    괄호 안까지 본다. `md` 는 본체명(`머천다이저`)과는 안 겹치지만
    전체명 `머천다이저(MD)` 와는 겹친다. `원무과` → `병원행정 사무원(원무)` 도 그렇다.
    본체명만 보던 처음 판에서는 엔지니어·실장·원무과·md 의 후보가 전부 비었다.

    이 후보는 **훑는 시간을 줄이는 힌트일 뿐 정답이 아니다.**
    글자만 보므로 `생산직` 에 `생산관리 사무원` 을 내놓는다(정답은 생산 현장직).
    """
    a = _bigrams(tok)
    sc = []
    for cr, full, code, nm in cores:
        j = max(len(a & b) / len(a | b) for b in (_bigrams(cr), _bigrams(full)))
        if j > 0:
            sc.append((round(j, 4), code, nm))
    sc.sort(reverse=True)
    return sc[:k]


def load_rows():
    return list(csv.DictReader(SRC.open(encoding="utf-8-sig")))


def cmd_sheet():
    m = Master()
    rows = load_rows()
    un = [r for r in rows if r["직종코드확실도"] == "미분류"]
    WORK.mkdir(parents=True, exist_ok=True)

    # ── 0. 참조용 분류표 — 대분류·중분류로 묶고, 부산에 실제로 나온 건수를 붙인다
    used = collections.Counter(r["직종코드"] for r in rows if r["직종코드"])
    with REF.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["대분류코드", "대분류명", "중분류코드", "소분류코드",
                    "직종코드", "직종명", "부산공고수(자동분류분)"])
        for c in sorted(m.name, key=lambda c: (c[:1], c[:2], c[:3], c)):
            L = m.levels(c)
            w.writerow([L["직종대분류코드"], L["직종대분류명"], L["직종중분류코드"],
                        L["직종소분류코드"], c, m.name[c], used[c] or ""])

    # ── 1. 토큰 시트
    cnt = collections.Counter()
    title = collections.defaultdict(list)
    for r in un:
        for t in tokens(r["직무"]):
            cnt[t] += 1
            if len(title[t]) < 3:
                title[t].append(r["공고제목"][:44])
    cores = [(core_of(nm), norm(nm), c, nm) for c, nm in m.name.items()]
    top = cnt.most_common(TOP_TOKENS)
    with TOKSHEET.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["직무토큰", "건수", "직종코드", "메모",
                    "후보1", "후보2", "후보3", "예시1", "예시2", "예시3"])
        for t, n in top:
            s = suggest(t, cores)
            ex = title[t] + [""] * 3
            w.writerow([t, n, "", ""] +
                       [f"{c} {nm}" for _, c, nm in s] + [""] * (3 - len(s)) +
                       ex[:3])

    # ── 2. 공고 시트 — 토큰 시트를 다 채워도 안 걸리는 공고
    topset = {t for t, _ in top}
    left = [r for r in un if not (set(tokens(r["직무"])) & topset)]
    # 같은 토큰·비슷한 제목끼리 붙여 놓아 위에서 한 번 채우면 아래로 복사할 수 있게 한다.
    # 토큰이 없는 공고(제목밖에 단서가 없는 것)는 맨 뒤로 몰아 둔다.
    left.sort(key=lambda r: (not tokens(r["직무"]),
                             ", ".join(tokens(r["직무"])), r["공고제목"]))
    with JOBSHEET.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["공고ID", "직종코드", "메모", "공고제목", "직무토큰",
                    "회사명", "업종", "시군구", "대표URL"])
        for r in left:
            w.writerow([r["통합키"], "", "", r["공고제목"],
                        ", ".join(tokens(r["직무"])), r["회사명"],
                        r["업종"] if r["업종"] != "-" else "", r["시군구"], r["대표URL"]])

    print(f"{REF.relative_to(BASE)}       {len(m.name):,}행  ← 분류표 (대분류→중분류 정렬)")
    print(f"{TOKSHEET.relative_to(BASE)}          {len(top):,}행  ← 먼저 이걸 채우세요")
    print(f"{JOBSHEET.relative_to(BASE)}          {len(left):,}행  ← 토큰으로 안 걸리는 공고")
    covered = len(un) - len(left)
    print(f"\n미분류 {len(un):,}건")
    print(f"  토큰 시트 {len(top)}행을 다 채우면      {covered:,}건 ({100*covered/len(un):.0f}%)")
    print(f"  나머지는 공고 시트에서 한 줄씩          {len(left):,}건")
    print(f"\n채우고 나면:")
    print(f"  cp {TOKSHEET.relative_to(BASE)} {STORE_TOK.relative_to(BASE)}")
    print(f"  cp {JOBSHEET.relative_to(BASE)} {STORE_JOB.relative_to(BASE)}")
    print(f"  python3 src/pipeline/keco_manual.py apply")


# ---------------------------------------------------------------------------
def load_manual(m):
    """(토큰→코드, 공고ID→코드). 코드 검증까지 여기서 한다."""
    tok, job, bad = {}, {}, []

    def check(code, where):
        code = (code or "").strip()
        if not code or code.lower() == "x":
            return ""
        if code in m.name:                     # 6자리 세세분류
            return code
        if len(code) in (1, 2, 3, 4) and any(c.startswith(code) for c in m.name):
            return code                        # 존재하는 상위 접두
        bad.append((where, code))
        return ""

    if STORE_TOK.exists():
        for r in csv.DictReader(STORE_TOK.open(encoding="utf-8-sig")):
            c = check(r.get("직종코드"), f"토큰 {r.get('직무토큰')}")
            if c:
                tok[norm(r["직무토큰"])] = c
    if STORE_JOB.exists():
        for r in csv.DictReader(STORE_JOB.open(encoding="utf-8-sig")):
            c = check(r.get("직종코드"), f"공고 {r.get('공고ID')}")
            if c:
                job[r["공고ID"].strip()] = c
    return tok, job, bad


def cmd_apply():
    m = Master()
    tok, job, bad = load_manual(m)
    if bad:
        print(f"!! 분류표에 없는 코드 {len(bad)}개 — 고쳐 주세요")
        for w, c in bad[:20]:
            print(f"   {w}: {c}")
        return
    if not tok and not job:
        print(f"채운 시트가 없습니다. {STORE_TOK.relative_to(BASE)} / "
              f"{STORE_JOB.relative_to(BASE)} 로 복사한 뒤 다시 실행하세요.")
        return

    rows = load_rows()
    cols = list(rows[0].keys())
    st = collections.Counter()
    for r in rows:
        if r["직종코드확실도"] != "미분류":
            continue
        code, why = "", ""
        if r["통합키"] in job:                  # 공고 시트가 우선
            code, why = job[r["통합키"]], "수동분류(공고)"
        else:
            for t in tokens(r["직무"]):
                if t in tok:
                    code, why = tok[t], "수동분류(토큰)"
                    break
        if not code:
            continue
        r.update(m.levels(code))
        r["직종코드근거"] = why
        # 사람이 분류표를 보고 붙인 값이다. 6자리면 강, 상위 접두면 그 깊이만큼.
        r["직종코드확실도"] = "강" if len(code) == 6 else "중"
        r["직종매칭토큰"] = "수동"
        r["직종후보코드"] = ""
        st[why] += 1

    with SRC.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

    g = collections.Counter(r["직종코드확실도"] for r in rows)
    n = len(rows)
    print(f"{SRC.relative_to(BASE)}  {n:,}건")
    print(f"  수동분류 적용 — 토큰 {st['수동분류(토큰)']:,}건 · 공고 {st['수동분류(공고)']:,}건")
    print(f"  미분류 {g['미분류']:,}건 ({100*g['미분류']/n:.1f}%)")
    print(f"  대분류 부여 {n - g['미분류']:,}건 ({100*(n-g['미분류'])/n:.1f}%)")
    print("\n이어서:  python3 src/pipeline/refine.py && python3 src/make_deliverable.py")


if __name__ == "__main__":
    {"sheet": cmd_sheet, "apply": cmd_apply}[sys.argv[1] if len(sys.argv) > 1 else "sheet"]()
