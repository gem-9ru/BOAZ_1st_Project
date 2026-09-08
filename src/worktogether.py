"""워크투게더(한국장애인고용공단) — 장애인 채용정보 게시판.

[경로 찾기] worktogether.or.kr 로 접근하면 kead.or.kr 루트로 리다이렉트되어
       게시판 본문이 안 나온다(초기 진단에서 'JS 렌더링'으로 오판한 원인).
       실제 경로는 **www.kead.or.kr/bbs/jobinfo/bbsPage.do?menuId=MENU2201** 이고,
       이 URL로 직접 요청하면 정적 HTML에 표가 그대로 들어있다.
[구조] table.board_table 에 10건씩. 열은
       번호 | 제목 | 도·광역시 | 시·군·구 | 분류 | 마감일 | 등록일.
       지역이 광역/기초로 이미 분리돼 있어 정규화가 쉽다.
[페이지네이션] pageIndex=N (HTML 안 페이지 링크에서 확인, 32페이지까지 존재)
[상세] 목록 링크는 javascript:void(0) 이지만 onclick 이 fn_bbsView('216084') 를 호출한다.
       이 함수는 searchForm 을 /bbs/jobinfo/bbsView.do 로 POST 하는 구조여서 상세도 접근 가능하다.
       실제로 열어보니 상세의 th-td 는 도·광역시 / 시·군·구 / 분류 / 마감일 / 등록일 /
       담당부서 / 전화번호 / FAX 뿐이고 **회사명 필드가 없다**(담당부서는 공단 부서).
       → 상세를 받아도 회사명을 얻을 수 없으므로 목록만 수집한다.

[회사명 — 제목에서 추출]
       "채용공고에 회사명이 없는 게 말이 되냐" 는 지적을 받고 다시 파본 결과,
       회사명은 별도 열이 아니라 **제목 안에 들어있다.**
         "[서울동부지사] 현대자동차 ★남양연구소★ 파이롯트센터 행정지원 …"
         "성남시 중원구 / 아이엠정형외과 미화, 주방 보조 1명"
       공단 지사/지역본부 머리표를 떼고, 지역명·근무형태 같은 비회사 토큰을 걸러
       회사명을 뽑는다. 오탐(지역을 회사로 잡는 것)보다 미추출이 안전하므로
       확신이 없으면 빈칸으로 남긴다.
"""
import re
from bs4 import BeautifulSoup
from common import Site, NOW

ROOT = "https://www.kead.or.kr"

SIDO = r"서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주"
# 공단이 붙이는 머리표: [서울동부지사], [대전지역본부], [장애인만 채용] 등
PREFIX = re.compile(r"^\s*(?:\[[^\]]*\]|★[^★]*★)\s*")
# 회사명이 될 수 없는 선행 토큰
STOP = re.compile(rf"^(?:{SIDO}|[가-힣]{{2,4}}(?:시|군|구)|재택근무|재택|주간|월간|정기|일반|"
                  r"장애인|장애인만|중증|주간구인정보|주간채용정보|채용정보|학교|공고|모집|채용|"
                  r"전일제|시간제|단순|오전|오후|야간|주말|\d{4}년?|\d+차|하반기|상반기)$")
# 법인·기관을 시사하는 접미
ORGISH = re.compile(r"(주|㈜|사|원|점|센터|랩|텍|컴|사무소|법인|재단|대학교|학교|병원|의원|"
                    r"은행|증권|카드|생명|화재|공사|공단|협회|연구소|복지관|어린이집|유치원)$")


# 장애인 채용 게시판에 자주 나오는 직무 어휘
JOBWORDS = re.compile(
    r"(환경미화|미화|사무보조|사무|경비|보안|조리|주방|급식|생산|포장|조립|검수|검사|품질|"
    r"운전|배송|물류|상담|콜센터|바리스타|간호|간병|청소|세차|시설관리|시설|영업|판매|안내|"
    r"디자인|개발|회계|총무|인사|제조|용접|도장|서빙|세탁|재활|사서|번역|데이터입력|IT지원)")


