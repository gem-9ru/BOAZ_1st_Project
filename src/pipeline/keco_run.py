"""부산 공고에 KECO 직종코드를 부여하고 정확도를 실측한다.

  python3 src/pipeline/keco_run.py eval    정답 2,560건 5-fold 교차검증
  python3 src/pipeline/keco_run.py build   최종 산출물 생성
"""
import csv, sys, random, collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.keco_v2 import Master, Classifier, tokens, norm, core_of, STOP  # noqa
from pipeline import keco_manual                                            # noqa
from pipeline import keco_lexicon                                           # noqa
from pipeline import keco13                                                 # noqa

csv.field_size_limit(10 ** 9)
BASE = Path(__file__).resolve().parents[2]
SRC = BASE / "부산" / "부산_공고_통합.csv"
OUT = BASE / "부산" / "부산_공고_직종분류.csv"
AGG = BASE / "부산" / "부산_직종별_집계.csv"
EVALOUT = BASE / "부산" / "직종분류_정확도.csv"

# `직종` 이 아닌 원본 컬럼. 정확도 측정에서 정답 누출을 걸러내는 기준이 된다.
RAW = ["공고제목", "직무상세", "직무키워드", "담당업무", "자격요건", "우대사항",
       "원본_직무", "직급직책"]
# 본문 스캔용. `직종` 은 정답이라 절대 넣지 않는다.
SCAN = ["담당업무", "자격요건", "직무상세", "공고제목"]


def scan_text(row):
    return " ".join((row.get(c) or "")[:200] for c in SCAN)


def load():
    return list(csv.DictReader(SRC.open(encoding="utf-8-sig")))


def leakfree_tokens(row):
    """`직종` 유래 토큰을 뺀 토큰. 다른 원본 컬럼 텍스트에 실제로 나타나야 살린다."""
    blob = norm(" ".join(row.get(c) or "" for c in RAW))
    return [t for t in tokens(row.get("직무")) if t in blob]


def learn(rows, m, min_n=2, min_purity=0.75):
    """정답 공고에서 토큰 사전을 만든다. (확정사전, 상위접두사전)

    [계층 학습]  처음에는 6자리가 순도 75% 를 넘는 토큰만 채택하고 나머지는 버렸다.
    그런데 버려진 토큰 상당수가 **상위 레벨에서는 순도가 충분**하다.
        "요양"   6자리로는 550101/550102/550100 로 갈리지만 앞 4자리 5501 은 100%
        "조리"   세세분류는 흩어지지만 대분류 8(설치·정비·생산)은 90%
    깊은 곳에서 실패하면 얕은 곳을 본다. 얕은 코드라도 미분류보다 낫고,
    표결(정확도 72%)보다는 정답에서 배운 쪽이 낫다.

    누출 없는 토큰만 쓴다 — `직종` 이 아닌 원본 컬럼에도 나타나야 살린다.
    """
    pair = collections.Counter()
    for r in rows:
        c = m.exact.get(norm(r["직종"])) or m.exact.get(core_of(r["직종"]))
        if not c:
            continue
        for t in leakfree_tokens(r):
            if t in m.exact or t in m.alias:
                continue
            pair[(t, c)] += 1
    per = collections.defaultdict(collections.Counter)
    for (t, c), n in pair.items():
        per[t][c] += n
    exact, prefix = {}, {}
    for t, dist in per.items():
        tot = sum(dist.values())
        if tot < min_n:
            continue
        for L in (6, 4, 3, 2, 1):               # 깊은 곳부터
            agg = collections.Counter()
            for c, n in dist.items():
                agg[c[:L]] += n
            code, n = agg.most_common(1)[0]
            if n / tot < min_purity:
                continue
            if L == 6:
                exact[t] = code
            else:
                prefix[t] = code
            break
    return exact, prefix


