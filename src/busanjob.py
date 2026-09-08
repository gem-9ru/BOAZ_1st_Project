"""부산일자리정보망(busanjob.net) — 부산광역시 운영 일자리 포털.

[정책] robots.txt 404(규칙 없음). 렌더링 확인 결과 푸터 고지는 '이메일 무단수집거부' 뿐이며
       이는 정보통신망법 제50조의2 스팸 방지 표시로 채용공고 수집과 무관하다.
       부산광역시가 운영하는 공공 사이트다.

[구조] /view.do?no={메뉴}&pgMode=index&pageIndex={N}
         no=1308 기업채용 / 1309 공공채용 / 1310 해외채용
       서버 렌더링이라 정적 HTML 에 목록이 들어있다(페이지당 12건).
       항목: ul.emif-lst > li
         div.tit                    공고제목
         div.stxt .item.date        접수기간 "2026-08-14 ~ 2033-01-01"
         div.stxt .item (2~4번째)    경력 / 학력 / 지역
         div.batcont.company        회사명
         div.provide-bat.{출처}      출처 (saramin·jobkorea·go24·busan·jobfair)
         a onclick="show('817303')" 공고 ID

[중요 — 출처 표시] 이 사이트는 자체 공고뿐 아니라 **사람인·잡코리아·고용24의 공고를 함께 노출**한다.
       provide-bat 클래스가 출처를 알려주므로 이를 외부원본ID 로 보존한다.
       중복제거 단계에서 다른 사이트와 겹치는지 판정하는 근거가 되고,
       우리가 직접 수집하지 못한 사람인 공고를 간접 확보하는 경로이기도 하다.

[페이지네이션] pageIndex=N. 2,000페이지까지 정상 동작 확인.

[누락 수정 — 해외채용] 1차 수집에서 해외채용(no=1310) 569건을 통째로 놓쳤다.
       원인: 기업/공공채용은 링크가 `onclick="show('817303')"` 인데
       **해외채용만 월드잡플러스(worldjob.or.kr) 외부 링크를 직접 걸어** onclick 이 없다.
       show() 정규식으로만 항목을 인식해 0건으로 처리됐다.
       또 해외채용은 항목 구조도 달라서
         .item 첫 칸 = 직무("그 외 전자공학 기술자 및 연구원")
         .item.date  = 접수기간
         .batcont.country = 국가 (기업채용의 .batcont.company 자리)
       → 링크 방식과 필드 배치를 메뉴별로 분기 처리한다.
"""
import re
from bs4 import BeautifulSoup
from common import Site, NOW

ROOT = "https://www.busanjob.net"
MENUS = [("1308", "기업채용"), ("1309", "공공채용"), ("1310", "해외채용")]
MAX_PAGE = 2400

def main():
    s = Site("부산일자리정보망", ROOT, delay=0.8)
    s.note("부산광역시 운영. robots 규칙 없음, 크롤링 금지 고지 없음(이메일 무단수집거부만 존재)")
    seen = set()
    for no, label in MENUS:
        empty = 0
        for page in range(1, MAX_PAGE + 1):
            try:
                soup = BeautifulSoup(
                    s.get(f"{ROOT}/view.do?no={no}&pgMode=index&pageIndex={page}").text, "html.parser")
            except Exception as e:
                s.note(f"{label} p{page} 실패: {e}"); break
            items = soup.select("ul.emif-lst > li")
            if not items:
                break
            new = 0
            for li in items:
                a = li.select_one("a")
                if not a:
                    continue
                onclick = a.get("onclick", "") or ""
                m = re.search(r"show\('(\d+)'\)", onclick)
                href = a.get("href", "") or ""
                if m:                       # 기업/공공채용: 내부 상세
                    jid = m.group(1)
                    url = f"{ROOT}/view.do?no={no}&pgMode=show&id={jid}"
                elif href.startswith("http"):   # 해외채용: 월드잡플러스 외부 링크
                    jid = href
                    url = href
                else:
                    continue
                if jid in seen:
                    continue
                seen.add(jid); new += 1
                get = lambda sel: (li.select_one(sel).get_text(" ", strip=True)
                                   if li.select_one(sel) else "")
                items_txt = [d.get_text(" ", strip=True) for d in li.select("div.stxt .item")]
                dnode = li.select_one("div.stxt .item.date")
                date = dnode.get_text(" ", strip=True) if dnode else (items_txt[0] if items_txt else "")
                deadline = date.split("~")[-1].strip() if "~" in date else ""
                # 해외채용은 .item 첫 칸이 직무, .batcont.country 가 국가다
                is_overseas = (no == "1310")
                ov_duty = items_txt[0] if (is_overseas and items_txt) else ""
                country = li.select_one("div.batcont.country")
                country = country.get_text(" ", strip=True) if country else ""
                # provide-bat 의 두 번째 클래스가 출처명
                pb = li.select_one("div.provide-bat")
                src = ""
                if pb:
                    cls = [c for c in (pb.get("class") or []) if c != "provide-bat"]
                    src = cls[0] if cls else ""
                s.add(회사명=get("div.batcont.company"),
                      공고제목=get("div.tit"),
                      직무=label,                       # 기업/공공/해외 구분 (세부 직무는 목록에 없음)
                      경력=items_txt[1] if len(items_txt) > 1 else "",
                      고용형태="",
                      지역=re.sub(r"\s{2,}", " ", items_txt[3]) if len(items_txt) > 3 else "",
                      기술스택="",
                      마감일=deadline,
                      공고URL=f"{ROOT}/view.do?no={no}&pgMode=show&id={jid}",
                      외부원본ID=(f"{src}:{jid}" if src else ""),
                      수집시각=NOW())
            if new == 0:
                empty += 1
                if empty >= 3:
                    break
            else:
                empty = 0
            if page % 50 == 0:
                print(f"    {label} p{page}: 누적 {len(seen):,}", flush=True)
                s.save()
        print(f"    {label} 완료 — 누적 {len(seen):,}", flush=True)
        s.save()
    s.note(f"수집 {len(seen):,}건")
    s.save()

if __name__ == "__main__":
    main()