def duty_from_title(title):
    """제목에서 직무 키워드를 뽑는다. 없으면 빈 문자열."""
    ms = JOBWORDS.findall(title or "")
    return ", ".join(dict.fromkeys(ms))[:80]


def company_from_title(title):
    """제목에서 회사명 후보를 뽑는다. 확신 없으면 빈 문자열(오탐보다 미추출 우선)."""
    t = title
    for _ in range(3):                      # 머리표가 겹쳐 붙는 경우가 있어 반복 제거
        t2 = PREFIX.sub("", t).strip()
        if t2 == t:
            break
        t = t2
    # "성남시 중원구 / 아이엠정형외과 …" → 슬래시 뒤가 회사명
    if "/" in t:
        t = t.split("/", 1)[1].strip()
    # [보강] 앞 토큰이 지역/근무형태면 건너뛰고 다음 토큰을 본다.
    #        "서울 창원초 미화직" → '서울' 스킵 후 '창원초' 채택
    #        "[서울지역본부] 한국언론진흥재단 체험형…" → 머리표 제거 후 첫 토큰 채택
    #        단 '주간구인정보' 처럼 공고 자체가 여러 회사 묶음이면 회사명이 없는 게 맞다.
    toks = [w.strip("()[]·,.") for w in re.split(r"[\s★☆,]+", t)]
    for w in toks[:4]:
        if not w or STOP.match(w):
            continue
        if ORGISH.search(w) or len(w) >= 3:
            return w[:40]
    return ""

LIST = ROOT + "/bbs/jobinfo/bbsPage.do?menuId=MENU2201"
MAX_PAGE = 60

def main():
    s = Site("워크투게더", ROOT, delay=1.2)
    s.note("worktogether.or.kr → kead.or.kr 리다이렉트. 게시판 직접 URL 사용")
    if not s.allowed(LIST):
        s.note("robots.txt 차단 — 중단"); s.save(); return
    seen = set()
    for page in range(1, MAX_PAGE + 1):
        try:
            soup = BeautifulSoup(s.get(f"{LIST}&pageIndex={page}").text, "html.parser")
        except Exception as e:
            s.note(f"page {page} 실패: {e}"); break
        t = soup.select_one("table.board_table")
        rows = t.select("tbody tr") if t else []
        if not rows:
            break
        new = 0
        for tr in rows:
            tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if len(tds) < 7 or not tds[0].isdigit():
                continue
            no = tds[0]
            if no in seen:
                continue
            seen.add(no); new += 1
            title = tds[1]
            # [직무 수정] 1차에서는 게시판 '분류' 열(대기업/일반구인/공사·공기업)을 직무로 넣었는데
            #   그건 구인처 유형이지 직무가 아니다. 게시판·상세 어디에도 직무 필드가 없어
            #   제목에서 직무 키워드를 뽑는다(표본상 61% 추출 가능).
            #   구인처 유형은 정보로서 의미가 있으므로 뒤에 병기한다.
            duty = duty_from_title(title)
            s.add(회사명=company_from_title(title),
                  공고제목=title,                          # 원문 보존(정보 손실 방지)
                  # 구인처 유형은 괄호로 묶으면 정규화 단계 토큰 분해에서 깨진다 → 콤마 병기
                  직무=(f"{duty}, {tds[4]}" if duty else tds[4]),
                  경력="", 고용형태="",
                  지역=f"{tds[2]} {tds[3]}".strip(),
                  기술스택="",
                  마감일=tds[5],
                  공고URL=f"{LIST}&pageIndex={page}",     # 상세 URL 생성 불가(javascript:void)
                  수집시각=NOW())
        print(f"    page {page}: 누적 {len(seen)}", flush=True)
        if new == 0:
            break
    got = sum(1 for r in s.rows if r.get("회사명"))
    s.note(f"수집 {len(seen)}건 / 제목에서 회사명 추출 {got}건 "
           f"(게시판에 회사명 열이 없어 제목 파싱으로 확보)")
    s.save()

if __name__ == "__main__":
    main()
