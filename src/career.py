"""커리어(career.co.kr) — 지역·직무 분할로 목록 캡 우회 수집.

[초기 오진] www.career.co.kr robots.txt 를 보고 "전체 차단" 으로 분류했었다.
       실제 `User-agent: *` 블록은 /signup·/login·/resume·/user·/company 만 막고
       공고 경로는 허용이며 Crawl-delay: 30 이 붙어 있었다. 재확인 후 정정했다.
[경로 찾기] www 쪽 /jobs 는 403, /recruit/list 는 404. 진짜 목록은
       **별도 서브도메인 job.career.co.kr/jobs/** 였다(메인 네비게이션에서 발견).
       이 서브도메인은 자체 robots.txt 로 /admin·/biz·/user·/signup 만 막는다.

[문제 1 — 링크가 href="#;"] 페이지 버튼이 `javascript:goList(N)` 이고 목록 행 링크도 #.
       브라우저로 확인하니 name="frm" 폼이 POST 로 page·i_pagesize 를 보낸다.
       그런데 POST 로 i_ac(지역) 를 함께 보내면 **필터가 무시**된다(모든 지역이 같은 100건).
       → GET 쿼리스트링 방식이 정상 동작하는 것을 실측해 GET 으로 전환.
[문제 2 — 100건 캡] 필터 없는 목록은 page/i_pagesize 를 어떻게 조합해도 약 100건이 상한이다.
       (size=100 이면 page2 가 빈 결과, size=50 이면 page3 이 빈 결과 → 총 100)
       단 /jobs/area?i_ac=N, /jobs/jobpart?i_jc=N 은 **각자 별도 윈도우**를 갖는다.
       → 지역 17개 × 직무 코드로 분할해 합집합을 취한다.
[상세URL] 목록 행의 a.tx 가 /recruit/view/{id}.
[문제 3 — 직무 칸이 없다] 목록 표에 직무 열이 없어 1차 수집에서 직무 채움률이 0% 였다.
       그런데 공고제목 뒤에 `#레저.스포츠 #외식.식음료.요리` 형태의 해시태그가 붙어 있고
       이것이 이 사이트의 직무 분류다(22%의 공고가 보유).
       → 상세 8,222건을 따로 받지 않고 제목에서 분리해 직무로 옮긴다.
         부수 효과로 제목이 정제되는데, 해시태그는 중복제거 시 제목 매칭의 노이즈라
         떼어내는 편이 정확도에 유리하다.
       (상세의 '모집부문' 표는 표본 8건 전부 없었다 → 상세로도 못 채움)
[문제 3 해결 — 직무 대분류 태깅]
       처음엔 직무 필터 코드를 i_jc=1..11 로 추측해 썼는데 그 파라미터는 무시됐다.
       브라우저로 /jobs/jobpart 를 열어보니 실제 파라미터는 **i_jc1** 이고 값이 숫자가 아니라
       문자 코드였다: A0 경영.기획 / B0 마케팅.광고 / C0 전문직 / D0 무역.유통 /
       E0 영업.고객상담.판매 / F0 생산.제조 / G0 건설 / H0 IT.인터넷 / I0 디자인 /
       J0 서비스 / M0 의료.보건 / N0 연구개발.엔지니어.
       각 대분류 슬라이스를 돌며 그 슬라이스에서 나온 공고에 대분류명을 직무로 붙인다.
       해시태그(22%)보다 커버리지가 훨씬 넓다.
"""
import re
from bs4 import BeautifulSoup
from common import Site, NOW

ROOT = "https://job.career.co.kr"
SIZE = 50
MAX_PAGE = 12                     # 슬라이스당 상한 (캡이 100~200건이라 넉넉)
AREAS = [str(i) for i in range(1, 18)] + ["30"]
# i_jc1 대분류 코드 → 직무명 (브라우저에서 실측)
JOBCAT1 = {"A0": "경영.기획", "B0": "마케팅.광고", "C0": "전문직", "D0": "무역.유통",
           "E0": "영업.고객상담.판매", "F0": "생산.제조", "G0": "건설", "H0": "IT.인터넷",
           "I0": "디자인", "J0": "서비스", "M0": "의료.보건", "N0": "연구개발.엔지니어"}
