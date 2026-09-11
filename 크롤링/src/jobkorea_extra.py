"""잡코리아 추가 수집 — 잡플래닛이 가리키는 사이트맵 밖 공고.

[배경] 잡플래닛의 경력 채움률이 64% 였고, 결손 17,849행이 **100% 잡코리아 원본**이었다
       (외부원본ID = jobkorea_posting_id). 잡플래닛 API 에는 다른 경력 필드가 없다
       (career_text None / annual.text null / recruitment_text []).

[해법] 잡플래닛 행의 경력을 채우는 대신, **원본인 잡코리아 공고를 직접 수집**한다.
       세 가지가 동시에 해결된다.
         1) 경력 100% 확보 (잡코리아는 JSON-LD 에 경력이 항상 있음)
         2) 잡코리아 커버리지 확장 — 이 공고들은 사이트맵에 거의 없다
            (표본 20,000건 대조 시 28,673건 중 19건만 사이트맵에 존재)
            즉 사이트맵 108,009건 밖의 공고를 잡플래닛 인링크 정보로 발굴하는 셈이다
         3) 정책 문제 해소 — 잡플래닛(무단수집 금지 고지)의 행이 잡코리아 행으로 대체된다

[부하] 본 잡코리아 크롤러가 동시에 돌고 있으므로 이쪽은 초당 2건으로 낮춘다.
       별도 사이트명("잡코리아추가")으로 체크포인트를 분리해 본 수집과 충돌하지 않게 한다.
       최종 산출 시 잡코리아.csv 와 합친다(공고번호 기준 중복 제거).
"""
import csv, json, re
from pathlib import Path
from common import Site, fetch_many_ckpt, parse_jobposting_ld, LOGS, DATA, LD_EXTRA_COLS

def collected_ids():
    """본 잡코리아 수집분(체크포인트 + CSV)의 공고번호."""
    ids = set()
    for p in [LOGS / "잡코리아.ckpt.jsonl"]:
        if p.exists():
            for line in p.open(encoding="utf-8"):
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
    p = DATA / "잡코리아.csv"
    if p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            m = re.search(r"GI_Read/(\d+)", r.get("공고URL", ""))
            if m:
                ids.add(m.group(1))
    return ids

def main():
    s = Site("잡코리아추가", "https://www.jobkorea.co.kr", delay=0.5)
    s.extra_cols = LD_EXTRA_COLS    # JSON-LD 가 주는 학력·급여·주소 등
    have = collected_ids()
    s.note(f"본 수집분 공고번호 {len(have):,}개 확인")

    jp = DATA / "잡플래닛.csv"
    if not jp.exists():
        s.note("잡플래닛.csv 없음 — 중단"); s.save(); return
    want = []
    for r in csv.DictReader(jp.open(encoding="utf-8-sig")):
        m = re.match(r"잡코리아:(\d+)$", (r.get("외부원본ID") or "").strip())
        if m and m.group(1) not in have:
            want.append(m.group(1))
    want = list(dict.fromkeys(want))
    s.note(f"잡플래닛이 가리키는 미수집 잡코리아 공고 {len(want):,}건 (사이트맵 밖 공고 발굴)")

    urls = [f"https://www.jobkorea.co.kr/Recruit/GI_Read/{i}" for i in want]
    fetch_many_ckpt(s, urls, parse_jobposting_ld, workers=3, per_sec=2.0, label="GI_Read추가")
    s.save()

if __name__ == "__main__":
    main()
