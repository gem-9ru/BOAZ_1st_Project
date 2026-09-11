# -*- coding: utf-8 -*-
"""잡플래닛 ↔ 잡코리아 대조 후 중복분 정리.

배경
  잡플래닛 푸터에 "모든 컨텐츠의 무단 전재, 무단 수집, 재배포 및 AI 학습 이용 금지" 고지가
  있어 데이터셋에 남기지 않는 방향으로 정한다. 다만 잡플래닛 공고의 96.7% 는 원본이
  잡코리아이고, 응답에 jobkorea_posting_id 를 그대로 담고 있다(수집 시 외부원본ID 로 보존).
  → 잡코리아 전량 수집이 끝나면 같은 공고를 잡코리아 쪽 데이터로 대체할 수 있다.

분류
  A 대체가능 : 외부원본ID 의 잡코리아 공고번호가 잡코리아 수집분에 존재  → 삭제(잡코리아로 대체)
  B 잡코리아누락: 잡코리아 원본이라고 표시돼 있으나 우리 수집분에 없음    → 보류(판단 필요)
  C 잡플래닛고유: 외부원본ID 자체가 없음                              → 보류(판단 필요)

--apply 를 주면 실제로 data/잡플래닛.csv 를 B+C 만 남기도록 다시 쓰고
A 는 제외됨/잡플래닛_잡코리아중복.csv 로 옮긴다. 옵션 없이 실행하면 집계만 보여준다(기본).
"""
import csv, re, sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
DATA, EXCL, LOGS = BASE / "data", BASE / "제외됨", BASE / "logs"

def jobkorea_ids():
    """잡코리아 수집분의 공고번호 집합.

    [수정] 처음엔 '잡코리아.csv' 하나만 읽어서, 사이트맵 밖 공고를 따로 받아둔
      '잡코리아추가.csv'(28,241건)가 대조에서 통째로 빠졌다.
      두 데이터셋과 각각의 체크포인트를 모두 합산한다.
    """
    import json
    ids = set()
    for name in ("잡코리아", "잡코리아추가"):
        ck = LOGS / f"{name}.ckpt.jsonl"
        if ck.exists():
            for line in open(ck, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    u = json.loads(line).get("공고URL", "")
                except Exception:
                    continue
                m = re.search(r"GI_Read/(\d+)", u)
                if m:
                    ids.add(m.group(1))
        f = DATA / f"{name}.csv"
        if f.exists():
            for r in csv.DictReader(open(f, encoding="utf-8-sig")):
                m = re.search(r"GI_Read/(\d+)", r.get("공고URL", ""))
                if m:
                    ids.add(m.group(1))
    return ids


def main():
    apply = "--apply" in sys.argv
    jk = jobkorea_ids()
    src = DATA / "잡플래닛.csv"
    if not src.exists():
        print("잡플래닛.csv 없음"); return
    rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
    cols = list(rows[0].keys()) if rows else []

    A, B, C = [], [], []
    for r in rows:
        ext = (r.get("외부원본ID") or "").strip()
        m = re.match(r"잡코리아:(\d+)$", ext)
        if not m:
            C.append(r)
        elif m.group(1) in jk:
            A.append(r)
        else:
            B.append(r)

    tot = len(rows)
    pct = lambda n: f"{100*n/tot:5.1f}%" if tot else "-"
    print(f"잡코리아 수집분 공고번호 {len(jk):,}개 확보 (전체 목표 108,009)")
    print(f"잡플래닛 {tot:,}행 분류")
    print(f"  A 대체가능(잡코리아에 있음)  {len(A):7,}  {pct(len(A))}  → 삭제 대상")
    print(f"  B 잡코리아 누락             {len(B):7,}  {pct(len(B))}  → 보류")
    print(f"  C 잡플래닛 고유             {len(C):7,}  {pct(len(C))}  → 보류")

    if not apply:
        print("\n집계만 수행했습니다. 실제 정리는 --apply 를 붙여 실행하세요.")
        return

    EXCL.mkdir(exist_ok=True)
    def dump(p, data):
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(data)
    dump(EXCL / "잡플래닛_잡코리아중복.csv", A)
    dump(src, B + C)
    print(f"\n적용 완료")
    print(f"  data/잡플래닛.csv        → {len(B)+len(C):,}행 (B+C 만 유지)")
    print(f"  제외됨/잡플래닛_잡코리아중복.csv → {len(A):,}행")

if __name__ == "__main__":
    main()
