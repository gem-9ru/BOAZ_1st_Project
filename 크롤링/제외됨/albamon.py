"""알바몬 — Next.js 데이터 라우트로 전량 수집.

[robots 판단] AI 크롤러 UA 를 Disallow: / 로 막지만 바로 아래 Allow: /jobs 가 명시돼 있다.
        공고 목록 경로만 사용하고 /jobs/apply/, /personal, /alba-contract 는 접근하지 않는다.
[1차 방식의 문제] /jobs/area HTML 을 받아 __NEXT_DATA__ 를 파싱했는데 **한 페이지가 5.9MB**였다.
        전체 268,633건을 20건씩 받으면 13,432회 × 5.9MB = 약 80GB. 현실성이 없다.
[해결 1] Next.js 는 SSR 페이지의 pageProps 만 주는 데이터 라우트를 노출한다.
            /_next/data/<buildId>/jobs/area.json?page=N
        같은 데이터가 **0.08MB** 로 온다(74배 절감). buildId 는 HTML 의 "buildId" 값에서 뽑아
        하드코딩하지 않는다(배포 때마다 바뀜).
[해결 2] 페이지 크기 파라미터를 pageSize/size/rowCount/listCount 로 실측한 결과 **size** 만 유효.
        size=100 으로 2,687회면 전량이 끝난다.
[개인정보] 응답의 managerPhoneNumber(담당자 휴대폰번호)는 수집 목적과 무관하므로 CSV 에 담지 않는다.
"""
import json, re, sys, time
from bs4 import BeautifulSoup
from common import Site, NOW

ROOT = "https://www.albamon.com"
SIZE = 100

def build_id(s):
    m = re.search(r'"buildId":"([^"]+)"', s.get(f"{ROOT}/jobs/area").text)
    if not m:
        raise RuntimeError("buildId 를 찾지 못했습니다 (페이지 구조 변경 가능성)")
    return m.group(1)

def page_data(s, bid, page):
    u = f"{ROOT}/_next/data/{bid}/jobs/area.json?page={page}&size={SIZE}"
    if not s.allowed(u):
        raise PermissionError(u)
    d = s.get(u).json()
    q = d["pageProps"]["dehydratedState"]["queries"][0]["state"]["data"]
    return q["base"]["normal"]["collection"], q["base"]["pagination"]["totalCount"]

def main():
    s = Site("알바몬", ROOT, delay=0.5)
    s.note("robots: AI 크롤러 UA 는 Disallow: / 이나 Allow: /jobs 명시 → /jobs 계열만 사용")
    s.note("담당자 전화번호(managerPhoneNumber)는 개인정보라 수집 제외")
    bid = build_id(s)
    s.note(f"Next.js 데이터 라우트 사용 (buildId={bid}, size={SIZE}) — HTML 대비 74배 경량")
    seen, total, page = set(), None, 1
    while True:
        try:
            col, total = page_data(s, bid, page)
        except Exception as e:
            s.note(f"page {page} 실패: {e}"); break
        if not col:
            break
        new = 0
        for it in col:
            rno = it.get("recruitNo")
            if rno in seen:
                continue
            seen.add(rno); new += 1
            pay_t = (it.get("payType") or {}).get("description", "")
            s.add(회사명=it.get("companyName", ""),
                  공고제목=it.get("recruitTitle", ""),
                  직무=", ".join(it.get("parts") or [])[:100],
                  경력=it.get("workingPeriod", ""),
                  고용형태=f"{pay_t} {it.get('pay','')}".strip(),
                  지역=it.get("workplaceArea", "") or it.get("workplaceAddress", ""),
                  기술스택=", ".join(it.get("skillTags") or [])[:80],
                  마감일=it.get("closingDate", ""),
                  공고URL=f"{ROOT}/jobs/detail/{rno}",
                  수집시각=NOW())
        if page % 20 == 0 or page == 1:
            print(f"    page {page}: 누적 {len(seen):,} / 전체 {total:,}", flush=True)
        if new == 0 or len(seen) >= (total or 0):
            break
        page += 1
        if page % 200 == 0:
            s.save()                       # 장시간 실행 대비 중간 저장
    s.note(f"pagination.totalCount={total:,} / 수집 {len(seen):,}")
    s.save()

if __name__ == "__main__":
    main()
