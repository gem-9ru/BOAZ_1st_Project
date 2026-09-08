"""부산 공고에 KECO 직종코드를 부여하고 정확도를 실측한다.

  python3 src/pipeline/keco_run.py eval    정답 2,560건 5-fold 교차검증
  python3 src/pipeline/keco_run.py build   최종 산출물 생성
"""
import csv, sys, random, collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.keco_v2 import Master, Classifier, tokens, norm, core_of, STOP  # noqa
from pipeline import keco_manual                                            # noqa

csv.field_size_limit(10 ** 9)
BASE = Path(__file__).resolve().parents[2]
SRC = BASE / "부산" / "부산_공고_통합.csv"
OUT = BASE / "부산" / "부산_공고_직종분류.csv"
AGG = BASE / "부산" / "부산_직종별_집계.csv"
EVALOUT = BASE / "부산" / "직종분류_정확도.csv"

# `직종` 이 아닌 원본 컬럼. 정확도 측정에서 정답 누출을 걸러내는 기준이 된다.
RAW = ["공고제목", "직무상세", "직무키워드", "담당업무", "자격요건", "우대사항",
       "원본_직무", "직급직책"]


def load():
    return list(csv.DictReader(SRC.open(encoding="utf-8-sig")))


def leakfree_tokens(row):
    """`직종` 유래 토큰을 뺀 토큰. 다른 원본 컬럼 텍스트에 실제로 나타나야 살린다."""
    blob = norm(" ".join(row.get(c) or "" for c in RAW))
    return [t for t in tokens(row.get("직무")) if t in blob]


def learn(rows, m, min_n=2, min_purity=0.75):
    """정답 공고에서 토큰→코드 사전을 만든다. 누출 없는 토큰만 쓴다."""
    pair = collections.Counter()
    for r in rows:
        c = m.exact.get(norm(r["직종"])) or m.exact.get(core_of(r["직종"]))
        if not c:
            continue
        for t in leakfree_tokens(r):
            if t in m.exact or t in m.alias:
                continue
            pair[(t, c)] += 1
    tot = collections.Counter()
    for (t, _), n in pair.items():
        tot[t] += n
    out = {}
    for (t, c), n in pair.items():
        if n >= min_n and n / tot[t] >= min_purity:
            best = out.get(t)
            if best is None or n > pair[(t, best)]:
                out[t] = c
    return out


def cmd_eval():
    rows = load()
    m = Master()
    gold = []
    for r in rows:
        c = m.exact.get(norm(r["직종"] or "")) or m.exact.get(core_of(r["직종"] or ""))
        if c:
            gold.append((r, c))
    print(f"정답 세트 {len(gold):,}건\n")

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
        clf = Classifier(m, learn(tr, m))
        for i in folds[f]:
            r, truth = gold[i]
            code, why, grade, tok, cand = clf.assign(leakfree_tokens(r))
            conf[grade] += 1
            if not code:
                lvl["미분류"] += 1
                detail.append((r["통합키"], truth, m.name[truth], "", "미분류", "", ""))
                continue
            lvl[why] += 1
            hit["대분류_판정"] += 1
            ok1 = code[:1] == truth[:1]
            hit["대분류_정답"] += ok1
            for n, key in ((2, "중분류"), (3, "소분류"), (4, "세분류"), (6, "세세분류")):
                if len(code) >= n:
                    hit[key + "_판정"] += 1
                    hit[key + "_정답"] += (code[:n] == truth[:n])
            detail.append((r["통합키"], truth, m.name[truth], code,
                           why, grade, tok))

    n = len(gold)
    print("── 경로별 배정 (전체포괄·상호배타 확인) ──")
    s = 0
    for k in ["별칭일치", "학습사전", "상위합의", "미분류"]:
        print(f"  {k:<8} {lvl[k]:>6,}  {100*lvl[k]/n:5.1f}%")
        s += lvl[k]
    print(f"  {'합계':<8} {s:>6,}  (정답세트 {n:,})  →  {'일치' if s==n else '불일치!'}")

    print("\n── 확실도 ──")
    for k in ["강", "중", "약", "미분류"]:
        print(f"  {k:<4} {conf[k]:>6,}  {100*conf[k]/n:5.1f}%")

    print("\n── 계층별 정확도 (분류된 건 중) ──")
    for key in ["대분류", "중분류", "소분류", "세분류", "세세분류"]:
        d, h = hit[key + "_판정"], hit[key + "_정답"]
        if d:
            print(f"  {key:<5} {h:>6,}/{d:>6,}  {100*h/d:5.1f}%"
                  f"   (정답세트 대비 {100*h/n:5.1f}%)")

    with EVALOUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["통합키", "정답코드", "정답명", "예측코드", "근거", "확실도", "매칭토큰"])
        w.writerows(detail)
    print(f"\n건별 결과 → {EVALOUT.relative_to(BASE)}")


def cmd_build():
    rows = load()
    m = Master()
    gold = [r for r in rows
            if m.exact.get(norm(r["직종"] or "")) or m.exact.get(core_of(r["직종"] or ""))]
    lex = learn(gold, m)
    clf = Classifier(m, lex)
    print(f"학습사전 {len(lex):,}개 (정답 {len(gold):,}건에서)")

    add = ["직종코드", "직종명", "직종코드깊이", "직종코드부분",
           "직종대분류코드", "직종대분류명", "직종중분류코드", "직종소분류코드",
           "직종세분류코드", "직종13대분류코드", "직종13대분류명",
           "직종114중분류코드", "직종114중분류명", "직종13대분류중복",
           "직종코드근거", "직종코드확실도", "직종매칭토큰", "직종후보코드"]
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
        code, why, grade, tok, cand = clf.assign(tokens(r.get("직무")), r.get("직종"))
        if not code:                              # 미분류일 때만 수동분류를 얹는다
            if r["통합키"] in mjob:               # 공고 시트가 토큰 시트보다 우선
                code, why, tok, cand = mjob[r["통합키"]], "수동분류(공고)", "수동", []
            else:
                for t in tokens(r.get("직무")):
                    if t in mtok:
                        code, why, tok, cand = mtok[t], "수동분류(토큰)", "수동", []
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
    for k in ["고용24직접", "별칭일치", "학습사전", "상위합의",
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