DUTY_TAG = {}          # 공고ID -> 직무 대분류명 (대분류 슬라이스 순회로 채움)

def rows_of(s, path, page, **flt):
    q = f"?page={page}&i_pagesize={SIZE}" + "".join(f"&{k}={v}" for k, v in flt.items())
    r = s.get(ROOT + path + q)
    return BeautifulSoup(r.text, "html.parser").select("tbody tr")

def harvest(s, seen, path, label, duty_tag=None, **flt):
    added = 0
    for page in range(1, MAX_PAGE + 1):
        try:
            rows = rows_of(s, path, page, **flt)
        except Exception as e:
            s.note(f"{label} p{page} 실패: {e}"); break
        if not rows:
            break
        new = 0
        for tr in rows:
            a = tr.select_one('a[href*="/recruit/view/"]')
            tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if not a or len(tds) < 5:
                continue
            m = re.search(r"/recruit/view/(\d+)", a["href"])
            if not m or m.group(1) in seen:
                continue
            gid = m.group(1)
            seen.add(gid); new += 1; added += 1
            if duty_tag:
                DUTY_TAG.setdefault(gid, duty_tag)
            # tds: [회사명, 제목, '경력 2년 학력무관', '정규직 경기 화성시', '바로지원 ~10/30(금) …']
            ea = tds[3].split()
            dm = re.search(r"~\s*(\d{2})/(\d{2})", tds[4])
            deadline = f"2026-{dm.group(1)}-{dm.group(2)}" if dm else (
                "상시채용" if re.search(r"상시|채용시|수시", tds[4]) else "")
            # 제목 뒤 해시태그 = 직무 분류 (문제3 대응)
            raw_title = tds[1]
            tags = re.findall(r"#([^#\s]+)", raw_title)
            title = re.sub(r"\s*#[^#\s]+", "", raw_title).strip()
            # 대분류 태그를 앞에 붙여 직무를 구성 (해시태그가 있으면 함께)
            duty_parts = ([DUTY_TAG[gid]] if DUTY_TAG.get(gid) else []) + tags
            s.add(회사명=tds[0], 공고제목=title,
                  직무=", ".join(dict.fromkeys(duty_parts))[:120], 경력=tds[2],
                  고용형태=ea[0] if ea else "", 지역=" ".join(ea[1:])[:40],
                  기술스택="", 마감일=deadline,
                  공고URL=f"{ROOT}/recruit/view/{m.group(1)}", 수집시각=NOW())
        if new == 0:
            break
    return added

def main():
    s = Site("커리어", ROOT, delay=1.0)
    s.note("www 가 아니라 job.career.co.kr 서브도메인이 실제 공고 목록")
    if not s.allowed(ROOT + "/jobs/"):
        s.note("robots.txt 차단 — 중단"); s.save(); return
    s.note("필터 없는 목록은 100건 캡 → 직무 대분류(i_jc1)·지역(i_ac) 분할로 우회")
    seen = set()
    harvest(s, seen, "/jobs/", "전체")
    for code, name in JOBCAT1.items():
        n = harvest(s, seen, "/jobs/jobpart", f"jc1:{code}", duty_tag=name, i_jc1=code)
        print(f"    i_jc1={code} {name:14s} 신규 {n:4d} 누적 {len(seen):5,}", flush=True)
        s.save()
    for ac in AREAS:
        n = harvest(s, seen, "/jobs/area", f"area{ac}", i_ac=ac)
        print(f"    i_ac={ac:>2s} 신규 {n:4d} 누적 {len(seen):5,}", flush=True)
        s.save()
    s.note(f"수집 {len(seen):,}건 / 직무 대분류 태깅 {len(DUTY_TAG):,}건")
    s.save()

if __name__ == "__main__":
    main()
