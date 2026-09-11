"""부산 노동수요 3중 비교: 졸업자 배출 / 공공채널 구인 / 민간채널 공고."""
import pandas as pd

w = pd.read_csv("out/워크넷_부산_월별_직종중분류.csv")
demand = w[(w.지표 == "신규구인인원") & (w.표 == "4-2")]     # 구인업체 소재지
supply = w[(w.지표 == "신규구직건수") & (w.표 == "5-2")]     # 구직자 거주지

def by_big(d, col="부산"):
    return d.groupby(["대분류코드", "대분류명"])[col].sum()

dem, sup = by_big(demand), by_big(supply)
dem_kr, sup_kr = by_big(demand, "전국"), by_big(supply, "전국")
dem_se = by_big(demand, "서울")

t = pd.DataFrame({"구인": dem, "구직": sup}).reset_index()
t["구인%"] = t.구인 / t.구인.sum() * 100
t["구직%"] = t.구직 / t.구직.sum() * 100
t["구인배수"] = t.구인 / t.구직
t["전국구인%"] = (dem_kr / dem_kr.sum() * 100).values
t["서울구인%"] = (dem_se / dem_se.sum() * 100).values
t["LQ_대전국"] = t["구인%"] / t["전국구인%"]

# 우리 크롤링 (민간 채널)
c = pd.read_csv("data/채용공고/부산_공고_분석용.csv")
c = c[c.직종대분류 != "미분류"]
crawl = c.직종대분류.value_counts(normalize=True) * 100
NAME = {"0": "경영·사무·금융·보험", "1": "연구·공학기술", "2": "교육·법률·사회복지·경찰·소방·군인",
        "3": "보건·의료", "4": "예술·디자인·방송·스포츠", "5": "미용·여행·숙박·음식·경비·돌봄·청소",
        "6": "영업·판매·운전·운송", "7": "건설·채굴", "8": "설치·정비·생산", "9": "농림어업"}
t["크롤링%"] = t.대분류코드.astype(str).map(lambda k: crawl.get(NAME[k]))

t = t.sort_values("구인%", ascending=False)
t.to_csv("out/부산_직종대분류_수요공급.csv", index=False, encoding="utf-8-sig")

pd.set_option("display.width", 200)
print("■ 부산 직종대분류별 노동수요·공급 (2025.08~2026.07, 고용24)\n")
print(t[["대분류명", "구인", "구인%", "구직%", "구인배수", "크롤링%", "LQ_대전국"]]
      .to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
print(f"\n부산 전체 구인배수 {t.구인.sum()/t.구직.sum():.3f}"
      f"  (전국 {dem_kr.sum()/sup_kr.sum():.3f})")
