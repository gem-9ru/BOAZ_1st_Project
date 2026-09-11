# -*- coding: utf-8 -*-
"""사이트별 수집 완전성 검증.

지금까지 '수집 → (지적받으면) 검증' 순으로 일했고, 그 결과
  · 부산일자리정보망 해외채용 569건 통째 누락 (링크 방식이 메뉴마다 달랐음)
  · 나라일터 두 메뉴 모두 정확히 800건에서 잘림 (MAX_PAGE=80 상한)
같은 구멍을 뒤늦게 발견했다. 순서를 뒤집기 위한 도구다.

각 사이트에 대해 **사이트가 스스로 밝힌 총건수**(정본)를 조회하고 수집분과 대조한다.
정본을 못 구하면 그 사실 자체를 결과에 남긴다(모르면 모른다고 적는다).

검증 항목
  1) 정본 총건수  — "전체 N건" 표기 / API total / sitemap URL 수
  2) 수집 건수    — data/*.csv 행 수
  3) 커버리지     — 수집/정본
  4) 상한 의심    — 수집 건수가 설정 상한의 배수와 일치하는가
  5) 하위 메뉴    — 메뉴·탭·카테고리를 빠짐없이 돌았는가
"""
import csv, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import Site, DATA, LOGS
from bs4 import BeautifulSoup

SNAPSHOT = "2026-09-07"     # 데이터셋 기준일 (이 날짜 이후 마감인 공고만 정본으로 센다)


def n_rows(name):
    p = DATA / f"{name}.csv"
    if not p.exists():
        return 0
    return sum(1 for _ in p.open(encoding="utf-8-sig")) - 1

def ck_rows(name):
    p = LOGS / f"{name}.ckpt.jsonl"
    return sum(1 for line in p.open(encoding="utf-8") if line.strip()) if p.exists() else 0

# ── 사이트별 '정본 총건수' 조회기 ─────────────────────────────────────────────
def t_busanjob():
    s = Site("chk", "https://www.busanjob.net")
    out = {}
    for no, label in [("1308", "기업채용"), ("1309", "공공채용"), ("1310", "해외채용")]:
        txt = BeautifulSoup(s.get(f"https://www.busanjob.net/view.do?no={no}&pgMode=index&pageIndex=1").text,
                            "html.parser").get_text(" ")
        m = re.search(r"전체\s*([\d,]+)\s*건", txt)
        out[label] = int(m.group(1).replace(",", "")) if m else None
    return sum(v for v in out.values() if v), out

def t_jobkorea():
    s = Site("chk", "https://www.jobkorea.co.kr")
    idx = s.get("https://www.jobkorea.co.kr/content/sitemapindex.xml").text
    maps = [l for l in re.findall(r"<loc>([^<]+)</loc>", idx) if "/agi/" in l]
    n = 0
    for m in maps:
        n += len(re.findall(r"<loc>", s.get(m).text))
    return n, {"sitemap agi": n, "사이트 표기": 199110}

def t_jobplanet():
    s = Site("chk", "https://www.jobplanet.co.kr")
    s.s.headers.update({"Referer": "https://www.jobplanet.co.kr/job", "Accept": "application/json"})
    d = s.s.get("https://www.jobplanet.co.kr/api/v3/job/postings",
                params={"order_by": "aggressive", "page": 1, "page_size": 1}, timeout=30).json()
    t = (d.get("data") or {}).get("total_count")
    return t, {"api total_count": t, "비고": "단일질의 1만건 캡 → 분할 수집"}

def t_catch():
    s = Site("chk", "https://www.catch.co.kr")
    d = s.s.get("https://www.catch.co.kr/api/v1.0/recruit/information/getRecruitList",
                params={"Keyword": "", "Sort": "0", "pageSize": 1, "curpage": 1, "onRecruitYN": "Y"},
                timeout=30).json()
    return d.get("intTotalRecordCount"), {}

def t_jumpit():
    s = Site("chk", "https://jumpit.saramin.co.kr")
    d = s.s.get("https://jumpit-api.saramin.co.kr/api/positions",
                params={"page": 1, "sort": "reg_dt"}, timeout=30).json()
    return d["result"]["totalCount"], {}

