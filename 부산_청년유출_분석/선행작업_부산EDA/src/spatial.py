# -*- coding: utf-8 -*-
"""공간 미스매치 — 청년이 사는 곳 vs 청년 일자리가 있는 곳.

입력  data/생활인구_행정동_연령.xlsx   Big-데이터웨이브 PD_LP00002 (통신사 기지국 신호)
      data/생활인구_행정동_성별.xlsx   Big-데이터웨이브 PD_LP00001
      data/산업단지_입주기업.csv       Big-데이터웨이브 15088731 (고용인원 포함)
      ../크롤링/분석/부산_공고_분석용.csv
출력  out/공간_시군구.csv · out/공간_행정동.csv

[기준 시점]  공고 2026-09-07 단면 · 생활인구 2025년 12개월 평균 (팀 결정)
생활인구 원본은 2023.01~2025.12 36개월이라 2025 만 잘라 계절성을 지운다.
9개월 시차는 보고서에 명시한다 — 같은 시점 데이터가 없다.

[지표]
    청년유입비 = 20대 직장인구 / 20대 주거인구
        > 1  청년을 «일하러 오게» 만드는 지역
        < 1  청년이 살지만 다른 데로 일하러 나가는 지역
생활인구의 직장지는 «평일 09~18시 30% 이상 체류», 우리 공고의 시군구는 사업장
소재지다. 서로 다른 방식으로 측정한 «일하는 곳» 이라 상관이 맞으면 교차검증이 된다.
"""
import csv, statistics
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "out"
JOBS = BASE.parent / "크롤링" / "분석" / "부산_공고_분석용.csv"
csv.field_size_limit(10 ** 9)
YEAR = "2025"
HI = {"대학교졸", "석사이상"}
NEW = {"무관", "신입"}
SGG = ["중구", "서구", "동구", "영도구", "부산진구", "동래구", "남구", "북구", "해운대구",
       "사하구", "금정구", "강서구", "연제구", "수영구", "사상구", "기장군"]


def corr(a, b):
    ma, mb = statistics.mean(a), statistics.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** .5
    return num / den if den else 0


