"""성별 축 — 선행작업(KEDI 취업률·유지율) + 우리(GOMS 이탈률·임금)를 13계열로 결합."""
import warnings; warnings.filterwarnings("ignore")
import sys, numpy as np, pandas as pd
sys.path.insert(0, "build"); from major_group import group

GRP = {'경영ㆍ경제':'경영·사무','사회과학':'경영·사무','법률':'경영·사무','산업':'경영·사무',
 '언어ㆍ문학':'인문·어학','인문과학':'인문·어학','컴퓨터ㆍ통신':'IT·컴퓨터','전기ㆍ전자':'기계·전기전자',
 '기계ㆍ금속':'기계·전기전자','소재ㆍ재료':'기계·전기전자','정밀ㆍ에너지':'기계·전기전자','화공':'기계·전기전자',
 '건축':'건설·토목','토목ㆍ도시':'건설·토목','디자인':'디자인·예술','응용예술':'디자인·예술',
 '미술ㆍ조형':'디자인·예술','연극ㆍ영화':'디자인·예술','음악':'디자인·예술','무용ㆍ체육':'디자인·예술',
 '치료ㆍ보건':'보건·의료','간호':'보건·의료','의료':'보건·의료','약학':'보건·의료',
 '생활과학':'생활과학·화학','생물ㆍ화학ㆍ환경':'생활과학·화학','수학ㆍ물리ㆍ천문ㆍ지리':'자연과학',
 '교육일반':'교육','유아교육':'교육','초등교육':'교육','중등교육':'교육','특수교육':'교육',
 '교통ㆍ운송':'물류·운송','농림ㆍ수산':'농림·수산','기타':'기타'}

# ── KEDI 취업률·유지율 (선행작업 지표)
g = pd.read_excel("data/취업통계/부산소재_고등교육기관_졸업자_취업통계_2024.xlsx", sheet_name="부산_전체")
g = g[g["학제"].isin(["대학", "교육대학", "전문대학"])].copy()
C = {"졸": "졸업자_", "취": "취업자_합계_", "유4": "4차 유지취업자_"}
for k, pre in C.items():
    for s in ["남", "여"]:
        g[k + s] = pd.to_numeric(g[pre + s], errors="coerce")
g["계열"] = g.중계열.map(GRP)
k = g[g.계열 != "기타"].groupby("계열")[[a + b for a in C for b in ("남", "여")]].sum()
for s in ["남", "여"]:
    k["취업률_" + s] = k["취" + s] / k["졸" + s] * 100
    k["유지4_" + s] = k["유4" + s] / k["취" + s] * 100
k["여성비중"] = k.졸여 / (k.졸남 + k.졸여) * 100
k["취업률격차"] = k.취업률_남 - k.취업률_여
k["유지격차"] = k.유지4_남 - k.유지4_여

# ── GOMS 이탈률·임금
p = pd.read_pickle("data/goms/pool/goms_pooled.pkl")
lut = p[p.dpmt_n.notna() & (p.dpmt_n.astype(str) != "nan")].groupby("dpmt").dpmt_n.first()
b = p[p.area == 2].copy(); ok = lambda s: s.between(1, 17)
b["지역"] = b.d020.where(ok(b.d020), b.a014.where(ok(b.a014)))
b = b[ok(b["지역"])].copy(); b["계열"] = b.dpmt.map(lut).map(group)
rows = []
for m, s in b.groupby("계열"):
    r = {"계열": m}
    for sx, lab in [(1, "남"), (2, "여")]:
        x = s[s.sex == sx]; w = x[x.a122 > 0]
        if len(x) < 40: r["이탈_" + lab] = r["잔류소득_" + lab] = np.nan; continue
        r["이탈_" + lab] = 100 - x.loc[x.지역 == 2, "wt"].sum() / x.wt.sum() * 100
        st = w[w.지역 == 2]
        r["잔류소득_" + lab] = (st.a122 * st.wt).sum() / st.wt.sum() if len(st) else np.nan
    rows.append(r)
go = pd.DataFrame(rows).set_index("계열")

t = k[["여성비중", "취업률_남", "취업률_여", "취업률격차", "유지4_남", "유지4_여", "유지격차"]].join(go)
t["소득격차"] = t.잔류소득_남 - t.잔류소득_여
t = t.sort_values("여성비중", ascending=False)
t.round(1).to_csv("out/성별_13계열.csv", encoding="utf-8-sig")
pd.set_option("display.width", 220)
print("■ 13계열 × 성별 (KEDI 취업률·유지율 + GOMS 이탈률·잔류소득)")
print(t[["여성비중", "취업률_남", "취업률_여", "취업률격차", "유지격차", "이탈_남", "이탈_여", "잔류소득_남", "잔류소득_여", "소득격차"]]
      .to_string(float_format=lambda v: f"{v:6.1f}"))
print(f"\n전체 평균 취업률격차 {t.취업률격차.mean():+.1f}%p · 유지격차 {t.유지격차.mean():+.1f}%p · 잔류소득격차 {t.소득격차.mean():+.0f}만원")
