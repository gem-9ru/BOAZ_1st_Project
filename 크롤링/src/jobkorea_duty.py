"""잡코리아 직무 보강 패스 — 안내문으로 채워진 직무 칸을 '모집분야' 로 교체.

[배경] 공용 JSON-LD 파서가 초기에 description 을 직무로 넣었다. 잡코리아는
       occupationalCategory 가 없어 직무 칸이 전부
         "㈜부림종합물류에서 계약직 경력무관 채용을 진행합니다. 근무지는 …"
       같은 안내문이 됐다(본 107,812 + 추가 25,772 = 133,584건 전량).
       파서는 이미 고쳤지만, 이미 수집한 데이터는 그대로다.

[방식] 상세 페이지를 다시 받아 본문의 '모집분야' 만 뽑아 기존 CSV 의 직무 칸을 갱신한다.
       회사·제목·경력·지역·마감일은 이미 정확하므로 건드리지 않는다.
       체크포인트(JSONL)에 {공고URL: 직무} 만 적재해 중단 시 이어받는다.

[범위] 전량(13.6만)은 5시간 이상 걸려, **부산 지역 공고만** 보강한다(4,149건, 약 15분).
       최종 산출물의 초점이 부산이므로 여기에 자원을 집중한다.
       부산 외 공고의 직무는 정규화 단계의 제목 기반 보강으로 채운다.
       전량이 필요해지면 BUSAN_ONLY = False 로 바꿔 다시 돌리면 된다(체크포인트 재사용).
"""


import csv, json, re, sys, threading, time
from pathlib import Path
from bs4 import BeautifulSoup
from common import Site, DATA, LOGS

NEXT = r"모집인원|고용형태|급여|근무시간|근무지|경력|학력|접수|마감|담당자|우대|근무형태"

BUSAN_ONLY = True
BUSAN_RE = re.compile(r"부산|해운대|기장|사상구|사하구|영도|동래|금정|수영구|연제|부산진")

def extract_duty(html):
    body = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    m = re.search(rf"모집\s?분야\s+(.{{2,80}}?)\s+(?:{NEXT})", body)
    if not m:
        m = re.search(r"모집\s?분야\s+([^\s]{2,80})", body)
    return m.group(1).strip(" ,·/|")[:150] if m else ""

def main():
    site = Site("잡코리아직무", "https://www.jobkorea.co.kr", delay=0.2)
    ck = LOGS / "잡코리아직무.ckpt.jsonl"
    done = {}
    if ck.exists():
        for line in ck.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                done[d["u"]] = d["d"]
            except Exception:
                pass
    site.note(f"체크포인트 복원 {len(done):,}건")

    urls = []
    for name in ("잡코리아", "잡코리아추가"):
        p = DATA / f"{name}.csv"
        if p.exists():
            for r in csv.DictReader(p.open(encoding="utf-8-sig")):
                u = r.get("공고URL", "")
                if not u or u in done:
                    continue
                if BUSAN_ONLY and not BUSAN_RE.search(r.get("지역", "") or ""):
                    continue
                urls.append(u)
    # 추가분 CSV 가 아직 없으면 체크포인트에서 URL 확보 (지역 필터 동일 적용)
    extra_ck = LOGS / "잡코리아추가.ckpt.jsonl"
    if not (DATA / "잡코리아추가.csv").exists() and extra_ck.exists():
        for line in extra_ck.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            u = d.get("공고URL", "")
            if not u or u in done:
                continue
            if BUSAN_ONLY and not BUSAN_RE.search(d.get("지역", "") or ""):
                continue
            urls.append(u)
    urls = list(dict.fromkeys(urls))
    site.note(f"직무 보강 대상 {len(urls):,}건" + (" (부산 한정)" if BUSAN_ONLY else " (전량)"))

    f = ck.open("a", encoding="utf-8")
    lock = threading.Lock()
    stat = {"ok": 0, "empty": 0, "fail": 0}
    from concurrent.futures import ThreadPoolExecutor
    from common import RateLimiter
    rl = RateLimiter(5.0)

    def work(u):
        for attempt in range(2):
            try:
                rl.wait()
                r = site.s.get(u, timeout=25)
                if r.status_code >= 500 or r.status_code == 429:
                    time.sleep(2); continue
                r.raise_for_status()
                d = extract_duty(r.text)
                with lock:
                    f.write(json.dumps({"u": u, "d": d}, ensure_ascii=False) + "\n"); f.flush()
                    stat["ok" if d else "empty"] += 1
                return
            except Exception:
                if attempt:
                    with lock: stat["fail"] += 1
    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, _ in enumerate(ex.map(work, urls), 1):
            if i % 2000 == 0:
                print(f"    {i:,}/{len(urls):,} ok={stat['ok']:,} 빈값={stat['empty']:,} 실패={stat['fail']}",
                      flush=True)
    f.close()
    site.note(f"완료 ok={stat['ok']:,} 빈값={stat['empty']:,} 실패={stat['fail']:,}")

    # CSV 갱신
    for line in ck.open(encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                d = json.loads(line); done[d["u"]] = d["d"]
            except Exception:
                pass
    for name in ("잡코리아", "잡코리아추가"):
        p = DATA / f"{name}.csv"
        if not p.exists():
            continue
        rows = list(csv.DictReader(p.open(encoding="utf-8-sig")))
        if not rows:
            continue
        n = 0
        for r in rows:
            nd = done.get(r.get("공고URL", ""))
            if nd:
                r["직무"] = nd; n += 1
        with p.open("w", newline="", encoding="utf-8-sig") as g:
            w = csv.DictWriter(g, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print(f"  {name}.csv 직무 갱신 {n:,}/{len(rows):,}행")

if __name__ == "__main__":
    main()