def main():
    import pandas as pd
    OUT.mkdir(exist_ok=True)

    def 생활(파일, 축):
        d = pd.read_excel(BASE / "data" / 파일)
        d["기준년월"] = d["기준년월"].astype(str)
        d = d[d["기준년월"].str.startswith(YEAR)].copy()
        d["시군구"] = d["행정동명"].str.split().str[0]
        미상 = sorted(set(d["시군구"]) - set(SGG))
        if 미상:
            print(f"  [주의] 시군구 미매칭: {미상}")
        n_month = d["기준년월"].nunique()
        # 12개월 평균 → 행정동·축 단위
        return d.groupby(["시군구", "행정동명", 축])[
            ["평균주거인구수", "평균직장인구수", "평균방문인구수"]].mean().reset_index(), n_month

    age, nm = 생활("생활인구_행정동_연령.xlsx", "나이대")
    sex, _ = 생활("생활인구_행정동_성별.xlsx", "성별")
    print(f"생활인구 {YEAR} {nm}개월 평균 · 행정동 {age['행정동명'].nunique()}개")

    # 산업단지 — 구군별 입주업체·고용인원
    단지 = {}
    for r in csv.DictReader((BASE / "data" / "산업단지_입주기업.csv").open(encoding="utf-8-sig")):
        g = 단지.setdefault(r["구군명"], {"산단": 0, "업체": 0, "고용": 0})
        g["산단"] += 1
        for k, c in (("업체", "입주업체(개사)"), ("고용", "고용인원(명)")):
            v = (r[c] or "").replace(",", "").strip()
            if v.isdigit():
                g[k] += int(v)
    print(f"산업단지 {sum(v['산단'] for v in 단지.values())}개 · "
          f"고용인원 {sum(v['고용'] for v in 단지.values()):,}명 · {len(단지)}개 구군")

    # 공고
    rows = list(csv.DictReader(JOBS.open(encoding="utf-8-sig")))
    job = {}
    for x in rows:
        d = job.setdefault(x["시군구"], {"공고": 0, "대졸신입": 0, "연봉": []})
        d["공고"] += 1
        if x["요구학력"] in HI and x["경력요건"] in NEW:
            d["대졸신입"] += 1
        if x["연봉환산최소"].isdigit():
            d["연봉"].append(int(x["연봉환산최소"]))
    print(f"공고 {len(rows):,}건 (2026-09-07)\n")

    pa = age.pivot_table(index="시군구", columns="나이대",
                         values=["평균주거인구수", "평균직장인구수"], aggfunc="sum")
    ps = sex.pivot_table(index="시군구", columns="성별",
                         values=["평균주거인구수", "평균직장인구수"], aggfunc="sum")
    rec = []
    for s in SGG:
        주20, 직20 = pa[("평균주거인구수", "20대")][s], pa[("평균직장인구수", "20대")][s]
        주전 = sum(pa[("평균주거인구수", a)][s] for a in pa["평균주거인구수"].columns)
        직전 = sum(pa[("평균직장인구수", a)][s] for a in pa["평균직장인구수"].columns)
        j = job.get(s, {"공고": 0, "대졸신입": 0, "연봉": []})
        g = 단지.get(s, {"산단": 0, "업체": 0, "고용": 0})
        rec.append({
            "시군구": s,
            "청년주거인구": round(주20), "청년직장인구": round(직20),
            "청년유입비": round(직20 / 주20, 3),
            "전체유입비": round(직전 / 주전, 3),
            "청년주거비중": round(100 * 주20 / 주전, 1),
            "여성유입비": round(ps[("평균직장인구수", "여성")][s] / ps[("평균주거인구수", "여성")][s], 3),
            "남성유입비": round(ps[("평균직장인구수", "남성")][s] / ps[("평균주거인구수", "남성")][s], 3),
            "공고": j["공고"], "대졸신입공고": j["대졸신입"],
            "청년주거1만명당_공고": round(10000 * j["공고"] / 주20, 1),
            "청년주거1만명당_대졸신입": round(10000 * j["대졸신입"] / 주20, 1),
            "연봉중앙": statistics.median(j["연봉"]) if j["연봉"] else "",
            "산단수": g["산단"], "산단고용인원": g["고용"],
            "산단고용1만명당_공고": (round(10000 * j["공고"] / g["고용"], 1) if g["고용"] else ""),
        })
    with (OUT / "공간_시군구.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rec[0])); w.writeheader(); w.writerows(rec)

    hdr = (f"{'시군구':<8}{'청년주거':>8}{'청년직장':>8}{'청년유입':>8}{'전체유입':>8}"
           f"{'공고':>7}{'대졸신입':>8}{'1만명당':>8}{'연봉':>7}")
    print(hdr); print("─" * len(hdr))
    for x in sorted(rec, key=lambda z: -z["청년유입비"]):
        print(f"{x['시군구']:<8}{x['청년주거인구']:>8,}{x['청년직장인구']:>8,}"
              f"{x['청년유입비']:>8.2f}{x['전체유입비']:>8.2f}{x['공고']:>7,}"
              f"{x['대졸신입공고']:>8,}{x['청년주거1만명당_대졸신입']:>8.1f}{str(x['연봉중앙']):>7}")

    유입 = [x["청년유입비"] for x in rec]
    print(f"\n[교차검증] 통신사 신호 vs 채용공고 — 출처가 다른 두 데이터")
    print(f"  청년유입비 ↔ 공고수        r = {corr(유입, [x['공고'] for x in rec]):+.3f}")
    print(f"  청년유입비 ↔ 대졸신입공고   r = {corr(유입, [x['대졸신입공고'] for x in rec]):+.3f}")
    print(f"  청년유입비 ↔ 연봉중앙      r = {corr(유입, [x['연봉중앙'] or 0 for x in rec]):+.3f}")

    print(f"\n[성별] 20대 아닌 전 연령 기준 — 여성이 일하러 나가는 구")
    for x in sorted(rec, key=lambda z: z["여성유입비"])[:5]:
        print(f"  {x['시군구']:<8}여성 {x['여성유입비']:.2f} / 남성 {x['남성유입비']:.2f}"
              f"  (격차 {x['남성유입비']-x['여성유입비']:+.2f})")

    print(f"\n[산업단지 정규화] 공고가 산단 규모 탓인가")
    for x in sorted([r for r in rec if r["산단고용인원"]],
                    key=lambda z: -z["산단고용인원"])[:6]:
        print(f"  {x['시군구']:<8}산단 {x['산단수']:>2}개  고용 {x['산단고용인원']:>7,}명  "
              f"공고 {x['공고']:>6,}  고용1만명당 {x['산단고용1만명당_공고']:>6.1f}건")

    dong = []
    for _, x in age[age["나이대"] == "20대"].iterrows():
        주, 직 = x["평균주거인구수"], x["평균직장인구수"]
        if 주 < 200:
            continue
        dong.append({"시군구": x["시군구"], "행정동명": x["행정동명"],
                     "청년주거인구": round(주), "청년직장인구": round(직),
                     "청년유입비": round(직 / 주, 3)})
    dong.sort(key=lambda z: -z["청년유입비"])
    with (OUT / "공간_행정동.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(dong[0])); w.writeheader(); w.writerows(dong)
    print(f"\n[행정동] 청년 일자리 거점 상위 8 / 청년 유출 하위 5  (주거 200명 이상 {len(dong)}개 동)")
    for x in dong[:8]:
        print(f"  {x['행정동명']:<16}주거 {x['청년주거인구']:>6,}  직장 {x['청년직장인구']:>6,}  {x['청년유입비']:>6.2f}")
    print("  ...")
    for x in dong[-5:]:
        print(f"  {x['행정동명']:<16}주거 {x['청년주거인구']:>6,}  직장 {x['청년직장인구']:>6,}  {x['청년유입비']:>6.2f}")
    print(f"\nout/공간_시군구.csv · out/공간_행정동.csv")


if __name__ == "__main__":
    main()