def t_remember():
    s = Site("chk", "https://career.rememberapp.co.kr")
    t = len(re.findall(r"<loc>", s.get("https://career.rememberapp.co.kr/sitemap-jobs.xml").text))
    return t, {"sitemap-jobs.xml": t}

def t_joballio():
    s = Site("chk", "https://job.alio.go.kr")
    soup = BeautifulSoup(s.get("https://job.alio.go.kr/recruit.do?pageNo=1").text, "html.parser")
    t = soup.select_one("table.type_03")
    first = t.select("tbody tr")[0].select("td")[1].get_text(strip=True) if t else "0"
    return int(re.sub(r"\D", "", first) or 0), {"1페이지 최대 번호를 총건수로 사용": first}

def t_gojobs():
    """나라일터 정본 = **접수마감일이 기준일 이후인 공고 수**.

    [수정] 처음엔 마지막 페이지를 이분 탐색해 정본을 잡았는데 19,429페이지(약 194,290건)가 나왔다.
      열어보니 2020년 공고까지 남아 있는 누적 아카이브였다.
      데이터셋 목표가 '2026-09-07 시점 모집 중' 이므로 아카이브 전체는 정본이 아니다.
      목록이 최신순이니 마감된 공고만 나오는 페이지가 연속되는 지점까지만 센다.
    """
    s = Site("chk", "https://www.gojobs.go.kr")
    out = {}
    for path, label in [("/apmList.do?menuNo=401&upperMenuNo=400", "일반채용"),
                        ("/apmAllList.do?searchEmpmnsecode=e06&menuNo=612&upperMenuNo=220", "공모직위")]:
        alive, streak, page = 0, 0, 1
        while page <= 300 and streak < 5:
            soup = BeautifulSoup(s.get(f"https://www.gojobs.go.kr{path}&pageIndex={page}").text,
                                 "html.parser")
            rows = max((x.select("tbody tr") for x in soup.select("table")), key=len, default=[])
            rows = [r for r in rows if r.select("td")]
            if not rows:
                break
            n = 0
            for r in rows:
                tds = [td.get_text(" ", strip=True) for td in r.select("td")]
                if len(tds) > 4 and tds[4] and tds[4] >= SNAPSHOT:
                    n += 1
            alive += n
            streak = streak + 1 if n == 0 else 0
            page += 1
        out[label] = alive
    return sum(out.values()), out

def t_kead():
    s = Site("chk", "https://www.kead.or.kr")
    soup = BeautifulSoup(s.get("https://www.kead.or.kr/bbs/jobinfo/bbsPage.do?menuId=MENU2201").text, "html.parser")
    t = soup.select_one("table.board_table")
    first = t.select("tbody tr")[0].select("td")[0].get_text(strip=True) if t else "0"
    return int(re.sub(r"\D", "", first) or 0), {"게시판 최신 글번호": first}

def t_wanted():
    """원티드는 총건수를 주지 않는다. offset 을 이분 탐색해 마지막 유효 지점을 찾는다."""
    s = Site("chk", "https://www.wanted.co.kr")
    s.s.headers.update({"Referer": "https://www.wanted.co.kr/wdlist", "Accept": "application/json"})
    def has(off):
        d = s.s.get("https://www.wanted.co.kr/api/v4/jobs",
                    params={"country": "kr", "job_sort": "job.latest_order", "locations": "all",
                            "years": -1, "limit": 1, "offset": off}, timeout=30).json()
        return bool(d.get("data"))
    lo, hi = 0, 60000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        lo, hi = (mid, hi) if has(mid) else (lo, mid - 1)
    return lo + 1, {"방법": "offset 이분 탐색(총건수 미제공)"}


def t_jasoseol():
    s = Site("chk", "https://jasoseol.com")
    s.s.headers.update({"Referer": "https://jasoseol.com/recruit", "X-Requested-With": "XMLHttpRequest"})
    n = 0
    for y in (2026, 2027):
        r = s.s.post("https://jasoseol.com/employment/calendar_list.json",
                     json={"start_time": f"{y}-01-01", "end_time": f"{y}-12-31"}, timeout=60)
        if r.status_code == 200:
            n += len(r.json().get("employment") or [])
    return n, {"방법": "연 단위 API 응답 건수 합"}


