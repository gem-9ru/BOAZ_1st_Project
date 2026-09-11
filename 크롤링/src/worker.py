"""건설워커 — 목록에서 공고 링크 수집 후 상세 JSON-LD 파싱.

[문제1] /job/list.asp?page=N 의 page 파라미터가 무시됨(1·2페이지 응답 바이트 완전 동일).
        → 페이지 대신 jobid 카테고리(all/eng/con/ccp/int/hh)를 바꿔가며 링크를 모으고 중복 제거.
[문제2] 문서 인코딩이 euc-kr 인데 Content-Type 에 charset 이 없어 requests 가 깨진 문자열을 반환.
        → 응답마다 resp.encoding='euc-kr' 을 강제 지정한 뒤 파싱.
[문제3] 목록 링크 상당수가 javascript:winopen('/view.asp...') 형태의 팝업 호출이라
        a[href] 만 긁으면 놓친다. → 정규식으로 winopen() 안의 경로까지 함께 추출.
[robots] robots.txt 에 SEO 봇 블랙리스트만 있고 일반 UA 규칙 없음 → 전체 허용으로 간주.
"""
import csv, os, re, sys
from bs4 import BeautifulSoup
from common import Site, fetch_many, parse_jobposting_ld, DATA, LD_EXTRA_COLS

ROOT = "https://www.worker.co.kr"
CATS = ["all", "eng", "con", "ccp", "int", "hh"]
LIMIT = 2000   # 1차 700 상한에서 수집 URL 1,696건을 다 못 담아 상향

def parse(u, r):
    r.encoding = "euc-kr"            # 문제2 대응
    row = parse_jobposting_ld(u, r)
    if row and not row.get("마감일"):
        # [문제6] JSON-LD 의 validThrough 가 빈 문자열인 건이 40% 였다(마감일 채움률 60%).
        #         상세 <title> 이 "[회사] 공고명 (마감일 : 채용시) - 건설취업 건설워커" 형식이라
        #         여기서 마감 표기를 읽어 채운다. '채용시' 같은 상시 표기도 원문대로 보존한다.
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        m = re.search(r"마감일\s*[:：]\s*([^)\]]+)", title)
        if m:
            row["마감일"] = m.group(1).strip()[:20]
    return row

def main():
    s = Site("건설워커", ROOT)
    s.extra_cols = LD_EXTRA_COLS    # JSON-LD 가 주는 학력·급여·주소 등
    s.note("euc-kr 강제 디코딩 적용 (Content-Type 에 charset 누락)")
    s.note("list.asp?page=N 무효 확인 → jobid 카테고리 순회로 대체")
    urls = {}          # no -> 정규화 URL
    for c in CATS:
        for path in (f"{ROOT}/job/list.asp?jobid={c}", f"{ROOT}/?menu=article&type=1&jobid={c}"):
            try:
                r = s.get(path); r.encoding = "euc-kr"
            except Exception as e:
                s.note(f"목록 실패 {path}: {e}"); continue
            soup = BeautifulSoup(r.text, "html.parser")
            found = {a["href"] for a in soup.select('a[href*="/job/view.asp"]')}
            found |= {m for m in re.findall(r"winopen\('(/view\.asp[^']+)'", r.text)}   # 문제3 대응
            for h in found:
                # [문제5] winopen 으로 열리는 /view.asp 는 '팝업용 경량 페이지'라 JSON-LD 가 없다.
                # 이걸 그대로 요청하면 파서가 None 을 돌려줘 전부 실패로 집계된다(1차 실행 실패 365건의 정체).
                # 같은 공고의 정식 페이지 /job/view.asp?jobid=..&no=.. 에는 JSON-LD 가 있으므로 URL 을 정규화한다.
                no = re.search(r"[?&]no=(\d+)", h)
                jid = re.search(r"[?&]jobid=(\w+)", h)
                if not no:
                    continue
                # 같은 공고가 jobid 만 다른 URL 로 중복 노출되므로 no 를 키로 중복 제거한다.
                urls[no.group(1)] = f"{ROOT}/job/view.asp?jobid={jid.group(1) if jid else 'all'}&no={no.group(1)}"
        print(f"    jobid={c:4s} 누적 {len(urls)}")
    urls = sorted(urls.values())[:LIMIT]
    s.note(f"공고 상세 URL {len(urls)}건 수집")

    # [문제4] 동시성 4 / 2 req/s 로 돌렸더니 1,696건 중 365건이 실패했다.
    # 개별 재요청은 정상 200 이라 서버 차단이 아니라 동시 연결에서 나는 일시적 실패였다.
    # → 이미 받은 CSV 를 읽어 남은 것만 낮은 동시성으로 재시도하는 이어받기를 넣었다.
    prev = {}
    out = DATA / f"{s.name}.csv"
    if "--resume" in sys.argv and out.exists():
        with out.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                prev[row["공고URL"]] = row
        s.rows.extend(prev.values())
        urls = [u for u in urls if u not in prev]
        s.note(f"이어받기: 기존 {len(prev)}건 유지, 미수집 {len(urls)}건만 재시도 (동시성 2 / 1.2 req/s)")
        fetch_many(s, urls, parse, workers=2, per_sec=1.2, label="view-retry")
    else:
        fetch_many(s, urls, parse, workers=4, per_sec=2.0, label="view")
    s.save()

if __name__ == "__main__":
    main()
