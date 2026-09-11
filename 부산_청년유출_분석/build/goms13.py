"""GOMS 4개 코호트 풀링 → 그룹계열 13종별 이탈률·임금 프리미엄.

코호트마다 부산 유출 규모가 달라(2016 6,594 → 2019 10,343) 연도 더미를 반드시 넣는다.
"""
import warnings; warnings.filterwarnings("ignore")
import sys, numpy as np, pandas as pd
sys.path.insert(0, "build"); from major_group import group

SCALE = {1:4.0, 2:4.3, 3:4.5}; CAP = {1,5,8}
g = pd.read_pickle("data/goms/pool/goms_pooled.pkl")
lut = g[g.dpmt_n.notna() & (g.dpmt_n.astype(str) != "nan")].groupby("dpmt").dpmt_n.first()
b = g[g.area == 2].copy()
ok = lambda s: s.between(1, 17)
b["지역"] = b.d020.where(ok(b.d020), b.a014.where(ok(b.a014)))
b = b[ok(b["지역"])].copy()
b["계열"] = b.dpmt.map(lut).map(group)
b["이탈"] = (b.지역 != 2).astype(float)
b["여성"] = (b.sex == 2).astype(float); b["사립"] = (b.found == 3).astype(float)
b["어학연수"] = (b.i001 == 1).astype(float)
gpa = np.where(b.f074 > 0, b.f074 / b.f073.map(SCALE).astype(float) * 100, np.nan)
b["평점"] = pd.Series(gpa, index=b.index).fillna(np.nanmean(gpa))
inc = np.where(b.p034.between(2, 9), b.p034, np.nan)
b["부모소득"] = pd.Series(inc, index=b.index).fillna(np.nanmean(inc))

def wols(y, X, w):
    X, y, w = np.asarray(X, float), np.asarray(y, float), np.asarray(w, float)
    W = w / w.mean(); A = X.T @ (X * W[:, None])
    beta = np.linalg.solve(A, X.T @ (y * W)); e = y - X @ beta
    inv = np.linalg.inv(A); Z = X * (W * e)[:, None]; n, k = X.shape
    V = inv @ (Z.T @ Z) @ inv * n / (n - k)
    return beta, np.sqrt(np.diag(V))

rows = []
for m, s in b.groupby("계열"):
    w = s[s.a122 > 0]
    if len(w) < 60: continue
    tot = s.wt.sum()
    rec = {"계열": m, "표본": len(s), "임금표본": len(w),
           "부산잔류%": s.loc[s.지역 == 2, "wt"].sum() / tot * 100,
           "수도권%": s.loc[s.지역.isin(CAP), "wt"].sum() / tot * 100}
    rec["부산이탈%"] = 100 - rec["부산잔류%"]
    for lab, sub in [("잔류자_월소득", w[w.지역 == 2]), ("이탈자_월소득", w[w.지역 != 2])]:
        rec[lab] = (sub.a122 * sub.wt).sum() / sub.wt.sum()
    # 임금 회귀 (연도 더미 포함)
    X = pd.DataFrame({"const": 1.0, "이탈": w.이탈, "여성": w.여성, "사립": w.사립,
                      "평점": w.평점, "어학연수": w.어학연수, "부모소득": w.부모소득}, index=w.index)
    for y_ in sorted(w.코호트.unique())[1:]:
        X[f"y{y_}"] = (w.코호트 == y_).astype(float)
    for c in ["2~3년제", "교육대"]:
        v = (w.school == {"2~3년제": 1, "교육대": 3}[c]).astype(float)
        if v.nunique() > 1: X[c] = v
    X = X[[c for c in X.columns if c == "const" or X[c].nunique() > 1]]
    beta, se = wols(np.log(w.a122.astype(float)), X, w.wt)
    i = list(X.columns).index("이탈")
    rec["임금프리미엄%"] = (np.exp(beta[i]) - 1) * 100
    rec["t"] = beta[i] / se[i]
    rows.append(rec)

r = pd.DataFrame(rows).sort_values("부산이탈%", ascending=False)
r["유의"] = r.t.abs() >= 1.96
r.round(2).to_csv("out/GOMS13_계열별.csv", index=False, encoding="utf-8-sig")
pd.set_option("display.width", 220)
print(f"부산 소재 대학 졸업자 {len(b):,}명 (2016~2019 4개 코호트, 첫 일자리 지역 확인분)\n")
print(r[["계열","표본","임금표본","부산이탈%","수도권%","잔류자_월소득","이탈자_월소득","임금프리미엄%","t","유의"]]
      .to_string(index=False, float_format=lambda v: f"{v:7.1f}"))
