"""국가데이터처 국내인구이동통계 연간 통계표 → 부산 유출 tidy 테이블."""
import glob, os, re
import pandas as pd

RAW = "raw_migration"
BUSAN = "부산"

def sheets(path):
    eng = "xlrd" if path.endswith(".xls") else "openpyxl"
    return pd.read_excel(path, sheet_name=None, header=None, engine=eng)

def find_sheet(bk, *keys):
    for name in bk:
        flat = name.replace(" ", "")
        if all(k.replace(" ", "") in flat for k in keys):
            return bk[name]
    return None

def busan_col(df, hdr_row):
    for j, v in enumerate(df.iloc[hdr_row]):
        if isinstance(v, str) and v.replace(" ", "").startswith(BUSAN):
            return j
    raise KeyError("부산 컬럼 없음")

def hdr_row_of(df):
    for i in range(min(8, len(df))):
        if any(isinstance(v, str) and v.replace(" ", "").startswith(BUSAN) for v in df.iloc[i]):
            return i
    raise KeyError("헤더행 없음")

age_rows, reason_rows, dest_rows = [], [], []
for path in sorted(glob.glob(f"{RAW}/20*.xls*")):
    year = int(os.path.basename(path)[:4])
    bk = sheets(path)

    # ── 연령별 순이동 (남녀전체 블록만)
    df = find_sheet(bk, "연령별", "순이동")
    h = hdr_row_of(df); bc = busan_col(df, h)
    started = False
    for i in range(h + 1, len(df)):
        lab0 = str(df.iat[i, 0]) if pd.notna(df.iat[i, 0]) else ""
        lab1 = str(df.iat[i, 1]) if pd.notna(df.iat[i, 1]) else ""
        if "남녀전체" in lab0: started = True; continue
        if started and lab0.strip() in ("남자", "여자"): break
        if not started or not lab1.strip(): continue
        v = pd.to_numeric(df.iat[i, bc], errors="coerce")
        if pd.notna(v):
            age_rows.append({"연도": year, "연령": lab1.strip().replace(" ", ""), "순이동": int(v)})

    # ── 전입사유별 순이동
    df = find_sheet(bk, "전입사유")
    if df is not None:
        h = hdr_row_of(df); bc = busan_col(df, h); inblk = False
        for i in range(h + 1, len(df)):
            lab0 = str(df.iat[i, 0]) if pd.notna(df.iat[i, 0]) else ""
            lab1 = str(df.iat[i, 1]) if pd.notna(df.iat[i, 1]) else ""
            if lab0.strip().replace(" ", "") == "순이동": inblk = True; continue
            if inblk and lab0.strip() and not lab1.strip(): break
            if not inblk or not lab1.strip(): continue
            v = pd.to_numeric(df.iat[i, bc], errors="coerce")
            if pd.notna(v):
                reason_rows.append({"연도": year, "사유": lab1.strip(), "순이동": int(v)})

    # ── 전출지별 순이동: 행=전입지 '부산', 열=전출지
    df = find_sheet(bk, "순이동", "전입출")
    if df is None: df = find_sheet(bk, "전입출지별(순이동)")
    if df is not None:
        h = hdr_row_of(df)
        hdr = [str(v).replace(" ", "") if pd.notna(v) else "" for v in df.iloc[h]]
        ri = next(i for i in range(h + 1, len(df))
                  if str(df.iat[i, 1]).replace(" ", "") == BUSAN)
        for j, name in enumerate(hdr):
            if j < 2 or not name: continue
            v = pd.to_numeric(df.iat[ri, j], errors="coerce")
            if pd.notna(v):
                dest_rows.append({"연도": year, "상대시도": name, "부산기준_순이동": int(v)})

os.makedirs("out", exist_ok=True)
for rows, fn in ((age_rows, "부산_연령별_순이동.csv"),
                 (reason_rows, "부산_전입사유별_순이동.csv"),
                 (dest_rows, "부산_상대시도별_순이동.csv")):
    pd.DataFrame(rows).to_csv(f"out/{fn}", index=False, encoding="utf-8-sig")
    print(f"out/{fn}  {len(rows)}행")

# ── 부록: 「최근 20년간 수도권 인구이동」 청년층/중장년층 시계열
sp = f"{RAW}/수도권20년.xlsx"
if os.path.exists(sp):
    df = pd.read_excel(sp, sheet_name="9.전출 시도별 수도권 순이동(청년층,중장년층)",
                       header=None)
    hdr = next(i for i in range(6)
               if any(isinstance(v, str) and v.replace(" ", "") == "연도" for v in df.iloc[i]))
    cols = [str(v).replace(" ", "") if pd.notna(v) else "" for v in df.iloc[hdr]]
    bc = cols.index("부산"); kc = cols.index("수도권(계)")
    rows, grp = [], None
    for i in range(hdr + 1, len(df)):
        a = str(df.iat[i, 0]) if pd.notna(df.iat[i, 0]) else ""
        b = str(df.iat[i, 1]) if pd.notna(df.iat[i, 1]) else ""
        tag = (a + b).replace(" ", "")
        if "청년층" in tag: grp = "청년층"; continue
        if "중장년" in tag: grp = "중장년층"; continue
        y = pd.to_numeric(a, errors="coerce")
        v = pd.to_numeric(df.iat[i, bc], errors="coerce")
        if pd.notna(y) and pd.notna(v) and grp:
            rows.append({"연령층": grp, "연도": int(y), "부산→수도권_순유출": int(v),
                         "전국비수도권→수도권": int(pd.to_numeric(df.iat[i, kc], errors="coerce"))})
    pd.DataFrame(rows).to_csv("out/부산_수도권순유출_20년.csv", index=False, encoding="utf-8-sig")
    print(f"out/부산_수도권순유출_20년.csv  {len(rows)}행")
