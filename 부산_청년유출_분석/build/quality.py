# -*- coding: utf-8 -*-
"""데이터 품질 점검 — 표본 수 · 이상치 · 관계 주장의 견고성

세 가지를 점검한다.
  ① 표본 수   비율을 몇 자리까지 말해도 되는가 (95% 오차범위)
  ② 이상치    극단값이 결론을 바꾸는가 (처리 방식별 재계산)
  ③ 관계      상관 주장이 점 하나에 기대고 있는가 (하나씩 빼보기)

출력 out/품질_표본점검.csv · out/품질_이상치_임금.csv · out/품질_상관점검.csv
"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, math

# 표본 수 기준 — 95% 신뢰구간 반폭이 얼마나 되는지로 정한다
MIN_SHOW   = 30    # 이보다 작으면 비율을 아예 말하지 않는다
MIN_TRUST  = 100   # 이보다 작으면 「표본 적음」을 붙이고 소수점을 쓰지 않는다

def moe(p, n):
    """비율 p(%)의 95% 오차범위(±%p). n이 0이면 NaN."""
    if not n or n <= 0: return np.nan
    q = p / 100
    return 1.96 * math.sqrt(max(q * (1 - q), 0) / n) * 100

def band(n):
    if n < MIN_SHOW:  return "표시 금지"
    if n < MIN_TRUST: return "표본 적음"
    return "사용 가능"

# ────────────────────────────────────────────────────────────
# ① 표본 수 — 대시보드가 비율을 보여주는 모든 행
# ────────────────────────────────────────────────────────────
rows = []
SRC = [
    ("②번 칸 · 직업별 요구학력", "out/공고_학력_직종별.csv", "공고수", "대졸이상"),
    ("④번 칸 · 업종별",          "out/공고_산업별_질.csv",   "공고수", "대졸이상률"),
    ("④번 칸 · 구·군별",         "out/공고_고용형태_구별.csv","공고수", "대졸이상률"),
]
for 칸, path, ncol, pcol in SRC:
    t = pd.read_csv(path, index_col=0)
    for k, r in t.iterrows():
        n = int(r[ncol]); p = float(r.get(pcol, np.nan))
        rows.append({"칸": 칸, "항목": k, "표본": n, "비율%": round(p, 1),
                     "오차범위±%p": round(moe(p, n), 1), "판정": band(n)})

# 계열별 GOMS 표본 (이탈률·소득)
d = pd.read_csv("out/대시보드_13계열.csv")
for _, r in d.iterrows():
    n = 0 if pd.isna(r.표본) else int(r.표본)
    p = np.nan if pd.isna(r["부산이탈%"]) else float(r["부산이탈%"])
    rows.append({"칸": "⑤번 칸 · 계열별 이탈률", "항목": r.계열, "표본": n,
                 "비율%": round(p, 1) if p == p else np.nan,
                 "오차범위±%p": round(moe(p, n), 1) if p == p else np.nan,
                 "판정": band(n)})
q = pd.DataFrame(rows)
q.to_csv("out/품질_표본점검.csv", index=False, encoding="utf-8-sig")

# ────────────────────────────────────────────────────────────
# ② 이상치 — 소득 극단값이 임금 격차를 바꾸는가
# ────────────────────────────────────────────────────────────
g = pd.read_pickle("data/goms/pool/goms_pooled.pkl")
ok = lambda s: s.between(1, 17); CAP = {1, 5, 8}
b = g[g.area == 2].copy()
b["지역"] = b.d020.where(ok(b.d020), b.a014.where(ok(b.a014)))
b = b[ok(b["지역"])].copy()
b["a122"] = pd.to_numeric(b.a122, errors="coerce")
b = b[b.a122 > 0]                                   # -1 은 무응답 코드
wm = lambda t, c: (t[c] * t.wt).sum() / t.wt.sum()
lo, hi = b.a122.quantile([.01, .99])

def gapof(t):
    r, c = t[t.지역 == 2], t[t.지역.isin(CAP)]
    return wm(r, "a122"), wm(c, "a122"), len(r), len(c)

cases = [("기준 — 무응답(-1)만 제외", b),
         ("월 1,000만원 초과 제외",    b[b.a122 <= 1000]),
         ("월 500만원 초과 제외",      b[b.a122 <= 500]),
         (f"상하위 1% 절단 ({lo:.0f}~{hi:.0f})", b[b.a122.between(lo, hi)]),
         ("상하위 1% 윈저화",          b.assign(a122=b.a122.clip(lo, hi)))]
out = []
for lab, t in cases:
    a, e, nr, nc = gapof(t)
    out.append({"처리": lab, "부산 잔류": round(a, 1), "수도권 이탈": round(e, 1),
                "격차": round(e - a, 1), "n_잔류": nr, "n_이탈": nc})
r0, c0 = b[b.지역 == 2].a122, b[b.지역.isin(CAP)].a122
out.append({"처리": "중앙값 기준(가중 아님)", "부산 잔류": r0.median(),
            "수도권 이탈": c0.median(), "격차": c0.median() - r0.median(),
            "n_잔류": len(r0), "n_이탈": len(c0)})
w = pd.DataFrame(out)
w.to_csv("out/품질_이상치_임금.csv", index=False, encoding="utf-8-sig")

# ────────────────────────────────────────────────────────────
# ③ 관계 — 점 하나를 빼면 상관이 뒤집히는가
# ────────────────────────────────────────────────────────────
def robust_corr(x, y, labels, name):
    x, y = pd.Series(x).astype(float), pd.Series(y).astype(float)
    n = len(x)
    r  = x.corr(y)
    rs = x.rank().corr(y.rank())
    t  = r * math.sqrt((n - 2) / (1 - r * r)) if abs(r) < 1 else np.inf
    loo = {labels[i]: x.drop(x.index[i]).corr(y.drop(y.index[i])) for i in range(n)}
    lo_r, hi_r = min(loo.values()), max(loo.values())
    worst = min(loo, key=lambda k: abs(loo[k] - r) * -1)   # r 에서 가장 멀어지는 점
    flip  = (lo_r < 0 < hi_r)
    return {"주장": name, "n": n, "Pearson": round(r, 3), "Spearman": round(rs, 3),
            "t": round(t, 2), "하나씩빼기_최소": round(lo_r, 3),
            "하나씩빼기_최대": round(hi_r, 3), "영향_최대_항목": worst,
            "부호뒤집힘": flip,
            "판정": "쓸 수 없음" if (flip or abs(t) < 2) else "조건부 사용"}

checks = []
i = pd.read_csv("out/공고_산업별_질.csv", index_col=0)
i = i[~i.index.isin(["미상", "기타"])]
checks.append(robust_corr(i.대졸이상률, i.정규직률, list(i.index),
                          "업종: 대졸 요구율 ~ 정규직률"))
e = d.dropna(subset=["부산이탈%"])
checks.append(robust_corr(e["부산이탈%"], e.구인배수, list(e.계열),
                          "계열: 떠난 비율 ~ 자리 여유"))
v = pd.read_csv("out/GOMS_검증_이탈률vs구인배수.csv")
checks.append(robust_corr(v["부산이탈%"], v.향하는직종_구인배수, list(v.전공),
                          "7대계열: 떠난 비율 ~ 자리 여유"))
gu = pd.read_csv("out/공고_고용형태_구별.csv", index_col=0)
gu = gu[gu.index != "미상"]
checks.append(robust_corr(gu.대졸이상률, gu.정규직률, list(gu.index),
                          "구·군: 대졸 요구율 ~ 정규직률"))
c = pd.DataFrame(checks)
c.to_csv("out/품질_상관점검.csv", index=False, encoding="utf-8-sig")

# ────────────────────────────────────────────────────────────
print("■ ① 표본 점검 — 판정별 개수");  print(q.판정.value_counts().to_string())
print("\n주의가 필요한 행:")
print(q[q.판정 != "사용 가능"].to_string(index=False))
print("\n■ ② 이상치 — 임금 격차가 바뀌는가"); print(w.to_string(index=False))
print("\n■ ③ 관계 — 점 하나에 기대고 있는가")
print(c[["주장","n","Pearson","Spearman","t","하나씩빼기_최소","하나씩빼기_최대","부호뒤집힘","판정"]].to_string(index=False))
