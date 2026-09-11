"""GOMS — 부산 잔류 vs 이탈 임금 격차에서 '지역 효과'와 '선발 효과' 분리.

4차에서 7개 계열 전부 이탈자 임금이 높았으나 누가 떠났는지를 통제하지 않았다.
개인 특성을 단계적으로 넣어 격차가 얼마나 남는지 본다.
statsmodels가 없어 가중 OLS + HC1 로버스트 표준오차를 numpy로 직접 계산한다.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

MAJOR = {1:"인문",2:"사회",3:"교육",4:"공학",5:"자연",6:"의약",7:"예체능"}
SCALE = {1:4.0, 2:4.3, 3:4.5}
CAP = {1, 5, 8}
COLS = ["g191wt","g191area","g191sex","g191school","g191found","g191majorcat","g191graduy",
        "g191f073","g191f074","g191p034","g191i001","g191a122","g191d020","g191a014"]

d = pd.read_stata("data/goms/GP19__2020.DTA", columns=COLS, convert_categoricals=False)
b = d[d.g191area == 2].copy()
ok = lambda s: s.between(1, 17)
b["지역"] = b.g191d020.where(ok(b.g191d020), b.g191a014.where(ok(b.g191a014)))
b = b[ok(b["지역"]) & (b.g191a122 > 0)].copy()

b["이탈"] = (b.지역 != 2).astype(float)
b["lnw"] = np.log(b.g191a122.astype(float))
b["여성"] = (b.g191sex == 2).astype(float)
b["사립"] = (b.g191found == 3).astype(float)
b["졸업2019"] = (b.g191graduy == 2019).astype(float)
b["어학연수"] = (b.g191i001 == 1).astype(float)
gpa = np.where(b.g191f074 > 0, b.g191f074 / b.g191f073.map(SCALE).astype(float) * 100, np.nan)
b["평점"] = pd.Series(gpa, index=b.index).fillna(np.nanmean(gpa))
b["평점결측"] = (b.g191f074 <= 0).astype(float)
inc = np.where(b.g191p034.between(2, 9), b.g191p034, np.nan)
b["부모소득"] = pd.Series(inc, index=b.index).fillna(np.nanmean(inc))
b["부모소득결측"] = (~b.g191p034.between(2, 9)).astype(float)

def dmy(s, mp, drop):
    return pd.DataFrame({v: (s == k).astype(float) for k, v in mp.items() if v != drop}, index=s.index)

maj = dmy(b.g191majorcat, MAJOR, "사회")
sch = dmy(b.g191school, {1:"2~3년제", 2:"4년제", 3:"교육대"}, "4년제")
sch = sch.loc[:, sch.sum() > 0]          # 표본에 없는 범주 제거(특이행렬 방지)
maj = maj.loc[:, maj.sum() > 0]

def wols(y, X, w):
    X, y, w = np.asarray(X, float), np.asarray(y, float), np.asarray(w, float)
    W = w / w.mean()
    A = X.T @ (X * W[:, None])
    beta = np.linalg.solve(A, X.T @ (y * W))
    e = y - X @ beta
    inv = np.linalg.inv(A)
    Z = X * (W * e)[:, None]
    n, k = X.shape
    V = inv @ (Z.T @ Z) @ inv * n / (n - k)
    r2 = 1 - np.sum(W * e ** 2) / np.sum(W * (y - np.average(y, weights=W)) ** 2)
    return beta, np.sqrt(np.diag(V)), r2

BASE = ["여성", "사립", "졸업2019"]
EXTRA = ["평점", "평점결측", "어학연수", "부모소득", "부모소득결측"]
SPECS = [
    ("M1  통제 없음", []),
    ("M2  +성별·설립·졸업년·학교유형", BASE + list(sch.columns)),
    ("M3  +전공계열", BASE + list(sch.columns) + list(maj.columns)),
    ("M4  +졸업평점·어학연수·부모소득", BASE + list(sch.columns) + list(maj.columns) + EXTRA),
]
pool = pd.concat([b[BASE + EXTRA], sch, maj], axis=1)
rows = []
for name, ctrl in SPECS:
    X = pd.concat([pd.Series(1.0, index=b.index, name="const"), b["이탈"].rename("이탈"),
                   pool[ctrl]], axis=1)
    X = X.loc[:, ~X.columns.duplicated()]
    keep = [c for c in X.columns if c == "const" or X[c].nunique() > 1]   # 상수열 제거
    X = X[keep]
    beta, se, r2 = wols(b.lnw, X, b.g191wt)
    i = list(X.columns).index("이탈")
    rows.append({"모형": name, "이탈 계수": beta[i], "s.e.": se[i], "t": beta[i] / se[i],
                 "임금차이%": (np.exp(beta[i]) - 1) * 100, "R²": r2, "변수": X.shape[1]})
r = pd.DataFrame(rows)
print(f"표본 {len(b):,}명 · 이탈 {int(b.이탈.sum()):,}명 / 잔류 {int((1-b.이탈).sum()):,}명\n")
print("■ '부산을 떠났다'가 로그 월소득에 주는 효과 (가중 OLS · HC1)")
print(r.to_string(index=False, float_format=lambda v: f"{v:8.3f}"))
r.round(4).to_csv("out/GOMS_임금회귀.csv", index=False, encoding="utf-8-sig")

# 전공계열별로도 (M4 사양, 계열 더미 제외)
print("\n■ 전공계열별 이탈 효과 (M4 통제, 계열 내 추정)")
sub = []
for m, g in b.groupby(b.g191majorcat.map(MAJOR)):
    if len(g) < 60: continue
    P = pd.concat([g[BASE + EXTRA], sch.loc[g.index]], axis=1)
    P = P.loc[:, P.nunique() > 1]
    X = pd.concat([pd.Series(1.0, index=g.index, name="const"), g["이탈"].rename("이탈"), P], axis=1)
    try:
        bt, s_, _ = wols(g.lnw, X, g.g191wt)
    except np.linalg.LinAlgError:
        continue
    i = list(X.columns).index("이탈")
    sub.append({"전공": m, "n": len(g), "이탈 계수": bt[i], "t": bt[i] / s_[i],
                "임금차이%": (np.exp(bt[i]) - 1) * 100})
print(pd.DataFrame(sub).sort_values("임금차이%", ascending=False)
      .to_string(index=False, float_format=lambda v: f"{v:8.2f}"))