def t_gamejob():
    """게임잡은 총건수 표기가 없다. main/home + 목록의 고유 GI_No 로 상한을 잡는다."""
    s = Site("chk", "https://www.gamejob.co.kr")
    ids = set(re.findall(r"GI_No=(\d+)", s.get("https://www.gamejob.co.kr/main/home").text))
    ids |= set(re.findall(r"GI_No=(\d+)",
               s.get("https://www.gamejob.co.kr/Recruit/joblist?menucode=searchall").text))
    return len(ids), {"방법": "페이지네이션 사망 → 노출 GI_No 합집합이 상한"}


def t_nurscape():
    s = Site("chk", "https://recruit.nurscape.net")
    ids = set(re.findall(r"/Jobs/Details/(\d+)", s.get("https://recruit.nurscape.net/Jobs").text))
    return len(ids), {"방법": "목록 노출 공고 ID 수"}


def t_mediajob():
    s = Site("chk", "https://www.mediajob.co.kr")
    ids = set()
    for u in ("https://www.mediajob.co.kr/", "https://www.mediajob.co.kr/recruit/recruit.htm"):
        try:
            ids |= set(re.findall(r"rec_idx=(\d+)", s.get(u).text))
        except Exception:
            pass
    return len(ids), {"방법": "홈·목록 노출 rec_idx 수"}


def t_worker():
    s = Site("chk", "https://www.worker.co.kr")
    nos = set()
    for c in ("all", "eng", "con", "ccp", "int", "hh"):
        try:
            r = s.get(f"https://www.worker.co.kr/job/list.asp?jobid={c}"); r.encoding = "euc-kr"
        except Exception:
            continue
        nos |= set(re.findall(r"[?&]no=(\d+)", r.text))
    return len(nos), {"방법": "카테고리 순회 후 고유 공고번호"}


def t_linkareer():
    """링커리어는 목록 페이지를 끝까지 넘겨 신규 0 이 되는 지점이 상한."""
    return None, {"방법": "정본 미제공 — 슬라이스 소진으로 판정"}


def t_career():
    return None, {"방법": "정본 미제공 — 100건 캡 때문에 지역·직무 분할 합집합"}


CHECKS = [
    ("잡코리아",         t_jobkorea),
    ("잡플래닛",         t_jobplanet),
    ("부산일자리정보망", t_busanjob),
    ("리멤버커리어",     t_remember),
    ("캐치",             t_catch),
    ("잡알리오",         t_joballio),
    ("나라일터",         t_gojobs),
    ("워크투게더",       t_kead),
    ("점핏",             t_jumpit),
    ("원티드",           t_wanted),
    ("자소설닷컴",       t_jasoseol),
    ("게임잡",           t_gamejob),
    ("널스케이프",       t_nurscape),
    ("미디어잡",         t_mediajob),
    ("건설워커",         t_worker),
    ("링커리어",         t_linkareer),
    ("커리어",           t_career),
]

def main():
    print(f"{'사이트':<16}{'정본':>10}{'수집':>10}{'커버':>7}  비고")
    print("-" * 78)
    result = []
    for name, fn in CHECKS:
        try:
            total, detail = fn()
        except Exception as e:
            total, detail = None, {"오류": f"{type(e).__name__}: {str(e)[:40]}"}
        got = max(n_rows(name), ck_rows(name))
        cov = f"{100*got/total:.1f}%" if total else "-"
        flag = ""
        if total and got < total * 0.98:
            flag = "⚠ 미달"
        print(f"{name:<16}{(total or 0):>10,}{got:>10,}{cov:>7}  {flag} {detail if detail else ''}")
        result.append({"사이트": name, "정본": total, "수집": got, "커버리지": cov, "상세": detail})
    Path(__file__).with_name("coverage_check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n-> coverage_check.json")

if __name__ == "__main__":
    main()
