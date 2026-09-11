"""한국고용직업분류(KECO) 직종코드 부여.

[왜 필요한가]
`직무` 는 사이트마다 태그 체계가 달라 그대로는 집계가 안 된다.
  잡코리아 "국제금융, 금융, 은행, 문서관리, 전산입력, 서무, 행정"
  사람인   "SNS마케팅, 광고마케팅, 바이럴마케팅"
공고를 직무 기준으로 묶으려면 **공통 키**가 있어야 하고, 그게 KECO 코드다.

[코드 체계] 고용24가 쓰는 6자리 코드. 앞 2자리가 대분류다.
    561101  건물 청소원(공공건물,아파트,사무실,병원,상가,공장 등)
    834002  빌딩 전기관리원
    550101  요양보호사(노인요양사)

[분류표를 어디서 얻나]
고용24는 코드 목록 API 를 공개하지 않는다(엔드포인트 전부 404).
대신 **수집한 공고에서 코드↔명칭 쌍을 모아** 표를 만든다.
부산 공고에 실제로 등장하는 직종만 담기므로 이 데이터셋에는 이게 더 적합하다.
표는 `data/keco_직종표.csv` 로 저장한다.

[부여 방식 3단계]  근거를 `직종코드근거` 컬럼에 남긴다
  1. 직접   고용24 상세에서 받은 코드           가장 확실
  2. 명칭   `직종` 텍스트가 표의 명칭과 일치      부산일자리정보망 자체등록분 등
  3. 추정   직무·제목·담당업무를 표의 명칭과 매칭   나머지
추정은 어디까지나 추정이므로 분석 시 `직종코드근거` 로 걸러 쓸 수 있다.
"""
import csv, json, re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
DATA, LOGS = BASE / "data", BASE / "logs"
# data/ 최상위에 두면 normalize 의 `data/*.csv` 글롭에 사이트로 잡힌다.
# 실제로 'keco_직종표' 라는 사이트가 생겨 정규화 결과에 388행이 섞였다.
TABLE = DATA / "keco" / "직종표_v1_수집역산.csv"

# KECO 2018 대분류는 **앞 1자리**다. 앞 2자리를 대분류로 보고 이름을 추측했다가
# 304000(간호사)을 '농림어업' 으로 분류하는 사고가 났다.
# 실측으로 확인: 304000 간호사→3(보건·의료), 561101 건물청소원→5, 813201 CNC선반→8,
#               231100 사회복지사→2, 890000 제조단순→8, 550102 재가요양보호사→5
MAJOR = {
    "0": "경영·사무·금융·보험",
    "1": "연구·공학기술",
    "2": "교육·법률·사회복지·경찰·소방·군인",
    "3": "보건·의료",
    "4": "예술·디자인·방송·스포츠",
    "5": "미용·여행·숙박·음식·경비·돌봄·청소",
    "6": "영업·판매·운전·운송",
    "7": "건설·채굴",
    "8": "설치·정비·생산",
    "9": "농림어업",
}

# 1글자도 토큰으로 센다. 2글자 이상만 세면 "웹 디자이너" 가 {디자이너} 하나가 되어
# 미용실 디자이너 공고에 웹디자이너 코드가 붙는다(실제로 그랬다).
_TOK = re.compile(r"[가-힣A-Za-z]+")
_PAREN = re.compile(r"\s*\([^)]*\)\s*")
_NOISE = {"관련", "종사원", "종사자", "기타", "및", "그외", "그", "외", "전문가", "단순", "노무",
          "원", "직", "사", "자", "등", "의", "를", "을", "이", "가", "와", "과"}


def _norm(name):
    """명칭에서 비교용 토큰 집합을 만든다. 괄호 예시는 뗀다."""
    core = _PAREN.sub(" ", name or "")
    return {w for w in _TOK.findall(core) if w not in _NOISE}


def build_table():
    """수집한 고용24 상세에서 코드↔명칭 표를 만든다."""
    seen, cnt = {}, Counter()
    src = LOGS / "고용24_상세.ckpt.jsonl"
    if src.exists():
        with src.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                c, n = (r.get("직종코드") or "").strip(), (r.get("직종") or "").strip()
                if c and n:
                    seen.setdefault(c, n); cnt[c] += 1
    rows = [{"직종코드": c, "직종명": n, "대분류코드": c[:1],
             "대분류명": MAJOR.get(c[:1], ""), "부산공고수": cnt[c]}
            for c, n in sorted(seen.items())]
    with TABLE.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["직종코드", "직종명", "대분류코드", "대분류명", "부산공고수"])
        w.writeheader(); w.writerows(rows)
    return rows


def load_table():
    if not TABLE.exists():
        build_table()
    rows = list(csv.DictReader(TABLE.open(encoding="utf-8-sig")))
    by_name = {}
    index = []          # (코드, 명칭, 토큰집합)
    for r in rows:
        by_name.setdefault(r["직종명"], r["직종코드"])
        by_name.setdefault(_PAREN.sub("", r["직종명"]).strip(), r["직종코드"])
        core = _PAREN.sub("", r["직종명"]).strip()
        index.append((r["직종코드"], r["직종명"], _norm(r["직종명"]),
                      re.sub(r"\s+", "", core)))
    return by_name, index, {r["직종코드"]: r for r in rows}


class Classifier:
    def __init__(self):
        self.by_name, self.index, self.meta = load_table()

    def assign(self, row):
        """(직종코드, 근거) — 근거: 직접 / 명칭 / 추정 / ''"""
        code = (row.get("직종코드") or "").strip()
        if code:
            return code, "직접"

        name = (row.get("직종") or "").strip()
        if name:
            c = self.by_name.get(name) or self.by_name.get(_PAREN.sub("", name).strip())
            if c:
                return c, "명칭"

        # 추정 — 직무·직무상세·제목·담당업무 앞부분을 합쳐 표의 명칭과 토큰을 맞춘다.
        text = " ".join(filter(None, [
            row.get("직무", ""), row.get("직무상세", ""), row.get("공고제목", ""),
            (row.get("담당업무") or "")[:120]]))
        toks = _norm(text)
        if not toks:
            return "", ""
        # 공백 변형까지 본다. "웹디자이너"(붙여쓰기)와 "웹 디자이너"(띄어쓰기)는 같은 말이다.
        flat = re.sub(r"\s+", "", text)
        best, score = None, 0
        for c, nm, nt, core in self.index:
            if core and len(core) >= 4 and core in flat:
                s = 1.5 + len(core) * 0.001      # 통째로 들어 있으면 가장 강한 근거
                if s > score:
                    best, score = c, s
                continue
            if not nt:
                continue
            hit = len(nt & toks)
            if not hit:
                continue
            # 표의 명칭 토큰을 얼마나 덮었는지. 짧은 명칭이 우연히 걸리는 걸 막으려고
            # 최소 2토큰 일치 또는 명칭 전체 일치를 요구한다.
            cov = hit / len(nt)
            if hit < 2 and cov < 1.0:
                continue
            s = cov + hit * 0.01
            if s > score:
                best, score = c, s
        return (best, "추정") if best else ("", "")


if __name__ == "__main__":
    rows = build_table()
    print(f"KECO 직종표 {len(rows):,}개 -> {TABLE.name}")
    top = sorted(rows, key=lambda r: -int(r["부산공고수"]))[:10]
    for r in top:
        print(f"  {r['직종코드']}  {r['부산공고수']:>5}건  {r['직종명'][:44]}")
