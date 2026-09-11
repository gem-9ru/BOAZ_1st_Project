"""사람인 부산 지역 전수 수집 (목록).

[정책] robots.txt 는 공고 조회 경로를 막지 않는다.
       `/zf_user/jobs/view/popup` 과 `/zf_user/jobs/relay/recruit-view` 는 **명시적 Allow**,
       `/zf_user/jobs/list/domestic`(목록)도 Disallow 목록에 없다.
       공고 페이지 본문·푸터에 크롤링 금지 고지 없음.
       이용약관의 "얻은 정보의 복사·복제 금지" 는 **개인회원 의무 조항**이며
       비로그인 수집에 그대로 적용되지 않는다. 재배포 시에는 별도 판단이 필요하다.
       → docs/03_정책감사.md ④

[왜 필요한가]
사람인은 그동안 직접 수집하지 않고 부산일자리정보망이 재노출하는 12,214건만 갖고 있었다.
사람인 자체 부산 공고는 13,946건이라 1,700여 건이 비고, 무엇보다
부산일자리정보망 경유분에는 직무 정보가 없다(그쪽 목록이 '기업채용' 만 준다).

[목록 한 행]  div.list_item
    #rec-{rec_idx}                     공고번호
    .company_nm a                      회사명
    .job_tit a[title]                  공고제목
    .job_sector span                   **직무 태그** ("메뉴개발 / 부주방장 / 조리사 / 주방보조 / 주방장")
    .work_place                        근무지
    .career                            "경력무관 · 계약직"
    .education                         학력
    .support_detail .date              마감일
페이지당 100건, `page_count=100` 지원.

상세(모집분야·담당업무·자격요건·근무시간)는 src/duty_detail.py 가 이어받는다.
"""
import re, sys
from bs4 import BeautifulSoup
from common import Site, NOW

ROOT = "https://www.saramin.co.kr"
LIST = (ROOT + "/zf_user/jobs/list/domestic?loc_mcd=106000"
             "&page={}&page_count=100&sort=RL&recruitPage={}")
MAX_PAGE = 300


def main():
    s = Site("사람인부산", ROOT, delay=1.0)
    s.note("robots: 공고 조회 경로 허용(popup/relay 는 명시적 Allow). 금지 고지 없음")
    s.note("loc_mcd=106000(부산) 전수. 사이트 표기 13,946건")
    s.extra_cols = ["학력"]    # 기본 12칸 밖이라 명시하지 않으면 save() 가 버린다
    seen, empty = set(), 0

    for page in range(1, MAX_PAGE + 1):
        try:
            soup = BeautifulSoup(s.get(LIST.format(page, page)).text, "html.parser")
        except Exception as e:
            s.note(f"p{page} 실패: {e}"); break
        items = soup.select("div.list_item")
        if not items:
            break
        new = 0
        for it in items:
            m = re.match(r"rec-(\d+)", it.get("id") or "")
            if not m:
                continue
            rid = m.group(1)
            if rid in seen:
                continue
            seen.add(rid); new += 1

            get = lambda sel: (it.select_one(sel).get_text(" ", strip=True)
                               if it.select_one(sel) else "")
            tit = it.select_one(".job_tit a")
            sectors = [x.get_text(" ", strip=True)
                       for x in it.select(".job_sector span") if x.get_text(strip=True)]
            # '외' 는 "더 있음" 표시라 직무가 아니다
            sectors = [x for x in sectors if x != "외"]

            # .career 는 경력과 고용형태가 한 칸에 붙어 온다.
            #   "경력무관 · 계약직"      2조각
            #   "신입 · 경력 · 정규직"   3조각  ← 앞에서 자르면 고용형태에 '경력' 이 섞인다
            # → 뒤에서부터 고용형태 어휘에 걸리는 조각만 떼어낸다.
            parts = [x.strip() for x in get(".career").split("·") if x.strip()]
            ETYPE = re.compile(r"^(정규직|계약직|인턴|파견직|위촉직|프리랜서|"
                               r"아르바이트|파트타임|병역특례|기간제|연수생)")
            etype = ""
            while parts and ETYPE.match(parts[-1]):
                etype = parts.pop() + ((" · " + etype) if etype else "")
            car = " · ".join(parts)

            date = get(".support_detail .date")
            dl = ""
            dm = re.search(r"(\d{2})\.(\d{2})", date)
            if dm:
                mm = int(dm.group(1))
                dl = f"{2026 if mm >= 9 else 2027}-{dm.group(1)}-{dm.group(2)}"
            elif "상시" in date:
                dl = "상시채용"

            s.add(회사명=get(".company_nm a"),
                  공고제목=(tit.get("title") if tit else "") or get(".job_tit a"),
                  직무=", ".join(sectors)[:400],
                  경력=car, 고용형태=etype,
                  지역=get(".work_place"),
                  기술스택="", 마감일=dl,
                  공고URL=f"{ROOT}/zf_user/jobs/relay/view?rec_idx={rid}",
                  외부원본ID=f"saramin:{rid}",
                  학력=get(".education"),
                  수집시각=NOW())
        if new == 0:
            empty += 1
            if empty >= 3:
                break
        else:
            empty = 0
        if page % 10 == 0:
            print(f"    p{page}: 누적 {len(seen):,}", flush=True); s.save()
    s.note(f"수집 {len(seen):,}건")
    s.save()
    got = sum(1 for r in s.rows if r.get("직무"))
    print(f"  직무 태그 확보 {got:,}/{len(s.rows):,}", file=sys.stderr)


if __name__ == "__main__":
    main()