def cmd_eval():
    rows = load()
    m = Master()
    gold = []
    for r in rows:
        c = m.exact.get(norm(r["직종"] or "")) or m.exact.get(core_of(r["직종"] or ""))
        if c:
            gold.append((r, c))
    lex = keco_lexicon.load_lexicon()
    print(f"정답 세트 {len(gold):,}건 · 직무사전 {len(lex):,}행\n")

    random.seed(20260909)
    idx = list(range(len(gold)))
    random.shuffle(idx)
    folds = [idx[i::5] for i in range(5)]

    lvl = collections.Counter()      # 깊이별 판정
    conf = collections.Counter()
    hit = collections.Counter()
    detail = []
    for f in range(5):
        te = set(folds[f])
        tr = [gold[i][0] for i in idx if i not in te]
        lx, px = learn(tr, m)
        clf = Classifier(m, lx, px, lex)
        for i in folds[f]:
            r, truth = gold[i]
            code, why, grade, tok, cand, est, e13, ebasis = clf.assign(
                leakfree_tokens(r), text=scan_text(r),
                k13=lambda c: keco13.of(c)[0])
            p13 = keco13.of(code)[0] if code else ""
            if not p13:
                p13 = e13 or (keco13.of(est)[0] if est else "")
            t13 = keco13.of(truth)[0]
            if p13:
                hit["13분류_판정"] += 1
                hit["13분류_정답"] += (p13 == t13)
            conf[grade] += 1
            if not code:
                lvl["미분류"] += 1
                detail.append((r["통합키"], truth, m.name[truth], "", "미분류", "", "",
                               keco13.of(truth)[0], p13, est, ebasis))
                continue
            lvl[why] += 1
            hit["대분류_판정"] += 1
            ok1 = code[:1] == truth[:1]
            hit["대분류_정답"] += ok1
            for n, key in ((2, "중분류"), (3, "소분류"), (4, "세분류"), (6, "세세분류")):
                if len(code) >= n:
                    hit[key + "_판정"] += 1
                    hit[key + "_정답"] += (code[:n] == truth[:n])
            detail.append((r["통합키"], truth, m.name[truth], code, why, grade, tok,
                           t13, p13, est, ebasis))

    n = len(gold)
    print("── 경로별 배정 (전체포괄·상호배타 확인) ──")
    s = 0
    for k in ["별칭일치", "학습사전", "본문명칭", "상위합의", "미분류"]:
        print(f"  {k:<8} {lvl[k]:>6,}  {100*lvl[k]/n:5.1f}%")
        s += lvl[k]
    print(f"  {'합계':<8} {s:>6,}  (정답세트 {n:,})  →  {'일치' if s==n else '불일치!'}")

    print("\n── 확실도 ──")
    for k in ["강", "중", "약", "미분류"]:
        print(f"  {k:<4} {conf[k]:>6,}  {100*conf[k]/n:5.1f}%")

    if hit["13분류_판정"]:
        print(f"\n── 팀 13대분류 ──\n  {hit['13분류_정답']:,}/{hit['13분류_판정']:,}  "
              f"{100*hit['13분류_정답']/hit['13분류_판정']:.1f}%   "
              f"(정답세트 대비 {100*hit['13분류_정답']/n:.1f}%)")
    print("\n── 계층별 정확도 (분류된 건 중) ──")
    for key in ["대분류", "중분류", "소분류", "세분류", "세세분류"]:
        d, h = hit[key + "_판정"], hit[key + "_정답"]
        if d:
            print(f"  {key:<5} {h:>6,}/{d:>6,}  {100*h/d:5.1f}%"
                  f"   (정답세트 대비 {100*h/n:5.1f}%)")

    with EVALOUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["통합키", "정답코드", "정답명", "예측코드", "근거", "확실도",
                    "매칭토큰", "정답13분류", "예측13분류", "추정코드", "추정근거"])
        w.writerows(detail)
    print(f"\n건별 결과 → {EVALOUT.relative_to(BASE)}")


def unclassified_reason(row, m, ebasis, est, e13):
    """행마다 왜 미분류인지 한 줄로 남긴다. 집계용이 아니라 사람이 읽는 값이다."""
    raw = (row.get("직무") or "").strip()
    tk = tokens(row.get("직무"))
    if not raw:
        return "직무없음 — 사이트가 직무 정보를 주지 않았고 제목·본문에서도 직무 어휘가 안 잡혔다"
    if not tk:
        return (f"무정보토큰 — 직무 칸이 «{raw[:40]}» 뿐이다. "
                "직원·사원·현장처럼 무슨 일인지 알려주지 않는 말이라 코드를 붙이지 않았다")
    if ebasis and not est and not e13:
        # 사전이 "이 토큰으로는 추정하지 않는다" 고 명시한 경우만이다
        return f"사전제외 — {ebasis}"
    if est or e13:
        return f"확정불가·추정만 — {ebasis}"
    return (f"분류표없음 — 토큰 «{', '.join(tk[:4])}» 이 공식 명칭 1,130개와 "
            "글자가 겹치지 않고 직무사전에도 없다")


