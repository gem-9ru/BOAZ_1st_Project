"""부산장애인일자리정보망(busanjob4u.net) — 부산광역시 운영 장애인 채용 포털.

[정책] 부산광역시가 운영하는 공공 사이트. 부산일자리정보망(busanjob.net)의 자매 사이트로
       같은 CMS(`view.do?no=&pgMode=index&pageIndex=`)를 쓴다.
       크롤링 금지 고지 없음. robots.txt 규칙 없음.

[왜 넣는가] 규모는 작지만(약 148건) 장애인 채용은 전국 종합 사이트에 잘 안 올라온다.
       무엇보다 **목록에 직무가 명시**돼 있어 직무 데이터로서 품질이 좋다.

[구조]  /view.do?no=122&pgMode=index&pageIndex={N}     페이지당 12건, 13페이지
        li.jobs_panel_item
          .panel_tag .tag_title        채용모집 / 상담 등 구분
          .panel_type .type_title      민간 / 공공
          h5.corp_name                 회사명
          h5.panel_title               공고제목
          dl.location dd               근무지역 (부산 시군구)
          dl.Job dd                    **직무** ("기물세척 및 관리")
          dl.date dd                   모집기간 "2026-09-08 00시 ~ 2026-09-25 00시"
          a onclick="show('2485','CP')" 공고 ID + 유형코드
"""
import re, sys
from bs4 import BeautifulSoup
from common import Site, NOW

ROOT = "https://busanjob4u.net"
LIST = ROOT + "/view.do?no=122&pgMode=index&pageIndex={}"
MAX_PAGE = 60


def main():
    s = Site("부산장애인일자리정보망", ROOT, delay=0.8)
    s.note("부산광역시 운영 장애인 채용 포털. busanjob.net 자매 사이트, 금지 고지 없음")
    s.extra_cols = ["구분", "기관유형"]
    s.s.verify = False              # 인증서 체인이 불완전해 검증에 실패한다(공공 사이트)
    seen, empty = set(), 0

    for page in range(1, MAX_PAGE + 1):
        try:
            soup = BeautifulSoup(s.get(LIST.format(page)).text, "html.parser")
        except Exception as e:
            s.note(f"p{page} 실패: {e}"); break
        items = soup.select("li.jobs_panel_item")
        if not items:
            break
        new = 0
        for li in items:
            a = li.select_one("a[onclick]")
            m = re.search(r"show\('(\d+)'\s*,\s*'([A-Z]+)'\)", a.get("onclick", "") if a else "")
            if not m or m.group(1) in seen:
                continue
            jid, typ = m.group(1), m.group(2)
            seen.add(jid); new += 1

            get = lambda sel: (li.select_one(sel).get_text(" ", strip=True)
                               if li.select_one(sel) else "")
            period = get("dl.date dd")
            deadline = ""
            dm = re.search(r"~\s*(\d{4}-\d{2}-\d{2})", period)
            if dm:
                deadline = dm.group(1)
            elif re.search(r"상시|채용시", period):
                deadline = "상시채용"

            s.add(회사명=get("h5.corp_name"),
                  공고제목=get("h5.panel_title"),
                  직무=get("dl.Job dd")[:200],
                  경력="", 고용형태="",
                  지역=("부산 " + get("dl.location dd")).strip(),
                  기술스택="", 마감일=deadline,
                  공고URL=f"{ROOT}/view.do?no=122&pgMode=show&idx={jid}&type={typ}",
                  외부원본ID=f"busanjob4u:{jid}",
                  구분=get(".panel_tag .tag_title"),
                  기관유형=get(".panel_type .type_title"),
                  수집시각=NOW())
        if new == 0:
            empty += 1
            if empty >= 3:
                break
        else:
            empty = 0
    s.note(f"수집 {len(seen):,}건")
    s.save()
    got = sum(1 for r in s.rows if r.get("직무"))
    print(f"  직무 {got:,}/{len(s.rows):,}", file=sys.stderr)


if __name__ == "__main__":
    main()
