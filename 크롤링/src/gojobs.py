"""나라일터(인사혁신처 공무원·공공기관 채용) — 모집공고 목록.

[막혔던 과정] 처음엔 /apmList.do 를 그냥 GET 하니 결과 표가 비어 있었다(필터 UI 만 렌더).
       name="listForm" 폼 필드 31개를 그대로 POST 해도 400, 브라우저에서 검색 함수
       fn_apmAllList() 를 직접 호출하니 오류 페이지로 갔다.
[해결] 좌측 메뉴 링크가 gfn_menu_move('apmList.do','401','N','400','') 를 호출하는 데서
       힌트를 얻어 **menuNo=401 & upperMenuNo=400** 을 쿼리로 붙이니 검색 없이 목록이 나온다.
       (메뉴 번호가 없으면 서버가 '검색 전 상태' 로 보고 빈 표를 준다)
[구조] 표 열: 번호 | 공고명 | 기관명 | 공고게시일 | 접수마감일 | 조회
       상세는 javascript:fn_apmView('020','303045') 형태라 두 번째 인자가 공고 일련번호.
[페이지네이션] pageIndex=N (1페이지 번호 1~, 2페이지 11~ 로 검증)
       ※ 1차 수집에서 MAX_PAGE=80 으로 잡아 두 메뉴가 정확히 800건씩에서 끊겼다.
         "메뉴별 건수가 상한과 딱 맞으면 전수가 아니다" 는 신호로 보고 상한을 올렸다.
[robots] robots.txt 에 Googlebot 대상 규칙만 있고 목록 경로는 제한 없음.
[참고] 같은 데이터가 인사혁신처 공공데이터 API(apis.data.go.kr/1051000/recruitment/list)로도
       제공된다. 키가 확보되면 그쪽이 더 안정적이다.

[상세 보강 범위 — 부산 한정]
       지역 필터(serachAreaClassCd=26000 등)는 GET 으로 넘겨도 서버가 무시한다(인천 결과 그대로).
       목록에는 근무지역 열이 아예 없어서 상세를 받기 전에는 지역을 알 수 없다.
       전량 상세(20,000건)는 4시간 가까이 걸리므로,
       **기관명·공고명에 부산 지명이 있는 건만** 상세를 받아 근무지역·채용직급을 채운다.
       (나라일터는 공공기관 채용이라 기관명이 지역을 강하게 시사한다)
       목록 자체는 전량 수집하므로 회사명·제목·마감일은 모든 공고에 대해 확보된다.

[2차 보강] 목록에는 근무지역 열이 없어 1차 수집에서 지역 채움률이 0% 였다.
       상세 URL 은 fn_apmView('020','303045') 의 두 번째 인자로 만들 수 있고
         /apmView.do?empmnsn={sn}&searchJobsecode={code}&menuNo=401
       상세 th-td 에 **근무지역**(예: 경기도 용인시 처인구)과 **채용직급** 이 있어 이를 병합한다.
"""

LIST_ROWS = {}          # 공고 일련번호 -> 목록에서 얻은 필드


def parse_detail(u, r):
    """상세 th-td 에서 근무지역·채용직급을 뽑아 목록 데이터에 병합."""
    m = re.search(r"empmnsn=(\d+)", u)
    base = dict(LIST_ROWS.get(m.group(1), {})) if m else {}
    if not base:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    kv = {}
    for th in soup.select("th, dt"):
        nx = th.find_next(["td", "dd"])
        if nx:
            kv.setdefault(re.sub(r"\s+", "", th.get_text(" ", strip=True)), nx.get_text(" ", strip=True))
    base["지역"] = (kv.get("근무지역") or "")[:60]
    grade = (kv.get("채용직급") or "")
    if grade:
        base["직무"] = f'{base.get("직무","")} / {grade}'.strip(" /")[:120]
    base["수집시각"] = NOW()
    return base
import re
from bs4 import BeautifulSoup
from common import Site, NOW, fetch_many

ROOT = "https://www.gojobs.go.kr"

BUSAN_DETAIL_ONLY = True
BUSAN_RE = re.compile(r"부산|해운대|기장군|기장|사상|사하|영도|동래|금정|수영구|연제|부산진")
# menuNo 별 공고 종류: 401 일반채용 / e06 공모직위 / e07 전입공모
TARGETS = [("일반채용", "/apmList.do?menuNo=401&upperMenuNo=400"),
           ("공모직위", "/apmAllList.do?searchEmpmnsecode=e06&menuNo=612&upperMenuNo=220")]
