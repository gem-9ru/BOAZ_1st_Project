"""점핏(Jumpit, 사람인) — 공개 JSON API 수집.
API: https://jumpit-api.saramin.co.kr/api/positions  (인증 불필요)
"""
from common import Site, NOW

API = "https://jumpit-api.saramin.co.kr/api/positions"
CAREER = lambda a, b: ("경력무관" if not a and not b else
                       f"{a}~{b}년" if a and b else f"{a or b}년")

def main():
    s = Site("점핏", "https://jumpit.saramin.co.kr")
    s.note("공개 JSON API 사용 (인증키 불필요)")
    page, total = 1, None
    while True:
        r = s.s.get(API, params={"page": page, "sort": "reg_dt"}, timeout=30)
        r.raise_for_status()
        res = r.json()["result"]
        total = total or res["totalCount"]
        items = res["positions"]
        if not items:
            break
        for p in items:
            s.add(회사명=p.get("companyName", ""),
                  공고제목=p.get("title", ""),
                  직무=p.get("jobCategory", ""),
                  경력=CAREER(p.get("minCareer"), p.get("maxCareer")),
                  고용형태="정규직",
                  지역=", ".join(p.get("locations") or []),
                  기술스택=", ".join(p.get("techStacks") or []),
                  마감일=("상시채용" if p.get("alwaysOpen") else (p.get("closedAt") or "")[:10]),
                  공고URL=f"https://jumpit.saramin.co.kr/position/{p['id']}",
                  수집시각=NOW())
        if len(s.rows) >= total:
            break
        page += 1
        import time; time.sleep(s.delay)
    s.note(f"API totalCount={total}")
    s.save()

if __name__ == "__main__":
    main()
