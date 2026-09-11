"""상세 보강 데이터 로더 — data/*_상세.csv, data/*_직무상세.csv 를 공고URL 로 붙인다.

목록 수집만으로는 '무슨 일을 하는 자리인지' 를 알 수 없어서,
사이트별 상세페이지를 따로 받아 두었다(src/busanjob_detail.py, src/duty_detail.py).
여기서는 그 결과를 정규화 단계에 합류시킨다.

  data/부산일자리정보망_상세.csv   직무내용·직종·업종·고용형태·근무지역·원출처URL
  data/{사이트}_직무상세.csv       모집분야·직무키워드·담당업무·자격요건·우대사항·
                                  직급직책·근무형태·근무시간·급여·업종·상세주소
  data/사람인_직무상세.csv          위와 동일 (rec_idx 경유)
"""
import csv, glob, json, re
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
DATA, LOGS = BASE / "data", BASE / "logs"


def _sources():
    """완료된 CSV 와 진행 중인 체크포인트를 모두 읽는다.

    상세 수집은 몇 시간씩 걸리고 CSV 는 끝나야 쓰인다.
    수집 도중에도 파이프라인을 돌려 중간 결과를 확인할 수 있어야 하므로
    logs/*.ckpt.jsonl 도 같은 형태로 읽어들인다.
    같은 이름이 양쪽에 있으면 **더 최근에 쓰인 쪽**을 쓴다.
    파서를 고쳐 재수집하는 동안에는 체크포인트가 CSV 보다 새롭고 컬럼도 많다.
    (예전에는 CSV 를 무조건 우선해서, 직종코드를 새로 받는 중인데도
     코드 없는 옛 CSV 가 계속 읽혔다.)
    """
    seen_name = set()
    for p in sorted(glob.glob(str(DATA / "*상세.csv"))):
        ck = LOGS / f"{Path(p).stem}.ckpt.jsonl"
        if ck.exists() and ck.stat().st_mtime > Path(p).stat().st_mtime:
            continue                      # 체크포인트가 더 새롭다 → 아래에서 읽는다
        seen_name.add(Path(p).stem)
        with open(p, encoding="utf-8-sig") as f:
            yield p, list(csv.DictReader(f))
    for p in sorted(glob.glob(str(LOGS / "*상세.ckpt.jsonl"))):
        name = Path(p).stem.replace(".ckpt", "")
        if name in seen_name:
            continue
        rows = []
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass          # 중단 시점에 잘린 마지막 줄
        yield p, rows

# 상세 파일이 쓰는 컬럼 → 정규화 출력 컬럼
MAP = {
    "직무내용": "담당업무", "담당업무": "담당업무",
    "모집분야": "직무상세", "직무키워드": "직무키워드",
    "자격요건": "자격요건", "우대사항": "우대사항",
    "직종": "직종", "직종코드": "직종코드", "업종": "업종", "직급직책": "직급직책",
    "근무시간": "근무시간", "근무형태": "근무형태상세", "급여": "급여",
    "모집인원": "모집인원", "학력": "학력", "상세주소": "상세주소",
    "고용형태": "_고용형태", "근무지역": "_근무지역", "원출처URL": "_원출처URL",
    "경력학력조건": "_경력학력", "기관명": "_기관명", "채용분야": "직무상세",
    # [누락 수정] 부산일자리정보망은 급여를 `임금조건` 칸에 담는다.
    #   여기에 없어서 22,694건(부산분 17,220건)이 통째로 버려지고 있었다.
    #   이 파일 docstring 에는 "얻는 것은 … 임금조건 …" 이라고 적혀 있었는데
    #   매핑만 빠져 있었다.
    "임금조건": "급여",
    # 고용24 상세의 경력 칸(`관계없음`/`신입`/`경력`).
    "경력": "_경력",
}

# 부산일자리정보망 `임금조건` 은 라벨이 한 번 더 붙어 온다.
#   "연봉 시급 10,320원"  "연봉 월급 360만원"  "연봉 연봉 3,000만원"  "연봉 면접후 결정"
# 앞의 `연봉` 은 칸 제목이고 실제 급여형태는 그 뒤에 있다. 그대로 쓰면
# 시급 10,320원이 '연봉 1만원' 으로 읽힌다.
_BJ_PAYLABEL = re.compile(r"^연봉\s+(?=(?:연봉|월급|주급|일급|시급|건별|성과급|협의|면접))")


def fix_busanjob_pay(v):
    return _BJ_PAYLABEL.sub("", (v or "").strip())

