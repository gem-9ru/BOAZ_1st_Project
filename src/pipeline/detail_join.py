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
    같은 공고가 양쪽에 있으면 CSV(완료본)를 우선한다.
    """
    seen_name = set()
    for p in sorted(glob.glob(str(DATA / "*상세.csv"))):
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
    "직종": "직종", "업종": "업종", "직급직책": "직급직책",
    "근무시간": "근무시간", "근무형태": "근무형태상세", "급여": "급여",
    "모집인원": "모집인원", "학력": "학력", "상세주소": "상세주소",
    "고용형태": "_고용형태", "근무지역": "_근무지역", "원출처URL": "_원출처URL",
    "경력학력조건": "_경력학력", "기관명": "_기관명", "채용분야": "직무상세",
}

DETAIL_COLS = ["직무상세", "직무키워드", "담당업무", "자격요건", "우대사항",
               "직종", "업종", "직급직책", "근무형태상세", "근무시간",
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
                # 먼저 채워진 값을 덮어쓰지 않는다(사이트 전용 파서 > 범용 파서).
                if v and not d.get(dst):
                    d[dst] = v
            k = _origin_key(r.get("원출처URL"))
            if k and k not in by_origin:
                by_origin[k] = d
    out["__by_origin__"] = by_origin
    return out


def stats(det):
    n = max(len(det), 1)
    return {c: sum(1 for d in det.values() if d.get(c)) * 100 // n
            for c in DETAIL_COLS}
