"""원티드 — 공개 REST API(v4/jobs) 수집.

[문제] 원티드는 CloudFront 앞단에서 봇을 강하게 막는다. robots.txt 자체가 403 이고
       UA 를 Googlebot 으로 바꿔도 동일 → robots 규칙을 읽을 수 없다.
[판단] robots.txt 가 '없음(404)' 이 아니라 '접근 불가(403)' 이므로 규칙 미확인 상태다.
       다만 공고 목록 페이지(/wdlist)와 그 페이지가 쓰는 공개 API 는 인증 없이 200 을
       반환하는 공개 엔드포인트라 이것만 사용하고, 상세/지원 경로는 건드리지 않는다.
       (README 의 주의사항에 이 판단 근거를 기록해 둔다.)
[엔드포인트] GET /api/v4/jobs?country=kr&job_sort=job.latest_order&locations=all
                     &years=-1&limit=20&offset=N
             응답에 links.next 가 있어 offset 페이지네이션이 그대로 가능.
[주의] Referer 를 붙이지 않으면 CloudFront 가 403 을 주는 경우가 있어 항상 지정한다.

[직무 수정] 1차 수집에서 직무 칸에 company.industry_name(= '제조', '판매, 유통')을 넣었는데
       그건 회사의 **업종**이지 공고의 직무가 아니다.
       실제 직무는 category_tags = [{parent_id:507, id:559}, …] 인데 이름이 없다.
       이름 매핑 엔드포인트를 8개 시도했으나 전부 404, JS 번들에도 없었다.
       대신 목록 URL 이 /wdlist/{부모}/{자식} 구조이고 그 페이지 <title> 이
       "PM·PO 채용 정보 | 원티드" 처럼 카테고리명을 담고 있어, 등장하는 조합만
       한 번 조회해 wanted_categories.json 으로 만들어 두고 그걸 참조한다.
"""


def duty_of(it):
    """category_tags(id) → 직무명. 매핑에 없으면 코드를 남겨 추적 가능하게 한다."""
    out = []
    for tg in (it.get("category_tags") or []):
        cid = str(tg.get("id") or "")
        pid = str(tg.get("parent_id") or "")
        nm = CATMAP.get(cid)
        if nm:
            out.append(nm)
        elif cid:
            out.append(f"코드{pid}/{cid}")
    return ", ".join(dict.fromkeys(out))[:150]
import json
from pathlib import Path
from common import Site, NOW

# 직무 카테고리 id → 이름. build_wanted_categories 로 생성해 둔 표(wanted_categories.json).
CATMAP = {}
_p = Path(__file__).with_name("wanted_categories.json")
if _p.exists():
    CATMAP = json.loads(_p.read_text(encoding="utf-8"))

API = "https://www.wanted.co.kr/api/v4/jobs"
LIMIT, MAX_PAGES = 100, 120   # 1차 30페이지(3,000건) 상한 → 상향

def main():
    s = Site("원티드", "https://www.wanted.co.kr", delay=1.0)
    s.note("robots.txt 가 403 으로 접근 불가 → 공개 API(/api/v4/jobs)만 사용, 상세/지원 경로 미접근")
    s.s.headers.update({"Referer": "https://www.wanted.co.kr/wdlist",
                        "Accept": "application/json"})
    seen = set()
    for page in range(MAX_PAGES):
        r = s.get(API, params={"country": "kr", "job_sort": "job.latest_order",
                               "locations": "all", "years": -1,
                               "limit": LIMIT, "offset": page * LIMIT})
        d = r.json()
        items = d.get("data") or []
        if not items:
            break
        new = 0
        for it in items:
            jid = it.get("id")
            if jid in seen:
                continue
            seen.add(jid); new += 1
            comp = it.get("company") or {}
            addr = it.get("address") or {}
            s.add(회사명=comp.get("name", ""),
                  공고제목=it.get("position", "") or it.get("title", ""),
                  직무=duty_of(it),
                  경력=str(it.get("annual_from") or "") + ("~" + str(it.get("annual_to"))
                        if it.get("annual_to") else ""),
                  고용형태="",
                  지역=" ".join(x for x in [addr.get("country"), addr.get("location")]
                                if isinstance(x, str)),
                  기술스택=", ".join(t.get("title", "") for t in (it.get("skill_tags") or []))[:120],
                  마감일=str(it.get("due_time") or "")[:10],
                  공고URL=f"https://www.wanted.co.kr/wd/{jid}",
                  수집시각=NOW())
        print(f"    offset {page*LIMIT}: {len(items)}건 new={new} 누적={len(seen)}")
        if not (d.get("links") or {}).get("next"):
            break
    s.save()

if __name__ == "__main__":
    main()
