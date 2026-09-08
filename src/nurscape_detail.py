"""널스케이프 상세 수집 — 부산 48건 중 33건이 상세 미확보였다.

[정책] robots.txt 가 `/Jobs/Details/` 를 허용한다(`site.allowed()` 로 건별 확인).

[구조] 본문이 "라벨 값 라벨 값 …" 한 줄로 온다. 페이지 148KB 중 대부분이
       좌측 카테고리 내비게이션이라, 라벨 사이 값만 뽑는다.

    모집분야    "병동간호사(DE-KEEP)>병동>소아청소년과"
    자격조건    "경력 1년 이상"   학력 "대학교(4년)"
    급여        "3800~4000만원 / 경력인정 시 연봉 협상 가능"
    근무일시    "주5일 07:00 ~ 15:00 / 2교대"
    근무지역    "부산 기장군 정관로 698, 8층"
    필수자격 · 우대조건 · 복리후생 · 모집인원 · 고용형태

[못 얻는 것] `담당업무`(모집 상세내용)는 **회원 전용**이다.
    "모집 상세내용, 근무환경, 접수방법, 인사담당자 정보는 회원에게만 공개"
    로그인해서 뚫지 않는다.

실행:  python3 src/nurscape_detail.py
"""
import csv, glob, re, sys
from pathlib import Path
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Site, DATA, NOW, fetch_many_ckpt      # noqa: E402

csv.field_size_limit(10 ** 9)
ROOT = "https://job.nurscape.net"
OUT = DATA / "널스케이프_상세.csv"
COLS = ["공고URL", "채용분야", "직종", "자격요건", "우대사항", "학력", "경력",
        "고용형태", "급여", "근무시간", "모집인원", "상세주소", "수집시각"]

LABELS = ["모집분야", "모집인원", "모집기간", "자격조건", "학력", "필수자격", "우대조건",
          "근무조건", "급여", "고용형태", "근무일시", "근무지역", "복리후생",
          "상세 모집정보", "남은 기간", "시작일", "마감일"]
_NEXT = "|".join(re.escape(x) for x in LABELS)


def field(txt, label):
    m = re.search(rf"(?:^|\s){re.escape(label)}\s+(.*?)(?=\s(?:{_NEXT})\s|$)", txt)
    return m.group(1).strip() if m else ""


def parse(url, resp):
    txt = re.sub(r"\s+", " ", BeautifulSoup(resp.text, "html.parser")
                 .get_text(" ", strip=True))
    i = txt.find("모집분야")
    if i < 0:
        return None
    txt = txt[i:]
    occ = field(txt, "모집분야")
    row = {
        "공고URL": url,
        "채용분야": occ,                       # MAP: 채용분야 -> 직무상세
        "직종": occ.split(">")[0].strip() if occ else "",
        "자격요건": " · ".join(x for x in [field(txt, "자격조건"),
                                         field(txt, "필수자격")] if x),
        "우대사항": field(txt, "우대조건"),
        "학력": field(txt, "학력"),
        "경력": field(txt, "자격조건"),
        "고용형태": field(txt, "고용형태"),
        "급여": field(txt, "급여"),
        "근무시간": field(txt, "근무일시"),
        "모집인원": field(txt, "모집인원"),
        "상세주소": field(txt, "근무지역"),
        "수집시각": NOW(),
    }
    return row if any(row[c] for c in COLS if c not in ("공고URL", "수집시각")) else None


def main():
    urls = []
    for p in ["data/널스케이프부산.csv", "data/널스케이프.csv"]:
        f = Path(p)
        if not f.exists():
            continue
        for r in csv.DictReader(f.open(encoding="utf-8-sig")):
            u = (r.get("공고URL") or "").strip()
            if u and "/Jobs/Details/" in u:
                urls.append(u)
    urls = list(dict.fromkeys(urls))
    print(f"대상 {len(urls):,}건")
    s = Site("널스케이프_상세", ROOT, delay=0.6)
    fetch_many_ckpt(s, urls, parse, workers=3, per_sec=3.0, label="널스케이프상세")
    rows = [r for r in s.rows if isinstance(r, dict)]
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    fill = {c: sum(1 for r in rows if r.get(c)) for c in COLS[1:-1]}
    print(f"-> {OUT.name} ({len(rows):,}건)")
    print("   " + " · ".join(f"{c} {v}" for c, v in fill.items() if v))


if __name__ == "__main__":
    main()
