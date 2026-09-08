"""잡알리오 (기획재정부 공공기관 채용정보시스템) — 목록 테이블 수집.

[의의] 전 공공기관 채용공고가 모이는 공식 창구다. 민간 잡보드만 모으면
       "한국 채용공고 원본데이터" 에 공공 부문이 통째로 빠진다.
[문제] 페이지에 table 이 3개 있고 앞의 둘은 직군 선택 필터 UI 다.
       `tbody tr` 로 긁으면 필터 표의 행이 섞여 들어온다 → class 로 공고 표만 특정한다.
[페이지네이션] page / pageIndex / curPage / pageNum 전부 무시되고 **pageNo** 만 동작한다.
       (실측: 다른 파라미터는 1페이지와 첫 idx 가 동일)
[robots] robots.txt 가 404 = 규칙 없음. 공공 사이트이므로 초당 1건으로 낮게 유지한다.

[2차 보강] 1차 수집(목록만)에서는 직무·경력 채움률이 0% 였다. 목록 표에 그 칸이 없기 때문.
       상세(recruitview.do)에 th-td 로 아래 값들이 있어 이를 병합한다.
         표준직무(NCS) / 근무분야 → 직무
         채용구분(신입+경력 등)     → 경력
         학력정보 · 급여정보 · 채용인원 등은 현재 스키마에 칸이 없어 사용하지 않음
"""

LIST_ROWS = {}          # idx -> 목록에서 얻은 필드


def parse_detail(u, r):
    """상세의 th-td 표에서 직무·경력을 뽑아 목록 데이터에 병합."""
    m = re.search(r"idx=(\d+)", u)
    idx = m.group(1) if m else ""
    base = dict(LIST_ROWS.get(idx, {}))
    soup = BeautifulSoup(r.text, "html.parser")
    kv = {}
    for th in soup.select("th"):
        td = th.find_next("td")
        if td:
            kv.setdefault(re.sub(r"\s+", "", th.get_text(" ", strip=True)), td.get_text(" ", strip=True))
    duty = " / ".join(x for x in [kv.get("표준직무(NCS)"), kv.get("근무분야")] if x)
    base["직무"] = duty[:120]
    base["경력"] = (kv.get("채용구분") or "")[:40]
    base["수집시각"] = NOW()
    return base or None
import re
from bs4 import BeautifulSoup
from common import Site, NOW, fetch_many

ROOT = "https://job.alio.go.kr"
MAX_PAGE = 400

def main():
    s = Site("잡알리오", ROOT, delay=1.0)
    s.note("공공기관 채용정보시스템 / 페이지 파라미터는 pageNo 만 유효")
    seen = set()
    for page in range(1, MAX_PAGE + 1):
        try:
            soup = BeautifulSoup(s.get(f"{ROOT}/recruit.do?pageNo={page}").text, "html.parser")
        except Exception as e:
            s.note(f"page {page} 실패: {e}"); break
        tbl = soup.select_one("table.type_03")          # 필터 표(type_01/02)와 구분
        rows = tbl.select("tbody tr") if tbl else []
        if not rows:
            break
        new = 0
        for tr in rows:
            a = tr.select_one('a[href*="recruitview"]')
            tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if not a or len(tds) < 9:
                continue
            m = re.search(r"idx=(\d+)", a["href"])
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1)); new += 1
            deadline = re.sub(r"\s*D-\s*\d+", "", tds[7]).strip()      # '26.09.14 D-6' → '26.09.14'
            dm = re.match(r"(\d{2})\.(\d{2})\.(\d{2})", deadline)
            if dm:
                deadline = f"20{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
            LIST_ROWS[m.group(1)] = {
                "회사명": tds[3], "공고제목": tds[2], "직무": "", "경력": "",
                "고용형태": tds[5], "지역": tds[4], "기술스택": "",
                "마감일": deadline,
                "공고URL": f"{ROOT}/recruitview.do?idx={m.group(1)}",
                "수집시각": NOW()}
        if page % 20 == 0 or page == 1:
            print(f"    page {page}: 누적 {len(seen):,}", flush=True)
        if new == 0:
            break
    s.note(f"목록에서 {len(seen):,}건 확보 → 직무·경력 보강을 위해 상세 요청")
    urls = [f"{ROOT}/recruitview.do?idx={i}" for i in sorted(LIST_ROWS)]
    fetch_many(s, urls, parse_detail, workers=2, per_sec=1.5, label="recruitview")
    s.save()

if __name__ == "__main__":
    main()
