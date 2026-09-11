# -*- coding: utf-8 -*-
"""포스터용 3개 절단면 — ①직종별 요구학력 ②구별 산업구성 ③구별·산업별 정규직 비율
입력: data/채용공고/부산_공고_분석용.csv (25,135건, 2025-09 수집 시점 stock)
출력: out/공고_학력_직종별.csv · out/공고_산업_구별.csv · out/공고_고용형태_구별.csv
      out/공고_산업별_질.csv
"""
import re, pandas as pd

d = pd.read_csv("data/채용공고/부산_공고_분석용.csv", low_memory=False)

EDU = {"대학교졸":"대졸이상","석사이상":"대졸이상","전문대졸":"전문대졸",
       "고졸":"고졸이하","중졸이하":"고졸이하","학력무관":"학력무관","미기재":"미기재"}
d["학력군"] = d.요구학력.map(EDU)

IND = [                                   # 위에서부터 먼저 맞는 것
 ("보건·의료·복지", r"의료|병원|제약|바이오|보건|간호|사회복지|요양|복지"),
 ("교육",           r"학원|어학원|교육|초중고|대학|유치원|보육"),
 ("IT·정보통신",    r"솔루션|SI|ERP|CRM|소프트웨어|SW|IT|정보통신|네트워크|통신서비스|게임|포털|웹"),
 ("금융·보험",      r"금융|은행|증권|보험|카드|캐피탈|투자"),
 ("건설·부동산",    r"건설|건축|토목|시공|인테리어|조경|부동산|임대|중개|설비·환경"),
 ("운수·물류",      r"물류|운송|운수|배송|해운|항만|택배"),
 ("유통·판매·무역",  r"유통|무역|상사|판매|도소매|백화점|쇼핑몰|오픈마켓|전자상거래|소매"),
 ("음식·숙박·여가",  r"외식|식음료|음식료|프랜차이즈|호텔|여행|숙박|레저|스포츠|여가|뷰티|미용|화장품"),
 ("제조",           r"기계|설비|자동차|조선|항공|우주|전기|전자|제어|금속|재료|철강|요업|제조|"
                    r"식품가공|섬유|의류|패션|화학|석유|에너지|반도체|생활용품|소비재|자재"),
 ("사업·전문서비스", r"광고|홍보|전시|회계|세무|법무|컨설팅|연구소|조사|시설관리|경비|용역|보안|"
                    r"콜센터|아웃소싱|디자인|설계|협회|단체|서비스업|사업시설"),
]
def ind(x):
    if not isinstance(x, str): return "미상"
    for name, pat in IND:
        if re.search(pat, x): return name
    return "기타"
d["산업군"] = d.업종원문.map(ind)

REG = d.고용형태.isin(["정규직"])
d["정규직"] = REG
gu = d[d.시군구 != "미상"].copy()

# ① 직종 × 요구학력
occ = d[d.직종대분류.notna()]
t1 = pd.crosstab(occ.직종대분류, occ.학력군, normalize="index").mul(100).round(1)
t1["공고수"] = occ.직종대분류.value_counts()
t1 = t1.sort_values("공고수", ascending=False)

# ② 구 × 산업군 구성
t2 = pd.crosstab(gu.시군구, gu.산업군, normalize="index").mul(100).round(1)
t2["공고수"] = gu.시군구.value_counts()
t2 = t2.sort_values("공고수", ascending=False)

# ③ 구별 일자리의 질
t3 = (gu.groupby("시군구")
        .agg(공고수=("공고ID","size"),
             정규직률=("정규직","mean"),
             대졸이상률=("학력군", lambda s:(s=="대졸이상").mean()),
             학력무관률=("학력군", lambda s:(s=="학력무관").mean()),
             신입가능률=("경력요건", lambda s: s.isin(["무관","신입"]).mean()))
        .assign(**{c: lambda x, c=c: (x[c]*100).round(1)
                   for c in ["정규직률","대졸이상률","학력무관률","신입가능률"]})
        .sort_values("공고수", ascending=False))

# ④ 산업군별 질 — 어떤 산업이 대졸을 부르는가
t4 = (d.groupby("산업군")
        .agg(공고수=("공고ID","size"),
             정규직률=("정규직","mean"),
             대졸이상률=("학력군", lambda s:(s=="대졸이상").mean()),
             학력무관률=("학력군", lambda s:(s=="학력무관").mean()),
             연봉중앙=("연봉환산최소","median"))
        .assign(**{c: lambda x, c=c: (x[c]*100).round(1)
                   for c in ["정규직률","대졸이상률","학력무관률"]})
        .sort_values("공고수", ascending=False))

for t, f in [(t1,"공고_학력_직종별"), (t2,"공고_산업_구별"),
             (t3,"공고_고용형태_구별"), (t4,"공고_산업별_질")]:
    t.to_csv(f"out/{f}.csv", encoding="utf-8-sig")

print("■ 구별 일자리의 질"); print(t3.to_string()); print()
print("■ 산업군별 질");      print(t4.to_string()); print()
print("산업 미상·기타 비중:",
      round((d.산업군.isin(["미상","기타"])).mean()*100,1), "%")
