"""자소설닷컴 — 채용달력 내부 API 수집.

[문제1] Next.js SPA. __NEXT_DATA__ 에는 광고(loadingAdvertises)만 있고 공고가 없다.
        /api/recruit, /api/v1/recruit 등 흔한 경로는 404.
[문제2] 브라우저 네트워크 관찰로 POST /employment/calendar_list.json 을 찾았지만
        빈 body / start_date·end_date / month / year+month 전부 400 "잘못된 요청입니다".
        Rails 앱이라 CSRF 토큰을 의심했으나 meta[name=csrf-token] 자체가 없었다.
[해결]  페이지의 JS 번들(_app-*.js)을 받아 'calendar_list' 문자열 주변을 읽어
        실제 호출부를 확인:
            getCalendarList(e,t) => post("/employment/calendar_list.json",
                                         {start_time:e, end_time:t})
        파라미터명이 start_time / end_time 이었다. 이걸로 넣으니 200.
[수집]  연 단위 1회 요청으로 4,300건 이상이 한 번에 오므로 페이지네이션 불필요.
[robots] Disallow 는 /crt/*, /core, /rocket_correction, /coach-sellers, /webview/,
        /demo/ 뿐이고 나머지는 Allow: / → 이 엔드포인트는 허용 범위.

[2차 보강] 목록 API 응답에 직무·지역이 없어 1차 수집에서 둘 다 채움률 0% 였다.
        상세 페이지 __NEXT_DATA__ 를 확인한 결과
          · 직무: initialEmploymentCompany.employments[].field  → 확보 가능
          · 지역: metaTags.seo_recruit.jobLocation 이 빈 배열      → **원본에 없음**
        직무만 상세 요청으로 보강하고, 지역은 원본 한계로 빈칸을 유지한다.
"""

LIST_ROWS = {}          # 공고ID -> 목록에서 얻은 필드


def parse_detail(u, r):
    """상세 __NEXT_DATA__ 에서 직무(employments[].field)를 뽑아 목록 데이터에 병합."""
    m = re.search(r"/recruit/(\d+)", u)
    base = dict(LIST_ROWS.get(m.group(1), {})) if m else {}
    if not base:
        return None
    nd = BeautifulSoup(r.text, "html.parser").select_one("#__NEXT_DATA__")
    if nd:
        try:
            pp = json.loads(nd.string)["props"]["pageProps"]
            emps = ((pp.get("initialEmploymentCompany") or {}).get("employments") or [])
            fields = [e.get("field") for e in emps if e.get("field")]
            if not fields:
                d = ((pp.get("metaTags") or {}).get("description") or "")
                mm = re.search(r"모집\s*직무\s*[:：]\s*([^-|]+)", d)
                if mm:
                    fields = [mm.group(1).strip()]
            base["직무"] = ", ".join(dict.fromkeys(fields))[:120]
        except Exception:
            pass
    base["수집시각"] = NOW()
    return base
import datetime as dt
import json, re
from bs4 import BeautifulSoup
from common import Site, NOW, fetch_many

API = "https://jasoseol.com/employment/calendar_list.json"
# [수정] 처음엔 값 4개를 눈대중으로 매핑했고(4를 '신입/경력'으로 오기), 5·6·7 은 아예 없어서
#        해당 공고의 경력 칸이 빈칸이 됐다(채움률 86%).
#        추측을 그만두고 JS 번들(_app-*.js)에서 공식 라벨 배열을 찾아 그대로 옮겼다:
#          [{id:1,label:"신입"},{id:2,label:"경력"},{id:3,label:"인턴"},
#           {id:4,label:"계약직"},{id:7,label:"교육"}]
#        번들에 없는 5·6 은 실데이터에 존재하므로 원본 코드값을 그대로 남겨 추적 가능하게 둔다.
# ※ division 7 '교육' 은 채용공고가 아니라 교육생 모집이다(청년취업사관학교, 아카데미 등).
#   데이터셋 성격상 제외 대상이라 별도 표시해 정규화 단계에서 걸러낸다.
DIVISION = {1: "신입", 2: "경력", 3: "인턴", 4: "계약직", 7: "교육"}
RECRUIT_TYPE = {0: "수시채용", 1: "상시채용", 2: "공개채용"}

def main():
    s = Site("자소설닷컴", "https://jasoseol.com", delay=1.0)
    if not s.allowed(API):
        s.note("robots.txt 차단 — 중단"); s.save(); return
    s.s.headers.update({"Referer": "https://jasoseol.com/recruit",
                        "Origin": "https://jasoseol.com",
                        "X-Requested-With": "XMLHttpRequest"})
    s.note("SPA + 파라미터 미상 → JS 번들 역추적으로 start_time/end_time 파라미터 확보")
    y = dt.date.today().year
    seen = set()
    for start, end in [(f"{y}-01-01", f"{y}-12-31"), (f"{y+1}-01-01", f"{y+1}-06-30")]:
        r = s.s.post(API, json={"start_time": start, "end_time": end}, timeout=60)
        if r.status_code != 200:
            s.note(f"{start}~{end} 실패 HTTP {r.status_code}"); continue
        items = r.json().get("employment") or []
        new = 0
        for it in items:
            eid = it.get("id")
            if eid in seen:
                continue
            seen.add(eid); new += 1
            emps = it.get("employments") or []
            divs = sorted({DIVISION.get(e.get("division")) or
                           (f"코드{e['division']}" if e.get("division") else "")
                           for e in emps} - {""})
            LIST_ROWS[str(eid)] = {
                "회사명": (it.get("company_group") or {}).get("name") or it.get("name", ""),
                "공고제목": it.get("title", ""), "직무": "",
                "경력": ", ".join(divs),
                "고용형태": RECRUIT_TYPE.get(it.get("recruit_type"), ""),
                "지역": "", "기술스택": "",
                "마감일": str(it.get("end_time") or "")[:10],
                "공고URL": f"https://jasoseol.com/recruit/{eid}",
                "수집시각": NOW()}
        s.note(f"{start}~{end}: {len(items)}건 수신 / 신규 {new}건")
    s.note(f"목록 {len(LIST_ROWS):,}건 → 직무 보강을 위해 상세 요청 (지역은 원본에 없어 제외)")
    urls = [f"https://jasoseol.com/recruit/{i}" for i in sorted(LIST_ROWS, key=int)]
    fetch_many(s, urls, parse_detail, workers=3, per_sec=2.5, label="recruit")
    s.save()

if __name__ == "__main__":
    main()
