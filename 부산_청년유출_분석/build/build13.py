"""13계열 통합 테이블 — 대시보드가 쓸 단일 소스.

두 매핑이 모두 `중계열`을 키로 쓴다는 점을 이용한다.
  중계열 → 그룹계열 13종        (팀 분류, 서현)
  중계열 → 직종대분류 10종 (가중)  (build/crosswalk.csv)
따라서 계열별 졸업자 가중치로 직종 분포를 만들고,
그 분포로 수요·구인배수·대졸요구율을 가중평균한다.
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd

GRP = {'경영ㆍ경제':'경영·사무','사회과학':'경영·사무','법률':'경영·사무','산업':'경영·사무',
 '언어ㆍ문학':'인문·어학','인문과학':'인문·어학','컴퓨터ㆍ통신':'IT·컴퓨터',
 '전기ㆍ전자':'기계·전기전자','기계ㆍ금속':'기계·전기전자','소재ㆍ재료':'기계·전기전자',
 '정밀ㆍ에너지':'기계·전기전자','화공':'기계·전기전자','건축':'건설·토목','토목ㆍ도시':'건설·토목',
 '디자인':'디자인·예술','응용예술':'디자인·예술','미술ㆍ조형':'디자인·예술','연극ㆍ영화':'디자인·예술',
 '음악':'디자인·예술','무용ㆍ체육':'디자인·예술','치료ㆍ보건':'보건·의료','간호':'보건·의료',
 '의료':'보건·의료','약학':'보건·의료','생활과학':'생활과학·화학','생물ㆍ화학ㆍ환경':'생활과학·화학',
 '수학ㆍ물리ㆍ천문ㆍ지리':'자연과학','교육일반':'교육','유아교육':'교육','초등교육':'교육',
 '중등교육':'교육','특수교육':'교육','교통ㆍ운송':'물류·운송','농림ㆍ수산':'농림·수산','기타':'기타'}
NAME = {0:"경영·사무·금융·보험",1:"연구·공학기술",2:"교육·법률·사회복지·경찰·소방",3:"보건·의료",
        4:"예술·디자인·방송·스포츠",5:"미용·여행·숙박·음식·경비·돌봄·청소",6:"영업·판매·운전·운송",
        7:"건설·채굴",8:"설치·정비·생산",9:"농림어업"}

# 졸업자
g = pd.read_excel("data/취업통계/부산소재_고등교육기관_졸업자_취업통계_2024.xlsx", sheet_name="부산_전체")
g = g[g["학제"].isin(["대학","교육대학","전문대학"])]
g["졸업자_계"] = pd.to_numeric(g["졸업자_계"], errors="coerce")
mid = g.groupby("중계열")["졸업자_계"].sum()

cw = pd.read_csv("build/crosswalk.csv")
m = cw.merge(mid.rename("졸업자").reset_index(), on="중계열")
m["계열"] = m.중계열.map(GRP)
m["배분"] = m.졸업자 * m.가중치                       # 중계열×직종 셀의 졸업자 수

# 직종 지표
# 대졸신입 공고 = 요구학력(대졸·석사) AND 경력(무관·신입) — 선행작업 지표를 13계열로 옮긴다
CR = {"경영·사무·금융·보험":0,"연구·공학기술":1,"교육·법률·사회복지·경찰·소방·군인":2,"보건·의료":3,
      "예술·디자인·방송·스포츠":4,"미용·여행·숙박·음식·경비·돌봄·청소":5,"영업·판매·운전·운송":6,
      "건설·채굴":7,"설치·정비·생산":8,"농림어업":9}
c = pd.read_csv("data/채용공고/부산_공고_분석용.csv")
c = c[c.직종대분류 != "미분류"].copy(); c["코드"] = c.직종대분류.map(CR)
NEW = (c[c.요구학력.isin(["대학교졸","석사이상"]) & c.경력요건.isin(["무관","신입"])]
       .코드.value_counts().reindex(range(10), fill_value=0))

ind = pd.read_csv("out/미스매치_대분류_확장.csv", index_col=0)
R = {v: k for k, v in NAME.items()}
ind["코드"] = [R[i] for i in ind.index]
ind = ind.set_index("코드").reindex(range(10))
IDX = pd.read_csv("out/부산_직종대분류_수요공급.csv").set_index("대분류코드").reindex(range(10))

# 계열 × 직종 배분행렬 — 직종별 공고를 계열에 나눌 때 총계가 보존되도록 열 기준으로 정규화한다
A = m[m.계열 != "기타"].pivot_table(index="계열", columns="직종대분류코드",
                                   values="배분", aggfunc="sum").reindex(columns=range(10)).fillna(0)
COLSHARE = A.div(A.sum(axis=0).replace(0, pd.NA), axis=1).fillna(0)
NEW13 = (COLSHARE * NEW).sum(axis=1)          # 계열별 대졸신입 공고(배분)
# 배분 의존도 — 받은 공고 1건당 그 직종에서 내가 차지한 평균 지분.
# 낮을수록 "어느 직종에서도 주된 수요자가 아니다" = N명당 수치가 배분 가정에 좌우된다.
REC = COLSHARE * NEW
DEP = (REC * COLSHARE).sum(axis=1) / REC.sum(axis=1).replace(0, pd.NA)

rows = []
for k, s in m.groupby("계열"):
    if k == "기타": continue
    w = s.groupby("직종대분류코드").배분.sum()
    p = (w / w.sum()).reindex(range(10), fill_value=0)   # 이 계열이 향하는 직종 분포
    rows.append({
        "계열": k,
        "졸업자": int(mid[s.중계열.unique()].sum()),
        "공공수요%": (p * IDX["구인%"]).sum(),
        "민간수요%": (p * ind["민간공고%"]).sum(),
        "구인배수":  (p * IDX["구인배수"]).sum(),
        "대졸요구율": (p * ind["대졸요구율"]).sum(),
        "주력직종":  NAME[int(p.idxmax())],
        "주력직종비중": p.max() * 100,
        "대졸신입공고": NEW13[k],
        "전용도": DEP[k],
    })
t = pd.DataFrame(rows)
t["배출%"] = t.졸업자 / t.졸업자.sum() * 100
t["N명당_대졸신입1개"] = t.졸업자 / t.대졸신입공고.replace(0, pd.NA)
t["배분의존"] = t.전용도 < 0.5          # True = 이 계열의 N명당은 배분 가정에 크게 의존

# GOMS(4코호트) · 정책 결합
go = pd.read_csv("out/GOMS13_계열별.csv")[["계열","부산이탈%","수도권%","잔류자_월소득","이탈자_월소득","임금프리미엄%","t","유의","표본"]]
po = pd.read_csv("out/정책_계열분류.csv")
po = po[po.계열 != "전계열"].groupby(["계열","성격"]).size().unstack(fill_value=0)
for c in ["양성","수요·매칭","창업","생활지원"]:
    if c not in po: po[c] = 0
t = t.merge(go, on="계열", how="left").merge(
        po[["양성","수요·매칭","창업"]].reset_index(), on="계열", how="left")
t[["양성","수요·매칭","창업"]] = t[["양성","수요·매칭","창업"]].fillna(0).astype(int)
t = t.sort_values("배출%", ascending=False)
t.round(2).to_csv("out/대시보드_13계열.csv", index=False, encoding="utf-8-sig")

pd.set_option("display.width", 240)
print("■ 13계열 통합 테이블 (대시보드 단일 소스)")
print(t[["계열","졸업자","배출%","대졸신입공고","N명당_대졸신입1개","전용도","배분의존","부산이탈%","임금프리미엄%","유의","양성","수요·매칭"]]
      .to_string(index=False, float_format=lambda v: f"{v:7.1f}"))
print(f"\n대졸신입 공고 총 {NEW.sum():,}건 · 배분 합 {NEW13.sum():,.0f}건 (총계 보존 확인)")
