"""직무 상세 보강 — 사이트별 상세페이지에서 '직무를 설명하는' 필드를 추가 수집한다.

[왜]
기존 스키마의 `직무` 한 칸으로는 무슨 일을 하는 자리인지 알 수 없다.
사이트 대부분이 상세페이지에 아래를 갖고 있는데 수집하지 않고 있었다.

    모집분야   자리 이름 (예: "5톤화물차,화물차운전,화물운송,운전직")
    담당업무   실제 하는 일 (예: "데스크 수납 예약 해피콜 리콜 관리")
    자격요건 / 우대사항
    직급직책 / 근무형태 / 근무시간 / 급여 / 업종 / 상세주소

근무시간(교대·야간 여부)은 중복 판정에도 쓰인다. 같은 회사·같은 직무라도
'야간전담'과 '주간'은 다른 공고이기 때문이다.

[범위] 부산 지역 공고만. 전국 157,007건 전체에 붙이려면 20만 요청이 필요하다.

[사이트별 경로]
  사람인   /zf_user/jobs/view/popup?rec_idx=  — robots.txt 가 명시적으로 Allow 한 경로.
           rec_idx 는 부산일자리정보망 상세의 wantedInfoUrl 에서 얻는다
  잡코리아  GI_Read 상세. React 렌더지만 SSR 된 HTML 에
           data-sentry-component="RecruitmentItem" 블록으로 라벨/값이 들어 있다
  원티드   /api/v4/jobs/{id} — detail.main_tasks / requirements / preferred_points
  그 외    상세 본문 텍스트에서 라벨 기반 절편 추출
"""
import csv, json, re, sys, time
from pathlib import Path
from bs4 import BeautifulSoup
from common import Site, DATA, NOW, fetch_many_ckpt

BASE = Path(__file__).resolve().parent.parent
BUSAN = BASE / "부산" / "부산_공고_원본.csv"

COLS = ["공고URL", "모집분야", "직무키워드", "담당업무", "자격요건", "우대사항", "직급직책",
        "근무형태", "근무시간", "급여", "업종", "직종", "상세주소",
        "모집인원", "학력", "수집시각"]

CLEAN = lambda t: re.sub(r"\s+", " ", (t or "")).strip()


def blank(url):
    r = {c: "" for c in COLS}
    r["공고URL"] = url
    r["수집시각"] = NOW()
    return r


def _has(r):
    return any(r[c] for c in COLS if c not in ("공고URL", "수집시각"))


def sanitize(r):
    """라벨 파싱이 옆 칸 값을 물고 오는 경우를 걷어낸다."""
    # 모집인원은 숫자 아니면 값이 아니다 ("지원자격" 같은 다음 라벨을 물고 오는 일이 있다)
    if r["모집인원"] and not re.search(r"\d|[○0-9]", r["모집인원"]):
        r["모집인원"] = ""
    # 업종은 짧은 분류명이다. 문장이면 회사 소개문을 물고 온 것
    u = r["업종"]
    if u and (len(u) > 60 or re.search(r"입니다|습니다|공고|채용 \|", u)):
        r["업종"] = ""
    return r


# ── 라벨 기반 본문 절편 추출 ───────────────────────────────────────────────
# "주요업무 ... 자격요건 ... 우대사항 ..." 처럼 라벨이 순서대로 나오는 본문에서
# 다음 라벨이 나오기 전까지를 값으로 본다.
SECTION = {
    "담당업무": r"주요\s?업무|담당\s?업무|직무\s?내용|업무\s?내용|수행\s?업무",
    "자격요건": r"자격\s?요건|지원\s?자격|필수\s?요건|자격\s?조건",
    "우대사항": r"우대\s?사항|우대\s?조건|이런\s?분",
}
STOP = (r"주요\s?업무|담당\s?업무|직무\s?내용|업무\s?내용|수행\s?업무|"
        r"자격\s?요건|지원\s?자격|필수\s?요건|자격\s?조건|"
        r"우대\s?사항|우대\s?조건|복지|혜택|근무\s?조건|채용\s?절차|전형|"
        r"접수\s?기간|제출\s?서류|접수\s?방법|유의\s?사항|기타\s?사항|모집\s?분야|"
        # 사이트 UI 문구 — 값이 아니라 안내문이라 여기서 끊는다
        r"핵심\s?역량|이\s?기업과\s?나의|로그인\s?하고|AI\s?추천공고|궁금해요|"
        r"관련\s?키워드|이슈\s?채용정보|오늘\s?본\s?공고|스크랩\s?공고|"
        r"지도보기|페이스북|인쇄하기|기업정보|근무환경|복리후생")