# 절편 추출이 앞 라벨을 물고 오는 경우가 있다.
#   "인원 근무지 수신 RM ※ 수신 RM(수신 마케팅 전문인력) …"
#   "자격요건 사무보조 및 고객응대 사원 …"
# 값을 다시 받지 않고 여기서 걷어낸다(이미 수집한 것에도 적용된다).
_LEAD = re.compile(
    r"^(?:\s*(?:자격\s?요건|지원\s?자격|우대\s?사항|모집\s?분야|모집\s?부문|모집\s?인원|"
    r"인원|근무지|근무\s?조건|담당\s?업무|주요\s?업무|업무\s?내용|직무\s?내용|"
    r"이런\s?업무를\s?해요|Key\s+Responsibilities)\s*[:：]?\s*)+", re.I)
_WRAP = re.compile(r"^[\(\[]\s*|\s*[\)\]]$")


def clean_duty(v):
    v = (v or "").strip()
    if not v:
        return ""
    prev = None
    while prev != v:                 # 라벨이 두세 개 겹쳐 붙는 경우가 있다
        prev = v
        v = _LEAD.sub("", v).strip()
        # "(Key Responsibilities) …" 처럼 라벨이 괄호에 싸여 오기도 한다
        v = re.sub(r"^[\(\[][^)\]]{0,30}[\)\]]\s*", "", v).strip() if _LEAD.search(
            re.sub(r"^[\(\[]|[\)\]]", "", v[:40])) else v
    return v.strip(" ·ㆍ-–—:：,")


DETAIL_COLS = ["직무상세", "직무키워드", "담당업무", "자격요건", "우대사항",
               "직종", "직종코드", "업종", "직급직책", "근무형태상세", "근무시간",
               "급여", "모집인원", "학력", "상세주소"]


# 원출처URL 에서 그 공고를 가리키는 열쇠를 뽑는다.
# 부산일자리정보망은 사람인·잡코리아·워크넷 공고를 재노출하면서 원본 URL 을 남긴다.
# 이걸로 '부산잡 상세'를 '사람인/잡코리아 목록'에 붙일 수 있다.
_SRC_KEY = [
    ("saramin",  re.compile(r"saramin\.co\.kr.*?rec_idx=(\d+)")),
    ("jobkorea", re.compile(r"jobkorea\.co\.kr/Recruit/GI_Read/(\d+)")),
    ("worknet",  re.compile(r"work24\.go\.kr.*?wantedAuthNo=([A-Za-z0-9]+)")),
]


def _origin_key(url):
    for name, pat in _SRC_KEY:
        m = pat.search(url or "")
        if m:
            return f"{name}:{m.group(1)}"
    return None


def _own_key(url):
    """우리가 가진 공고URL 에서 같은 형태의 열쇠를 만든다."""
    return _origin_key(url)


def load():
    """{공고URL: {정규화컬럼: 값}} 를 돌려준다.

    [교차 연결] 사람인은 상세 직접 수집이 IP 차단으로 막혔다(5,670건에서 중단).
    그런데 부산일자리정보망이 사람인 공고를 재노출하면서 상세를 함께 갖고 있고,
    그 상세에 원출처 rec_idx 가 적혀 있다. 이걸로 사람인 목록에 붙인다.
      · 부산잡 상세가 가진 사람인 원출처 12,820건
      · 사람인 상세 미확보 8,276건 중 3,761건을 이 경로로 메운다
    단 사람인 원출처 공고에는 '직무내용' 이 없다.
    얻는 것은 고용형태·근무지역·경력학력조건·임금조건·**모집인원**·업종이다.
    """
    out = {}
    by_origin = {}          # "saramin:54962641" -> 상세 dict
    for p, rows in _sources():
        for r in rows:
            u = (r.get("공고URL") or "").strip()
            if not u:
                continue
            d = out.setdefault(u, {})
            for src, dst in MAP.items():
                v = (r.get(src) or "").strip()
                if src == "임금조건":
                    v = fix_busanjob_pay(v)
                # 먼저 채워진 값을 덮어쓰지 않는다(사이트 전용 파서 > 범용 파서).
                if v and not d.get(dst):
                    d[dst] = clean_duty(v) if dst in ("담당업무", "자격요건", "우대사항") else v
            k = _origin_key(r.get("원출처URL"))
            if k and k not in by_origin:
                by_origin[k] = d
    # [양방향] 지금까지는 한 방향만 연결됐다.
    #   O  잡코리아·사람인 **목록** 행  <-  부산잡 상세 (by_origin)
    #   X  부산잡 **목록** 행          <-  잡코리아·사람인 상세
    # 06_알려진_한계.md 는 "잡코리아분 5,751건은 GI_No 교차 연결로 잡코리아
    # 상세에서 메운다" 고 적어 두었지만 반대 방향이 없었다. 중복병합이 대부분
    # 메우지만, 부산잡 행이 잡코리아 행과 안 묶인 3,558건은 그대로 비어 있었다.
    by_ownkey = {}
    for u, d in out.items():
        k = _own_key(u)
        if k:
            by_ownkey.setdefault(k, d)
    filled = 0
    for u, d in out.items():
        k = _origin_key(d.get("_원출처URL"))
        src = by_ownkey.get(k) if k else None
        if not src or src is d:
            continue
        for c, v in src.items():
            if c.startswith("_") or not v or d.get(c):
                continue
            d[c] = v
            filled += 1
    out["__by_origin__"] = by_origin
    out["__stat__"] = {"원출처_역방향_보강": filled}
    return out


