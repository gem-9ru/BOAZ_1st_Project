# -*- coding: utf-8 -*-
"""부산 청년 유출 EDA — 공고(수요) · 졸업자(배출) 다각도 점검.

실행:  python3 src/eda.py           전부
       python3 src/eda.py 급여      한 섹션만

출력: out/eda_*.csv  (섹션별) + 화면 요약
"""
import csv, collections, statistics, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
JOBS = BASE.parent / "크롤링" / "분석" / "부산_공고_분석용.csv"
XLSX = BASE / "data" / "부산소재_고등교육기관_졸업자_취업통계_2024.xlsx"
OUT = BASE / "out"
csv.field_size_limit(10 ** 9)

# 2026 최저임금 시급 10,320원 → 월 소정근로 209h × 12개월
MINW = 10320 * 209 * 12 // 10000        # 2,588만원
HI = {"대학교졸", "석사이상"}
NEW = {"무관", "신입"}
섹션 = {}


def 등록(name):
    def deco(f):
        섹션[name] = f
        return f
    return deco


def 공고():
    return list(csv.DictReader(JOBS.open(encoding="utf-8-sig")))


def 연봉(rows):
    return sorted(int(x["연봉환산최소"]) for x in rows if x["연봉환산최소"].isdigit())


def dump(name, rows):
    if not rows:
        return
    p = OUT / f"eda_{name}.csv"
    with p.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"   → {p.relative_to(BASE)}")


def 졸업자(학제=("대학",)):
    import pandas as pd
    df = pd.read_excel(XLSX, sheet_name="부산_전체")
    t = df[df["학제"].isin(학제)].copy()
    # KEDI 공식 취업률 분모. 진학·입대·유학생을 빼야 «부산 구직시장 진입 인원» 이 된다.
    t["대상"] = (t["졸업자_계"] - t["진학자_계"] - t["입대자"] - t["취업불가능자_계"]
               - t["외국인유학생_계"] - t["제외인정자_계"])
    return t


# ────────────────────────────────────────────────────────────── 수요(공고)
@등록("급여")
def s_급여():
    r = 공고()
    ps = 연봉(r)
    print(f"연봉 명시 {len(ps):,}/{len(r):,} ({100*len(ps)/len(r):.1f}%) · "
          f"최저임금 연환산 {MINW:,}만원")
    q = statistics.quantiles(ps, n=100)
    print("  분위:  " + " · ".join(f"{k}%={q[k-1]:,.0f}" for k in (10, 25, 50, 75, 90)))
    print(f"  최저임금 이하 {sum(1 for p in ps if p <= MINW):,}건 "
          f"({100*sum(1 for p in ps if p <= MINW)/len(ps):.1f}%)")
    print("  최빈값: " + " · ".join(f"{v:,}({n:,})" for v, n in collections.Counter(ps).most_common(5)))
    out = []
    for c in sorted({x["직종분류코드"] for x in r if x["직종분류코드"]}):
        G = [x for x in r if x["직종분류코드"] == c]
        p = 연봉(G)
        if len(p) < 30:
            continue
        low = sum(1 for v in p if v <= MINW)
        out.append({"직종분류코드": c, "직종분류명": G[0]["직종분류명"], "공고": len(G),
                    "연봉명시": len(p), "최저임금이하": low,
                    "최저임금이하율": round(100 * low / len(p), 1),
                    "연봉중앙": statistics.median(p)})
    for x in sorted(out, key=lambda z: -z["최저임금이하율"])[:5]:
        print(f"  {x['직종분류코드']} {x['직종분류명'][:26]:<28}최저임금이하 {x['최저임금이하율']:>5.1f}%")
    dump("급여_직종별", out)


@등록("진입")
def s_진입():
    """학력 티어별로 «신입이 지원할 수 있는 자리» 를 센다."""
    r = 공고()
    티어 = [("대학교졸·석사", HI),
           ("전문대졸 이상", {"전문대졸"} | HI),
           ("고졸 이상+학력무관", {"고졸", "전문대졸", "학력무관"} | HI)]
    out = []
    for lbl, eds in 티어:
        G = [x for x in r if x["요구학력"] in eds]
        n = [x for x in G if x["경력요건"] in NEW]
        p = 연봉(n)
        out.append({"학력티어": lbl, "공고": len(G), "신입가능": len(n),
                    "연봉중앙": statistics.median(p) if p else ""})
        print(f"  {lbl:<20}공고 {len(G):>7,}  신입가능 {len(n):>7,}  "
              f"연봉중앙 {statistics.median(p) if p else 0:>5,.0f}")
    dump("진입_학력티어", out)
    # 경력 요구 연차
    yr = collections.Counter(x["최소연차"] for x in r if x["경력요건"] == "경력")
    t = sum(yr.values())
    print(f"  경력 요구 {t:,}건 — 1년 {yr['1']:,}({100*yr['1']/t:.1f}%) · "
          f"3년↑ {sum(v for k, v in yr.items() if k.isdigit() and int(k) >= 3):,}")