def sections(text, row, limit=1200):
    """라벨이 순서대로 나오는 본문에서 각 구간을 잘라낸다.

    첫 매칭만 쓰면 안 된다. 리멤버처럼 본문 앞에 '담당업무 자격요건 우대사항' 목차
    앵커가 먼저 나오는 사이트가 있어서, 첫 매칭을 잡으면 값 대신 다른 라벨들이 들어온다.
    → 라벨 위치를 전부 모아 '다음 라벨 직전까지'를 후보로 삼고, 그중 가장 긴 것을 쓴다.
      목차 앵커는 라벨끼리 붙어 있어 구간이 거의 비므로 자연히 탈락한다.
    """
    marks = []                      # (위치, 끝, 컬럼|None)
    for m in re.finditer(rf"(?:{STOP})\s*[:：]?", text):
        col = None
        head = m.group(0)
        for c, pat in SECTION.items():
            if re.fullmatch(rf"(?:{pat})\s*[:：]?", head):
                col = c; break
        marks.append((m.start(), m.end(), col))
    if not marks:
        return
    best = {}
    for i, (_, end, col) in enumerate(marks):
        if not col or row[col]:
            continue
        nxt = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        val = CLEAN(text[end:nxt])[:limit]
        if len(val) >= 10 and len(val) > len(best.get(col, "")):
            best[col] = val
    for col, val in best.items():
        row[col] = val


# ── 사이트별 파서 ─────────────────────────────────────────────────────────
def p_saramin(url, resp):
    s = BeautifulSoup(resp.text, "html.parser")
    for t in s(["script", "style"]):
        t.decompose()
    r = blank(url)
    txt = re.sub(r"\n{2,}", "\n", s.get_text("\n", strip=True))
    # 핵심 정보 블록: "경력 / 학력 / 근무형태 / 급여 / 직급/직책 / 근무지역" 이 줄 단위로 온다
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    KEY = {"경력": None, "학력": "학력", "근무형태": "근무형태", "급여": "급여",
           "직급/직책": "직급직책", "근무지역": "상세주소"}
    for i, l in enumerate(lines[:-1]):
        col = KEY.get(l)
        if col and not r[col]:
            r[col] = CLEAN(lines[i + 1])[:200]
    m = re.search(r"모집분야\s*\n(.{2,150}?)\n", txt)
    if m:
        r["모집분야"] = CLEAN(m.group(1))[:200]
    sections(re.sub(r"\s+", " ", txt), r)
    return sanitize(r) if _has(r) else None


def p_jobkorea(url, resp):
    s = BeautifulSoup(resp.text, "html.parser")
    r = blank(url)
    MAP = {"모집분야": "모집분야", "모집인원": "모집인원", "고용형태": "근무형태",
           "직급/직책": "직급직책", "급여": "급여", "근무시간": "근무시간",
           "근무지주소": "상세주소", "학력": "학력", "산업(업종)": "업종"}
    for d in s.select('[data-sentry-component="RecruitmentItem"],'
                      '[data-sentry-component="RecruitmentField"]'):
        sp = d.find_all("span")
        if not sp:
            continue
        lab = sp[0].get_text(" ", strip=True)
        col = MAP.get(lab)
        if not col or r[col]:
            continue
        val = CLEAN(d.get_text(" ", strip=True))[len(lab):].strip(" :·")
        # 근무시간은 같은 문장이 두 번 반복돼 오는 경우가 있다
        half = len(val) // 2
        if half > 8 and val[:half].strip() == val[half:].strip():
            val = val[:half].strip()
        if val:
            r[col] = val[:300]
    txt = re.sub(r"\s+", " ", s.get_text(" ", strip=True))
    m = re.search(r"산업\(업종\)\s*(.{2,60}?)\s*(?:지도보기|위치|사원수|기업구분)", txt)
    if m and not r["업종"]:
        r["업종"] = CLEAN(m.group(1))
    sections(txt, r)
    return sanitize(r) if _has(r) else None


def p_wanted(url, resp):
    try:
        d = (resp.json() or {}).get("job") or {}
    except Exception:
        return None
    det = d.get("detail") or {}
    r = blank(url)
    r["모집분야"] = CLEAN(d.get("position"))[:200]
    r["담당업무"] = CLEAN(det.get("main_tasks"))[:1200]
    r["자격요건"] = CLEAN(det.get("requirements"))[:1200]
    r["우대사항"] = CLEAN(det.get("preferred_points"))[:1200]
    r["업종"] = CLEAN((d.get("company") or {}).get("industry_name"))
    r["상세주소"] = CLEAN((d.get("address") or {}).get("full_location"))[:200]
    return sanitize(r) if _has(r) else None


