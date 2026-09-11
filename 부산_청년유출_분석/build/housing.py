# -*- coding: utf-8 -*-
"""부산 4년제 졸업자의 행선지별 월소득·주거비 실측 (GOMS 2018·2019)
주거비 문항(r024, 전년도 월평균 주거비 지출액)은 2018·2019 코호트에만 있다.
거주형태 구성이 행선지마다 달라(부산 잔류는 부모집 22.3% vs 수도권 6.2%)
집계 평균은 구성 효과에 오염된다. 따라서 독립 거주(자취·분가)로 층화해 비교한다.
출력: out/주거비_행선지.csv
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd

CAP = {1, 5, 8}            # 서울·인천·경기
VARS = ["wt", "area", "d020", "a014", "a122", "r024", "p046", "p037"]

fr = []
for yr, pre in {"2018": "g181", "2019": "g191"}.items():
    d = pd.read_stata(f"data/goms/pool/{yr}.DTA",
                      columns=[pre + v for v in VARS], convert_categoricals=False)
    d.columns = [c.replace(pre, "", 1) for c in d.columns]
    d["코호트"] = yr
    fr.append(d)
g = pd.concat(fr, ignore_index=True)

ok = lambda s: s.between(1, 17)
b = g[g.area == 2].copy()                       # 부산 소재 대학 졸업자
b["지역"] = b.d020.where(ok(b.d020), b.a014.where(ok(b.a014)))
b = b[ok(b["지역"]) & (b.a122 > 0) & (b.r024 > 0)].copy()
b["행선"] = b.지역.map(lambda x: "부산 잔류" if x == 2
                      else ("수도권 이탈" if x in CAP else "그 외 지역"))

wm = lambda s, c: (s[c] * s.wt).sum() / s.wt.sum()

def block(df, 층):
    out = []
    for lab in ["부산 잔류", "수도권 이탈", "그 외 지역"]:
        s = df[df.행선 == lab]
        if len(s) < 30:
            continue
        inc, hou = wm(s, "a122"), wm(s, "r024")
        out.append({"층": 층, "행선": lab, "n": len(s),
                    "월소득": round(inc, 1), "월주거비": round(hou, 1),
                    "주거비비중%": round(hou / inc * 100, 1),
                    "주거비뺀소득": round(inc - hou, 1)})
    return out

rows = []
rows += block(b, "전체(구성 효과 포함)")
rows += block(b[b.p046 == 3], "독립 거주(자취·분가)")
rows += block(b[(b.p046 == 3) & (b.p037 == 3)], "독립 거주 · 보증금 월세")
t = pd.DataFrame(rows)

for 층 in t.층.unique():
    s = t[t.층 == 층].set_index("행선")
    base = s.loc["부산 잔류"]
    for lab in s.index:
        if lab == "부산 잔류":
            continue
        n = s.loc[lab, "월소득"] - base.월소득
        h = s.loc[lab, "월주거비"] - base.월주거비
        t.loc[(t.층 == 층) & (t.행선 == lab), "명목격차"] = round(n, 1)
        t.loc[(t.층 == 층) & (t.행선 == lab), "주거비격차"] = round(h, 1)
        t.loc[(t.층 == 층) & (t.행선 == lab), "실질격차"] = round(n - h, 1)
        t.loc[(t.층 == 층) & (t.행선 == lab), "격차유지%"] = round((n - h) / n * 100, 0)

# 거주형태 구성 — 집계 평균이 왜 뒤집혔는지 보이는 표
FORM = {1: "부모집", 2: "하숙", 3: "자취·분가", 4: "기숙사·사택", 5: "친인척집", 6: "기타"}
comp = (b.assign(형태=b.p046.map(FORM))
          .pivot_table(index="행선", columns="형태", values="wt", aggfunc="sum"))
comp = (comp.div(comp.sum(axis=1), axis=0) * 100).round(1)

t.to_csv("out/주거비_행선지.csv", index=False, encoding="utf-8-sig")
comp.to_csv("out/주거비_거주형태구성.csv", encoding="utf-8-sig")
print(t.to_string(index=False)); print(); print(comp.to_string())
