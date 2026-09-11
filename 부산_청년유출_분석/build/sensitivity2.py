"""설계 선택 2개 추가 민감도 — 학제 범위 × 수요 채널.

학제  : 전체(대학+교대+전문대) / 4년제만 / 전문대만
수요  : 공공(고용24 12개월) / 민간(크롤링 전체) / 민간 대졸명시 공고만
두 결론이 9개 조합 전부에서 유지되는지 본다.
  A. 대졸요구 40%↑ 직종의 배출비중 > 수요비중
  B. 배출비중 ~ 구인배수 순위상관 < 0
"""
import itertools
import pandas as pd

NAME = {0:"경영·사무·금융·보험", 1:"연구·공학기술", 2:"교육·법률·사회복지·경찰·소방",
        3:"보건·의료", 4:"예술·디자인·방송·스포츠", 5:"미용·여행·숙박·음식·경비·돌봄·청소",
        6:"영업·판매·운전·운송", 7:"건설·채굴", 8:"설치·정비·생산", 9:"농림어업"}
HIGH, LOW = [1, 2, 3], [5, 8, 9, 7]
CRAWL = {"경영·사무·금융·보험":0, "연구·공학기술":1, "교육·법률·사회복지·경찰·소방·군인":2,
         "보건·의료":3, "예술·디자인·방송·스포츠":4, "미용·여행·숙박·음식·경비·돌봄·청소":5,
         "영업·판매·운전·운송":6, "건설·채굴":7, "설치·정비·생산":8, "농림어업":9}

g = pd.read_excel("data/취업통계/부산소재_고등교육기관_졸업자_취업통계_2024.xlsx", sheet_name="부산_전체")
g["졸업자_계"] = pd.to_numeric(g["졸업자_계"], errors="coerce")
cw = pd.read_csv("build/crosswalk.csv")

def grad(levels):
    sub = g[g["학제"].isin(levels)]
    mid = sub.groupby("중계열")["졸업자_계"].sum()
    m = cw.merge(mid.rename("졸업자").reset_index(), on="중계열")
    s = (m.졸업자 * m.가중치).groupby(m.직종대분류코드).sum()
    return (s / s.sum() * 100).reindex(range(10)).fillna(0), sub["졸업자_계"].sum()

w = pd.read_csv("out/워크넷_부산_월별_직종중분류.csv")
pub = w[(w.지표=="신규구인인원") & (w.표=="4-2")].groupby("대분류코드")["부산"].sum()
sup = w[(w.지표=="신규구직건수") & (w.표=="5-2")].groupby("대분류코드")["부산"].sum()
ratio = (pub / sup).reindex(range(10))
c = pd.read_csv("data/채용공고/부산_공고_분석용.csv")
c = c[c.직종대분류 != "미분류"]; c["코드"] = c.직종대분류.map(CRAWL)
DEMAND = {
    "공공(고용24 12개월)": (pub / pub.sum() * 100).reindex(range(10)).fillna(0),
    "민간(크롤링 전체)": c.코드.value_counts(normalize=True).mul(100).reindex(range(10)).fillna(0),
    "민간(대졸명시만)": c[c.요구학력.isin(["대학교졸","석사이상"])].코드
                        .value_counts(normalize=True).mul(100).reindex(range(10)).fillna(0),
}
LEVELS = {"전체(대학+교대+전문대)": ["대학","교육대학","전문대학"],
          "4년제만": ["대학"], "전문대만": ["전문대학"]}

rows = []
for (ln, lv), (dn, d) in itertools.product(LEVELS.items(), DEMAND.items()):
    gs, n = grad(lv)
    rows.append({
        "학제": ln, "졸업자": int(n), "수요기준": dn,
        "대졸직종_배출%": gs[HIGH].sum(), "대졸직종_수요%": d[HIGH].sum(),
        "비대졸직종_배출%": gs[LOW].sum(), "비대졸직종_수요%": d[LOW].sum(),
        "예술_배출%": gs[4], "예술_수요%": d[4],
        "ρ(배출~구인배수)": gs.rank().corr(ratio.rank()),
    })
r = pd.DataFrame(rows)
r["A_성립"] = r["대졸직종_배출%"] > r["대졸직종_수요%"]
r["B_성립"] = r["ρ(배출~구인배수)"] < 0
r["배출/수요_배율"] = r["대졸직종_배출%"] / r["대졸직종_수요%"]
r.round(2).to_csv("out/민감도_설계선택.csv", index=False, encoding="utf-8-sig")

pd.set_option("display.width", 200)
print(r[["학제","졸업자","수요기준","대졸직종_배출%","대졸직종_수요%","배출/수요_배율",
         "예술_배출%","예술_수요%","ρ(배출~구인배수)","A_성립","B_성립"]]
      .to_string(index=False, float_format=lambda v: f"{v:.2f}"))
print(f"\nA(대졸직종 배출>수요) 성립 {r.A_성립.sum()}/{len(r)}  "
      f"· 배율 최소 {r['배출/수요_배율'].min():.2f}배")
print(f"B(ρ<0) 성립 {r.B_성립.sum()}/{len(r)}  "
      f"· ρ 범위 {r['ρ(배출~구인배수)'].min():.2f} ~ {r['ρ(배출~구인배수)'].max():.2f}")

# ── 직종별: 9개 조합 전부에서 격차(배출−수요) 부호가 유지되는가
print("\n■ 직종별 격차(배출%−수요%) 부호 안정성 — 9개 조합")
cells = []
for (ln, lv), (dn, d) in itertools.product(LEVELS.items(), DEMAND.items()):
    gs, _ = grad(lv)
    cells.append((gs - d).rename(f"{ln[:4]}/{dn[:4]}"))
gapdf = pd.concat(cells, axis=1)
gapdf.index = [NAME[i] for i in gapdf.index]
gapdf["최소"] = gapdf.min(axis=1); gapdf["최대"] = gapdf.max(axis=1)
gapdf["판정"] = [("과잉 확정" if lo > 0 else "과소 확정" if hi < 0 else "불확정")
                for lo, hi in zip(gapdf["최소"], gapdf["최대"])]
gapdf.to_csv("out/민감도_직종별격차.csv", encoding="utf-8-sig")
print(gapdf[["최소", "최대", "판정"]].to_string(float_format=lambda v: f"{v:+7.1f}"))