def p_saramin_detail(url, resp):
    """사람인 상세요강 — /zf_user/jobs/relay/view-detail?rec_idx=

    [엔드포인트 선택] 같은 상세요강을 주는 경로가 둘 있다.
        /zf_user/jobs/view/popup      431KB  (robots 명시적 Allow, 그러나 전체 페이지 껍데기 포함)
        /zf_user/jobs/relay/view-detail 9KB  (robots Disallow 아님, 상세요강 본문만)
    13,946건을 받아야 하므로 48배 가벼운 view-detail 을 쓴다. 서버 부하도 그만큼 적다.

    [모집인원] 사람인은 별도 필드가 없다. 정형 템플릿 공고만
        모집분야
        [최고대우] … 데스크사원
        (1명)                      ← 모집분야 바로 뒤 괄호
    형태로 붙는다. 자유 서술·이미지 공고는 인원이 아예 없어서 빈칸으로 남는다.
    본문 아무 데서나 'N명' 을 긁으면 "경력 3년 이상 25명 지원" 같은 걸 인원으로
    오인하므로 반드시 모집분야 직후만 본다.
    """
    s = BeautifulSoup(resp.text, "html.parser")
    for t_ in s(["script", "style"]):
        t_.decompose()
    r = blank(url)
    txt = re.sub(r"\n{2,}", "\n", s.get_text("\n", strip=True))

    m = re.search(r"모집분야\s*\n(.{2,200}?)\n\s*\((\d{1,4})\s*명\)", txt)
    if m:
        r["모집분야"] = CLEAN(m.group(1))[:200]
        r["모집인원"] = m.group(2)
    else:
        m2 = re.search(r"모집분야\s*\n(.{2,200}?)\n", txt)
        if m2:
            r["모집분야"] = CLEAN(m2.group(1))[:200]

    # 근무조건 블록: "• 고용형태 : 정규직 / • 급여 : … / • 근무지 : …"
    for col, pat in [("근무형태", r"고용형태"), ("급여", r"급여"), ("상세주소", r"근무지")]:
        mm = re.search(rf"[•ㆍ·]\s*{pat}\s*[:：]\s*\n?(.{{2,120}}?)\n", txt)
        if mm and not r[col]:
            r[col] = CLEAN(mm.group(1))[:200]

    sections(re.sub(r"\s+", " ", txt), r)
    return sanitize(r) if _has(r) else None


def p_text(url, resp):
    """라벨 기반 범용 파서 — 커리어·캐치·리멤버·점핏·링커리어·잡알리오 등."""
    s = BeautifulSoup(resp.text, "html.parser")
    for t in s(["script", "style", "nav", "header", "footer"]):
        t.decompose()
    r = blank(url)
    txt = re.sub(r"\s+", " ", s.get_text(" ", strip=True))
    sections(txt, r)
    for col, pat in [("모집분야", r"모집\s?분야"), ("직급직책", r"직급\s?/?\s?직책"),
                     ("근무형태", r"근무\s?형태|고용\s?형태"), ("근무시간", r"근무\s?시간"),
                     ("급여", r"급여|연봉|임금"), ("업종", r"업종|산업")]:
        m = re.search(rf"(?:{pat})\s*[:：]?\s*(.{{2,120}}?)(?=\s*(?:{STOP}|모집\s?인원|근무\s?지|경력|학력|마감|접수)\s*[:：]?\s|$)", txt)
        if m:
            r[col] = CLEAN(m.group(1))[:200]
    return sanitize(r) if _has(r) else None


def p_career(url, resp):
    """커리어 — 상세모집요강이 base64 PNG 이미지인 공고가 많다.
    대신 '관련 키워드'(a.lobs)가 직무 코드로 구조화돼 있어 이걸 직무키워드로 쓴다."""
    s = BeautifulSoup(resp.text, "html.parser")
    for t_ in s(["script", "style"]):
        t_.decompose()
    r = blank(url)
    kw = [a.get_text(" ", strip=True) for a in s.select("div.lobsGrop a.lobs")]
    r["직무키워드"] = ", ".join(dict.fromkeys(k for k in kw if k))[:300]

    txt = re.sub(r"\n{2,}", "\n", s.get_text("\n", strip=True))
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    KEY = {"근무형태": "근무형태", "근무시간": "근무시간", "학력": "학력",
           "급여": "급여", "근무지역": "상세주소", "모집인원": "모집인원",
           "주요사업": "업종"}
    for i, l in enumerate(lines[:-1]):
        col = KEY.get(l)
        if col and not r[col]:
            r[col] = CLEAN(lines[i + 1])[:200]

    # 상세모집요강이 텍스트인 공고는 본문에서 절편을 뽑는다
    body = s.select_one("#custom_recruit")
    if body:
        bt = re.sub(r"\s+", " ", body.get_text(" ", strip=True))
        if len(bt) > 40:
            sections(bt, r)
            if not r["모집분야"]:
                r["모집분야"] = bt[:200]
    return sanitize(r) if _has(r) else None


