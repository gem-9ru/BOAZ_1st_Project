"""크로스워크 쟁점 3계열 민감도 — 극단 배분 전수 조합.

쟁점 계열(언어ㆍ문학·인문과학·생활과학, 졸업자 4,561명 = 12.3%)을
가능한 직종대분류에 100% 몰아넣는 모든 조합(3×2×3=18)을 돌려
결론이 배분 선택에 흔들리는지 상한·하한으로 본다.
배출비중은 가중치의 선형함수라 최대·최소는 코너에서 나온다.
"""
import itertools
import pandas as pd

NAME = {0:"경영·사무·금융·보험", 1:"연구·공학기술", 2:"교육·법률·사회복지·경찰·소방",
        3:"보건·의료", 4:"예술·디자인·방송·스포츠", 5:"미용·여행·숙박·음식·경비·돌봄·청소",
        6:"영업·판매·운전·운송", 7:"건설·채굴", 8:"설치·정비·생산", 9:"농림어업"}
CONTESTED = {"언어ㆍ문학": [0, 2, 4], "인문과학": [0, 2], "생활과학": [0, 3, 5]}
HIGH = [1, 2, 3]   # 대졸요구율 40% 이상 직종 (연구·공학 45.2 / 교육·법률·복지 55.7 / 보건·의료 42.3)
LOW  = [5, 8, 9, 7]  # 대졸요구율 15% 미만

g = pd.read_excel("data/취업통계/부산소재_고등교육기관_졸업자_취업통계_2024.xlsx", sheet_name="부산_전체")
g = g[g["학제"].isin(["대학", "교육대학", "전문대학"])]
g["졸업자_계"] = pd.to_numeric(g["졸업자_계"], errors="coerce")
mid = g.groupby("중계열")["졸업자_계"].sum()

cw0 = pd.read_csv("build/crosswalk.csv")
w = pd.read_csv("out/워크넷_부산_월별_직종중분류.csv")
dem = w[(w.지표 == "신규구인인원") & (w.표 == "4-2")].groupby("대분류코드")["부산"].sum()
sup = w[(w.지표 == "신규구직건수") & (w.표 == "5-2")].groupby("대분류코드")["부산"].sum()
dem_pct = dem / dem.sum() * 100
ratio = (dem / sup).reindex(range(10))

def grad_share(cw):
    m = cw.merge(mid.rename("졸업자").reset_index(), on="중계열")
    s = (m.졸업자 * m.가중치).groupby(m.직종대분류코드).sum()
    return (s / s.sum() * 100).reindex(range(10)).fillna(0)

def scenario(assign):
    cw = cw0[~cw0.중계열.isin(CONTESTED)][["중계열", "직종대분류코드", "가중치"]]
    add = pd.DataFrame([{"중계열": k, "직종대분류코드": v, "가중치": 1.0}
                        for k, v in assign.items()])
    return grad_share(pd.concat([cw, add], ignore_index=True))

rows = []
base = grad_share(cw0)
rows.append({"시나리오": "기준(가중배분)", **{NAME[i]: base[i] for i in range(10)}})
for combo in itertools.product(*CONTESTED.values()):
    assign = dict(zip(CONTESTED, combo))
    s = scenario(assign)
    tag = " / ".join(f"{k[:4]}→{NAME[v][:6]}" for k, v in assign.items())
    rows.append({"시나리오": tag, **{NAME[i]: s[i] for i in range(10)}})

r = pd.DataFrame(rows)
r["대졸직종_배출%"] = r[[NAME[i] for i in HIGH]].sum(axis=1)
r["비대졸직종_배출%"] = r[[NAME[i] for i in LOW]].sum(axis=1)
# 순위상관 (배출% ~ 구인배수)
def rho(row):
    s = pd.Series({i: row[NAME[i]] for i in range(10)})
    return s.rank().corr(ratio.rank())
r["ρ(배출~구인배수)"] = r.apply(rho, axis=1)
r.round(2).to_csv("out/민감도_크로스워크.csv", index=False, encoding="utf-8-sig")

HI_DEM = dem_pct[HIGH].sum(); LO_DEM = dem_pct[LOW].sum()
print(f"쟁점 계열 졸업자 {mid[list(CONTESTED)].sum():,.0f}명 "
      f"({mid[list(CONTESTED)].sum()/mid.sum()*100:.1f}%) · 시나리오 {len(r)}개\n")
print("■ 핵심지표 범위")
for c, ref in [("대졸직종_배출%", HI_DEM), ("비대졸직종_배출%", LO_DEM)]:
    print(f"  {c:<16} {r[c].min():5.1f} ~ {r[c].max():5.1f}   (기준 {r[c][0]:.1f}) "
          f"↔ 부산 수요 {ref:.1f}%")
print(f"  ρ(배출~구인배수)   {r['ρ(배출~구인배수)'].min():5.2f} ~ {r['ρ(배출~구인배수)'].max():5.2f}"
      f"   (기준 {r['ρ(배출~구인배수)'][0]:.2f})")
print("\n■ 직종별 배출% 범위 vs 부산 수요%")
for i in range(10):
    col = r[NAME[i]]
    gap_lo, gap_hi = col.min() - dem_pct[i], col.max() - dem_pct[i]
    flip = "" if gap_lo * gap_hi > 0 else "  ← 부호 뒤집힘"
    print(f"  {NAME[i]:<22} 배출 {col.min():5.1f}~{col.max():5.1f}  수요 {dem_pct[i]:5.1f}"
          f"  격차 {gap_lo:+6.1f}~{gap_hi:+6.1f}{flip}")
