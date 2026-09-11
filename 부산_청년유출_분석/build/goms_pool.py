"""GOMS 2016~2019 4개 코호트 풀링 — 접두사만 다르고 변수명 뒷부분은 동일하다."""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd

SUF = ["wt","area","sex","school","found","majorcat","graduy","dpmt","dpmt_n",
       "f073","f074","p034","i001","a122","a144","d020","a014","p024","f006"]
YR = {"2016":"g161","2017":"g171","2018":"g181","2019":"g191"}

frames = []
for yr, pre in YR.items():
    cols = [pre + s for s in SUF]
    try:
        d = pd.read_stata(f"data/goms/pool/{yr}.DTA", columns=cols, convert_categoricals=False)
    except ValueError as e:                       # 없는 변수는 빼고 재시도
        avail = set(pd.read_stata(f"data/goms/pool/{yr}.DTA", chunksize=1,
                                  convert_categoricals=False).__next__().columns)
        cols = [c for c in cols if c in avail]
        d = pd.read_stata(f"data/goms/pool/{yr}.DTA", columns=cols, convert_categoricals=False)
        print(f"  {yr} 누락 변수: {[s for s in SUF if pre+s not in avail]}")
    d.columns = [c.replace(pre, "", 1) for c in d.columns]
    d["코호트"] = int(yr)
    frames.append(d)
    print(f"  {yr}: {len(d):,}행 · 컬럼 {len(d.columns)}")

g = pd.concat(frames, ignore_index=True)
g.to_parquet("data/goms/pool/goms_pooled.parquet") if False else g.to_pickle("data/goms/pool/goms_pooled.pkl")
print(f"\n풀링 완료 {len(g):,}행")
b = g[g.area == 2]
print(f"부산 소재 대학 졸업자 {len(b):,}명  (연도별 {b.코호트.value_counts().sort_index().to_dict()})")