PARSER = {"사람인": p_saramin_detail, "잡코리아": p_jobkorea, "원티드": p_wanted,
          "커리어": p_career}


# 사이트 지역 필터로 새로 받은 부산 목록. 이쪽이 전수라 우선한다.
#   전국 수집 후 부산을 걸러내면 다지역 공고("서울, 경기, …, 부산")가 통째로 빠진다.
#   잡코리아는 그렇게 4,149건이었는데 지역 필터로는 8,660건이다.
BUSAN_LIST = {"잡코리아": "잡코리아부산", "사람인": "사람인부산",
              "커리어": "커리어부산"}


def urls_for(site):
    """해당 사이트의 부산 공고 URL 목록(중복 제거, 순서 유지)."""
    seen, out = set(), []
    src = DATA / f"{BUSAN_LIST.get(site, '')}.csv"
    if src.exists():
        rows = csv.DictReader(src.open(encoding="utf-8-sig"))
    else:
        rows = (r for r in csv.DictReader(BUSAN.open(encoding="utf-8-sig"))
                if r["사이트"] == site)
    for r in rows:
        u = (r.get("공고URL") or "").strip()
        if site == "사람인":
            # 상세요강만 주는 가벼운 경로로 바꿔 요청한다(431KB -> 9KB)
            m = re.search(r"rec_idx=(\d+)", u)
            if not m:
                continue
            u = ("https://www.saramin.co.kr/zf_user/jobs/relay/view-detail"
                 f"?rec_idx={m.group(1)}")
        if u and u not in seen:
            seen.add(u); out.append(u)
    return out


def run(site, urls, parse, root, workers=4, per_sec=3.0):
    s = Site(f"{site}_직무상세", root, delay=0)
    s.note(f"직무 상세 보강 대상 {len(urls):,}건")
    fetch_many_ckpt(s, urls, parse, workers=workers, per_sec=per_sec, label=site)
    out = DATA / f"{site}_직무상세.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in s.rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    fill = {c: sum(1 for r in s.rows if r.get(c)) for c in COLS[1:-1]}
    n = max(len(s.rows), 1)
    print(f"  -> {out.name} ({len(s.rows):,}건)", file=sys.stderr)
    print("     " + "  ".join(f"{c} {fill[c]*100//n}%" for c in COLS[1:-1]), file=sys.stderr)
    return s.rows


ROOT = {"사람인": "https://www.saramin.co.kr",
        "잡코리아": "https://www.jobkorea.co.kr", "커리어": "https://job.career.co.kr",
        "캐치": "https://www.catch.co.kr", "리멤버커리어": "https://career.rememberapp.co.kr",
        "점핏": "https://jumpit.saramin.co.kr", "링커리어": "https://linkareer.com",
        "잡알리오": "https://job.alio.go.kr", "나라일터": "https://www.gojobs.go.kr",
        "건설워커": "https://www.worker.co.kr", "워크투게더": "https://www.worktogether.or.kr",
        "미디어잡": "https://www.mediajob.co.kr", "원티드": "https://www.wanted.co.kr"}


def main():
    want = sys.argv[1:] or ["잡코리아", "커리어", "캐치", "리멤버커리어", "잡알리오",
                            "나라일터", "링커리어", "건설워커", "점핏", "워크투게더", "미디어잡"]
    for site in want:
        urls = urls_for(site)
        if not urls:
            print(f"  [{site}] 부산 URL 없음 — 건너뜀", file=sys.stderr); continue
        if site == "원티드":
            ids = [re.search(r"/wd/(\d+)", u) for u in urls]
            urls = [f"https://www.wanted.co.kr/api/v4/jobs/{m.group(1)}" for m in ids if m]
        # 잡코리아는 세션 단위 스로틀이 있다. 4워커 3req/s 로 돌리면 1,200건쯤에서
        # 전량 실패로 돌아선다(단건 요청은 여전히 200). 느리게 간다.
        w, ps = (2, 1.2) if site == "잡코리아" else (4, 3.0)
        run(site, urls, PARSER.get(site, p_text), ROOT.get(site, ""),
            workers=w, per_sec=ps)


if __name__ == "__main__":
    main()
