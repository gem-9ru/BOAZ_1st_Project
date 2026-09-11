"""잡플래닛 — 내부 REST API 전량 수집 (딥페이지네이션 캡 우회).

[초기 오진] curl 로 /job 을 치면 403 Cloudflare 라 '봇 차단' 으로 분류했으나,
        일반 브라우저 UA + Accept-Language 를 붙인 Session 으로는 200. curl 헤더 문제였다.
[엔드포인트] GET /api/v3/job/postings?order_by=..&page=N&page_size=200  (인증 불필요)
        브라우저 네트워크 관찰로 특정. 응답 data.recruits[] + data.total_count.

[문제 — 10,000건 하드 캡]
        page_size=200 으로 page 50(=10,000건)까지는 정상이고 page 51 부터 recruits=[] ,
        total_count 까지 0 으로 떨어진다. 전체는 56,139건인데 단일 질의로는 1만 건이 상한.
[해결 — 3축 분할]
        1) city: 실측 결과 유효한 파티션 축(서울 26,208 / 경기 15,242 / … 합계 ≈ 전체).
        2) job_type: city 안에서 3(정규직)·4(계약직)로 다시 갈린다.
        3) order_by: aggressive / recent / deadline 세 정렬이 **서로 다른 결과 순서**를 준다.
           한 슬라이스가 1만을 넘으면(예: 서울+정규직 20,996) 세 정렬로 각각 1만씩 긁어
           합집합을 취해 커버리지를 끌어올린다.
        ※ occupation_level1 / occupation_level2 는 값을 바꿔도 total 이 안 변한다(무시되는 파라미터).
          education_level_id 는 값이 없는 공고가 많아 파티션이 되지 않는다. 둘 다 채택하지 않았다.
[robots] Disallow 는 /apply, /profile*, /users, /wizard/ 등 개인 영역뿐. 이 API 는 허용 범위.
[비고] posting_apply_type 이 jobkorea_inlink 인 건은 원본이 잡코리아 공고이며
       jobkorea_posting_id 를 그대로 갖는다 → 나중 중복제거에서 확정 매칭 키로 쓴다.
"""
from common import Site, NOW

API = "https://www.jobplanet.co.kr/api/v3/job/postings"
PAGE_SIZE = 200
CAP = 10000                      # 서버 측 딥페이지네이션 상한
ORDERS = ["aggressive", "recent", "deadline"]

def total(s, **kw):
    d = s.s.get(API, params={"order_by": "aggressive", "page": 1, "page_size": 1, **kw},
                timeout=30).json().get("data") or {}
    return d.get("total_count") or 0

def harvest(s, seen, order, **kw):
    """한 슬라이스를 지정 정렬로 캡까지 긁는다. 새로 추가된 건수를 반환."""
    added = 0
    for page in range(1, CAP // PAGE_SIZE + 1):
        try:
            d = (s.get(API, params={"order_by": order, "page": page,
                                    "page_size": PAGE_SIZE, **kw}).json() or {}).get("data") or {}
        except Exception as e:
            s.note(f"{kw} {order} page{page} 실패: {e}"); break
        items = d.get("recruits") or []
        if not items:
            break
        for it in items:
            jid = it.get("id")
            if jid in seen:
                continue
            seen.add(jid); added += 1
            occ = it.get("occupation_names") or {}
            s.add(회사명=(it.get("company") or {}).get("name", ""),
                  공고제목=it.get("title", ""),
                  직무=", ".join((occ.get("level2") or occ.get("level1") or []))[:100],
                  경력=it.get("career_text", "") or (it.get("annual") or {}).get("text", ""),
                  고용형태=it.get("job_type", "") or "",
                  지역=", ".join(it.get("cities") or []),
                  기술스택=", ".join(str(x) for x in (it.get("skills") or []))[:100],
                  마감일=str(it.get("end_at") or "")[:10],
                  공고URL=f"https://www.jobplanet.co.kr/job/search?posting_ids={jid}",
                  # 잡플래닛이 잡코리아 공고를 인링크로 재노출하는 경우 원본 공고번호를 그대로 준다.
                  # 중복제거 1단계(확정 매칭)의 근거가 되므로 반드시 보존.
                  외부원본ID=(f"잡코리아:{it['jobkorea_posting_id']}"
                            if it.get("jobkorea_posting_id") else ""),
                  수집시각=NOW())
    return added

def main():
    s = Site("잡플래닛", "https://www.jobplanet.co.kr", delay=0.4)
    if not s.allowed(API):
        s.note("robots.txt 차단 — 중단"); s.save(); return
    s.s.headers.update({"Referer": "https://www.jobplanet.co.kr/job", "Accept": "application/json"})
    grand = total(s)
    s.note(f"전체 {grand:,}건 / 단일 질의 상한 {CAP:,}건 → city × job_type × order_by 분할")

    cities = [c for c in range(1, 26) if 0 < total(s, city=c) < grand]
    s.note(f"유효 city 코드 {len(cities)}개: {cities}")

    seen = set()
    for c in cities:
        ct = total(s, city=c)
        slices = [{"city": c}] if ct <= CAP else [{"city": c, "job_type": j} for j in (3, 4)]
        for sl in slices:
            st = total(s, **sl)
            if not st:
                continue
            orders = ORDERS if st > CAP else ORDERS[:1]
            before = len(seen)
            for o in orders:
                harvest(s, seen, o, **sl)
            print(f"    {sl} total={st:,} orders={len(orders)} → 신규 {len(seen)-before:,} 누적 {len(seen):,}",
                  flush=True)
        s.save()                                   # 지역 단위로 중간 저장
    s.note(f"수집 {len(seen):,} / 사이트 표기 {grand:,} (캡으로 도달 불가한 잔여분 존재)")
    s.save()

if __name__ == "__main__":
    main()
