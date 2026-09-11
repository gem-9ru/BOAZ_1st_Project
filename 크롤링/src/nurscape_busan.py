"""널스케이프 부산 지역 전수 수집.

[왜 다시 받는가]
기존 수집(src/nurscape.py)은 목록 첫 페이지 `/Jobs` 만 읽고 페이지네이션이 없었다.
그래서 314건을 받았는데 그중 **부산이 0건**이었다.
사이트의 지역 필터로 보면 부산만 **49건**이 있다. 첫 페이지에 부산 공고가 안 실렸을 뿐이다.

[경로]  /Jobs/List/AREA_FG/?AREA_FG=140&page={N}     AREA_FG=140 이 부산
        page 1~2 각 20건, page 3 에 9건, page 4 부터 0 → 총 49건
[상세]  job.nurscape.net/Jobs/Details/{id}  — 기관명(og:title)이 여기에만 있다.
        단 '너스케입프로매칭채용' 상품은 기관명을 비공개하므로 빈칸을 유지한다.
"""
import re, sys
from bs4 import BeautifulSoup
from common import Site, NOW, fetch_many

LIST = "https://recruit.nurscape.net/Jobs/List/AREA_FG/?AREA_FG=140&page={}"
DETAIL = "https://job.nurscape.net/Jobs/Details/{}"
MAX_PAGE = 40
SIDO = (r"서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|"
        r"충북|충남|전북|전남|경북|경남|제주|전국|해외")
NONDISCLOSED = re.compile(r"너스케입|프로매칭|NURSCAPE", re.I)
CARDS = {}


def card_text(a):
    p = a
    for _ in range(6):
        p = p.parent
        if p is None:
            return None
        t = p.get_text(" | ", strip=True)
        if 30 < len(t) < 400:
            return t
    return None


def split_card(t, title):
    parts = [x.strip() for x in t.split("|") if x.strip() and x.strip() != "자세히 보기"]
    parts = [p for p in parts if p != title]
    out = {"고용형태": "", "경력": "", "지역": "", "연봉": "", "직무": ""}
    for p in parts:
        if not out["고용형태"] and re.search(r"정규직|계약직|파트타임|인턴|촉탁", p):
            out["고용형태"] = p
        elif not out["경력"] and re.search(r"경력\s*무관|신입|\d+\s*년\s*(이상|이하|차)", p):
            out["경력"] = p
        elif not out["연봉"] and re.search(r"[\d,]+\s*~\s*[\d,]+\s*만원", p):
            out["연봉"] = p
        elif not out["지역"] and re.match(SIDO, p):
            out["지역"] = p
        elif not out["직무"] and (">" in p or len(p) > 4):
            out["직무"] = p
    if not out["지역"]:
        b = re.match(rf"\[({SIDO})[/\]]", title)
        out["지역"] = b.group(1) if b else "부산"    # 부산 슬라이스에서 나온 공고다
    return out


def parse_detail(u, r):
    m = re.search(r"/Jobs/Details/(\d+)", u)
    jid = m.group(1) if m else ""
    soup = BeautifulSoup(r.text, "html.parser")
    og = soup.select_one('meta[property="og:title"]')
    og = og.get("content", "") if og else ""
    seg = [x.strip() for x in og.split(" - ")]
    org = seg[1] if len(seg) > 2 else ""
    if NONDISCLOSED.search(org):
        org = ""
    c = CARDS.get(jid, {})
    return {"회사명": org,
            "공고제목": c.get("title", "") or (seg[2] if len(seg) > 2 else og),
            "직무": c.get("직무", ""), "경력": c.get("경력", ""),
            "고용형태": c.get("고용형태", "") or c.get("연봉", ""),
            "지역": c.get("지역", "부산"), "기술스택": "",
            "마감일": "", "공고URL": u,
            "외부원본ID": f"nurscape:{jid}", "수집시각": NOW()}


def main():
    s = Site("널스케이프부산", "https://recruit.nurscape.net", delay=0.8)
    s.note("지역 슬라이스 AREA_FG=140(부산) 전수. 사이트 표기 49건")
    s.note("기존 수집은 목록 첫 페이지만 읽어 부산이 0건이었다")
    for page in range(1, MAX_PAGE + 1):
        soup = BeautifulSoup(s.get(LIST.format(page)).text, "html.parser")
        links = soup.select('a[href*="/Jobs/Details/"]')
        new = 0
        for a in links:
            m = re.search(r"/Jobs/Details/(\d+)", a.get("href", ""))
            if not m or m.group(1) in CARDS:
                continue
            t = card_text(a)
            if not t:
                continue
            parts = [x.strip() for x in t.split("|")
                     if x.strip() and x.strip() != "자세히 보기"]
            title = parts[0] if parts else ""
            d = split_card(t, title); d["title"] = title
            CARDS[m.group(1)] = d; new += 1
        print(f"    p{page}: 누적 {len(CARDS)}", flush=True)
        if new == 0:
            break
    s.note(f"목록 {len(CARDS)}건 → 기관명 확보를 위해 상세 요청")
    fetch_many(s, [DETAIL.format(i) for i in sorted(CARDS)],
               parse_detail, workers=2, per_sec=1.5, label="Details")
    nd = sum(1 for r in s.rows if not r.get("회사명"))
    s.note(f"기관명 비공개(프로매칭 상품) {nd}건 — 원본에 없어 빈칸 유지")
    s.save()


if __name__ == "__main__":
    main()
