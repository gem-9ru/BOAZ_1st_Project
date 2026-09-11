"""부산장애인일자리정보망 상세 수집 — 118건 전량이 상세 미확보였다.

[왜 없었나] 목록 수집기(`busanjob4u.py`)가 공고URL 을 `?idx={id}&type=CP` 로
조립했는데, 실제 상세 파라미터는 **`rcrtSeq`** 다. 목록 페이지의 `show(id, type)`
함수가 `move_form` 의 `rcrtSeq` 에 값을 넣어 GET 한다.
잘못된 URL 이라 상세를 받을 수 없었고, 최종 산출물의 `대표URL` 118건도 내용 없는
페이지를 가리키고 있었다. 목록 수집기의 URL 조립도 함께 고쳤다.

[정책] 부산광역시 운영 공공 사이트. robots.txt 없음(SSL 체인이 불완전해 조회 자체가
       실패한다), 크롤링 금지 고지 없음 — `docs/03_정책감사.md` 참조.

[얻는 것] 상세가 대단히 풍부하다. 목록에 없는 필드가 거의 전부 있다.
    모집직종   "미용·여행·숙박·음식·경비·돌봄·청소 > 청소·방역 및 가사 서비스"
    직무내용   "기물세척 및 관리"
    급여조건/급여액  "시급" / "1만320원 이상 ~ 1만320원 이하"
    근무형태/근무시간 "주 5일" / "직접입력 / 13:00~22:00"
    학력·경력조건·고용형태·모집인원·근무예정지·사업내용(업종)

실행:  python3 src/busanjob4u_detail.py
"""
import csv, re, sys, warnings
from pathlib import Path
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Site, DATA, NOW, fetch_many_ckpt      # noqa: E402

warnings.filterwarnings("ignore")
csv.field_size_limit(10 ** 9)
ROOT = "https://busanjob4u.net"
LIST = DATA / "부산장애인일자리정보망.csv"
OUT = DATA / "부산장애인일자리정보망_상세.csv"
COLS = ["공고URL", "직무내용", "직종", "채용분야", "업종", "고용형태", "경력",
        "학력", "급여", "근무시간", "근무형태", "모집인원", "상세주소",
        "우대사항", "수집시각"]

# 라벨과 그 다음 라벨 사이의 값을 뽑는다. 본문이 "라벨 값 라벨 값 …" 한 줄로 온다.
LABELS = ["사업체명", "본사/지사", "직종", "사업체규모", "사업내용", "장애인근로자 수",
          "주소", "홈페이지", "모집기간", "모집인원", "모집직종", "직무내용", "경력조건",
          "학력", "고용형태", "수습기간", "근무예정지", "상세주소", "급여조건", "급여액",
          "사회보험", "상여금", "퇴직금", "근무형태", "근무시간", "주 소정근로시간",
          "교대근무", "잔업근무", "휴게시간", "식대비", "기타근무조건", "전공",
          "컴퓨터 활용", "복리후생", "편의시설", "장애인 채용희망", "우대조건",
          "기타 우대사항", "전형방법", "접수방법", "제출서류", "취업지원기관"]
_NEXT = "|".join(re.escape(x) for x in LABELS)


def field(txt, label):
    m = re.search(rf"(?:^|\s){re.escape(label)}\s+(.*?)(?=\s(?:{_NEXT})\s|$)", txt)
    return m.group(1).strip() if m else ""


# "1만320원" 같은 혼합 표기를 숫자로 바꾼다. split_pay 가 원/만원만 알아본다.
def won(v):
    v = (v or "").replace(",", "")
    def rep(m):
        man = int(m.group(1)) * 10000
        return str(man + int(m.group(2) or 0))
    v = re.sub(r"(\d+)\s*만\s*(\d+)?", rep, v)
    return v


def parse(url, resp):
    soup = BeautifulSoup(resp.text, "html.parser")
    main = soup.select_one("#contents") or soup
    txt = re.sub(r"\s+", " ", main.get_text(" ", strip=True))
    if "모집직종" not in txt:
        return None
    occ = field(txt, "모집직종")
    # "대분류 > 중분류" 형태. 끝 조각이 가장 구체적이다.
    leaf = occ.split(">")[-1].strip() if occ else ""
    kind, amt = field(txt, "급여조건"), won(field(txt, "급여액"))
    pay = f"{kind} {amt}".strip() if (kind or amt) else ""
    wt = field(txt, "근무시간")
    wt = re.sub(r"^직접입력\s*/\s*", "", wt).strip()
    days = field(txt, "근무형태")
    row = {
        "공고URL": url,
        "직무내용": field(txt, "직무내용"),
        "직종": leaf,
        "채용분야": occ,                     # MAP: 채용분야 -> 직무상세
        "업종": field(txt, "사업내용"),
        "고용형태": field(txt, "고용형태"),
        "경력": field(txt, "경력조건"),
        "학력": field(txt, "학력"),
        "급여": pay,
        "근무시간": (f"{days} {wt}".strip() if days or wt else ""),
        "근무형태": days,
        "모집인원": field(txt, "모집인원"),
        "상세주소": field(txt, "상세주소") or field(txt, "근무예정지"),
        "우대사항": " ".join(x for x in [field(txt, "우대조건"),
                                       field(txt, "기타 우대사항")] if x).strip(),
        "수집시각": NOW(),
    }
    return row if any(row[c] for c in COLS if c not in ("공고URL", "수집시각")) else None


def main():
    ids = []
    for r in csv.DictReader(LIST.open(encoding="utf-8-sig")):
        m = re.search(r"idx=(\d+)|rcrtSeq=(\d+)", r.get("공고URL") or "")
        if m:
            ids.append(m.group(1) or m.group(2))
    urls = [f"{ROOT}/view.do?no=122&pgMode=show&rcrtSeq={i}" for i in dict.fromkeys(ids)]
    print(f"대상 {len(urls):,}건")
    s = Site("부산장애인일자리정보망_상세", ROOT, delay=0.8)
    s.s.verify = False              # 인증서 체인이 불완전하다(공공 사이트)
    fetch_many_ckpt(s, urls, parse, workers=2, per_sec=2.0, label="장애인포털상세")
    rows = [r for r in s.rows if isinstance(r, dict)]
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    fill = {c: sum(1 for r in rows if r.get(c)) for c in COLS[1:-1]}
    print(f"-> {OUT.name} ({len(rows):,}건)")
    print("   " + " · ".join(f"{c} {v}" for c, v in fill.items() if v))


if __name__ == "__main__":
    main()
