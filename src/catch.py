"""캐치(CATCH) — 내부 REST API 수집.

[문제] 캐치는 Nuxt SPA 라 정적 HTML 에 공고가 없다. /api/v1.0/recruit,
       /api/v1.0/recruit/list 등 흔한 경로는 전부 404.
[해결] 브라우저로 실제 페이지를 열어 네트워크 요청을 관찰해 실 엔드포인트를 특정:
         GET /api/v1.0/recruit/information/getRecruitList
             ?Keyword=&JobCode=&Sido=&Career=&...&curpage=N&pageSize=30&onRecruitYN=Y
       응답은 {recruitData:[...], intTotalRecordCount:N} 형태의 JSON.
[robots] robots.txt 가 막는 API 는 /api/v1.0/common, /api/v1.0/product,
       /api/v1.0/recruit/detail/log, /api/v1.0/recruit/log 4개뿐이고
       getRecruitList 는 Allow: / 범위 안 → Site.allowed() 로 확인 후 요청.
"""
from common import Site, NOW

API = "https://www.catch.co.kr/api/v1.0/recruit/information/getRecruitList"
PAGE_SIZE, MAX_PAGE = 30, 120   # 1차 40페이지(1,200건) 상한 → 전체 3,201건 커버하도록 상향
BASE = {"Keyword": "", "JobCode": "", "Sido": "", "Career": "", "JCode": "", "Size": "",
        "EduLevel": "", "WorkPosition": "", "CompID": "", "GroupCode": "", "Sort": "0",
        "pageSize": PAGE_SIZE, "onRecruitYN": "Y"}

def main():
    s = Site("캐치", "https://www.catch.co.kr", delay=1.0)
    if not s.allowed(API):
        s.note("robots.txt 차단 — 중단"); s.save(); return
    s.note("SPA라 HTML 파싱 불가 → 브라우저 네트워크 관찰로 찾은 내부 API 사용")
    seen, total = set(), None
    for page in range(1, MAX_PAGE + 1):
        r = s.get(API, params={**BASE, "curpage": page})
        d = r.json()
        total = total or d.get("intTotalRecordCount")
        items = d.get("recruitData") or []
        if not items:
            break
        new = 0
        for it in items:
            rid = it.get("RecruitID")
            if rid in seen:
                continue
            seen.add(rid); new += 1
            # [보강] ExperienceText/Range 가 null 인 20% 는 CareerGubunCode·NewbieText 에
            #        '신입' 이 들어있다. 이걸 폴백으로 쓰면 경력 채움률 83% → 100%.
            exp = " ".join(x for x in [it.get("ExperienceText"), it.get("ExperienceRange")] if x)
            if not exp:
                exp = it.get("CareerGubunCode") or it.get("NewbieText") or ""
            # [보강] ApplyEndTimeHide 가 true 인데 ApplyEndCode 가 null 이면 마감일이 빈칸이 됐다.
            #        ApplyEndDatetime 은 100% 존재하므로 최종 폴백으로 사용.
            end = (it.get("ApplyEndCode") if it.get("ApplyEndTimeHide") else None) \
                  or str(it.get("ApplyEndDatetime") or "")[:10] or it.get("ApplyEndCode") or ""
            s.add(회사명=it.get("CompName", ""),
                  공고제목=it.get("RecruitTitle", ""),
                  직무=it.get("Depth", "") or "",
                  경력=exp,
                  고용형태=it.get("GubunCode", "") or "",
                  지역=it.get("WorkArea", "") or "",
                  기술스택="",
                  마감일=end,
                  공고URL=f"https://www.catch.co.kr/Comp/CompDetail/{it.get('CompID')}/Recruit/{rid}",
                  수집시각=NOW())
        print(f"    page {page}: {len(items)}건 new={new} 누적={len(seen)} / 전체 {total}")
        if new == 0 or len(seen) >= (total or 0):
            break
    s.note(f"API intTotalRecordCount={total}")
    s.save()

if __name__ == "__main__":
    main()
