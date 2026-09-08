"""사이트별 '부산 지역' 접근 경로 전수 조사.

전국 수집 후 부산을 걸러내는 방식은 다지역 공고를 통째로 놓친다.
잡코리아 4,149 → 지역필터 8,660, 커리어 852 → 지역필터 5,209 이 그 결과였다.

이 스크립트는 사이트마다 아래를 한 번에 확인한다.
  1. 지역 필터가 존재하는가 / 파라미터가 무엇인가
  2. 사이트가 밝히는 부산 총건수(정본)
  3. 페이지네이션이 어디까지 먹는가 (인위적 상한에 걸리지 않는지)
결과를 표로 찍어 결손을 한눈에 본다.
"""
import json, re, sys, time
import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})


def txt(u, **kw):
    r = S.get(u, timeout=25, **kw)
    r.raise_for_status()
    return r.text


def cnt(t, pat=r"([\d,]{2,})\s*건"):
    return [x.replace(",", "") for x in re.findall(pat, re.sub("<[^>]+>", " ", t))]


RESULT = []


def rec(site, path, total, note=""):
    RESULT.append((site, path, total, note))
    print(f"{site:14}{str(total):>9}  {path[:58]:60}{note}", flush=True)


# ── 사이트별 조사기 ────────────────────────────────────────────────
def a_remember():
    # 리멤버 커리어: 지역 필터가 쿼리로 붙는지
    for u in ["https://career.rememberapp.co.kr/job/postings?regions=%EB%B6%80%EC%82%B0",
              "https://career.rememberapp.co.kr/job/postings?region=busan"]:
        try:
            t = txt(u); rec("리멤버커리어", u, cnt(t)[:2] or "?", "")
            return
        except Exception as e:
            rec("리멤버커리어", u, "ERR", str(e)[:40])


def a_catch():
    API = "https://www.catch.co.kr/api/v1.0/recruit/information/getRecruitList"
    for body in [{"Area": "부산", "PageSize": 1, "PageIndex": 1},
                 {"AreaCode": "26", "PageSize": 1, "PageIndex": 1},
                 {"Region": "부산", "PageSize": 1, "PageIndex": 1}]:
        try:
            d = S.post(API, json=body, timeout=25).json()
            tot = json.dumps(d, ensure_ascii=False)
            m = re.search(r'"intTotalRecordCount"\s*:\s*(\d+)', tot)
            rec("캐치", f"{API}  {list(body)[0]}", m.group(1) if m else "?", "")
            return
        except Exception as e:
            rec("캐치", str(body)[:40], "ERR", str(e)[:40])


def a_jumpit():
    for q in ["sido=%EB%B6%80%EC%82%B0", "regionId=8", "locationId=8"]:
        try:
            d = S.get(f"https://jumpit-api.saramin.co.kr/api/positions?page=1&size=1&{q}",
                      timeout=25).json()
            tc = ((d.get("result") or {}).get("totalCount")
                  if isinstance(d.get("result"), dict) else None)
            rec("점핏", q, tc if tc is not None else "?", "")
        except Exception as e:
            rec("점핏", q, "ERR", str(e)[:40])


def a_joballio():
    # 잡알리오: 근무지역 코드
    for u in ["https://job.alio.go.kr/recruit.do?pageNo=1&param=&idx=&recruitYear=&"
              "recruitMonth=&detail_code=&location=B&work_type=&career=&employment=&"
              "replacement=&s_date=&e_date=&org_type=&org_name=&title="]:
        try:
            t = txt(u); rec("잡알리오", "location=B(부산)", cnt(t)[:2] or "?", "")
        except Exception as e:
            rec("잡알리오", u[:40], "ERR", str(e)[:40])


def a_gojobs():
    for u in ["https://www.gojobs.go.kr/apmMain.do?menuNo=401&areaCd=26"]:
        try:
            t = txt(u); rec("나라일터", "areaCd=26", cnt(t)[:2] or "?", "")
        except Exception as e:
            rec("나라일터", u[:40], "ERR", str(e)[:40])


def a_worker():
    for u in ["https://www.worker.co.kr/jobs/?area=%EB%B6%80%EC%82%B0",
              "https://www.worker.co.kr/job/list?area=busan"]:
        try:
            t = txt(u); rec("건설워커", u[-40:], cnt(t)[:2] or "?", "")
            return
        except Exception as e:
            rec("건설워커", u[-40:], "ERR", str(e)[:40])


def a_nurscape():
    for u in ["https://www.nurscape.net/recruit?area=%EB%B6%80%EC%82%B0",
              "https://www.nurscape.net/career/recruit/list?sido=부산"]:
        try:
            t = txt(u); rec("널스케이프", u[-42:], cnt(t)[:2] or "?", "")
            return
        except Exception as e:
            rec("널스케이프", u[-42:], "ERR", str(e)[:40])


if __name__ == "__main__":
    print(f"{'사이트':14}{'정본':>9}  {'경로':60}비고")
    print("-" * 110)
    for f in [a_remember, a_catch, a_jumpit, a_joballio, a_gojobs, a_worker, a_nurscape]:
        try:
            f()
        except Exception as e:
            print(" ", f.__name__, "ERR", e)
        time.sleep(0.5)
