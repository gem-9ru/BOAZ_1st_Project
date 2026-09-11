"""급여·경력 파싱 버그 소급 수정.

`split_pay` 와 `norm_career` 를 고쳤지만(아래), 이미 만들어 배포한 CSV 에는
옛 값이 들어 있다. 전체 파이프라인 재실행(수집 240,608행 → 정규화 → 중복병합)은
몇십 분이 걸리고 통합키까지 다시 만든다.

이 두 컬럼은 **보존된 원문의 순수 함수**다. 그래서 원문에서 다시 계산해
해당 컬럼만 덮어쓴다. 다른 값·행 순서·통합키는 건드리지 않는다.

  급여최소·급여최대   `연봉 5,027~7,078만원` → 최소=7078·최대=(빈칸) 이었다.
                    _MONEY 가 숫자 뒤 단위를 요구해서 앞쪽 숫자를 놓쳤다.
  경력구분·최소연차   `관계없음` 758건이 `기타` 로 빠져 있었다.
                    경력 칸에 날짜가 들어온 행도 `기타` 로 실제 값처럼 세어졌다.

실행:  python3 src/pipeline/repair_fields.py
"""
import csv, sys, collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detail_join                                     # noqa: E402
from normalize import norm_career                       # noqa: E402

csv.field_size_limit(10 ** 9)
BASE = Path(__file__).resolve().parents[2]
VALID_CAREER = {"무관", "신입", "경력"}
TARGETS = ["부산/부산_공고_직종분류.csv", "부산/부산_공고_통합.csv", "부산/부산_공고_원본.csv"]


def repair(path):
    p = BASE / path
    rows = list(csv.DictReader(p.open(encoding="utf-8-sig")))
    cols = list(rows[0].keys())
    st = collections.Counter()
    for r in rows:
        if "급여" in cols:
            k, lo, hi = detail_join.split_pay(r.get("급여"))
            if (k, lo, hi) != (r.get("급여형태"), r.get("급여최소"), r.get("급여최대")):
                st["급여"] += 1
            r["급여형태"], r["급여최소"], r["급여최대"] = k, lo, hi
        # 경력은 `기타` 로 잘못 분류된 것만 손댄다.
        #   `최소연차` 는 중복병합 그룹의 대표값이고, 연차를 밝힌 사이트가
        #   `원본_경력` 을 준 사이트와 다를 수 있다. 원문으로 전부 다시 계산했더니
        #   `경력 3년` 이 `경력 (빈칸)` 이 되어 2,369건의 연차가 날아갔다.
        #   이미 유효한 값이 든 행은 건드리지 않는다.
        if "원본_경력" in cols and (r.get("경력구분") or "") not in VALID_CAREER:
            c, y = norm_career(r.get("원본_경력"))
            if (c, y) != (r.get("경력구분"), r.get("최소연차")):
                st["경력"] += 1
                r["경력구분"] = c
                if not (r.get("최소연차") or "").strip():
                    r["최소연차"] = y
    with p.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(rows)
    print(f"  {path}  {len(rows):,}행 — 급여 {st['급여']:,} · 경력 {st['경력']:,} 수정")


if __name__ == "__main__":
    for t in TARGETS:
        repair(t)
