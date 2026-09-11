"""KOSIS 2표 파싱 — 시도·산업·규모별 임금 / 시도·산업·종사자규모별 사업체·종사자."""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd

def tidy(path, keys, vals):
    d = pd.read_excel(path, sheet_name="데이터", header=None)
    head = [str(x).strip() if pd.notna(x) else "" for x in d.iloc[1]]
    d = d.iloc[2:].copy()
    d.columns = head
    for k in keys:                      # 병합셀 → 앞값 채우기
        d[k] = d[k].astype(str).str.replace(r"\s+", "", regex=True).replace("nan", pd.NA).ffill()
    for v in vals:
        d[v] = pd.to_numeric(d[v], errors="coerce")
    return d[keys + vals].dropna(subset=vals, how="all")

wage = tidy("data/산업임금/시도_산업_규모별_임금.xlsx",
            ["지역별", "산업별", "규모별"],
            ["상용월급여액 (원)", "상용총근로시간 (시간)"])
wage.columns = ["시도", "산업", "규모", "월급여액", "총근로시간"]
wage.to_csv("out/KOSIS_시도산업규모별_임금.csv", index=False, encoding="utf-8-sig")

est = tidy("data/산업임금/시도_산업_종사자규모별_사업체.xlsx",
           ["행정구역별", "산업별", "종사자규모별"],
           ["사업체수 (개)", "종사자수 (명)"])
est.columns = ["시도", "산업", "규모", "사업체수", "종사자수"]
est.to_csv("out/KOSIS_시도산업규모별_사업체.csv", index=False, encoding="utf-8-sig")

print(f"임금  {len(wage):,}행 · 시도 {wage.시도.nunique()} · 산업 {wage.산업.nunique()} · 규모 {wage.규모.nunique()}")
print(f"사업체 {len(est):,}행 · 시도 {est.시도.nunique()} · 산업 {est.산업.nunique()} · 규모 {est.규모.nunique()}")
print("\n규모 구분:"); print(" 임금 :", list(wage.규모.unique()))
print(" 사업체:", list(est.규모.unique()))
