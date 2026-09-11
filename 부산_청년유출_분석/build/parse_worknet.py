"""고용24(워크넷) 월간 구인구직통계 → 부산 KECO 직업중분류 tidy 테이블.

각 시트에 표가 2개씩 들어 있다.
  4-1/5-1/6-1  구인구직을 등록한 지방노동관서 지역 기준
  4-2          구인업체 소재 지역 기준      ← 수요는 이걸 쓴다
  5-2/6-2      구직자 거주 지역 기준        ← 공급은 이걸 쓴다
시도 컬럼은 월마다 순서가 바뀌므로(2026-07 전남광주통합특별시 신설) 반드시 이름으로 찾는다.
"""
import glob, os, re
import openpyxl, pandas as pd

SHEETS = {"구인_고용직업중분류": "신규구인인원",
          "구직_고용직업중분류": "신규구직건수",
          "취업_고용직업중분류": "취업건수"}
REGIONS = ["전 체", "부산광역시", "서울특별시", "경기도", "울산광역시", "경상남도"]

def parse_sheet(ws):
    rows = list(ws.iter_rows(values_only=True))
    txt = [" ".join(str(c).strip() for c in r if c) if r else "" for r in rows]
    # 표 시작 = 'N-M.' 캡션, 바로 아래 ※ 가 지역기준
    starts = [i for i, t in enumerate(txt) if re.match(r"^[456]-[12]\.", t)]
    frames = []
    for k, s in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(rows)
        basis = next((txt[i].lstrip("※ ").strip() for i in range(s + 1, min(s + 3, end))
                      if txt[i].startswith("※")), "")
        hi = next(i for i in range(s, end)
                  if rows[i] and any(str(c).strip() == "부산광역시" for c in rows[i] if c))
        hdr = [str(c).strip() if c else "" for c in rows[hi]]
        ci = {n: j for j, n in enumerate(hdr) if n}
        out, cur = [], None
        for r in rows[hi + 1:end]:
            if not r: continue
            big, mid = r[ci["직업 대분류"]], r[ci["직업 중분류"]]
            if big and str(big).strip(): cur = str(big).strip()
            if not mid or not str(mid).strip() or cur is None: continue
            rec = {"표": txt[s].split(".")[0], "지역기준": basis,
                   "대분류": cur, "중분류": str(mid).strip()}
            for reg in REGIONS:
                try: rec[reg] = int(r[ci[reg]])
                except (KeyError, TypeError, ValueError): rec[reg] = None
            out.append(rec)
        frames.append(pd.DataFrame(out))
    return pd.concat(frames, ignore_index=True)

frames = []
for f in sorted(glob.glob("data/고용24/*.xlsx")):
    ym = os.path.basename(f)[:7]
    wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
    for sheet, metric in SHEETS.items():
        d = parse_sheet(wb[sheet])
        d.insert(0, "연월", ym); d.insert(1, "지표", metric)
        frames.append(d)
    wb.close()

df = pd.concat(frames, ignore_index=True)
df["대분류코드"] = df["대분류"].str.extract(r"^(\d)")
df["대분류명"] = df["대분류"].str.replace(r"^\d", "", regex=True)
df = df.rename(columns={"전 체": "전국", "부산광역시": "부산", "서울특별시": "서울",
                        "경기도": "경기", "울산광역시": "울산", "경상남도": "경남"})
df = df[["연월", "지표", "표", "지역기준", "대분류코드", "대분류명", "중분류",
         "전국", "부산", "서울", "경기", "울산", "경남"]]
df.to_csv("out/워크넷_부산_월별_직종중분류.csv", index=False, encoding="utf-8-sig")

print(f"행 {len(df):,} · 월 {df.연월.nunique()}개 ({df.연월.min()}~{df.연월.max()}) "
      f"· 중분류 {df.중분류.nunique()}종")
print("\n[표별 지역기준]")
print(df.groupby(["지표", "표", "지역기준"]).size().to_string())
print("\n[검산] 표별 부산 12개월 합")
print(df.groupby(["지표", "표"])["부산"].sum().to_string())