@등록("업종")
def s_업종():
    r = 공고()
    out = []
    for i, v in collections.Counter(x["업종원문"] for x in r if x["업종원문"]).items():
        if v < 100:
            continue
        G = [x for x in r if x["업종원문"] == i]
        p = 연봉(G)
        t13 = collections.Counter(x["직종분류명"] for x in G
                                  if x["직종분류명"] != "미분류").most_common(1)
        out.append({"업종": i, "공고": v,
                    "대졸요구율": round(100 * sum(1 for x in G if x["요구학력"] in HI) / v, 1),
                    "연봉중앙": statistics.median(p) if p else "",
                    "1위직종": t13[0][0] if t13 else ""})
    for x in sorted(out, key=lambda z: -z["대졸요구율"])[:6]:
        print(f"  {x['업종'][:24]:<26}{x['공고']:>5,}건  대졸요구 {x['대졸요구율']:>5.1f}%")
    dump("업종별", out)


@등록("시군구")
def s_시군구():
    r = 공고()
    out = []
    for s, v in collections.Counter(x["시군구"] for x in r).most_common():
        G = [x for x in r if x["시군구"] == s]
        p = 연봉(G)
        dn = sum(1 for x in G if x["요구학력"] in HI and x["경력요건"] in NEW)
        t13 = collections.Counter(x["직종분류명"] for x in G
                                  if x["직종분류명"] != "미분류").most_common(1)
        out.append({"시군구": s, "공고": v, "대졸신입공고": dn,
                    "천건당_대졸신입": round(1000 * dn / v, 1),
                    "연봉중앙": statistics.median(p) if p else "",
                    "최저임금이하율": round(100 * sum(1 for q in p if q <= MINW) / len(p), 1) if p else "",
                    "1위직종": t13[0][0] if t13 else ""})
    for x in sorted(out, key=lambda z: -z["천건당_대졸신입"])[:5]:
        print(f"  {x['시군구']:<8}공고 {x['공고']:>6,}  천건당 대졸신입 {x['천건당_대졸신입']:>5.1f}  {x['1위직종'][:20]}")
    dump("시군구별", out)


@등록("함정")
def s_함정():
    """임금 해석을 망치는 것 — 지입 화물기사 매출이 «연봉» 으로 들어와 있다."""
    r = 공고()
    G = [x for x in r if x["직종분류코드"] == "08"]
    p = 연봉(G)
    hi = [x for x in G if x["연봉환산최소"].isdigit() and int(x["연봉환산최소"]) >= 6000]
    print(f"08 운전·운송직 {len(G):,}건 · 연봉중앙 {statistics.median(p):,.0f}만원")
    print(f"  6,000만원 이상 {len(hi):,}건 = 명시분의 {100*len(hi)/len(p):.0f}%")
    print(f"  그 제목에 «지입/임대/직영» 포함: "
          f"{sum(1 for x in hi if any(k in x['공고제목'] for k in ('지입', '임대', '직영', '차량지원'))):,}건")
    print("  → 사업소득(매출)이다. 유류비·차량유지비를 빼면 임금이 아니다.")
    fl = [x for x in r if x["고용형태"] == "프리랜서"]
    print(f"프리랜서 {len(fl):,}건 · 연봉중앙 {statistics.median(연봉(fl)):,.0f}만원 — 같은 함정")


@등록("회사")
def s_회사():
    r = 공고()
    co = collections.Counter(x["회사명"].strip() for x in r if x["회사명"].strip())
    tot = sum(co.values())
    print(f"회사 {len(co):,}곳 · 공고 {tot:,}건")
    for k in (10, 50, 100, 500):
        print(f"  상위 {k:>3}곳 = {100*sum(v for _, v in co.most_common(k))/tot:>4.1f}%")
    print("  → 대규모 채용 주체가 없다. 초분산 시장이다.")


# ────────────────────────────────────────────────────────────── 배출(졸업자)
@등록("학제")
def s_학제():
    df = 졸업자(("대학", "전문대학", "교육대학", "일반대학원", "기능대학", "사이버대학(대학)"))
    out = []
    for lb in df["학제"].unique():
        t = df[df["학제"] == lb]
        d, e = t["대상"].sum(), t["취업자_합계_계"].sum()
        if d < 50:
            continue
        out.append({"학제": lb, "졸업자": int(t["졸업자_계"].sum()), "취업대상": int(d),
                    "취업률": round(100 * e / d, 1),
                    "1차유지율": round(100 * t["1차 유지취업자_계"].sum() / e, 1),
                    "4차유지율": round(100 * t["4차 유지취업자_계"].sum() / e, 1),
                    "진학률": round(100 * t["진학자_계"].sum() / t["졸업자_계"].sum(), 1)})
    for x in sorted(out, key=lambda z: -z["취업률"]):
        print(f"  {x['학제']:<14}졸업 {x['졸업자']:>6,}  취업률 {x['취업률']:>5.1f}%  "
              f"4차유지 {x['4차유지율']:>5.1f}%  진학률 {x['진학률']:>4.1f}%")
    dump("학제별", out)


