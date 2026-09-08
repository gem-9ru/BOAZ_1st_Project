"""잡코리아 부산 지역 전수 수집.

[왜 다시 받는가]
기존 잡코리아 수집은 전국 sitemap 기반이었고, 거기서 지역이 '부산'인 행은 4,149건이었다.
그런데 잡코리아 지역 필터가 밝히는 부산 공고는 **8,660건**이다. 절반이 빠져 있었다.

원인 두 가지.
  1. 상세 JSON-LD 의 jobLocation 은 주소를 하나만 준다.
     "서울, 경기, 대구, 경북, 부산, 경남" 처럼 여러 지역에 걸린 공고가
     첫 주소(서울)로만 기록돼 부산 집계에서 빠졌다.
  2. sitemap 에 노출되지 않는 공고가 있다.

→ 지역 필터 목록을 직접 훑는다.

[목록과 상세의 역할이 다르다]
  목록  = 빠짐없이 '찾아내는' 단계. 부산 공고 8,660건의 GI_No 를 확보한다.
  상세  = '깊이' 단계. 모집분야·담당업무·자격요건·우대사항·근무시간·업종·상세주소는
          상세페이지에만 있다. 목록의 직무 태그로 대체되지 않는다.
목록에서 끝내면 안 된다. 여기서 모은 URL 을 src/duty_detail.py 가 이어받아 상세를 받는다.

[목록 한 행에 들어 있는 것]  tr.devloopArea
    data-gno                공고번호
    td.tplCo a              회사명
    td.tplTit strong a      공고제목 + /Recruit/GI_Read/{gno}
    p.etc .cell             경력 / 학력 / 지역 / 고용형태 / 급여
    p.dsc                   **직무 키워드 전량** (예: "국제금융, 금융, 은행, 문서관리, …")
    data-gainfo dimension46 **전체 근무지역 목록** ("서울, 경기, 대구, 경북, 부산, 경남")
    span.date               마감일

특히 p.dsc 는 잡코리아가 공고에 붙인 직무 태그라 제목 파싱보다 훨씬 정확하고,
학력 칸은 '대졸 이상 수요' 를 세는 데 그대로 쓰인다.
"""
import json, re, sys
from bs4 import BeautifulSoup
from common import Site, NOW

ROOT = "https://www.jobkorea.co.kr"
# 지역 필터 목록 진입 URL. 이 페이지를 먼저 받아 세션에 검색조건을 넣어야 아래 API 가 동작한다.
ENTRY = ROOT + "/recruit/joblist?menucode=local&localorder=1&local=H000"
# [페이지네이션] URL 파라미터(Page / Page_No)는 먹지 않는다. 몇 페이지를 요청해도 1페이지가 온다.
#   실제로는 페이저가 아래 POST 를 친다. 브라우저 네트워크를 떠서 확인했다.
API = ROOT + "/Recruit/Home/_GI_List/"
PAGE_SIZE = 100          # 기본 40. 100 까지 받아준다
MAX_PAGE = 400

EDU = re.compile(r"학력무관|고졸|초대졸|대졸|석사|박사|대학")
CAREER = re.compile(r"신입|경력|무관")
ETYPE = re.compile(r"정규직|계약직|인턴|파견|아르바이트|위촉|프리랜서|병역특례|파트타임")
PAY = re.compile(r"만원|연봉|월급|시급|회사내규|면접")


def main():
    s = Site("잡코리아부산", ROOT, delay=1.0)
    s.note("지역 필터(local=H000) 전수. 목록에 직무 태그·학력·전체지역이 모두 들어 있다")
    s.extra_cols = ["학력", "급여", "지역표기"]    # 기본 12칸 밖이라 명시하지 않으면 save() 가 버린다
    seen, empty = set(), 0

    s.get(ENTRY)                       # 세션에 검색조건(local=H000) 등록
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": ENTRY}

    for page in range(1, MAX_PAGE + 1):
        try:
            import time as _t
            _t.sleep(s.delay)
            r = s.s.post(API, data={"page": page, "condition[local]": "H000",
                                    "condition[menucode]": "", "direct": 0, "order": 20,
                                    "pagesize": PAGE_SIZE, "tabindex": 0,
                                    "onePick": 0, "confirm": 0, "profile": 0},
                         headers=hdr, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            s.note(f"p{page} 실패: {e}"); break
        trs = soup.select("tr.devloopArea")
        if not trs:
            break
        new = 0
        for tr in trs:
            gno = tr.get("data-gno")
            if not gno or gno in seen:
                continue
            seen.add(gno); new += 1

            co = tr.select_one("td.tplCo a.link")
            tit = tr.select_one("td.tplTit .titBx strong a")
            dsc = tr.select_one("td.tplTit p.dsc")
            cells = [c.get_text(" ", strip=True)
                     for c in tr.select("td.tplTit p.etc span.cell") if c.get_text(strip=True)]

            # .cell 은 개수와 순서가 공고마다 달라서(급여가 없으면 한 칸이 사라진다)
            # 위치가 아니라 내용으로 판별한다.
            career = edu = region = etype = pay = ""
            for c in cells:
                if not career and CAREER.search(c) and "학력" not in c:
                    career = c
                elif not edu and EDU.search(c):
                    edu = c
                elif not etype and ETYPE.fullmatch(c.strip()):
                    etype = c
                elif not pay and PAY.search(c):
                    pay = c
                elif not region:
                    region = c

            # 전체 근무지역 — 목록 셀은 "부산 전지역 외" 로 잘리므로 미리보기 데이터에서 가져온다
            region_all = ""
            btn = tr.select_one("button[data-gainfo]")
            if btn:
                try:
                    region_all = (json.loads(btn["data-gainfo"]) or {}).get("dimension46", "")
                except Exception:
                    pass

            dnode = tr.select_one("span.date")
            deadline = ""
            if dnode:
                m = re.search(r"(\d{2})/(\d{2})", dnode.get_text(" ", strip=True))
                if m:
                    mm = int(m.group(1))
                    # 09월 이전 달은 내년 공고다(스냅샷 2026-09-07 기준)
                    yy = 2026 if mm >= 9 else 2027
                    deadline = f"{yy}-{m.group(1)}-{m.group(2)}"
                elif "상시" in dnode.get_text():
                    deadline = "상시채용"

            s.add(회사명=co.get_text(" ", strip=True) if co else "",
                  공고제목=tit.get("title") or (tit.get_text(" ", strip=True) if tit else ""),
                  직무=re.sub(r"\s+", " ", dsc.get_text(" ", strip=True))[:500] if dsc else "",
                  경력=career, 고용형태=etype,
                  지역=region_all or region,
                  기술스택="", 마감일=deadline,
                  공고URL=f"{ROOT}/Recruit/GI_Read/{gno}",
                  외부원본ID=f"jobkorea:{gno}",
                  학력=edu, 급여=pay, 지역표기=region,
                  수집시각=NOW())
        if new == 0:
            empty += 1
            if empty >= 3:
                break
        else:
            empty = 0
        if page % 10 == 0:
            print(f"    p{page}: 누적 {len(seen):,}", flush=True)
            s.save()
    s.note(f"수집 {len(seen):,}건")
    s.save()

    # 목록만으로 직무를 얼마나 확보했는지
    got = sum(1 for r in s.rows if r.get("직무"))
    edu_got = sum(1 for r in s.rows if r.get("학력"))
    print(f"  직무 태그 확보 {got:,}/{len(s.rows):,}  학력 {edu_got:,}", file=sys.stderr)


if __name__ == "__main__":
    main()