# [상한 이력과 판단 변경]
#   80(=800건) → 600 → 2200 으로 올려가며 "전수"를 쫓았는데, 이분 탐색으로 끝을 찾아보니
#   마지막 유효 페이지가 **19,429페이지(약 194,290건)** 였다.
#   내용을 열어보니 2020년 공고까지 들어있는 **누적 아카이브**였다.
#     p2500 → 2025년도 경기도교육청 공고 / p19429 → 2020년 오대산 겨울철 환경미화
#   목표는 "2026-09-07 시점 모집 중인 공고" 이므로 전수를 받는 게 오히려 틀렸다.
#   → 페이지 상한 대신 **접수마감일이 기준일 이후인 공고까지만** 받고 멈춘다.
#     목록이 최신순이라 마감된 공고가 연속으로 나오면 그 뒤는 볼 필요가 없다.
MAX_PAGE = 3000                 # 안전장치(정상 종료는 마감일 조건으로 이뤄진다)
SNAPSHOT = "2026-09-07"         # 스냅샷 기준일
STOP_AFTER_EXPIRED_PAGES = 5    # 마감 공고만 나오는 페이지가 연속 N회면 종료

def biggest_table(soup):
    cands = [(t, len(t.select("tbody tr"))) for t in soup.select("table")]
    return max(cands, key=lambda x: x[1])[0] if cands else None

def main():
    s = Site("나라일터", ROOT, delay=1.2)
    s.note("menuNo 파라미터를 붙이지 않으면 서버가 빈 표를 반환 → menuNo 필수")
    seen = set()
    for label, path in TARGETS:
        expired_streak = 0
        for page in range(1, MAX_PAGE + 1):
            try:
                soup = BeautifulSoup(s.get(f"{ROOT}{path}&pageIndex={page}").text, "html.parser")
            except Exception as e:
                s.note(f"{label} p{page} 실패: {e}"); break
            t = biggest_table(soup)
            rows = t.select("tbody tr") if t else []
            if not rows:
                break
            new = 0
            for tr in rows:
                tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
                a = tr.select_one("a")
                if len(tds) < 5:
                    continue
                sn = ""
                if a:
                    m = re.search(r"fn_apmView\(\s*'([^']*)'\s*,\s*'(\d+)'", a.get("href", "") or a.get("onclick", "") or "")
                    if m:
                        sn = m.group(2)
                key = sn or f"{label}:{tds[1][:30]}:{tds[2][:20]}"
                if key in seen:
                    continue
                seen.add(key); new += 1
                url = (f"{ROOT}/apmView.do?empmnsn={sn}&searchJobsecode=020&menuNo=401"
                       if sn else ROOT + path)
                deadline = tds[4] if len(tds) > 4 else ""
                if deadline and deadline < SNAPSHOT:
                    continue                      # 기준일 이전 마감 → 스냅샷 대상 아님
                row = {"회사명": tds[2], "공고제목": tds[1], "직무": label,
                       "경력": "", "고용형태": "공무원·공공", "지역": "", "기술스택": "",
                       "마감일": tds[4] if len(tds) > 4 else "",
                       "공고URL": url, "수집시각": NOW()}
                if sn:
                    LIST_ROWS[sn] = row
                else:
                    s.add(**row)
            # 이 페이지에 '기준일 이후 마감' 공고가 하나도 없으면 과거 구간에 들어선 것
            alive = 0
            for tr in rows:
                tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
                if len(tds) > 4 and tds[4] and tds[4] >= SNAPSHOT:
                    alive += 1
            expired_streak = expired_streak + 1 if alive == 0 else 0
            if page % 10 == 0 or page == 1:
                print(f"    {label} p{page}: 누적 {len(seen)} (진행중 {alive}/{len(rows)})", flush=True)
            if expired_streak >= STOP_AFTER_EXPIRED_PAGES:
                s.note(f"{label}: 마감 공고만 {STOP_AFTER_EXPIRED_PAGES}페이지 연속 → 과거 아카이브 구간으로 판단, 종료")
                break
            if new == 0:
                break
        s.save()
    if BUSAN_DETAIL_ONLY:
        targets = [r for r in LIST_ROWS.values()
                   if BUSAN_RE.search(f"{r.get('회사명','')} {r.get('공고제목','')}")]
        s.note(f"목록 {len(seen):,}건 수집 / 그중 부산 후보 {len(targets):,}건만 상세 요청 "
               f"(지역 필터가 서버에서 무시되어 기관명·제목으로 선별)")
        # 부산 후보가 아닌 행은 목록 정보만으로 바로 적재한다(누락 방지)
        for r in LIST_ROWS.values():
            if r not in targets:
                s.add(**r)
    else:
        targets = list(LIST_ROWS.values())
        s.note(f"목록 {len(seen):,}건 → 전량 상세 요청")
    urls = [r["공고URL"] for r in targets]
    fetch_many(s, urls, parse_detail, workers=2, per_sec=1.5, label="apmView")
    s.save()

if __name__ == "__main__":
    main()
