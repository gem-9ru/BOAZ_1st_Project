"""미디어잡 — 공고 상세 JSON-LD 수집.

[문제1] /Recruit/List 는 3.7KB 껍데기만 반환(실제 목록 경로가 아님).
        실제 경로는 /recruit/recruit.htm?cmd=view&rec_idx=N 형태였고,
        홈 화면이 이 링크를 395개 노출한다.
[문제2] robots.txt 에 Crawl-delay: 5 가 선언돼 있다. 이건 명시적 요청이므로
        지켜야 하고, 그만큼 느리다 → RateLimiter 를 0.2 req/s(=5초 간격),
        동시성 1로 고정하고 LIMIT 으로 상한을 둔다.
[파싱]  상세에 schema.org JobPosting JSON-LD 가 있어 공용 파서 재사용.
"""
import re
from bs4 import BeautifulSoup
from common import Site, fetch_many, parse_jobposting_ld, LD_EXTRA_COLS

ROOT = "https://www.mediajob.co.kr"
LIMIT = 220

def parse(u, r):
    """JSON-LD 파싱 + 마감일 보강.

    [보강] JSON-LD 의 validThrough 가 None 인 건이 66% 였다(마감일 채움률 34%).
           상세 본문에 "접수기간 6.08.21 (금) ~ 채용시까지" 형태의 표기가 있어 이를 읽는다.
    """
    row = parse_jobposting_ld(u, r)
    if row:
        # [직무 수정] JSON-LD 에 occupationalCategory 가 없어 공용 파서가 빈칸을 준다.
        #   본문에 "모집업종 종합편성채널 모집직종 PD/방송연출 | AD/조연출 | …" 가 있어
        #   '모집직종' 값을 직무로 쓴다(모집업종은 업종이라 직무가 아니다).
        body = re.sub(r"\s+", " ", BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True))
        m = re.search(r"모집직종\s+(.{2,90}?)\s+(?:담당업무|자격요건|근무지|접수|모집인원)", body)
        if m:
            row["직무"] = re.sub(r"\s*\|\s*", ", ", m.group(1)).strip(" ,|")[:150]
    if row and not row.get("마감일"):
        txt = re.sub(r"\s+", " ", BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True))
        m = re.search(r"접수기간[^\d가-힣]{0,3}([^|]{0,40}?)(?:주의|$|\|)", txt)
        if m:
            seg = m.group(1)
            # "~ 뒤쪽" 이 마감. 날짜(YY.MM.DD) 또는 '채용시까지' 같은 상시 표기.
            tail = seg.split("~")[-1].strip()
            dm = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{1,2})", tail)
            if dm:
                y, mo, d = dm.groups()
                row["마감일"] = f"20{int(y)+20:02d}-{int(mo):02d}-{int(d):02d}" if len(y) <= 2 else tail[:20]
            else:
                row["마감일"] = re.sub(r"까지.*$", "", tail).strip()[:20]
    return row


def main():
    s = Site("미디어잡", ROOT)
    s.extra_cols = LD_EXTRA_COLS    # JSON-LD 가 주는 학력·급여·주소 등
    s.note("robots.txt Crawl-delay: 5 준수 → 0.2 req/s, 동시성 1")
    urls = set()
    for page in [ROOT + "/", ROOT + "/recruit/recruit.htm"]:
        try:
            soup = BeautifulSoup(s.get(page).text, "html.parser")
        except Exception as e:
            s.note(f"목록 실패 {page}: {e}"); continue
        for a in soup.select('a[href*="recruit.htm"]'):
            if "cmd=view" in a["href"]:
                urls.add(a["href"] if a["href"].startswith("http") else ROOT + a["href"])
    urls = sorted(urls)[:LIMIT]
    s.note(f"공고 상세 URL {len(urls)}건 (Crawl-delay 5초 → 약 {len(urls)*5//60}분 소요 예상)")
    fetch_many(s, urls, parse, workers=1, per_sec=0.2, label="recruit")
    s.save()

if __name__ == "__main__":
    main()
