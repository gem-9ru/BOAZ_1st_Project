"""시도별 20대 순유출을 인구로 나눈다 — '부산 특유'라는 주장의 전제.

인구: 행정안전부 주민등록 연령별 인구현황 2025-12 (20-29세)
이동: 국가데이터처 국내인구이동통계 2025 연간
  → 시점이 일치한다. 2026-07 전남광주통합특별시 출범 이전 시점이라 광주·전남도 분리된다.
"""
import pandas as pd

POP2029 = {  # 행정안전부 주민등록 연령별 인구현황 2025-12 (이동 데이터와 동일 시점)
    "서울":1254885,"부산":338697,"대구":253449,"인천":338166,"광주":170562,"대전":187702,
    "울산":110774,"세종":36463,"경기":1557604,"강원":148129,"충북":166917,"충남":212177,
    "전북":172187,"전남":159467,"경북":220603,"경남":288774,"제주":65686}

df = pd.read_excel("data/인구이동/2025년.xlsx", sheet_name="5. 시도 및 연령별 순이동", header=None)
hdr = [str(v).strip() if pd.notna(v) else "" for v in df.iloc[2]]
rows, started = [], False
for i in range(3, len(df)):
    l0 = str(df.iat[i, 0]) if pd.notna(df.iat[i, 0]) else ""
    l1 = str(df.iat[i, 1]) if pd.notna(df.iat[i, 1]) else ""
    if "남녀전체" in l0: started = True; continue
    if started and l0.strip() in ("남자", "여자"): break
    if not started or not l1.strip(): continue
    rec = {"연령": l1.strip().replace(" ", "")}
    for j, n in enumerate(hdr):
        if j >= 2 and n:
            v = pd.to_numeric(df.iat[i, j], errors="coerce")
            if pd.notna(v): rec[n] = int(v)
    rows.append(rec)
t = pd.DataFrame(rows).set_index("연령")

out = []
for sido, pop in POP2029.items():
    if sido not in t.columns: continue
    a, b = t.loc["20-24세", sido], t.loc["25-29세", sido]
    out.append({"시도": sido, "20대인구": pop, "20-24세": a, "25-29세": b,
                "20대순이동": a + b,
                "25-29순유출률(‰)": -b / pop * 1000,
                "20대순유출률(‰)": -(a + b) / pop * 1000,
                "전환폭": b - a})
r = pd.DataFrame(out).sort_values("25-29순유출률(‰)", ascending=False)
r.round(2).to_csv("out/시도별_청년순유출률.csv", index=False, encoding="utf-8-sig")
pd.set_option("display.width", 200)
print("■ 시도별 청년 순유출률 (2025 순이동 ÷ 20대 인구, ‰ = 1천명당)")
print("  ※ 인구·이동 모두 2025년 기준 · 17개 시도 전체\n")
print(r.to_string(index=False, float_format=lambda v: f"{v:9.2f}"))
