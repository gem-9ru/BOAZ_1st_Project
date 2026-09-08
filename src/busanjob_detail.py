"""부산일자리정보망 상세페이지 수집 — 직무 보강 패스.

[왜 필요한가]
목록 수집만으로는 직무 칸에 메뉴 이름('기업채용'/'공공채용'/'해외채용')밖에 들어오지 않는다.
100% 채워져 보이지만 정보량이 0 이라, 부산 데이터의 78% 가 제목 파싱에만 의존하고 있었다.

[상세페이지에 실제로 있는 것]
  /view.do?no={메뉴}&pgMode=show&id={id}
    div.board-view__dcont 안에 라벨/값 쌍이 들어 있다.
      직무내용   실제 담당 업무 서술        ← 워크넷·알리오·구청·부산자체 등록분
      직종       표준 직업분류명            ← 부산 자체등록분
      업종       산업 분류
      고용형태   정규직/계약직/기간제       ← 목록에 없어 채움률 0% 였던 필드
      근무지역   다지역 상세 (목록보다 정확)
      경력/학력조건, 임금조건, 모집인원, 근무시간, 근무형태, 접수방법, 기관명 …

    또 스크립트 변수 wantedInfoUrl 에 **원출처 URL 이 그대로** 들어 있다.
      saramin.co.kr/zf_user/jobs/relay/view?rec_idx=54753349
      jobkorea.co.kr/Recruit/GI_Read/49933356
      work24.go.kr/...?wantedAuthNo=KF10912609070022
    → 사람인·잡코리아 원문으로 이어가는 열쇠라 반드시 보존한다.

[정책] 부산광역시 운영 공공 포털. robots.txt 404(규칙 없음),
       크롤링 금지 고지 없음(푸터의 '이메일 무단수집거부'는 정보통신망법 스팸 방지 표시).
"""
import csv, json, re, sys
from bs4 import BeautifulSoup
from common import Site, DATA, NOW, fetch_many_ckpt

ROOT = "https://www.busanjob.net"
SRC = DATA / "부산일자리정보망.csv"
OUT = DATA / "부산일자리정보망_상세.csv"

COLS = ["공고URL", "직무내용", "직종", "업종", "고용형태", "근무지역", "근무시간", "근무형태",
        "경력학력조건", "임금조건", "모집인원", "기관명", "분류", "접수방법",
        "기타사항", "채용분야", "원출처URL", "수집시각"]

# 라벨 → 우리 컬럼. 사이트가 쓰는 라벨명이 출처마다 조금씩 다르다.
LABEL = {
    "직무내용": "직무내용", "직종": "직종", "업종": "업종", "고용형태": "고용형태",
    "근무지역": "근무지역", "근무지": "근무지역", "근무시간": "근무시간", "근무형태": "근무형태",
    "경력/학력조건": "경력학력조건", "임금조건": "임금조건", "모집인원": "모집인원",
    "기관명": "기관명", "분류": "분류", "접수방법": "접수방법",
    "기타사항": "기타사항", "채용분야": "채용분야",
}


def parse(url, resp):
    soup = BeautifulSoup(resp.text, "html.parser")
    row = {c: "" for c in COLS}
    row["공고URL"] = url
    row["수집시각"] = NOW()

    cont = soup.select_one("div.board-view__dcont")
    if cont:
        # 라벨/값은 <div class="...__h">라벨</div><div class="...__b">값</div> 쌍으로 온다.
        # 클래스 접두어가 sm-formlst / boxlst-h / boxlst-v / sm-titlst 로 제각각이라
        # 접미어(__h, __b)로만 잡는다.
        for li in cont.select("li"):
            h = li.select_one('[class$="__h"]')
            b = li.select_one('[class$="__b"]')
            if not (h and b):
                continue
            key = LABEL.get(h.get_text(" ", strip=True))
            if key and not row[key]:
                row[key] = re.sub(r"\s+", " ", b.get_text(" ", strip=True))[:2000]

    # 원출처 URL — 스크립트 변수. 같은 값이 여러 번 나오므로 첫 개만.
    m = re.search(r"wantedInfoUrl\s*=\s*'([^']+)'", resp.text)
    if m:
        row["원출처URL"] = m.group(1)

    # 아무것도 못 건졌으면 실패로 본다(빈 행이 쌓이는 걸 막는다).
    return row if any(row[c] for c in COLS if c not in ("공고URL", "수집시각")) else None


def main():
    urls = [r["공고URL"] for r in csv.DictReader(SRC.open(encoding="utf-8-sig"))
            if "busanjob.net" in r["공고URL"] and "pgMode=show" in r["공고URL"]]
    # 중복 제거(순서 유지)
    seen, todo = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u); todo.append(u)

    s = Site("부산일자리정보망_상세", ROOT, delay=0)
    s.note("부산광역시 운영 공공 포털. robots 규칙 없음, 크롤링 금지 고지 없음")
    s.note(f"상세 대상 {len(todo):,}건")

    fetch_many_ckpt(s, todo, parse, workers=4, per_sec=4.0, label="상세")

    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in s.rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    print(f"  -> {OUT.name} ({len(s.rows):,}건)", file=sys.stderr)

    # 출처별 직무내용 확보율
    from collections import Counter
    c = Counter()
    for r in s.rows:
        host = re.sub(r"^https?://(www\.)?([^/]+)/.*$", r"\2", r.get("원출처URL") or "") or "(없음)"
        c[(host, bool(r.get("직무내용")))] += 1
    print("\n  원출처별 직무내용 확보", file=sys.stderr)
    for host in sorted({h for h, _ in c}):
        y, n = c[(host, True)], c[(host, False)]
        print(f"    {host:34}{y:>7,} / {y+n:>7,}", file=sys.stderr)


if __name__ == "__main__":
    main()