def stats(det):
    n = max(len(det), 1)
    return {c: sum(1 for d in det.values() if d.get(c)) * 100 // n
            for c in DETAIL_COLS}


# ---------------------------------------------------------------------------
# 한 칸에 여러 정보가 담긴 값 쪼개기
# ---------------------------------------------------------------------------
# "주5일(월~금) 09:00 ~ 18:00" 은 근무요일·시작·종료 세 가지다.
# "연봉 3,000만원 ~ 4,000만원" 은 급여형태·최소·최대 세 가지다.
# 원문은 그대로 두고 쪼갠 값을 옆에 함께 싣는다.

_PAYKIND = re.compile(r"(연봉|월급|주급|일급|시급|건별|성과급|협의|면접\s*후\s*결정|회사\s*내규)")
_MONEY = re.compile(r"([\d,]{2,})\s*(만원|원)")
# "연봉 5,027~7,078만원" 처럼 단위가 **뒤쪽 숫자에만** 붙는 표기가 흔하다.
# _MONEY 는 숫자 뒤에 단위를 요구하므로 5,027 을 놓치고 7,078 만 잡아
# 하한 칸에 상한값이 들어갔다(1,853행). 미리 단위를 양쪽에 펴 준다.
_PAYRANGE = re.compile(r"([\d,]{2,})\s*[~\-–]\s*([\d,]{2,})\s*(만원|원)")
_TIME = re.compile(r"(\d{1,2})\s*[:시]\s*(\d{0,2})")
_DAYS = re.compile(r"(주\s?\d일(?:\([^)]{1,12}\))?|격일제?|주말|평일|월~금|월~토|교대|"
                   r"[23]교대|탄력근무제|시간제|자율출퇴근|협의)")

# 급여 칸에 엉뚱한 문장이 들어오는 경우가 있다(라벨 파싱이 옆 문단을 물었을 때).
# "조건 학력무관", "정보 신입 / 평균 채용인원 11명" 처럼.
# 급여 어휘로 시작하지 않고 금액도 없으면 급여로 인정하지 않는다.
def clean_pay(v):
    v = (v or "").strip()
    if not v:
        return ""
    if not _PAYKIND.search(v[:20]) and not _MONEY.search(v[:40]):
        return ""
    return v[:200]


def split_pay(v):
    """(급여형태, 최소, 최대) — 금액은 만원 단위 정수 문자열."""
    v = (v or "").strip()
    if not v:
        return "", "", ""
    v = _PAYRANGE.sub(lambda m: f"{m.group(1)}{m.group(3)} ~ {m.group(2)}{m.group(3)}", v)
    k = _PAYKIND.search(v)
    kind = k.group(1) if k else ""
    kind = {"면접 후 결정": "면접후결정", "면접후 결정": "면접후결정",
            "회사 내규": "회사내규", "회사내규": "회사내규"}.get(kind.replace("  ", " "), kind)
    nums = []
    for m in _MONEY.finditer(v):
        n = int(m.group(1).replace(",", ""))
        if m.group(2) == "원":
            if n < 100000:          # 시급·일급은 원 단위 그대로 둔다
                nums.append(n)
                continue
            n = n // 10000
        nums.append(n)
    nums = [n for n in nums if n > 0]
    lo = str(nums[0]) if nums else ""
    hi = str(nums[1]) if len(nums) > 1 else ""
    if hi and hi == "0":            # "3700만원 ~ 0만원" 은 상한 미기재다
        hi = ""
    if hi and int(lo) > int(hi):    # 표기 순서가 뒤집힌 공고
        lo, hi = hi, lo
    return kind, lo, hi


def split_worktime(v):
    """(근무요일, 시작, 종료)"""
    v = (v or "").strip()
    if not v:
        return "", "", ""
    d = _DAYS.search(v)
    days = d.group(1) if d else ""
    ts = _TIME.findall(v)
    fmt = lambda h, m: f"{int(h):02d}:{(m or '00'):0>2}"
    start = fmt(*ts[0]) if ts else ""
    end = fmt(*ts[1]) if len(ts) > 1 else ""
    return days, start, end


def clean_addr(v):
    """지도보기 같은 UI 문구를 뗀다."""
    v = re.sub(r"\s*(지도보기|약도|로드뷰|길찾기)\s*$", "", (v or "").strip())
    return v[:200]
