"""GOMS — 부산 졸업자는 '역량이 부족'한가, '남아도는'가.

정책 예산의 57.5%가 인력 양성(교육)에 간다. 그 전제는 '졸업자 역량이 모자란다'이다.
GOMS는 취업자에게 직접 물었다.
  A34 교육 수준 ↔ 일 수준   1-2 = 일이 내 수준보다 낮다(과잉학력)  4-5 = 일이 더 높다(역량부족)
  A35 기술 수준 ↔ 일 기술   같은 방향
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd

MAJOR = {1:"인문",2:"사회",3:"교육",4:"공학",5:"자연",6:"의약",7:"예체능"}
C = ["g191wt","g191area","g191majorcat","g191d020","g191a014","g191a142","g191a143","g191a144","g191a146"]
d = pd.read_stata("data/goms/GP19__2020.DTA", columns=C, convert_categoricals=False)
ok = lambda s: s.between(1, 17)
d["지역"] = d.g191d020.where(ok(d.g191d020), d.g191a014.where(ok(d.g191a014)))

def split(g, col):
    v = g[g[col].between(1, 5)]
    w = v.g191wt.sum()
    return pd.Series({
        "n": len(v),
        "과잉학력%": v[v[col] <= 2].g191wt.sum() / w * 100,
        "적정%": v[v[col] == 3].g191wt.sum() / w * 100,
        "역량부족%": v[v[col] >= 4].g191wt.sum() / w * 100})

b = d[d.g191area == 2]
groups = {
    "부산 대학 → 부산 취업": b[b.지역 == 2],
    "부산 대학 → 부산 밖 취업": b[ok(b.지역) & (b.지역 != 2)],
    "[비교] 전국 전체": d[ok(d.지역)],
    "[비교] 서울 대학 → 서울 취업": d[(d.g191area == 1) & (d.지역 == 1)],
}
for col, label in [("g191a142", "교육 수준"), ("g191a143", "기술(기능) 수준")]:
    print(f"\n■ {label} ↔ 일의 수준 (가중 %)")
    print(pd.DataFrame({k: split(v, col) for k, v in groups.items()}).T
          .to_string(float_format=lambda x: f"{x:7.1f}"))

print("\n■ 부산 잔류자 전공계열별 — 내 수준보다 낮은 일을 하고 있는가 (교육 수준 기준)")
stay = b[b.지역 == 2]
rows = []
for m, g in stay.groupby(stay.g191majorcat.map(MAJOR)):
    s = split(g, "g191a142")
    if s["n"] < 30: continue
    t = g[g.g191a144.between(1, 5)]
    s["전공일치(1~5)"] = (t.g191a144 * t.g191wt).sum() / t.g191wt.sum() if len(t) else float("nan")
    rows.append(pd.Series(s, name=m))
r = pd.DataFrame(rows).sort_values("과잉학력%", ascending=False)
print(r.to_string(float_format=lambda x: f"{x:7.1f}"))
r.round(1).to_csv("out/GOMS_과잉학력.csv", encoding="utf-8-sig")
