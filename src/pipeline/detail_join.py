"""상세 보강 데이터 로더 — data/*_상세.csv, data/*_직무상세.csv 를 공고URL 로 붙인다.

목록 수집만으로는 '무슨 일을 하는 자리인지' 를 알 수 없어서,
사이트별 상세페이지를 따로 받아 두었다(src/busanjob_detail.py, src/duty_detail.py).
여기서는 그 결과를 정규화 단계에 합류시킨다.

  data/부산일자리정보망_상세.csv   직무내용·직종·업종·고용형태·근무지역·원출처URL
  data/{사이트}_직무상세.csv       모집분야·직무키워드·담당업무·자격요건·우대사항·
                                  직급직책·근무형태·근무시간·급여·업종·상세주소
  data/사람인_직무상세.csv          위와 동일 (rec_idx 경유)
"""
import csv, glob, re
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "data"

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


def load():
    """{공고URL: {정규화컬럼: 값}} 를 돌려준다."""
    out = {}
    for p in sorted(glob.glob(str(DATA / "*_상세.csv"))):
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            u = (r.get("공고URL") or "").strip()
            if not u:
                continue
            d = out.setdefault(u, {})
            for src, dst in MAP.items():
                v = (r.get(src) or "").strip()
                # 먼저 채워진 값을 덮어쓰지 않는다(사이트 전용 파서 > 범용 파서).
                if v and not d.get(dst):
                    d[dst] = v
    return out


def stats(det):
    n = max(len(det), 1)
    return {c: sum(1 for d in det.values() if d.get(c)) * 100 // n
            for c in DETAIL_COLS}
