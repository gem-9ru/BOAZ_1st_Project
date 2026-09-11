"""③ 빈일자리 · ④ 직능수준별 미충원 — '역량 부족이냐 수요 부족이냐'."""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd

def tidy(path, keys, sheet="데이터"):
    d = pd.read_excel(path, sheet_name=sheet, header=None)
    per = [str(x).strip() for x in d.iloc[0]]
    head = [str(x).strip() for x in d.iloc[1]]
    cols = [h if i < len(keys) else f"{per[i]}|{h}" for i, h in enumerate(head)]
    d = d.iloc[2:].copy(); d.columns = cols
    for k in keys:
        d[k] = d[k].astype(str).str.replace(r"\s+", "", regex=True).replace("nan", pd.NA).ffill()
    return d

# ── ③ 시도·산업별 빈일자리
v = tidy("data/산업임금/시도_산업별_빈일자리.xlsx", ["지역별(1)", "지역별(2)", "산업분류(1)"])
col = [c for c in v.columns if "2025|빈일자리율" in c]
cnt = [c for c in v.columns if "2025|빈일자리_" in c]
v["빈일자리율"] = pd.to_numeric(v[col[0]], errors="coerce")
v["빈일자리수"] = pd.to_numeric(v[cnt[0]], errors="coerce")
KNOW = ["J정보통신업(58~63)", "K금융및보험업(64~66)", "M전문,과학및기술서비스업(70~73)"]
MET = ["전국", "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "경기도"]
a = v[v["산업분류(1)"] == "전체"].groupby("지역별(1)")["빈일자리율"].first()
print("■ ③ 시도별 빈일자리율 (2025 연간, %)")
print(a.reindex([m for m in MET if m in a.index]).round(2).to_string())

print("\n■ ③ 지식산업 빈일자리율 — 부산 vs 서울")
k = v[v["산업분류(1)"].isin([s for s in v["산업분류(1)"].unique() if any(x in s for x in ["정보통신", "금융및보험", "전문,과학"])])]
p = k.pivot_table(index="산업분류(1)", columns="지역별(1)", values="빈일자리율", aggfunc="first")
print(p[[c for c in ["전국", "서울특별시", "부산광역시"] if c in p.columns]].round(2).to_string())

# ── ④ 직능수준별 미충원
m = tidy("data/산업임금/직종별_직능수준별_미충원.xlsx", ["시도별(17개)", "규모별", "직종별"])
lv = {c: c.split("|")[1].split("_")[0] for c in m.columns if "미충원인원" in c}
for c in lv: m[c] = pd.to_numeric(m[c], errors="coerce")
m = m.rename(columns=lv)
L = list(lv.values())
b = m[(m["시도별(17개)"] == "부산광역시") & (m.직종별 != "전직종")].groupby("직종별")[L].sum()
n = m[(m["시도별(17개)"] == "전국") & (m.직종별 != "전직종")].groupby("직종별")[L].sum()
print("\n■ ④ 부산 직종별·직능수준별 미충원인원 (2024 상반기, 명)")
b["계"] = b.sum(axis=1)
b["고숙련(3+4수준)"] = b["직능3수준"] + b["직능4수준"]
print(b.astype(int).to_string())
tot_b, tot_n = b[L].sum(), n[L].sum()
print("\n■ ④ 미충원의 숙련 구성 — 부산 vs 전국 (%)")
print(pd.DataFrame({"부산%": tot_b / tot_b.sum() * 100, "전국%": tot_n / tot_n.sum() * 100}).round(1).to_string())
