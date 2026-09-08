# -*- coding: utf-8 -*-
"""사이트별 크롤링 정책 감사.

로켓펀치에서 robots.txt(Allow: /)만 보고 '허용' 으로 판단했다가, 페이지 푸터에
"크롤링 등 기술적 장치를 이용한 수집 금지, 형사처벌 가능" 고지가 있는 것을 뒤늦게 발견했다.
같은 누락이 다른 사이트에도 있을 수 있으므로 세 층을 모두 확인한다.

  1) robots.txt          — 크롤러 대상 지시 (비회원에게도 적용)
  2) 페이지 본문/푸터 고지 — 사이트가 게시한 거부 의사 (비회원에게도 적용, 가장 강함)
  3) 이용약관            — 회원 의무 (계정을 만들면 계약상 의무가 됨)

3번은 '계정을 만들면 오히려 제약이 늘어나는지' 를 판단하는 근거가 된다.
"""
import json, re, sys, time
import urllib.robotparser as rp
from pathlib import Path
import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# 비회원에게도 적용되는 '수집 거부' 고지 — 강한 신호
NOTICE = re.compile(
    r"크롤링[^.。]{0,60}(금지|거부|불가|제한|처벌)"
    r"|(금지|거부)[^.。]{0,40}크롤링"
    r"|기술적\s*장치[^.。]{0,50}(수집|금지)"
    r"|무단\s*(수집|복제|전재)"
    r"|동의\s*없이[^.。]{0,40}수집[^.。]{0,30}(금지|거부)"
    r"|스크래핑[^.。]{0,40}(금지|거부)"
    r"|자동화된?\s*(수단|프로그램|장치)[^.。]{0,40}(수집|금지)", re.I)

# 회원 의무 조항 — 계정 생성 시 적용
MEMBER = re.compile(
    r"(복사|복제|전재|재배포|출판|방송)[^.。]{0,60}(금지|없이|안\s?된다|할\s*수\s*없)"
    r"|영리\s*(행위|목적)"
    r"|자동화된?[^.。]{0,30}(수단|프로그램|매크로|로봇)"
    r"|데이터베이스[^.。]{0,40}(구축|추출)", re.I)

SITES = [
    # (이름, 루트, 현재상태)
    ("잡코리아",      "https://www.jobkorea.co.kr", "수집중"),
    ("원티드",        "https://www.wanted.co.kr",   "수집완료"),
    ("잡플래닛",      "https://www.jobplanet.co.kr","수집완료"),
    ("캐치",          "https://www.catch.co.kr",    "수집완료"),
    ("자소설닷컴",    "https://jasoseol.com",       "수집완료"),
    ("리멤버커리어",  "https://career.rememberapp.co.kr", "수집중"),
    ("점핏",          "https://jumpit.saramin.co.kr","수집완료"),
    ("링커리어",      "https://linkareer.com",      "수집완료"),
    ("건설워커",      "https://www.worker.co.kr",   "수집완료"),
    ("게임잡",        "https://www.gamejob.co.kr",  "수집완료"),
    ("미디어잡",      "https://www.mediajob.co.kr", "수집완료"),
    ("잡알리오",      "https://job.alio.go.kr",     "수집완료"),
    ("널스케이프",    "https://recruit.nurscape.net","수집완료"),
    ("슈퍼루키",      "https://www.superookie.com", "미수집"),
    ("나라일터",      "https://www.gojobs.go.kr",   "미수집"),
    ("워크투게더",    "https://www.worktogether.or.kr","미수집"),
    ("커리어",        "https://www.career.co.kr",   "미수집"),
    ("노트폴리오",    "https://notefolio.net",      "미수집"),
    ("유니코써치",    "http://www.unicosearch.com", "미수집"),
    ("로켓펀치",      "https://www.rocketpunch.com","제외(고지)"),
]

POLICY_HINT = re.compile(r"약관|정책|이용안내|terms|policy|agreement|privacy", re.I)


def get(s, url, timeout=20):
    r = s.get(url, timeout=timeout)
    r.raise_for_status()
    return r


def flat(soup):
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def audit(name, root, state):
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    out = {"사이트": name, "루트": root, "상태": state,
           "robots": "?", "robots_공고허용": None,
           "본문고지": [], "약관조항": [], "약관URL": [], "오류": []}

    # 1) robots.txt
    try:
        rr = s.get(root + "/robots.txt", timeout=15)
        if rr.status_code == 200 and "html" not in rr.headers.get("content-type", ""):
            p = rp.RobotFileParser(); p.parse(rr.text.splitlines())
            out["robots"] = "존재"
            out["robots_공고허용"] = p.can_fetch(UA, root + "/")
        else:
            out["robots"] = f"없음(HTTP{rr.status_code})"
    except Exception as e:
        out["오류"].append(f"robots: {type(e).__name__}")

    # 2) 홈페이지 본문/푸터 고지
    home = None
    try:
        home = BeautifulSoup(get(s, root + "/").text, "html.parser")
        txt = flat(home)
        for m in NOTICE.finditer(txt):
            seg = txt[max(0, m.start() - 90): m.start() + 190].strip()
            out["본문고지"].append(seg)
            if len(out["본문고지"]) >= 3:
                break
    except Exception as e:
        out["오류"].append(f"home: {type(e).__name__}")

    # 3) 약관 문서
    if home is not None:
        cands, seen = [], set()
        for a in home.select("a[href]"):
            h = a.get("href", "")
            if not h or h.startswith(("javascript", "#", "mailto")):
                continue
            if POLICY_HINT.search(a.get_text(" ", strip=True) + " " + h):
                u = h if h.startswith("http") else root.rstrip("/") + "/" + h.lstrip("/")
                if u in seen:
                    continue
                seen.add(u); cands.append(u)
            if len(cands) >= 4:
                break
        for u in cands:
            try:
                t = flat(BeautifulSoup(get(s, u, 25).text, "html.parser"))
            except Exception:
                continue
            if len(t) < 800:            # 약관 본문이 아닌 껍데기
                continue
            out["약관URL"].append(u)
            for m in MEMBER.finditer(t):
                seg = t[max(0, m.start() - 90): m.start() + 170].strip()
                out["약관조항"].append(seg)
                if len(out["약관조항"]) >= 3:
                    break
            if out["약관조항"]:
                break
    return out


def main():
    res = []
    for name, root, state in SITES:
        try:
            r = audit(name, root, state)
        except Exception as e:
            r = {"사이트": name, "루트": root, "상태": state, "오류": [str(e)[:60]]}
        res.append(r)
        flag = "★고지있음" if r.get("본문고지") else ""
        print(f"{name:12s} robots={str(r.get('robots')):14s} "
              f"본문고지={len(r.get('본문고지', [])):d} 약관조항={len(r.get('약관조항', [])):d} {flag}",
              flush=True)
        time.sleep(0.6)
    Path(__file__).with_name("policy_audit.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n-> policy_audit.json 저장")


if __name__ == "__main__":
    main()
