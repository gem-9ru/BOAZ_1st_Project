"""잡부산시대(job.busansidae.com) — 부산 전용 상용 취업 사이트.

[정책] robots.txt 는 `Allow: /` 이고 `/lesson/`·`/resume/` 만 차단한다(이력서·과외).
       채용 경로는 허용. 크롤링 금지 고지 없음.

[왜 넣는가] 규모는 207건으로 작지만 부산 지역 소규모 업체 공고가 많아
       전국 종합 사이트에 안 올라오는 자리가 섞여 있다.

[구조 — 목록이 JS 렌더링]
       정적 HTML 에는 광고 12건만 있다. 실제 목록은 아래 JSON API 로 온다.
         /employ/ajax/json.linead.html?page={N}[&cate={코드}]
         -> {"response":{"data":[...], "totalpage":11, "totalnum":207}}
       페이지당 20건. `cate` 없이 부르면 전체다.

       한 항목이 주는 값(HTML 조각으로 옴 — 태그를 벗겨서 쓴다)
         linead   공고제목        comp   회사명
         area     "부산 영도구"    cate   **직무·업종 서술**
         carr     경력            school 학력
         fdate    마감일          uid    공고번호

       `cate` 필드가 이 사이트의 직무 정보다.
         "일반공장 기계/금속 - 생산/제조 용접/배관 가공 기술직 조공(보.."
       끝이 잘려 오므로(".."), 온전한 값은 상세페이지에서 받는다.

[주의] 페이지 인코딩이 EUC-KR 이다.
[알바] '서비스/알바'(cate=U) 등 알바가 섞여 있다. 여기서 버리지 않고
       고용형태/제목 그대로 두어 정규화 단계의 알바 필터가 판단하게 한다.
"""
import json, re, sys
from bs4 import BeautifulSoup
from common import Site, NOW

ROOT = "http://job.busansidae.com"
API = ROOT + "/employ/ajax/json.linead.html"
MAX_PAGE = 60

strip_tag = lambda v: re.sub(r"\s+", " ", BeautifulSoup(v or "", "html.parser")
                             .get_text(" ", strip=True)).strip()


def main():
    s = Site("잡부산시대", ROOT, delay=0.8)
    s.note("robots Allow:/ (이력서·과외 경로만 차단). 금지 고지 없음")
    s.note("목록은 JS 렌더링 — /employ/ajax/json.linead.html JSON API 사용")
    s.s.headers.update({"X-Requested-With": "XMLHttpRequest",
                        "Referer": ROOT + "/employ/"})
    seen, total = set(), None

    for page in range(1, MAX_PAGE + 1):
        try:
            r = s.get(API, params={"page": page})
            r.encoding = "euc-kr"
            d = json.loads(r.text)["response"]
        except Exception as e:
            s.note(f"p{page} 실패: {e}"); break
        total = total or d.get("totalnum")
        rows = d.get("data") or []
        if not rows:
            break
        for it in rows:
            uid = str(it.get("uid") or "")
            if not uid or uid in seen:
                continue
            seen.add(uid)
            fdate = strip_tag(it.get("fdate"))
            deadline = ""
            dm = re.search(r"(\d{4})[.-](\d{2})[.-](\d{2})", fdate)
            if dm:
                deadline = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
            elif re.search(r"채용시|상시|수시", fdate):
                deadline = "상시채용"
            else:
                dm = re.search(r"(\d{2})[./-](\d{2})", fdate)
                if dm:
                    mm = int(dm.group(1))
                    deadline = f"{2026 if mm >= 9 else 2027}-{dm.group(1)}-{dm.group(2)}"

            s.add(회사명=strip_tag(it.get("comp")),
                  공고제목=strip_tag(it.get("linead")),
                  직무=strip_tag(it.get("cate"))[:300],
                  경력=strip_tag(it.get("carr")),
                  고용형태="",
                  지역=strip_tag(it.get("area")),
                  기술스택="", 마감일=deadline,
                  공고URL=f"{ROOT}/employ/employDetail.html?uid={uid}",
                  외부원본ID=f"busansidae:{uid}",
                  학력=strip_tag(it.get("school")),
                  수집시각=NOW())
    s.extra_cols = ["학력"]
    s.note(f"수집 {len(seen):,}건 (사이트 표기 {total})")
    s.save()
    got = sum(1 for r in s.rows if r.get("직무"))
    print(f"  직무 {got:,}/{len(s.rows):,}", file=sys.stderr)


if __name__ == "__main__":
    main()
