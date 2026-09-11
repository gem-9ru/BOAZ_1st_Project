"""게임잡 — 목록에서 GI_No 수집 → 상세 meta 태그 파싱.

[문제1] 잡코리아와 동일 엔진. ?Page / page / Page_No / pageNo / currentPage,
        구형 /List_GI/GI_Game_List.asp?Page=N 까지 전부 무시(응답 바이트 완전 동일).
        menucode 10종을 돌려도 전부 같은 40건 → 목록만으로는 40건이 한계였음.
[문제2] /Company/Detail 페이지는 JS 렌더링이라 정적 HTML 에 공고가 없음(링크 0개).
[해결]  main/home 이 노출하는 GI_No 142개 + 목록 40건을 합쳐 중복 제거한 뒤
        상세 페이지를 직접 요청. 상세에는 JSON-LD 가 없지만
        <meta name="description"> 가
        "[회사] 채용 | [제목] | [경력] | [학력] | [고용형태] | [급여] | [마감]"
        형태로 필드를 파이프 구분해 담고 있어 이걸 정규식으로 분해했다.
[보강]  목록 행의 p.info span 순서가 [경력, 학력, 지역, 업종, 고용형태] 로 고정이라
        지역·업종은 목록에서 얻어 상세 결과에 병합.
[보강2] main/home 에서만 얻은 142건은 목록 메타가 없어 직무·지역이 빈칸이었다(채움률 23%).
        상세 본문을 다시 뜯어보니 meta 태그가 아니라 **본문 dl** 에
          "근무지역 경기 > 성남시 분당구 …" / "모집분야 사업기획(국내), 마케팅 …"
        형태로 들어있다. EXTRA(목록 유래) 가 없을 때 이 값을 쓴다.
        ※ 처음에 "상세 meta 에는 지역이 없다" 고 단정했는데, meta 만 보고 본문을
          확인하지 않은 오판이었다.
"""
import re
from bs4 import BeautifulSoup
from common import Site, NOW, fetch_many

ROOT = "https://www.gamejob.co.kr"
MENUS = ["searchall", "duty", "local", "corp", "area", "category",
         "condition", "qualification", "searchdetail", "searchtot"]
EXTRA = {}          # GI_No -> {지역, 업종} (목록에서 확보)

def collect_list(s):
    ids = set()
    for m in MENUS:
        try:
            soup = BeautifulSoup(s.get(f"{ROOT}/Recruit/joblist?menucode={m}").text, "html.parser")
        except Exception as e:
            s.note(f"목록 실패 {m}: {e}"); continue
        for tr in soup.select("tbody tr"):
            a = tr.select_one('a[href*="GI_Read"]')
            if not a:
                continue
            g = re.search(r"GI_No=(\d+)", a["href"])
            if not g:
                continue
            spans = [x.get_text(" ", strip=True) for x in tr.select("p.info span")]
            EXTRA[g.group(1)] = {"지역": spans[2] if len(spans) > 2 else "",
                                 "업종": spans[3] if len(spans) > 3 else ""}
            ids.add(g.group(1))
        if m == MENUS[0]:
            s.note(f"목록 menucode 순회 시작 (1회당 40건 고정, 중복 다수)")
    return ids

def parse(u, r):
    soup = BeautifulSoup(r.text, "html.parser")
    d = soup.select_one('meta[name="description"]')
    if not d:
        return None
    # 원제목에 대괄호가 들어있어 strip("[]") 를 쓰면 "[퍼스트 디센던트] ..." 의 앞 대괄호까지
    # 잘려나간다. 바깥쪽 한 쌍만 정확히 벗겨낸다.
    def unwrap(x):
        x = x.strip()
        return x[1:-1].strip() if x.startswith("[") and x.endswith("]") else x
    f = [unwrap(x) for x in (d.get("content") or "").split("|")]
    # f[0] 은 "[회사명] 채용" 형태. unwrap 은 '채용' 이 붙어 있어 안 먹으므로 여기서 따로 벗긴다.
    company = re.sub(r"\s*채용\s*$", "", f[0]).strip() if f else ""
    company = unwrap(company)
    gi = re.search(r"GI_No=(\d+)", u)
    ex = EXTRA.get(gi.group(1), {}) if gi else {}
    # [보강2] 목록 유래 값이 없으면 본문에서 근무지역·모집분야를 읽는다.
    body = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    region = ex.get("지역", "")
    if not region:
        m = re.search(r"근무지역\s*([가-힣]{2}\s*>\s*[가-힣]+(?:시|군|구)(?:\s*[가-힣]+)?)", body)
        if not m:
            m = re.search(r"근무지역\s*([가-힣]{2,3}\s*>\s*[^복리·]{2,18})", body)
        region = re.sub(r"\s+", " ", m.group(1)).strip()[:30] if m else ""
    duty = ex.get("업종", "")
    if not duty:
        m = re.search(r"모집분야\s*([^툴팁]{2,60})", body)
        duty = re.sub(r"\s+", " ", m.group(1)).strip(" ,")[:80] if m else ""
    kw = soup.find(string=re.compile(r"^\s*키워드\s*$"))
    tech = ""
    if kw and kw.find_parent("dl"):
        tech = re.sub(r"툴팁\S*", "", kw.find_parent("dl").get_text(" ", strip=True))
        tech = re.sub(r"^\s*키워드\s*", "", tech).strip()
        tech = re.sub(r"(.+?)\1$", r"\1", tech).strip()      # 툴팁 때문에 같은 문자열이 2번 반복됨
    return {"회사명": company,
            "공고제목": f[1] if len(f) > 1 else "",
            "직무": duty,
            "경력": re.sub(r"^경력(?=경력|신입|무관)", "", f[2]).strip() if len(f) > 2 else "",
            "고용형태": f[4] if len(f) > 4 else "",
            "지역": region,
            "기술스택": tech[:120],
            "마감일": (f[6] if len(f) > 6 else "").replace("마감", "").strip(),
            "공고URL": u, "수집시각": NOW()}

def main():
    s = Site("게임잡", ROOT, delay=1.0)
    s.note("페이지네이션 전부 무효(구형 ASP 목록 포함) → main/home + 목록에서 GI_No 수집 후 상세 직접 요청")
    ids = collect_list(s)
    s.note(f"목록에서 GI_No {len(ids)}건")
    main_ids = set(re.findall(r"GI_No=(\d+)", s.get(f"{ROOT}/main/home").text))
    s.note(f"main/home 에서 GI_No {len(main_ids)}건 추가 수집")
    ids |= main_ids
    urls = [f"{ROOT}/Recruit/GI_Read/View?GI_No={i}" for i in sorted(ids)]
    s.note(f"상세 요청 대상 {len(urls)}건 (중복 제거 후)")
    fetch_many(s, urls, parse, workers=3, per_sec=2.0, label="GI_Read")
    s.save()

if __name__ == "__main__":
    main()