def cmd_build():
    rows = load()
    m = Master()
    gold = [r for r in rows
            if m.exact.get(norm(r["직종"] or "")) or m.exact.get(core_of(r["직종"] or ""))]
    lex, pfx = learn(gold, m)
    lx = keco_lexicon.load_lexicon()
    clf = Classifier(m, lex, pfx, lx)
    print(f"학습사전 {len(lex):,}개(세세분류) + {len(pfx):,}개(상위접두) "
          f"— 정답 {len(gold):,}건에서")
    print(f"직무사전 {len(lx):,}행 (data/keco/직무사전.csv)")

    add = ["직종코드", "직종명", "직종코드깊이", "직종코드부분",
           "직종대분류코드", "직종대분류명", "직종중분류코드", "직종소분류코드",
           "직종세분류코드", "직종13대분류코드", "직종13대분류명",
           "직종114중분류코드", "직종114중분류명", "직종13대분류중복",
           "직종코드근거", "직종코드확실도", "직종매칭토큰", "직종후보코드",
           "직종분류코드", "직종분류명",
           "직종추정코드", "직종추정명", "직종추정근거", "직종미분류사유"]
    base = list(rows[0].keys())
    cols = base + [c for c in add if c not in base]

    # 수동분류 — 사람이 분류표를 보고 붙인 값. 미분류로 남는 공고에만 적용된다.
    # build 를 다시 돌려도 작업이 살아 있어야 하므로 여기서 함께 반영한다.
    mtok, mjob, mbad = keco_manual.load_manual(m)
    if mbad:
        print(f"!! 수동분류에 분류표에 없는 코드 {len(mbad)}개 — 무시하고 진행합니다")
        for w, c in mbad[:5]:
            print(f"     {w}: {c}")
    if mtok or mjob:
        print(f"수동분류 사전 — 토큰 {len(mtok):,}개 · 공고 {len(mjob):,}개")

    why_c, grade_c, lvl_c = collections.Counter(), collections.Counter(), collections.Counter()
    out = []
    for r in rows:
        code, why, grade, tok, cand, est, e13, ebasis = clf.assign(
            tokens(r.get("직무")), r.get("직종"), text=scan_text(r),
            k13=lambda c: keco13.of(c)[0])
        if not code:                              # 미분류일 때만 수동분류를 얹는다
            if r["통합키"] in mjob:               # 공고 시트가 토큰 시트보다 우선
                code, why, tok, cand, est, e13, ebasis = (mjob[r["통합키"]],
                    "수동분류(공고)", "수동", [], "", "", "")
            else:
                for t in tokens(r.get("직무")):
                    if t in mtok:
                        code, why, tok, cand, est, e13, ebasis = (mtok[t],
                            "수동분류(토큰)", "수동", [], "", "", "")
                        break
            if code:
                grade = "강" if len(code) == 6 else "중"
        rec = dict(r)
        if code:
            rec.update(m.levels(code))
        else:
            rec.update({k: "" for k in add[:14]})
            rec["직종코드깊이"] = 0
        rec["직종코드근거"] = why
        rec["직종코드확실도"] = grade
        rec["직종매칭토큰"] = tok
        rec["직종후보코드"] = "|".join(cand)
        # 약 등급 참고용. 홀드아웃 실측 세세분류 7% · 중분류 42% — 집계에 쓰면 안 된다.
        rec["직종추정코드"] = est
        rec["직종추정명"] = m.name.get(est, "")
        rec["직종추정근거"] = ebasis
        # 팀이 쓰는 13대분류.
        #   ① 확정 코드가 있으면 거기서 파생
        #   ② 없으면 사전이 준 13분류
        #   ③ 없으면 추정 6자리에서 파생
        #   ④ 없으면 후보코드들의 13분류가 한 곳으로 모일 때만 채운다
        #      (KECO 1자리는 1·6·8 이 13분류로 갈려서 그것만으론 못 정한다)
        # 순서 주의 — `약` 등급은 code 가 KECO 1자리라서 of() 가 빈값을 줄 수 있다.
        #   1·6·8 은 13분류로 갈린다. code 가 있다고 먼저 채택하면 거기서 멈춘다.
        c13 = keco13.of(code)[0] if code else ""
        if not c13 and e13:
            c13 = e13                          # 사전이 준 13분류 또는 후보 표결 결과
        if not c13 and est:
            c13 = keco13.of(est)[0]
        if not c13:
            ks = {keco13.of(x)[0] for x in cand if x}
            ks.discard("")
            c13 = ks.pop() if len(ks) == 1 else ""
        n13 = keco13.NAMES.get(c13, "")
        rec["직종분류코드"], rec["직종분류명"] = c13, n13
        rec["직종미분류사유"] = (unclassified_reason(r, m, ebasis, est, e13)
                              if not code else "")
        out.append(rec)
        why_c[why or "미분류"] += 1
        grade_c[grade] += 1
        lvl_c[rec["직종코드깊이"]] += 1

    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(out)

    n = len(out)
    print(f"\n{OUT.relative_to(BASE)}  {n:,}건 · {len(cols)}컬럼")
    print("\n── 근거 ──")
    tot = 0
    for k in ["고용24직접", "별칭일치", "학습사전", "본문명칭", "상위합의",
              "수동분류(공고)", "수동분류(토큰)", "미분류"]:
        print(f"  {k:<8} {why_c[k]:>6,}  {100*why_c[k]/n:5.1f}%"); tot += why_c[k]
    print(f"  {'합계':<8} {tot:>6,}  → {'전체포괄 OK' if tot == n else '누락!'}")
    print("\n── 확실도 ──")
    for k in ["강", "중", "약", "미분류"]:
        print(f"  {k:<4} {grade_c[k]:>6,}  {100*grade_c[k]/n:5.1f}%")
    print("\n── 부여 깊이 ──")
    for k in sorted(lvl_c, reverse=True):
        nm = {6: "세세분류(6자리)", 4: "세분류(4)", 3: "소분류(3)", 2: "중분류(2)",
              1: "대분류(1)", 0: "미분류"}.get(k, str(k))
        print(f"  {nm:<14} {lvl_c[k]:>6,}  {100*lvl_c[k]/n:5.1f}%")

    # 집계표 — 정본은 KECO 자릿수 계층
    ag = collections.Counter()
    head = collections.Counter()
    for r in out:
        if r["직종코드"]:
            ag[(r["직종코드"], r["직종명"], r["직종대분류코드"], r["직종대분류명"])] += 1
        if r["직종대분류코드"]:
            head[(r["직종대분류코드"], r["직종대분류명"])] += 1
    with AGG.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["직종코드", "직종명", "대분류코드", "대분류명", "부산공고수"])
        for k, v in sorted(ag.items(), key=lambda x: (-x[1], x[0][0])):
            w.writerow([*k, v])
    MAJ = BASE / "부산" / "부산_직종대분류_집계.csv"
    with MAJ.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["대분류코드", "대분류명", "부산공고수", "비중"])
        tt = sum(head.values())
        for k, v in sorted(head.items()):
            w.writerow([k[0], k[1], v, f"{100*v/tt:.1f}%"])
        w.writerow(["", "미분류", len(out) - tt, f"{100*(len(out)-tt)/len(out):.1f}%"])
    print(f"\n{AGG.relative_to(BASE)}  세세분류 {len(ag):,}종")
    print(f"{MAJ.relative_to(BASE)}  대분류 10종")
    print("\n── 대분류 분포 (미분류 제외) ──")
    tt = sum(head.values())
    for k, v in sorted(head.items()):
        print(f"  {k[0]} {k[1]:<32} {v:>6,}  {100*v/tt:5.1f}%")




def cmd_table():
    """팀 조인용 계층표. 라벨 체계는 문서마다 다르니 **6자리 코드로 조인**한다."""
    m = Master()
    out = BASE / "data" / "keco" / "직종코드_계층.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["직종코드", "직종명",
                    "대분류코드", "대분류명", "중분류코드", "소분류코드", "세분류코드",
                    "work24_13대분류코드", "work24_13대분류명",
                    "work24_114중분류코드", "work24_114중분류명", "부모중복"])
        for c in sorted(m.name):
            L = m.levels(c)
            w.writerow([c, L["직종명"], L["직종대분류코드"], L["직종대분류명"],
                        L["직종중분류코드"], L["직종소분류코드"], L["직종세분류코드"],
                        L["직종13대분류코드"], L["직종13대분류명"],
                        L["직종114중분류코드"], L["직종114중분류명"],
                        L["직종13대분류중복"]])
    print(f"{out.relative_to(BASE)}  {len(m.name):,}코드")


if __name__ == "__main__":
    {"eval": cmd_eval, "build": cmd_build, "table": cmd_table}[sys.argv[1] if len(sys.argv) > 1 else "eval"]()