@등록("성별")
def s_성별():
    t = 졸업자()
    for s in ("남", "여"):
        t[f"대상_{s}"] = (t[f"졸업자_{s}"] - t[f"진학자_{s}"] - t[f"취업불가능자_{s}"]
                       - t[f"외국인유학생_{s}"] - t[f"제외인정자_{s}"])
    t["대상_남"] -= t["입대자"]          # 입대자는 성별 분리가 없다 — 전부 남
    for s in ("남", "여"):
        d, e = t[f"대상_{s}"].sum(), t[f"취업자_합계_{s}"].sum()
        print(f"  {s}  취업대상 {d:>6,}  취업률 {100*e/d:>5.1f}%  "
              f"4차유지율 {100*t[f'4차 유지취업자_{s}'].sum()/e:>5.1f}%")
    g = t.groupby("중계열").sum(numeric_only=True).reset_index()
    g = g[(g.대상_남 + g.대상_여) >= 200]
    out = []
    for _, x in g.iterrows():
        out.append({"중계열": x["중계열"],
                    "여성비중": round(100 * x["졸업자_여"] / (x["졸업자_남"] + x["졸업자_여"]), 1),
                    "취업률_남": round(100 * x["취업자_합계_남"] / x["대상_남"], 1),
                    "취업률_여": round(100 * x["취업자_합계_여"] / x["대상_여"], 1),
                    "유지율_남": round(100 * x["4차 유지취업자_남"] / x["취업자_합계_남"], 1),
                    "유지율_여": round(100 * x["4차 유지취업자_여"] / x["취업자_합계_여"], 1)})
    for x in out:
        x["취업률격차"] = round(x["취업률_남"] - x["취업률_여"], 1)
        x["유지율격차"] = round(x["유지율_남"] - x["유지율_여"], 1)
    for x in sorted(out, key=lambda z: -z["유지율격차"])[:5]:
        print(f"  {x['중계열']:<16}유지율 남 {x['유지율_남']:>5.1f}% / 여 {x['유지율_여']:>5.1f}%  "
              f"격차 {x['유지율격차']:>+5.1f}p")
    dump("성별격차", out)


@등록("유지곡선")
def s_유지곡선():
    t = 졸업자()
    g = t.groupby("중계열").sum(numeric_only=True).reset_index()
    g = g[g.대상 >= 300]
    out = []
    for _, x in g.iterrows():
        e = x["취업자_합계_계"]
        row = {"중계열": x["중계열"], "취업대상": int(x["대상"]),
               "취업률": round(100 * e / x["대상"], 1)}
        for c in (1, 2, 3, 4):
            row[f"{c}차유지율"] = round(100 * x[f"{c}차 유지취업자_계"] / e, 1)
        row["이탈폭"] = round(row["1차유지율"] - row["4차유지율"], 1)
        out.append(row)
    for x in sorted(out, key=lambda z: z["4차유지율"])[:5]:
        print(f"  {x['중계열']:<16}취업률 {x['취업률']:>5.1f}%  "
              f"1차 {x['1차유지율']:>5.1f}% → 4차 {x['4차유지율']:>5.1f}%  (−{x['이탈폭']:.1f}p)")
    dump("유지곡선", out)


@등록("학교")
def s_학교():
    t = 졸업자(("대학", "교육대학"))
    g = t.groupby(["학교명", "설립"]).sum(numeric_only=True).reset_index()
    out = []
    for _, x in g.iterrows():
        e = x["취업자_합계_계"]
        out.append({"학교명": x["학교명"], "설립": x["설립"],
                    "졸업자": int(x["졸업자_계"]), "취업대상": int(x["대상"]),
                    "취업률": round(100 * e / x["대상"], 1),
                    "4차유지율": round(100 * x["4차 유지취업자_계"] / e, 1),
                    "유학생비중": round(100 * x["외국인유학생_계"] / x["졸업자_계"], 1),
                    "진학률": round(100 * x["진학자_계"] / x["졸업자_계"], 1)})
    for x in sorted(out, key=lambda z: -z["취업률"])[:4]:
        print(f"  {x['학교명']:<14}{x['설립']}  취업률 {x['취업률']:>5.1f}%  4차유지 {x['4차유지율']:>5.1f}%")
    h = t.groupby("설립").sum(numeric_only=True)
    for s in h.index:
        x = h.loc[s]
        print(f"  [{s}] 취업률 {100*x['취업자_합계_계']/x['대상']:>5.1f}%  "
              f"4차유지 {100*x['4차 유지취업자_계']/x['취업자_합계_계']:>5.1f}%")
    dump("학교별", out)


def main():
    OUT.mkdir(exist_ok=True)
    want = sys.argv[1:] or list(섹션)
    for k in want:
        if k not in 섹션:
            print(f"[{k}] 없는 섹션. 가능: {' '.join(섹션)}"); continue
        print(f"\n{'='*72}\n{k}\n{'='*72}")
        섹션[k]()


if __name__ == "__main__":
    main()
