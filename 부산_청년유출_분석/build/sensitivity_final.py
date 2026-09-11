"""통합 민감도 — 크로스워크 코너 19 × 학제 3 × 수요정의 2 = 114 시나리오.

수요 정의에서 '민간 대졸명시 공고만'은 제외한다.
분모를 대졸 공고로 한정하면 "대졸 일자리 중 대졸 직종의 비중"을 묻는 것이 되어
"부산 일자리 중 대졸이 갈 자리가 얼마나 되는가"라는 질문과 다른 질문이 된다(동어반복).
대신 진단용으로 따로 보고한다.
"""
import itertools
import pandas as pd

NAME = {0:"경영·사무·금융·보험", 1:"연구·공학기술", 2:"교육·법률·사회복지·경찰·소방",
        3:"보건·의료", 4:"예술·디자인·방송·스포츠", 5:"미용·여행·숙박·음식·경비·돌봄·청소",
        6:"영업·판매·운전·운송", 7:"건설·채굴", 8:"설치·정비·생산", 9:"농림어업"}
CONTESTED = {"언어ㆍ문학": [0, 2, 4], "인문과학": [0, 2], "생활과학": [0, 3, 5]}
HIGH = [1, 2, 3]
LEVELS = {"전체": ["대학","교육대학","전문대학"], "4년제만": ["대학"], "전문대만": ["전문대학"]}
CRAWL = {"경영·사무·금융·보험":0,"연구·공학기술":1,"교육·법률·사회복지·경찰·소방·군인":2,
         "보건·의료":3,"예술·디자인·방송·스포츠":4,"미용·여행·숙박·음식·경비·돌봄·청소":5,
         "영업·판매·운전·운송":6,"건설·채굴":7,"설치·정비·생산":8,"농림어업":9}

g = pd.read_excel("data/취업통계/부산소재_고등교육기관_졸업자_취업통계_2024.xlsx", sheet_name="부산_전체")
g["졸업자_계"] = pd.to_numeric(g["졸업자_계"], errors="coerce")
cw0 = pd.read_csv("build/crosswalk.csv")
w = pd.read_csv("out/워크넷_부산_월별_직종중분류.csv")
pub = w[(w.지표=="신규구인인원") & (w.표=="4-2")].groupby("대분류코드")["부산"].sum()
sup = w[(w.지표=="신규구직건수") & (w.표=="5-2")].groupby("대분류코드")["부산"].sum()
ratio = (pub / sup).reindex(range(10))
c = pd.read_csv("data/채용공고/부산_공고_분석용.csv")
c = c[c.직종대분류 != "미분류"]; c["코드"] = c.직종대분류.map(CRAWL)
DEMAND = {"공공(고용24)": (pub/pub.sum()*100).reindex(range(10)).fillna(0),
          "민간(크롤링)": c.코드.value_counts(normalize=True).mul(100).reindex(range(10)).fillna(0)}
DIAG = c[c.요구학력.isin(["대학교졸","석사이상"])].코드.value_counts(normalize=True).mul(100).reindex(range(10)).fillna(0)

CW = {"기준(가중배분)": cw0}
for combo in itertools.product(*CONTESTED.values()):
    a = dict(zip(CONTESTED, combo))
    CW[" / ".join(f"{k[:2]}→{v}" for k, v in a.items())] = pd.concat([
        cw0[~cw0.중계열.isin(CONTESTED)][["중계열","직종대분류코드","가중치"]],
        pd.DataFrame([{"중계열":k,"직종대분류코드":v,"가중치":1.0} for k,v in a.items()])],
        ignore_index=True)

rows = []
for (cn, cwx), (ln, lv), (dn, d) in itertools.product(CW.items(), LEVELS.items(), DEMAND.items()):
    mid = g[g["학제"].isin(lv)].groupby("중계열")["졸업자_계"].sum()
    m = cwx.merge(mid.rename("졸업자").reset_index(), on="중계열")
    s = (m.졸업자*m.가중치).groupby(m.직종대분류코드).sum()
    gs = (s/s.sum()*100).reindex(range(10)).fillna(0)
    rec = {"크로스워크":cn, "학제":ln, "수요":dn,
           "대졸직종_배출%":gs[HIGH].sum(), "대졸직종_수요%":d[HIGH].sum(),
           "ρ":gs.rank().corr(ratio.rank())}
    for i in range(10): rec[f"격차_{NAME[i]}"] = gs[i] - d[i]
    rows.append(rec)
r = pd.DataFrame(rows)
r["배율"] = r["대졸직종_배출%"] / r["대졸직종_수요%"]
r.round(3).to_csv("out/민감도_통합.csv", index=False, encoding="utf-8-sig")

print(f"시나리오 {len(r)}개 = 크로스워크 {len(CW)} × 학제 {len(LEVELS)} × 수요 {len(DEMAND)}\n")
print("■ 핵심 결론의 하한")
print(f"  A. 대졸직종 배출 > 수요            성립 {(r.배율>1).sum()}/{len(r)}"
      f"   배율 {r.배율.min():.2f}~{r.배율.max():.2f}배")
print(f"  B. ρ(배출~구인배수) < 0            성립 {(r.ρ<0).sum()}/{len(r)}"
      f"   ρ {r.ρ.min():.2f}~{r.ρ.max():.2f}")
print("\n■ 직종별 격차 부호 안정성 (114 시나리오 전부)")
for i in range(10):
    col = r[f"격차_{NAME[i]}"]
    lo, hi = col.min(), col.max()
    v = "과잉 확정" if lo > 0 else "과소 확정" if hi < 0 else "불확정"
    print(f"  {NAME[i]:<22} {lo:+7.1f} ~ {hi:+7.1f}   {v}")
print("\n■ [진단] 수요를 '민간 대졸명시 공고'로 한정하면 (동어반복이라 본 분석에서 제외)")
base = cw0.merge(g[g.학제.isin(LEVELS['전체'])].groupby('중계열')['졸업자_계'].sum()
                 .rename('졸업자').reset_index(), on='중계열')
bs = (base.졸업자*base.가중치).groupby(base.직종대분류코드).sum()
bs = (bs/bs.sum()*100).reindex(range(10)).fillna(0)
print(f"  대졸직종 배출 {bs[HIGH].sum():.1f}% vs 수요 {DIAG[HIGH].sum():.1f}%  → 배율 {bs[HIGH].sum()/DIAG[HIGH].sum():.2f}배 (A 불성립)")
print(f"  단 예술·디자인은 배출 {bs[4]:.1f}% vs 수요 {DIAG[4]:.1f}%  → {bs[4]/DIAG[4]:.1f}배 과잉으로 유지")
