"""배출(졸업자) vs 수요(공공·민간) 구성비 비교 + 구인배수."""
import pandas as pd

NAME = {0:"경영·사무·금융·보험", 1:"연구·공학기술", 2:"교육·법률·사회복지·경찰·소방",
        3:"보건·의료", 4:"예술·디자인·방송·스포츠", 5:"미용·여행·숙박·음식·경비·돌봄·청소",
        6:"영업·판매·운전·운송", 7:"건설·채굴", 8:"설치·정비·생산", 9:"농림어업"}

# ── 1) 졸업자 → 직종대분류 (가중 배분)
g = pd.read_excel("data/취업통계/부산소재_고등교육기관_졸업자_취업통계_2024.xlsx", sheet_name="부산_전체")
g = g[g["학제"].isin(["대학", "교육대학", "전문대학"])]
g["졸업자_계"] = pd.to_numeric(g["졸업자_계"], errors="coerce")
mid = g.groupby("중계열")["졸업자_계"].sum()

cw = pd.read_csv("build/crosswalk.csv")
unmapped = sorted(set(mid.index) - set(cw.중계열))
drop = mid[mid.index.isin(unmapped)].sum()
m = cw.merge(mid.rename("졸업자").reset_index(), on="중계열")
m["배분"] = m.졸업자 * m.가중치
grad = m.groupby("직종대분류코드")["배분"].sum()

# ── 2) 공공채널 (고용24 12개월)
w = pd.read_csv("out/워크넷_부산_월별_직종중분류.csv")
pub_d = w[(w.지표=="신규구인인원") & (w.표=="4-2")].groupby("대분류코드")["부산"].sum()
pub_s = w[(w.지표=="신규구직건수") & (w.표=="5-2")].groupby("대분류코드")["부산"].sum()

# ── 3) 민간채널 (우리 크롤링)
c = pd.read_csv("data/채용공고/부산_공고_분석용.csv")
c = c[c.직종대분류 != "미분류"]
code = {v: k for k, v in {0:"경영·사무·금융·보험",1:"연구·공학기술",
        2:"교육·법률·사회복지·경찰·소방·군인",3:"보건·의료",4:"예술·디자인·방송·스포츠",
        5:"미용·여행·숙박·음식·경비·돌봄·청소",6:"영업·판매·운전·운송",7:"건설·채굴",
        8:"설치·정비·생산",9:"농림어업"}.items()}
priv = c.직종대분류.map(code).value_counts()
priv_grad = c[c.요구학력.isin(["대학교졸","석사이상"])].직종대분류.map(code).value_counts()

t = pd.DataFrame({"졸업자": grad, "공공구인": pub_d, "공공구직": pub_s,
                  "민간공고": priv, "민간대졸공고": priv_grad}).fillna(0)
t.index = [NAME[i] for i in t.index]
for col in t.columns:
    t[col + "%"] = t[col] / t[col].sum() * 100
t["구인배수"] = t.공공구인 / t.공공구직
t["배출-공공수요"] = t["졸업자%"] - t["공공구인%"]
t["배출-민간수요"] = t["졸업자%"] - t["민간공고%"]
t = t.sort_values("졸업자%", ascending=False)
t.round(2).to_csv("out/미스매치_대분류.csv", encoding="utf-8-sig")

pd.set_option("display.width", 220)
print(f"■ 부산 배출 vs 수요 (졸업자 2024 · 고용24 2025.08~2026.07 · 공고 2026-09-07)")
print(f"  크로스워크 미매핑 중계열 {unmapped} → 졸업자 {drop:,.0f}명 제외\n")
show = ["졸업자%", "공공구인%", "민간공고%", "민간대졸공고%", "공공구직%", "구인배수", "배출-공공수요"]
print(t[show].to_string(float_format=lambda v: f"{v:6.2f}"))
