"""GOMS 2019 — 부산 소재 대학 졸업자는 어디에 자리를 잡았나.

첫직장(D섹션)은 이직 경험자 위주라 커버리지가 27%뿐이다.
그래서 '첫 일자리 지역'을 다음 우선순위로 구성한다.
   1) D7 첫직장 시도가 있으면 그것
   2) 없고 A6 현 직장 시도가 있으면 그것 (이직 기록이 없으므로 현직장 = 첫 일자리)
→ 커버리지 27.0% → 78.4%
현재 거주지(P8)는 100% 커버되므로 별도 지표로 함께 본다.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd

SIDO = {1:"서울",2:"부산",3:"대구",4:"대전",5:"인천",6:"광주",7:"울산",8:"경기",
        9:"강원",10:"충북",11:"충남",12:"전북",13:"전남",14:"경북",15:"경남",16:"제주",17:"세종"}
MAJOR = {1:"인문",2:"사회",3:"교육",4:"공학",5:"자연",6:"의약",7:"예체능"}
# GOMS 2018 KECO 대분류는 1~10. 우리 직종코드 앞 1자리(0~9)와 한 칸 어긋나므로 -1 해서 맞춘다.
KECO = {1:"경영·사무·금융·보험",2:"연구·공학기술",3:"교육·법률·사회복지·경찰·소방",
        4:"보건·의료",5:"예술·디자인·방송·스포츠",6:"미용·여행·숙박·음식·경비·돌봄·청소",
        7:"영업·판매·운전·운송",8:"건설·채굴",9:"설치·정비·생산",10:"농림어업"}
CAP = {1, 5, 8}   # 서울·인천·경기

C = ["g191wt","g191area","g191school","g191majorcat","g191d020","g191a014","g191p024",
     "g191f006","g191a144","g191a122","g191a007a_2018","g191d010a_2018"]
d = pd.read_stata("data/goms/GP19__2020.DTA", columns=C, convert_categoricals=False)
b = d[d.g191area == 2].copy()

ok = lambda s: s.between(1, 17)
b["일자리시도"] = b.g191d020.where(ok(b.g191d020), b.g191a014.where(ok(b.g191a014)))
b["직종대분류"] = b.g191d010a_2018.where(b.g191d010a_2018.between(1, 10),
                                     b.g191a007a_2018.where(b.g191a007a_2018.between(1, 10)))
b["전공"] = b.g191majorcat.map(MAJOR)
j = b[ok(b["일자리시도"])].copy()

print(f"부산 소재 대학 졸업자 {len(b):,}명 (가중 {b.g191wt.sum():,.0f}명)")
print(f"  첫 일자리 지역 확인 {len(j):,}명 ({len(j)/len(b)*100:.1f}%)"
      f"  · 현재 거주지 확인 {ok(b.g191p024).sum():,}명 (100%)\n")

def share(g, col, targets):
    w = g.g191wt.sum()
    return {k: g[g[col].isin(v)].g191wt.sum() / w * 100 for k, v in targets.items()}

TGT = {"부산": {2}, "수도권": CAP, "경남·울산": {15, 7}, "그 외": set(SIDO) - CAP - {2, 15, 7}}

print(f"■ 지표 1 — 첫 일자리 소재 시도 (가중 %, n={len(j)})")
s = share(j, "일자리시도", TGT)
for k, v in s.items(): print(f"   {k:<8} {v:5.1f}%")
print(f"   → 부산 이탈 {100-s['부산']:.1f}%")

print(f"\n■ 지표 2 — 조사시점 거주 시도 (가중 %, n={len(b)} · 전수)")
s2 = share(b, "g191p024", TGT)
for k, v in s2.items(): print(f"   {k:<8} {v:5.1f}%")
print(f"   → 부산 이탈 {100-s2['부산']:.1f}%")

print("\n■ 전공계열별 첫 일자리 지역")
rows = []
for m, g in j.groupby("전공"):
    sh = share(g, "일자리시도", TGT)
    rows.append({"전공": m, "표본": len(g), "부산잔류%": sh["부산"],
                 "수도권%": sh["수도권"], "경남·울산%": sh["경남·울산"],
                 "부산이탈%": 100 - sh["부산"]})
r = pd.DataFrame(rows).sort_values("부산이탈%", ascending=False)
print(r.to_string(index=False, float_format=lambda v: f"{v:6.1f}"))
r.round(1).to_csv("out/GOMS_전공계열별_첫일자리지역.csv", index=False, encoding="utf-8-sig")

print("\n■ 출신 고교 지역별 — '외지 학생이 고향 간 것' 반론 점검")
for lab, sub in [("부산 출신", j[j.g191f006 == 2]),
                 ("타지 출신", j[(j.g191f006 != 2) & ok(j.g191f006)])]:
    sh = share(sub, "일자리시도", TGT)
    print(f"   {lab:<8} 표본 {len(sub):>4}  부산잔류 {sh['부산']:5.1f}%  "
          f"수도권 {sh['수도권']:5.1f}%  이탈 {100-sh['부산']:5.1f}%")

print("\n■ 첫 일자리 직종(2018 KECO 대분류)별 부산 잔류율 — 우리 수요 분석과 직접 접합")
rows = []
for c, g in j[j.직종대분류.notna()].groupby("직종대분류"):
    if len(g) < 15: continue
    rows.append({"직종코드": int(c) - 1, "직종": KECO.get(int(c), str(c)), "표본": len(g),
                 "부산잔류%": g[g.일자리시도 == 2].g191wt.sum() / g.g191wt.sum() * 100})
o = pd.DataFrame(rows).sort_values("부산잔류%")
print(o.to_string(index=False, float_format=lambda v: f"{v:6.1f}"))
o.round(1).to_csv("out/GOMS_직종별_부산잔류율.csv", index=False, encoding="utf-8-sig")

print("\n■ 잔류 vs 이탈 — 일자리의 질")
j["행선"] = j.일자리시도.map(lambda x: "부산잔류" if x == 2 else ("수도권" if x in CAP else "기타지역"))
def wmean(g, col):
    m = g[col] > 0
    return (g.loc[m, col] * g.loc[m, "g191wt"]).sum() / g.loc[m, "g191wt"].sum() if m.any() else float("nan")
q = j.groupby("행선").apply(lambda g: pd.Series({
    "표본": len(g), "월소득(만원)": wmean(g, "g191a122"), "전공일치(1~5)": wmean(g, "g191a144")}))
print(q.to_string(float_format=lambda v: f"{v:8.1f}"))
q.round(1).to_csv("out/GOMS_잔류vs이탈_질.csv", encoding="utf-8-sig")

# ── 직접 검증: 전공계열 이탈률 ↔ 그 계열이 향하는 직종의 부산 구인배수
# 전공은 졸업 이전에 정해진 값이라 '선택의 결과'가 아니다(내생성이 적다).
# 반면 '첫 일자리 직종'은 떠난 뒤 잡은 직종이라 이미 선택의 결과다 — 검증축으로 부적절.
print("\n■ 검증 — 전공계열 이탈률 ↔ 해당 계열이 향하는 직종의 부산 구인배수")
MAJ2MID = {   # GOMS 7계열 → 취업통계 중계열 (크로스워크 재사용을 위한 다리)
    "인문": ["언어ㆍ문학","인문과학"], "사회": ["경영ㆍ경제","사회과학","법률","산업"],
    "교육": ["교육일반","유아교육","초등교육","중등교육","특수교육"],
    "공학": ["컴퓨터ㆍ통신","전기ㆍ전자","기계ㆍ금속","소재ㆍ재료","정밀ㆍ에너지","화공",
             "건축","토목ㆍ도시","교통ㆍ운송"],
    "자연": ["생물ㆍ화학ㆍ환경","수학ㆍ물리ㆍ천문ㆍ지리","생활과학","농림ㆍ수산"],
    "의약": ["간호","치료ㆍ보건","의료","약학"],
    "예체능": ["디자인","응용예술","미술ㆍ조형","연극ㆍ영화","음악","무용ㆍ체육"]}

cw = pd.read_csv("build/crosswalk.csv")
w = pd.read_csv("out/워크넷_부산_월별_직종중분류.csv")
dem = w[(w.지표=="신규구인인원") & (w.표=="4-2")].groupby("대분류코드")["부산"].sum()
sup = w[(w.지표=="신규구직건수") & (w.표=="5-2")].groupby("대분류코드")["부산"].sum()
ratio = (dem / sup)
g24 = pd.read_excel("data/취업통계/부산소재_고등교육기관_졸업자_취업통계_2024.xlsx", sheet_name="부산_전체")
g24 = g24[g24["학제"].isin(["대학","교육대학","전문대학"])]
g24["졸업자_계"] = pd.to_numeric(g24["졸업자_계"], errors="coerce")
grads = g24.groupby("중계열")["졸업자_계"].sum()

rows = []
for maj, mids in MAJ2MID.items():
    sub = cw[cw.중계열.isin(mids)].merge(grads.rename("n").reset_index(), on="중계열")
    if sub.empty: continue
    wt = sub.n * sub.가중치
    br = (wt * sub.직종대분류코드.map(ratio)).sum() / wt.sum()   # 졸업자 가중 평균 구인배수
    out = r.loc[r.전공 == maj, "부산이탈%"]
    if len(out): rows.append({"전공": maj, "부산이탈%": out.iloc[0], "향하는직종_구인배수": br})
v = pd.DataFrame(rows).sort_values("부산이탈%", ascending=False)
print(v.to_string(index=False, float_format=lambda x: f"{x:7.3f}"))
print(f"\n  피어슨  이탈률 ~ 구인배수 : {v['부산이탈%'].corr(v['향하는직종_구인배수']):+.3f}")
print(f"  스피어만 이탈률 ~ 구인배수 : "
      f"{v['부산이탈%'].rank().corr(v['향하는직종_구인배수'].rank()):+.3f}")
v.round(3).to_csv("out/GOMS_검증_이탈률vs구인배수.csv", index=False, encoding="utf-8-sig")

print("\n■ 참고 — 첫 일자리 직종별 행선지 (설치·정비·생산 이상치 확인)")
t = (j[j.직종대분류.notna()].assign(직종=lambda x: (x.직종대분류 - 1).map(
        {k-1: v for k, v in KECO.items()}))
     .groupby(["직종", "행선"]).g191wt.sum().unstack(fill_value=0))
t = (t.T / t.T.sum()).T * 100
print(t.round(1).to_string())
