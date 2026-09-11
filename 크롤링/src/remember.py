"""리멤버 커리어 — sitemap-jobs.xml + 상세 JSON-LD 수집.

[진입점] robots.txt 가 sitemap-jobs.xml 을 직접 공개(Allow: /job/). 공고 URL 13,502건.
[문제]   /job_postings/ 와 /job/private-positions/ 는 robots Disallow → Site.allowed()
         가 자동으로 걸러낸다(fetch_many 의 skip 카운트).
[해결]   상세 페이지에 schema.org JobPosting JSON-LD 가 있어 공용 파서 재사용.
[부하]   전량 13,502건. 초당 3건 고정 + 체크포인트로 중단 시 이어받기.
"""
import json
import re
from bs4 import BeautifulSoup
from common import Site, fetch_many_ckpt, parse_jobposting_ld, LD_EXTRA_COLS


def parse(u, r):
    """JSON-LD 파싱 + 경력 보강.

    [보강] JSON-LD 의 experienceRequirements 가 None 인 건이 9%(1,131건) 있었다.
           본문에는 '경력직' / '신입' 같은 표기가 남아 있어 이를 폴백으로 읽는다.
    [보강2] 마감일도 validThrough 가 빈 문자열인 건이 77% 였다. 처음엔 "원본에 없음" 으로
           결론냈지만, 마감일이 있는 공고와 없는 공고의 상세 본문을 비교해 보니
             validThrough='2026-09-25' → 본문 "마감일 2026.09.25"
             validThrough=''           → 본문 "채용 시 마감"
           즉 결손이 아니라 **상시채용** 이었다. 빈칸으로 두지 않고 본문 표기를 그대로 넣는다.
    """
    row = parse_jobposting_ld(u, r)
    if row:
        # [직무·기술스택 수정] 공용 파서는 JSON-LD 만 보는데 리멤버는 occupationalCategory 가 없어
        #   직무가 description(업무 설명 산문)으로 채워지고 있었다.
        #   실제 직무 분류는 __NEXT_DATA__ 안에 구조화돼 있다:
        #     jobCategories: [{"id":221,"level1":"리서치·분석","level2":"시장조사"}, …]
        #     skills:        [{"name":"마케팅 리서치"}, {"name":"소비자조사"}, …]
        #   전자를 직무로, 후자를 기술스택으로 옮긴다(기술스택도 0% 였다).
        nd = BeautifulSoup(r.text, "html.parser").select_one("#__NEXT_DATA__")
        if nd and nd.string:
            try:
                blob = nd.string
                mcat = re.search(r'"jobCategories"\s*:\s*(\[.*?\])', blob, re.S)
                if mcat:
                    cats = json.loads(mcat.group(1))
                    names = []
                    for c in cats:
                        l1, l2 = c.get("level1", ""), c.get("level2", "")
                        names.append(f"{l1} > {l2}" if l1 and l2 else (l2 or l1))
                    row["직무"] = ", ".join(dict.fromkeys(n for n in names if n))[:150]
                msk = re.search(r'"skills"\s*:\s*(\[.*?\])', blob, re.S)
                if msk:
                    sk = [x.get("name", "") for x in json.loads(msk.group(1)) if x.get("name")]
                    row["기술스택"] = ", ".join(dict.fromkeys(sk))[:150]
            except Exception:
                pass
        if not row.get("직무"):
            row["직무"] = ""      # description 을 직무로 남기지 않는다
    if row and (not row.get("경력") or not row.get("마감일")):
        txt = re.sub(r"\s+", " ", BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True))
        if not row.get("경력"):
            m = re.search(r"(경력\s*무관|신입\s*[·/]?\s*경력|경력직|신입|"
                          r"\d+년\s*~\s*\d+년\s*차|\d+년\s*이상)", txt)
            if m:
                row["경력"] = m.group(1).strip()[:30]
        if not row.get("마감일"):
            m = re.search(r"(채용\s*시\s*마감|상시\s*채용|수시\s*채용)", txt)
            if m:
                row["마감일"] = re.sub(r"\s+", " ", m.group(1))
    return row

SITEMAP = "https://career.rememberapp.co.kr/sitemap-jobs.xml"

def main():
    s = Site("리멤버커리어", "https://career.rememberapp.co.kr")
    s.extra_cols = LD_EXTRA_COLS    # JSON-LD 가 주는 학력·급여·주소 등
    urls = re.findall(r"<loc>([^<]+)</loc>", s.get(SITEMAP).text)
    # [변경] 표본 900건 → 전량. 중단 대비 체크포인트(JSONL)로 이어받는다.
    s.note(f"sitemap-jobs.xml 공고 URL {len(urls):,}건 전량 수집")
    fetch_many_ckpt(s, urls, parse, workers=4, per_sec=3.0, label="posting")
    s.save()

if __name__ == "__main__":
    main()
