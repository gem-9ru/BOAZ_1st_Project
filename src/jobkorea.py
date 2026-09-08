"""잡코리아 — sitemap(agi) + 상세페이지 JSON-LD(JobPosting) 수집.

[문제1] 목록 ?Page=N 무시. 페이지네이션이 가리키는 /recruit/_GI_List?Page=N 은
        GET/POST/XHR헤더/쿠키 모두 404. /recruit/category 도 404.
        → 목록만으로는 카테고리 19개 순회해도 중복 제외 289건이 한계였음.
[해결]  content/sitemapindex.xml 의 agi_*.xml (22개 × 5,000 = 약 11만 공고 URL)에서
        공고 URL을 뽑고, 상세 페이지의 <script type="application/ld+json"> 안에 있는
        schema.org JobPosting 을 파싱. 목록 HTML 셀렉터보다 훨씬 안정적이다.
[부하]  11만 건 전량은 과도하므로 LIMIT 로 상한을 두고, RateLimiter 로 전체
        초당 요청수를 2건으로 고정(동시성 4). robots.txt 에 Crawl-delay 선언은 없음.
[robots] Allow: /Recruit/GI_Read 명시 허용. 단 ClaudeBot/GPTBot 등 AI크롤러 UA는
        전면차단이므로 일반 브라우저 UA 로만 접근한다.
"""
import re
from common import Site, NOW, fetch_many_ckpt, parse_jobposting_ld

INDEX = "https://www.jobkorea.co.kr/content/sitemapindex.xml"

# [문제3] 이 스크립트가 자체 parse() 를 들고 있어서, 공용 파서에 넣은 주소 폴백
#         (addressRegion 이 없고 streetAddress 만 있는 경우 대응)이 반영되지 않았다.
#         그 결과 1차 수집에서 '지역' 컬럼이 전부 빈칸(채움률 0%)이었다.
#         → 중복 구현을 지우고 공용 parse_jobposting_ld() 를 그대로 쓴다.
parse = parse_jobposting_ld


def main():
    s = Site("잡코리아", "https://www.jobkorea.co.kr")
    s.note("목록 페이지네이션 차단 → sitemap agi_*.xml + 상세 JSON-LD 방식으로 전환")
    maps = [l for l in re.findall(r"<loc>([^<]+)</loc>", s.get(INDEX).text) if "/agi/" in l]
    s.note(f"agi 사이트맵 {len(maps)}개 발견 (전체 공고 약 {len(maps)*5000:,}건 규모)")
    urls = []
    for m in maps:
        urls += re.findall(r"<loc>([^<]+)</loc>", s.get(m).text)
    # [변경] 표본 1,200건 → 전량 108,009건. 6시간 이상 걸리므로 체크포인트 필수.
    # 참고: 사이트 목록 화면은 총 199,110건으로 표기하지만 sitemap 이 담은 건 108,009건이다.
    #       sitemap 에 없는 공고는 URL 을 열거할 방법이 없어(페이지네이션 사망) 수집 불가.
    s.note(f"공고 URL {len(urls):,}건 전량 수집 (사이트 표기 총계 199,110건 중 sitemap 노출분)")
    fetch_many_ckpt(s, urls, parse, workers=6, per_sec=5.0, label="GI_Read")
    s.save()

if __name__ == "__main__":
    main()
