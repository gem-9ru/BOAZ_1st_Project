"""링커리어 — Next.js __NEXT_DATA__(Apollo state) 파싱.

[문제1] sitemap 은 activities(대외활동) 13.5만 URL 뿐이라 채용공고를 직접 못 고른다.
        activity 상세를 다 받아 activityTypeID 로 거르는 건 낭비.
[해결1] 목록 /list/recruit (인턴은 /list/intern) 이 서버사이드 렌더링이라
        <script id="__NEXT_DATA__"> 안 Apollo 캐시에 Activity 객체가 통째로 들어있다.
        HTML 셀렉터 없이 JSON 을 그대로 읽으면 되고, activityTypeID=5 가 채용이다.
[문제2] 페이지 파라미터명이 문서화돼 있지 않음 → page/pageNo/p 를 순서대로 시도해
        1페이지와 id 집합이 달라지는 파라미터를 런타임에 자동 선택하도록 했다.
"""
import datetime as dt
import json, re
from bs4 import BeautifulSoup
from common import Site, NOW

ROOT = "https://linkareer.com"
LISTS = ["/list/recruit", "/list/intern"]
MAX_PAGE = 25

def epoch_to_date(v):
    """epoch 초/밀리초 → YYYY-MM-DD. 값이 없으면 빈 문자열."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    if n > 10 ** 12:
        n //= 1000
    try:
        return dt.datetime.fromtimestamp(n).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return ""


def activities(site, url):
    """Activity 객체와 함께 Category 사전도 돌려준다.

    [직무 수정] 처음엔 jobTypes(=INTERN/EXPERIENCED)를 직무로 넣었는데 그건 고용형태다.
       실제 직무는 Activity.categories 가 가리키는 Category 객체에 있다.
         Activity.categories: [{"__ref": "Category:103000"}]
         Category:103000    : {"name": "전체", "parent": {"__ref": "Category:100003"}}
         Category:100003    : {"name": "IT/개발"}
       상위(parent)와 하위 이름을 합쳐 "IT/개발 > 전체" 형태로 만든다.
    """
    nd = BeautifulSoup(site.get(url).text, "html.parser").select_one("#__NEXT_DATA__")
    if not nd:
        return {}, {}
    st = json.loads(nd.string).get("props", {}).get("pageProps", {}).get("__APOLLO_STATE__", {})
    cats = {k: v for k, v in st.items() if k.startswith("Category:")}
    return {k: v for k, v in st.items() if k.startswith("Activity:")}, cats


def duty_of(v, cats):
    out = []
    for c in (v.get("categories") or []):
        ref = c.get("__ref") if isinstance(c, dict) else None
        node = cats.get(ref) if ref else None
        if not node:
            continue
        name = node.get("name", "")
        par = (node.get("parent") or {}).get("__ref") if isinstance(node.get("parent"), dict) else None
        pname = (cats.get(par) or {}).get("name", "") if par else ""
        out.append(f"{pname} > {name}" if pname and name and name != pname else (name or pname))
    return ", ".join(dict.fromkeys(x for x in out if x))[:150]

def detect_page_param(site, base):
    """페이지 파라미터명을 런타임에 탐지 (문제2 대응)."""
    first = set(activities(site, ROOT + base)[0])
    for p in ("page", "pageNo", "p", "currentPage"):
        try:
            if set(activities(site, f"{ROOT}{base}?{p}=2")[0]) - first:
                site.note(f"{base}: 페이지 파라미터 '{p}' 확인")
                return p
        except Exception:
            continue
    site.note(f"{base}: 유효한 페이지 파라미터 없음 → 1페이지만 수집")
    return None

def main():
    s = Site("링커리어", ROOT, delay=1.0)
    seen = set()
    for base in LISTS:
        param = detect_page_param(s, base)
        pages = range(1, MAX_PAGE + 1) if param else [1]
        for pg in pages:
            u = ROOT + base + (f"?{param}={pg}" if param and pg > 1 else "")
            try:
                acts, cats = activities(s, u)
            except Exception as e:
                s.note(f"{u} 실패: {e}"); break
            new = 0
            for k, v in acts.items():
                if v.get("activityTypeID") not in (5, None) and v.get("type") != "RECRUIT":
                    continue
                aid = k.split(":")[1]
                if aid in seen:
                    continue
                seen.add(aid); new += 1
                s.add(회사명=v.get("organizationName", ""),
                      공고제목=v.get("title", ""),
                      직무=duty_of(v, cats),
                      경력=str(v.get("recruitType", "") or ""),
                      고용형태=str(v.get("recruitType", "") or ""),
                      # [버그수정] regions 는 {"__typename":"Region","id":..,"name":"서울"} 객체 리스트다.
                      # str(x) 로 넣으면 CSV 에 dict 문자열이 그대로 박힌다 → name 만 뽑는다.
                      지역=", ".join(x.get("name", "") if isinstance(x, dict) else str(x)
                                    for x in (v.get("regions") or []))[:80],
                      기술스택="",
                      # [버그수정] recruitCloseAt 은 epoch 밀리초(예: 1789916399999)다.
                      # 문자열 앞 10자를 자르면 '1789916399' 같은 숫자가 마감일로 들어간다.
                      마감일=epoch_to_date(v.get("recruitCloseAt")),
                      공고URL=f"{ROOT}/activity/{aid}",
                      수집시각=NOW())
            print(f"    {base} p{pg}: activity={len(acts)} new={new} 누적={len(seen)}")
            if new == 0 and pg > 1:
                break
    s.save()

if __name__ == "__main__":
    main()
