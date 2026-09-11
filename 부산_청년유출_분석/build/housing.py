# -*- coding: utf-8 -*-
"""주거비 실측 — 「덜 벌어도 주거비가 싸면 상쇄된다」를 검증한다 (GOMS 2018·2019)

주거비 문항 r024(전년도 월평균 주거비 지출액)는 2018·2019 코호트에만 있다.

세 겹으로 걸러야 비교가 성립한다.
  ① 거주 형태  부모집 거주자는 가구 전체 지출을 적는 경우가 섞여 값이 부풀려진다
               → 자취·분가만
  ② 점유 형태  전세·자가는 월 지출이 관리비·이자뿐이라 월세와 성격이 다르다
               게다가 수도권이 전세 비중이 높아(42.4% vs 30.9%) 섞으면 수도권이 과소평가된다
               → 보증금 있는 월세만
  ③ 이상치     월 732만원 같은 오기가 있다 → 월세 100만원 초과·소득 1,000만원 초과 제외

출력 out/주거비_행선지.csv · out/주거비_거주형태구성.csv · out/주거비_점유형태.csv
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd

CAP  = {1, 5, 8}                                   # 서울·인천·경기
VARS = ["wt", "area", "d020", "a014", "a122", "r024", "p046", "p037"]
CAP_RENT, CAP_INC = 100, 1000                      # 이상치 상한 (만원)

fr = []
for yr, pre in {"2018": "g181", "2019": "g191"}.items():
    d = pd.read_stata(f"data/goms/pool/{yr}.DTA",
                      columns=[pre + v for v in VARS], convert_categoricals=False)
    d.columns = [c.replace(pre, "", 1) for c in d.columns]
    fr.append(d)
g = pd.concat(fr, ignore_index=True)

ok = lambda s: s.between(1, 17)
b = g[g.area == 2].copy()
b["지역"] = b.d020.where(ok(b.d020), b.a014.where(ok(b.a014)))
b = b[ok(b["지역"])].copy()
for c in ("r024", "a122"):
    b[c] = pd.to_numeric(b[c], errors="coerce")
b = b[(b.r024 > 0) & (b.a122 > 0)]
b["행선"] = b.지역.map(lambda x: "부산 잔류" if x == 2
                      else ("수도권 이탈" if x in CAP else "그 외 지역"))

wm = lambda s, c: (s[c] * s.wt).sum() / s.wt.sum()

def block(df, 층, note=""):
    out = []
    for lab in ["부산 잔류", "수도권 이탈", "그 외 지역"]:
        s = df[df.행선 == lab]
        if len(s) < 30:                            # 품질 기준: 30 미만은 내지 않는다
            continue
        inc, hou = wm(s, "a122"), wm(s, "r024")
        out.append({"층": 층, "행선": lab, "n": len(s),
                    "월소득": round(inc, 1), "월주거비": round(hou, 1),
                    "주거비비중%": round(hou / inc * 100, 1),
                    "주거비뺀소득": round(inc - hou, 1),
                    "월소득_중앙": s.a122.median(), "월주거비_중앙": s.r024.median(),
                    "비고": note})
    return out

자취 = b[b.p046 == 3]
월세 = 자취[자취.p037 == 3]
월세_정 = 월세[(월세.r024 <= CAP_RENT) & (월세.a122 <= CAP_INC)]

rows  = block(월세_정, "★ 보증금 월세 · 이상치 제외", "주 수치")
rows += block(월세,    "보증금 월세 (이상치 포함)", "부산 평균이 오기 몇 건에 부풀려진다")
rows += block(자취,    "자취·분가 전체", "전세·자가가 섞여 수도권이 과소평가된다 — 쓰지 말 것")
rows += block(b,       "전체 (구성 효과 포함)",     "부모집 거주자가 섞인다 — 쓰지 말 것")
t = pd.DataFrame(rows)

for 층 in t.층.unique():
    s = t[t.층 == 층].set_index("행선")
    if "부산 잔류" not in s.index: continue
    base = s.loc["부산 잔류"]
    for lab in s.index:
        if lab == "부산 잔류": continue
        n = s.loc[lab, "월소득"] - base.월소득
        h = s.loc[lab, "월주거비"] - base.월주거비
        nm = s.loc[lab, "월소득_중앙"] - base.월소득_중앙
        hm = s.loc[lab, "월주거비_중앙"] - base.월주거비_중앙
        sel = (t.층 == 층) & (t.행선 == lab)
        t.loc[sel, "명목격차"]   = round(n, 1)
        t.loc[sel, "주거비격차"] = round(h, 1)
        t.loc[sel, "실질격차"]   = round(n - h, 1)
        t.loc[sel, "격차유지%"]  = round((n - h) / n * 100, 0)
        t.loc[sel, "실질격차_중앙"] = round(nm - hm, 1)
        t.loc[sel, "격차유지%_중앙"] = round((nm - hm) / nm * 100, 0) if nm else None

FORM = {1: "부모집", 2: "하숙", 3: "자취·분가", 4: "기숙사·사택", 5: "친인척집", 6: "기타"}
OCC  = {1: "자가", 2: "전세", 3: "보증금 월세", 4: "보증금 없는 월세", 5: "무상·기타"}
comp = b.assign(형태=b.p046.map(FORM)).pivot_table(index="행선", columns="형태", values="wt", aggfunc="sum")
comp = (comp.div(comp.sum(axis=1), axis=0) * 100).round(1)
occ  = 자취.assign(점유=자취.p037.map(OCC)).pivot_table(index="행선", columns="점유", values="wt", aggfunc="sum")
occ  = (occ.div(occ.sum(axis=1), axis=0) * 100).round(1)

t.to_csv("out/주거비_행선지.csv", index=False, encoding="utf-8-sig")
comp.to_csv("out/주거비_거주형태구성.csv", encoding="utf-8-sig")
occ.to_csv("out/주거비_점유형태.csv", encoding="utf-8-sig")

C = ["층","행선","n","월소득","월주거비","주거비비중%","명목격차","주거비격차","실질격차","격차유지%","격차유지%_중앙"]
print(t[C].to_string(index=False)); print()
print("■ 거주 형태 구성(%)"); print(comp.to_string())
print("\n■ 자취·분가 안에서 점유 형태(%)"); print(occ.to_string())
