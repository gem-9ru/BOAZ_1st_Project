"""고용24(work24.go.kr) 상세 — 워크넷 연계 공고의 직무내용·표준 직종.

[왜]
부산 공고에서 담당업무가 가장 크게 비는 곳이 워크넷 연계분이다.
  잡코리아 부산 8,671건 중 4,214건이 워크넷 연계(`/Ext?siteCode=WN`)
  커리어 부산 5,070건은 표본 25건이 전부 워크넷 연계
그런데 잡코리아 워크넷 공고 페이지가 **work24 상세를 iframe 으로 직접 걸고 있다.**

    <iframe src="https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do
                 ?wantedAuthNo=K130112609080002&infoTypeGroup=tb_workinfoworknet">

여기서 `직무내용` 이 나온다.
    "CGV 부산 센텀시티점 미화원 구인 합니다. 주 업무 : 상영관청소, 분리수거 및
     화장실 청소 등 미화업무 일체"

[정책] work24.go.kr robots 는 `/wk/` 를 허용한다(`/cm/common/`·`/sa/`·`/ei/` 만 차단).
       urllib.robotparser 로 can_fetch=True 확인.
       ※ 구 도메인 work.go.kr 은 `User-Agent: *` 가 `/empInfo/` 를 전면 차단하므로
         그쪽으로는 접근하지 않는다.

[2단계 수집]
  1) 잡코리아 Ext 페이지에서 iframe 의 wantedAuthNo 를 뽑는다
  2) work24 상세를 받아 직무내용·직종·학력·경력·임금을 파싱한다

[실패 1,577건은 마감분이다]
4,214건 중 2,637건만 본문이 왔다. 나머지는 1.2KB 자동제출 폼만 돌아오는데
그 안에 이유가 적혀 있다.

    var msgStr = '마감된 채용정보입니다.';

워크넷 원본은 내려갔는데 잡코리아에는 아직 남아 있는 공고다.
차단이나 파싱 실패가 아니라 재시도해도 소용없다.
※ 응답이 200 이고 HTML 도 정상이라 조용히 실패한다. **본문 길이**로 구분한다
  (정상 330KB / 마감 1.2KB). 문구로 거르면 정상 페이지의 메시지 템플릿에도
  같은 말이 있어 전부 걸러진다.
"""
import csv, json, re, sys
from bs4 import BeautifulSoup
from common import Site, DATA, NOW, fetch_many_ckpt

ROOT = "https://www.work24.go.kr"
DETAIL = (ROOT + "/wk/a/b/1500/empDetailAuthView.do"
                 "?wantedAuthNo={}&infoTypeGroup=tb_workinfoworknet")
SRC = DATA / "잡코리아부산.csv"
OUT = DATA / "고용24_상세.csv"
COLS = ["공고URL", "직종코드", "담당업무", "직종", "직무키워드", "학력", "경력",
        "급여", "근무형태", "상세주소", "모집인원", "수집시각"]

CLEAN = lambda t: re.sub(r"\s+", " ", (t or "")).strip()
AUTH = re.compile(r"wantedAuthNo=([A-Za-z0-9]+)")
# 한국고용직업분류(KECO) 6자리 코드. 입사지원 팝업 파라미터에 들어 있다.
#   jobsCd: "561101"  ↔  직종 "건물 청소원(공공건물,아파트,사무실,병원,상가,공장 등)"
# 화면에는 코드가 안 보이고 이름만 나온다. 코드가 있어야 분류 키로 쓸 수 있다.
JOBSCD = re.compile(r'jobsCd\s*:\s*"(\d{4,8})"')


def parse(url, resp):
    """work24 상세. url 에 원래 잡코리아 URL 을 되돌려 넣기 위해 MAP 을 쓴다.

    마감된 공고는 자동제출 폼(1.2KB)만 200 으로 온다.
    ※ '마감된 채용정보' 문구로 거르면 안 된다. 정상 페이지의 스크립트에도
      같은 문구가 메시지 템플릿으로 들어 있어서 전부 걸러진다(ok=0 사고).
      본문 길이로 판별한다.
    """
    if len(resp.text) < 5000:
        return None
    s = BeautifulSoup(resp.text, "html.parser")
    for t in s(["script", "style"]):
        t.decompose()
    txt = re.sub(r"\n{2,}", "\n", s.get_text("\n", strip=True))
    r = {c: "" for c in COLS}
    r["공고URL"] = MAP.get(url, url)
    r["수집시각"] = NOW()

    m = JOBSCD.search(resp.text)
    if m:
        r["직종코드"] = m.group(1)

    m = re.search(r"직무내용\s*\n(.{10,1500}?)\n\s*(?:더보기|접기|모집\s?인원|$)", txt, re.S)
    if m:
        r["담당업무"] = CLEAN(m.group(1))[:1500]
    for col, pat, lim in [("직종", r"모집\s?직종", 120), ("직무키워드", r"직종\s?키워드", 200),
                          ("학력", r"학력", 60), ("경력", r"경력", 60),
                          ("급여", r"임금", 120), ("근무형태", r"고용형태", 120),
                          ("모집인원", r"모집\s?인원", 30)]:
        mm = re.search(rf"(?:^|\n){pat}\s*\n(.{{1,{lim}}}?)\n", txt)
        if mm:
            r[col] = CLEAN(mm.group(1))
    mm = re.search(r"지역\s*\n(.{4,160}?)\n", txt)
    if mm:
        r["상세주소"] = CLEAN(mm.group(1))
    return r if any(r[c] for c in COLS[1:-1]) else None


MAP = {}          # work24 URL -> 원래 잡코리아 공고URL


def main():
    jk = [r["공고URL"] for r in csv.DictReader(SRC.open(encoding="utf-8-sig"))
          if r.get("출처") == "worknet"]
    print(f"  워크넷 연계 공고 {len(jk):,}건 — 1단계: wantedAuthNo 추출", file=sys.stderr)

    s1 = Site("고용24_인증번호", "https://www.jobkorea.co.kr", delay=0)
    def grab(u, resp):
        m = AUTH.search(resp.text)
        return {"공고URL": u, "authNo": m.group(1)} if m else None
    # 잡코리아는 워커를 늘려도 3req/s 부근이 천장이다(4/8/12워커 실측).
    fetch_many_ckpt(s1, jk, grab, workers=6, per_sec=3.5, label="authNo")

    pairs = [(r["공고URL"], r["authNo"]) for r in s1.rows if r.get("authNo")]
    print(f"  인증번호 확보 {len(pairs):,}건 — 2단계: 고용24 상세", file=sys.stderr)

    urls = []
    for jkurl, auth in pairs:
        u = DETAIL.format(auth)
        MAP[u] = jkurl
        urls.append(u)

    s2 = Site("고용24_상세", ROOT, delay=0)
    s2.note("robots 가 /wk/ 를 허용한다(구 도메인 work.go.kr 은 /empInfo/ 전면 차단이라 미사용)")
    # 고용24는 동시성이 잘 늘어난다. 실측: 3워커 1.97 / 6워커 5.68 / 10워커 8.70 req/s (실패 0).
    # 공공 사이트라 천장까지 밀지 않고 8워커 7req/s 로 둔다.
    fetch_many_ckpt(s2, urls, parse, workers=8, per_sec=7.0, label="고용24")

    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in s2.rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    n = max(len(s2.rows), 1)
    got = sum(1 for r in s2.rows if r.get("담당업무"))
    print(f"  -> {OUT.name} ({len(s2.rows):,}건)  담당업무 {got*100//n}%", file=sys.stderr)


if __name__ == "__main__":
    main()
