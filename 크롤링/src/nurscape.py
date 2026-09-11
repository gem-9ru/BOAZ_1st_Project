"""널스케이프(너스케입) 커리어 — 간호 직군 채용공고.

[경로] 본 도메인 www.nurscape.net 은 /job, /jobs, /recruit 전부 404.
       메인의 '커리어' 링크가 recruit.nurscape.net/Jobs 를 가리키고,
       상세는 또 다른 서브도메인 job.nurscape.net 이다. 서브도메인 3개로 쪼개진 구조.

[문제 1 — 카드형 목록] 표가 없고 카드 클래스가 상품 유형별로 갈린다(promatching_list 등).
       클래스를 하드코딩하면 일부만 잡히므로, 상세 링크에서 조상을 거슬러 올라가며
       '적당한 길이의 텍스트 블록' 을 카드로 인식한다.

[문제 2 — 카드 필드 수가 다르다]
       4필드형: 제목 | 직무 | 지역 | 연봉
       6필드형: 제목 | 고용형태 | 경력 | 지역 | 연봉 | 직무
       위치 기반으로 자르면 어긋나므로 **토큰의 성격으로 판별**한다
       (정규직/계약직 → 고용형태, 'N년 이상' → 경력, 시도명 → 지역, 'N~N만원' → 연봉).

[문제 3 — 회사명이 목록에 없다]  1차 수집에서 회사명 채움률이 0% 였다.
       회사명은 중복제거의 핵심 키라 이대로면 312건이 통합 대상에서 빠진다.
       → 상세 페이지 og:title 이 "너스케입 커리어 - {기관명} - {제목}" 형식이라 여기서 뽑는다.
       단 '너스케입프로매칭채용' 상품은 병원명을 비공개로 하므로 그때는 빈칸을 유지하고
       비공개임을 기록한다(없는 값을 만들어내지 않는다).
"""
import re
from bs4 import BeautifulSoup
from common import Site, NOW, fetch_many

LIST = "https://recruit.nurscape.net/Jobs"
DETAIL = "https://job.nurscape.net/Jobs/Details/{}"
SIDO = (r"서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|"
        r"충북|충남|전북|전남|경북|경남|제주|전국|해외")
NONDISCLOSED = re.compile(r"너스케입|프로매칭|NURSCAPE", re.I)

def card_text(a):
    """상세 링크에서 위로 올라가며 카드 단위 텍스트 블록을 찾는다."""
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
    """카드 텍스트를 토큰 성격으로 분해 (문제2 대응)."""
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
        out["지역"] = b.group(1) if b else ""
    return out

CARDS = {}          # 공고ID -> 목록에서 얻은 필드

def parse_detail(u, r):
    m = re.search(r"/Jobs/Details/(\d+)", u)
    jid = m.group(1) if m else ""
    soup = BeautifulSoup(r.text, "html.parser")
    og = (soup.select_one('meta[property="og:title"]') or {})
    og = og.get("content", "") if og else ""
    # "너스케입 커리어 - {기관명} - {제목}"
    seg = [x.strip() for x in og.split(" - ")]
    org = seg[1] if len(seg) > 2 else ""
    if NONDISCLOSED.search(org):
        org = ""                       # 병원명 비공개 상품 → 값을 만들지 않는다
    c = CARDS.get(jid, {})
    return {"회사명": org,
            "공고제목": c.get("title", "") or (seg[2] if len(seg) > 2 else og),
            "직무": c.get("직무", ""), "경력": c.get("경력", ""),
            "고용형태": c.get("고용형태", "") or c.get("연봉", ""),
            "지역": c.get("지역", ""), "기술스택": "",
            "마감일": "", "공고URL": u, "수집시각": NOW()}

def main():
    s = Site("널스케이프", "https://recruit.nurscape.net", delay=0.8)
    s.note("목록(recruit.) + 상세(job.) 서브도메인 조합")
    soup = BeautifulSoup(s.get(LIST).text, "html.parser")
    for a in soup.select('a[href*="/Jobs/Details/"]'):
        m = re.search(r"/Jobs/Details/(\d+)", a.get("href", ""))
        if not m or m.group(1) in CARDS:
            continue
        t = card_text(a)
        if not t:
            continue
        parts = [x.strip() for x in t.split("|") if x.strip() and x.strip() != "자세히 보기"]
        title = parts[0] if parts else ""
        d = split_card(t, title); d["title"] = title
        CARDS[m.group(1)] = d
    s.note(f"목록에서 {len(CARDS)}건 카드 확보 → 회사명 확보를 위해 상세 요청")
    urls = [DETAIL.format(i) for i in sorted(CARDS)]
    fetch_many(s, urls, parse_detail, workers=2, per_sec=1.5, label="Details")
    nd = sum(1 for r in s.rows if not r.get("회사명"))
    s.note(f"회사명 비공개(프로매칭 상품) {nd}건 — 원본에 병원명이 없어 빈칸 유지")
    s.save()

if __name__ == "__main__":
    main()
