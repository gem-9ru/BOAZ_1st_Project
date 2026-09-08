"""공용 크롤러 유틸.

- robots.txt 를 매 실행마다 내려받아 대상 URL 허용 여부를 검사한다(urllib.robotparser).
- Crawl-delay 가 선언된 사이트는 그 값을, 없으면 기본 1.0초를 지킨다.
- UA 는 일반 브라우저 UA. AI 크롤러 전용 UA(ClaudeBot/GPTBot 등)로 차단된 경로는 애초에 대상에서 뺀다.
"""
import csv, json, sys, threading, time, urllib.robotparser as rp
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
BASE = Path(__file__).resolve().parent.parent
DATA, LOGS = BASE / "data", BASE / "logs"
DEFAULT_DELAY = 1.0


class Site:
    def __init__(self, name, root, delay=None):
        self.name, self.root = name, root
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
        self.rows, self.notes = [], []
        # 기본 12칸 외에 사이트가 더 주는 값(학력·급여 등)을 남기고 싶을 때 지정한다.
        # 지정하지 않으면 save() 가 extrasaction="ignore" 로 조용히 버린다.
        self.extra_cols = []
        self.rp = rp.RobotFileParser()
        self.delay = delay if delay is not None else DEFAULT_DELAY
        try:
            r = self.s.get(root.rstrip("/") + "/robots.txt", timeout=20)
            if r.status_code == 200 and "text/html" not in r.headers.get("content-type", ""):
                self.rp.parse(r.text.splitlines())
                cd = self.rp.crawl_delay(UA) or self.rp.crawl_delay("*")
                if cd:
                    self.delay = max(self.delay, float(cd))
                    self.note(f"robots.txt Crawl-delay={cd}s 적용")
            else:
                self.rp = None
                self.note(f"robots.txt 없음/비표준 (HTTP {r.status_code}) — 명시적 제한 없음으로 간주")
        except Exception as e:
            self.rp = None
            self.note(f"robots.txt 조회 실패: {e}")

    def allowed(self, url):
        return True if self.rp is None else self.rp.can_fetch(UA, url)

    def get(self, url, **kw):
        if not self.allowed(url):
            raise PermissionError(f"robots.txt 차단: {url}")
        time.sleep(self.delay)
        r = self.s.get(url, timeout=30, **kw)
        r.raise_for_status()
        return r

    def note(self, msg):
        self.notes.append(msg)
        print(f"  [{self.name}] {msg}", file=sys.stderr)

    def add(self, **row):
        self.rows.append(row)

    def save(self):
        DATA.mkdir(parents=True, exist_ok=True); LOGS.mkdir(parents=True, exist_ok=True)
        # 사이트: 통합 데이터셋에서 출처를 남기기 위해 save() 가 자동으로 채운다.
        # 외부원본ID: "이 공고의 원본은 다른 사이트의 공고 N번" 이라고 사이트가 스스로 밝히는 값.
        #   (예: 잡플래닛 jobkorea_posting_id) 중복제거에서 추측 없이 확정 매칭할 수 있는 유일한 키라
        #   반드시 보존한다.
        cols = ["사이트", "회사명", "공고제목", "직무", "경력", "고용형태", "지역",
                "기술스택", "마감일", "공고URL", "외부원본ID", "수집시각"]
        cols += [c for c in self.extra_cols if c not in cols]
        out = DATA / f"{self.name}.csv"
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in self.rows:
                row = {c: r.get(c, "") for c in cols}
                row["사이트"] = row.get("사이트") or self.name
                w.writerow(row)
        (LOGS / f"{self.name}.log.json").write_text(
            json.dumps({"site": self.name, "root": self.root, "count": len(self.rows),
                        "delay": self.delay, "notes": self.notes,
                        "at": time.strftime("%Y-%m-%d %H:%M:%S")},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [{self.name}] -> {out.name} ({len(self.rows)}건)", file=sys.stderr)
        return len(self.rows)


NOW = lambda: time.strftime("%Y-%m-%d %H:%M:%S")


class RateLimiter:
    """전역 초당 요청수 제한 — 병렬 수집 시에도 서버 부하를 일정하게 유지."""
    def __init__(self, per_sec):
        self.gap = 1.0 / per_sec
        self.lock = threading.Lock()
        self.next = 0.0
    def wait(self):
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next)
            self.next = t + self.gap
        d = t - time.monotonic()
        if d > 0:
            time.sleep(d)


def fetch_many(site, urls, parse, workers=4, per_sec=2.0, label=""):
    """urls 를 병렬로 받아 parse(url, response) -> dict|None 을 site.rows 에 적재.

    - RateLimiter 로 전체 초당 요청수를 묶어 동시성이 늘어도 부하는 고정.
    - 실패는 건별로 삼키고 카운트만 남긴다(한 건 때문에 전체가 죽지 않게).
    """
    rl = RateLimiter(per_sec)
    lock = threading.Lock()
    stat = {"ok": 0, "fail": 0, "skip": 0}

    def work(u):
        if not site.allowed(u):
            with lock: stat["skip"] += 1
            return
        for attempt in range(3):
            try:
                rl.wait()
                r = site.s.get(u, timeout=30)
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(2 ** attempt * 2); continue
                r.raise_for_status()
                row = parse(u, r)
                with lock:
                    if row: site.rows.append(row); stat["ok"] += 1
                    else: stat["fail"] += 1
                return
            except Exception:
                if attempt == 2:
                    with lock: stat["fail"] += 1
                else:
                    time.sleep(2 ** attempt)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, _ in enumerate(ex.map(work, urls), 1):
            if i % 200 == 0:
                print(f"    {label} {i}/{len(urls)} ok={stat['ok']} fail={stat['fail']}", file=sys.stderr)
    site.note(f"{label} 병렬수집 ok={stat['ok']} fail={stat['fail']} skip(robots)={stat['skip']} "
              f"(workers={workers}, {per_sec}req/s)")
    return stat


def parse_jobposting_ld(url, resp, tech=""):
    """schema.org JobPosting(JSON-LD) 공통 파서.

    잡코리아/리멤버 등 여러 사이트가 동일 스키마를 심어둬서 셀렉터 대신 이걸 쓴다.
    HTML 구조가 바뀌어도 깨지지 않는 게 장점.
    """
    import json as _j, re as _re
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")
    d = None
    for b in soup.select('script[type="application/ld+json"]'):
        try:
            cand = _j.loads(b.string or "{}")
        except Exception:
            continue
        if isinstance(cand, list):
            cand = next((c for c in cand if c.get("@type") == "JobPosting"), None)
        if cand and cand.get("@type") == "JobPosting":
            d = cand
            break
    if not d:
        return None
    org = (d.get("hiringOrganization") or {})
    org = org.get("name", "") if isinstance(org, dict) else str(org)
    loc = d.get("jobLocation") or {}
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
    # 사이트마다 주소를 담는 키가 다르다. 잡코리아는 addressRegion/addressLocality 없이
    # streetAddress 하나에 "부산 사상구 ..." 를 통째로 넣어서, 이걸 안 보면 지역이 전부 빈칸이 된다.
    region = " ".join(x for x in [addr.get("addressRegion"), addr.get("addressLocality")]
                      if isinstance(x, str)).strip()
    if not region and isinstance(addr.get("streetAddress"), str):
        region = " ".join(addr["streetAddress"].split()[:2])
    strip = lambda v: _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", str(v or ""))).strip()

    # employmentType 은 사이트에 따라 문자열 / 리스트("['FULL_TIME','CONTRACTOR']") 로 온다.
    # 리스트를 str() 하면 파이썬 repr 이 그대로 CSV 에 박히므로 평탄화 + 한국어 매핑한다.
    ETYPE = {"FULL_TIME": "정규직", "PART_TIME": "파트타임", "CONTRACTOR": "계약직",
             "TEMPORARY": "임시직", "INTERN": "인턴", "VOLUNTEER": "자원봉사",
             "PER_DIEM": "일용직", "OTHER": "기타"}
    et = d.get("employmentType")
    if not isinstance(et, list):
        et = [et] if et else []
    et = [ETYPE.get(str(x).strip().upper(), strip(x)) for x in et]
    seen_et, etype = set(), []
    for x in et:                      # 중복 제거(순서 유지). 원본에 같은 값이 2번 오는 경우가 있다.
        if x and x not in seen_et:
            seen_et.add(x); etype.append(x)
    # [중대 수정] 직무 칸에 description(공고 설명문 전체)을 넣고 있었다.
    #   예) "㈜하이브랩에서 정규직 경력 채용을 진행합니다. 근무지는 경기 성남시 분당구 …"
    #   직무가 아니라 안내문이라 데이터로서 쓸모가 없다(잡코리아 100%, 미디어잡 97%,
    #   건설워커 80%, 리멤버 다수가 이 상태였다).
    # 우선순위: occupationalCategory(스키마 표준) → 본문 '모집분야' → 그래도 없으면 빈칸.
    #   description 은 절대 직무로 쓰지 않는다(빈칸이 잘못된 값보다 낫다).
    occ = d.get("occupationalCategory")
    if isinstance(occ, list):
        occ = ", ".join(str(x) for x in occ)
    duty = strip(occ)
    if not duty:
        body = _re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        # '모집분야 A,B,C 모집인원 1 명 …' 형태. 다음 라벨이 나오기 전까지를 직무로 본다.
        NEXT = r"모집인원|고용형태|급여|근무시간|근무지|경력|학력|접수|마감|담당자|우대"
        m = _re.search(rf"모집\s?분야\s+(.{{2,80}}?)\s+(?:{NEXT})", body)
        if not m:
            m = _re.search(r"모집\s?분야\s+([^\s]{2,80})", body)
        if m:
            duty = m.group(1).strip(" ,·/|")[:120]

    return {"회사명": org, "공고제목": d.get("title", ""),
            "직무": duty[:150],
            "경력": strip(d.get("experienceRequirements"))[:60],
            "고용형태": ", ".join(etype)[:40],
            "지역": region or strip(loc.get("name") if isinstance(loc, dict) else "")[:40],
            "기술스택": tech,
            "마감일": str(d.get("validThrough", ""))[:10],
            "공고URL": url, "수집시각": time.strftime("%Y-%m-%d %H:%M:%S")}


# ---------------------------------------------------------------------------
# 체크포인트 (전량 수집용)
# ---------------------------------------------------------------------------
# 10만 건 규모는 한 번에 끝나지 않는다. 중간에 끊겨도 이어받을 수 있어야 하고,
# 메모리에 다 들고 있다가 마지막에 쓰면 중단 시 전부 날아간다.
# → 수집하는 족족 JSONL 로 append 하고, 재실행 시 이미 받은 URL 은 건너뛴다.

def ckpt_path(site):
    LOGS.mkdir(parents=True, exist_ok=True)
    return LOGS / f"{site.name}.ckpt.jsonl"


def ckpt_load(site):
    """체크포인트에서 이미 수집한 행을 복원하고, 완료된 URL 집합을 돌려준다."""
    p = ckpt_path(site)
    done = set()
    if not p.exists():
        return done
    bad = 0
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                bad += 1          # 중단 시점에 잘린 마지막 줄 — 버리고 계속
                continue
            u = row.get("공고URL")
            if u and u not in done:
                done.add(u)
                site.rows.append(row)
    site.note(f"체크포인트 복원: {len(done):,}건" + (f" (손상 {bad}줄 무시)" if bad else ""))
    return done


def fetch_many_ckpt(site, urls, parse, workers=4, per_sec=2.0, label=""):
    """fetch_many 와 같지만 수집 즉시 체크포인트에 append 하고 이미 받은 URL 은 건너뛴다."""
    done = ckpt_load(site)
    todo = [u for u in urls if u not in done]
    site.note(f"{label}: 전체 {len(urls):,}건 중 남은 {len(todo):,}건 수집")
    if not todo:
        return {"ok": 0, "fail": 0, "skip": 0}

    f = ckpt_path(site).open("a", encoding="utf-8")
    wlock = threading.Lock()
    orig_append = site.rows.append

    def parse_and_log(u, r):
        row = parse(u, r)
        if row:
            with wlock:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
        return row

    try:
        stat = fetch_many(site, todo, parse_and_log, workers=workers,
                          per_sec=per_sec, label=label)
    finally:
        f.close()
    return stat
