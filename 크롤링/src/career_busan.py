"""커리어 부산 지역 전수 수집.

[왜 다시 받는가]
기존 커리어 수집(src/career.py)은 지역 17개 × 직무 대분류로 슬라이스해 합집합을 취했는데
슬라이스마다 `MAX_PAGE = 12`(× 50건 = 600건) 상한을 걸어두었다.
그 결과 부산은 852건만 남았다. 그런데 사이트가 밝히는 부산은 **5,209건**이다.

원인은 '목록 100건 캡' 이라는 초기 진단을 슬라이스에도 그대로 적용한 것이다.
실측해보니 **지역 슬라이스는 깊게 페이지네이션된다** — page 100 까지 정상,
page 105 부터 소진. 인위적 상한이 84%를 잘라내고 있었다.

[경로]  /jobs/area?i_ac=9&page={N}&i_pagesize=50      i_ac=9 가 부산
[종료]  결과가 비거나 신규 0 이 이어지면 중단. 사이드바 링크 2건이 항상 섞여 나오므로
        tbody tr 기준으로 센다.

상세(모집분야·담당업무·직무키워드)는 src/duty_detail.py 가 이어받는다.
"""
import re, sys
from bs4 import BeautifulSoup
from common import Site, NOW

ROOT = "https://job.career.co.kr"
AC_BUSAN = "9"
SIZE = 50
MAX_PAGE = 200        # 5,209 / 50 ≈ 105 페이지. 넉넉히 두고 신규 0 으로 종료한다.


def main():
    s = Site("커리어부산", ROOT, delay=1.0)
    s.note("지역 슬라이스 /jobs/area?i_ac=9 전수. 사이트 표기 5,209건")
    s.note("기존 커리어 수집은 슬라이스당 MAX_PAGE=12 상한 때문에 852건에서 잘렸다")
    s.extra_cols = ["학력"]
    seen, empty = set(), 0

    for page in range(1, MAX_PAGE + 1):
        try:
            r = s.get(f"{ROOT}/jobs/area?page={page}&i_pagesize={SIZE}&i_ac={AC_BUSAN}")
        except Exception as e:
            s.note(f"p{page} 실패: {e}"); break
        trs = BeautifulSoup(r.text, "html.parser").select("tbody tr")
        if not trs:
            break
        new = 0
        for tr in trs:
            a = tr.select_one('a[href*="/recruit/view/"]')
            tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if not a or len(tds) < 5:
                continue
            m = re.search(r"/recruit/view/(\d+)", a["href"])
            if not m or m.group(1) in seen:
                continue
            gid = m.group(1)
            seen.add(gid); new += 1

            # tds: [회사명, 제목, '경력 2년 학력무관', '정규직 부산 해운대구', '바로지원 ~10/30(금)']
            ea = tds[3].split()
            dm = re.search(r"~\s*(\d{2})/(\d{2})", tds[4])
            deadline = ""
            if dm:
                mm = int(dm.group(1))
                deadline = f"{2026 if mm >= 9 else 2027}-{dm.group(1)}-{dm.group(2)}"
            elif re.search(r"상시|채용시|수시", tds[4]):
                deadline = "상시채용"

            # 경력·학력이 한 칸에 붙어 온다: "경력 2년 학력무관"
            edu = ""
            em = re.search(r"(학력무관|고졸[↑이상]*|초대졸[↑이상]*|대졸[↑이상]*|"
                           r"대학[^\s]*|석사[↑이상]*|박사[↑이상]*)", tds[2])
            if em:
                edu = em.group(1)
            career = tds[2].replace(edu, "").strip() if edu else tds[2]

            # 제목 뒤 해시태그가 이 사이트의 직무 분류다
            tags = re.findall(r"#([^#\s]+)", tds[1])
            title = re.sub(r"\s*#[^#\s]+", "", tds[1]).strip()

            s.add(회사명=tds[0], 공고제목=title,
                  직무=", ".join(dict.fromkeys(tags))[:200],
                  경력=career, 고용형태=ea[0] if ea else "",
                  지역=" ".join(ea[1:])[:40], 기술스택="", 마감일=deadline,
                  공고URL=f"{ROOT}/recruit/view/{gid}",
                  외부원본ID=f"career:{gid}", 학력=edu, 수집시각=NOW())
        if new == 0:
            empty += 1
            if empty >= 3:
                break
        else:
            empty = 0
        if page % 20 == 0:
            print(f"    p{page}: 누적 {len(seen):,}", flush=True); s.save()

    s.note(f"수집 {len(seen):,}건")
    s.save()
    print(f"  직무 태그 {sum(1 for r in s.rows if r.get('직무')):,} / "
          f"학력 {sum(1 for r in s.rows if r.get('학력')):,}", file=sys.stderr)


if __name__ == "__main__":
    main()
