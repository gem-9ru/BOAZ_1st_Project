# -*- coding: utf-8 -*-
"""Phase 3 — 사이트 간 중복 공고를 하나로 합친다.

입력: ../../build/공고_정규화.csv
출력: ../../build/공고_통합.csv       중복 제거된 마스터 (1행 = 1채용건)
      ../../build/중복매핑.csv       통합키 ↔ 원본행 (무엇이 왜 합쳐졌는지)
      ../../build/검수후보.csv       3단계에서 애매하게 걸린 건 (자동병합 안 함)

3단계 전략 — 신뢰도 높은 순서로 적용하고, 앞 단계에서 묶인 건 뒤 단계에서 건드리지 않는다.
  1단계 확정: 사이트가 스스로 밝힌 외부원본ID (예: 잡플래닛의 jobkorea_posting_id).
             추측이 0% 라 가장 안전하다.
  2단계 완전일치: 회사키 + 제목키 + 시도 가 모두 같음.
  3단계 유사도: 회사키가 같고 제목 토큰 Jaccard 유사도가 임계값 이상.
             AUTO 이상은 자동 병합, REVIEW~AUTO 사이는 검수후보로 빼서 사람이 보게 한다.
"""
import csv, re, sys, unicodedata
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
BUILD = BASE / "build"
SIM_AUTO, SIM_REVIEW = 0.95, 0.60   # 0.80 -> 0.92 -> 0.95. 낮은 쪽은 diff_is_generic 이 담당

# 사이트가 붙이는 순수 장식 문구만 제거한다.
#
# [1차 설계의 실패] 처음에는 대괄호/괄호 안을 통째로 지우고 신입·경력·정규직·계약직까지
# 상용구로 묶어 제거했다. 그 결과 서로 다른 공고가 같은 제목으로 뭉개져 오병합이 났다.
#   · "건설안전부 (안전관리자)" vs "건설안전부 (보건관리자)"  → 괄호 삭제로 동일 판정
#   · "2026년도 계약직 채용공고(토목,안전)" vs "2026년도 신입사원 공개채용" → 둘 다 "2026년도"
#   · "울산 건축공사관리" vs "군산 건축공사관리" → 유사도 0.92 로 자동병합
# 괄호 안에는 오히려 직무·지역 같은 **식별 정보**가 들어있다.
# → 괄호는 기호만 벗기고 내용은 살린다. 고용형태·경력 어휘도 식별 신호라 남긴다.
_NOISE = re.compile(
    r"채용\s*공고|채용\s*중|공고|구인|모집\s*공고|"
    r"[dD]\s?-\s?\d+|마감\s*임박|급구|재공고|상시\s*모집|수시\s*모집|"
    r"인재\s*영입|사원\s*모집|직원\s*모집|채용\s*연계")

def title_key(s):
    """비교용 제목 키. 괄호 기호만 벗기고 안의 내용은 보존한다."""
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"[\[\]()【】<>{}]", " ", s)      # 기호만 제거, 내용 유지
    s = _NOISE.sub(" ", s)
    s = re.sub(r"[^0-9A-Za-z가-힣]+", " ", s).strip().lower()
    return re.sub(r"\s+", "", s)

def tokens(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"[\[\]()【】<>{}]", " ", s)      # 괄호 내용 보존
    s = _NOISE.sub(" ", s)
    s = re.sub(r"[^0-9A-Za-z가-힣]+", " ", s).lower()
    out = set()
    for w in s.split():
        if len(w) <= 1:
            continue
        out.add(w)
        if re.fullmatch(r"[가-힣]+", w) and len(w) >= 3:
            out |= {w[i:i + 2] for i in range(len(w) - 1)}   # 한글은 bigram 도 함께
    return out

# 두 제목의 "차이나는 단어"가 의미를 갖는지 판정하기 위한 사전.
#
# [왜 필요한가] 유사도 숫자만으로는 아래 둘을 구분할 수 없다.
#   · "…울산 건축공사관리…" vs "…군산 건축공사관리…"      → 0.92, 다른 공고 (지역이 다름)
#   · "본사 이커머스영업 대리/과장급" vs "…+ 채용"          → 0.92, 같은 공고 (군더더기 차이)
# 차이가 '채용' 같은 군더더기뿐이면 같은 공고, '울산/군산'·'안전/보건'처럼 식별어가 다르면 다른 공고다.
GENERIC = {
    "채용", "모집", "공고", "구인", "인재", "영입", "인재영입", "직원", "사원",
    "및", "등", "전형", "수시", "상시", "공채", "부문", "분야", "직군", "직무", "포지션",
    "년", "년도", "차", "차수", "명", "관련", "우대", "가능", "지원", "신규", "충원", "추가",
}
# 지역·조직 단위처럼 그 자체가 공고를 가르는 토큰
REGIONISH = re.compile(r"(시|군|구|도|권|공장|지사|지점|캠퍼스|사업장|본부|센터|현장)$")
PLACE = set(SIDO_WORDS) if (SIDO_WORDS := [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원",
    "충북", "충남", "전북", "전남", "경북", "경남", "제주", "판교", "성남", "수원",
    "용인", "안양", "화성", "평택", "천안", "청주", "군산", "여수", "포항", "창원",
    "김해", "구미", "원주", "춘천", "제천", "당진", "아산", "익산", "전주", "목포",
]) else set()


def words(s):
    """유사도 보조용 단어 토큰 (bigram 없이 원형 단어만)."""
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"[\[\]()【】<>{}]", " ", s)
    s = _NOISE.sub(" ", s)
    s = re.sub(r"[^0-9A-Za-z가-힣]+", " ", s).lower()
    return {w for w in s.split() if len(w) > 1}


# [검수후보 195건을 실제로 훑고 나서 둘로 쪼갠 사전]
#
# 처음에는 직급과 고용형태를 LEVEL 하나로 묶어 전부 '검수 보류' 로 뺐다.
# 그런데 실물을 보니 두 부류의 성격이 완전히 달랐다.
#
# EMP_TAG — 사이트가 붙이는 '고용형태 꼬리표'. 차이가 나도 같은 공고인 경우가 압도적이었다.
#   · 버즈빌:  "백엔드 개발자(3년 이상)"        vs "백엔드 개발자(경력 3년 이상)"
#   · 콘스탄트: "[리필드] 글로벌 인플루언서 마케터" vs "…마케터 (인턴)"
#   · 바이트랩: "[인턴] 뷰티 콘텐츠 마케터"       vs "뷰티 콘텐츠 마케터(전환형 인턴)"
#   원티드은 [인턴] 접두, 잡플래닛은 (인턴) 접미로 쓰는 등 표기 습관 차이일 뿐이다. → 병합.
#
# SENIORITY — 실제 직급/레벨. 이게 다르면 별개 채용인 경우가 실제로 있었다.
#   · 아정네트웍스: "협력사 운영/영업 팀장"        vs "협력사 운영/영업 담당자"
#   · 피에프씨:    "B2B Senior Data Engineer" vs "B2B Data Engineer"
#   → 자동병합하지 않고 검수후보로 남긴다.
EMP_TAG = {"인턴", "인턴십", "신입", "경력", "경력직", "체험형", "전환형", "채용형", "사원"}
# 직급어도 다시 둘로 나눈다. 검수후보 16건을 하나씩 보고 정한 기준이다.
#
# KO_LEVEL — 한국어 직급. 한쪽이 그냥 생략한 경우가 대부분이라 포함관계면 병합한다.
#   · 아렌시아: "글로벌 인플루언서 마케팅 팀장"   vs "글로벌 인플루언서 마케팅"
#   · 라포랩스: "상품기획 MD (시니어)"          vs "상품기획 MD"
#   · 국립중앙의료원: "콜센터 매니저(원무팀)"      vs "콜센터(원무팀)"
#
# EN_LEVEL — 영문 직함의 레벨. 테크 회사는 주니어/시니어 자리를 실제로 따로 공고한다.
#   · 노타: "Senior AI Engineer" vs "AI Engineer"  → 별개 채용으로 본다(분리 유지)
#   단, 차이가 긴 구절이면 직함이 아니라 '영문 병기 주석' 이므로 예외로 병합한다.
#   · 이스트소프트: "…기획리드" vs "…기획리드 (Project Lead / Planning Manager)"
#     → 차이 토큰이 4개(project/lead/planning/manager) = 설명 문구. 병합.
KO_LEVEL = {"시니어", "주니어", "팀장", "실장", "본부장", "리더", "리드", "총괄", "임원",
            "매니저", "대리", "과장", "과장급", "차장", "부장", "책임", "선임", "수석",
            "파트장", "그룹장", "센터장", "지점장"}
# 근무형태·시간대·장소 수식어. 같은 회사·같은 직무라도 이게 다르면 **별개 공고**다.
#   예) 세움병원 "병동 간호사" vs "병동 야간전담 간호사"
#       ㈜신건 "부산시 전지역 배송" vs "부산 울산 강원 경북 배송"
SHIFT_WORDS = {"야간", "주간", "심야", "오전", "오후", "저녁", "새벽", "주말", "평일",
               "교대", "2교대", "3교대", "격일", "상근", "전담", "야간전담", "당직",
               "재택", "파견", "출장", "상주", "순회", "단기", "장기", "주5일", "주6일",
               "풀타임", "시간제", "격주"}
EN_LEVEL = {"senior", "junior", "sr", "jr", "principal", "staff", "head", "chief"}
EN_GLOSS_MAX = 2      # 차이 토큰이 이보다 많으면 직함이 아니라 설명 문구로 간주
MONTHISH = re.compile(r"^\d+(월|년|년도|분기|차|기)$")


def _despace(words_set):
    r"""띄어쓰기만 다른 토큰을 같은 것으로 보기 위해, 토큰들을 이어붙인 문자열도 함께 만든다.

    [문제] "CJ 생수 택배기사" vs "CJ생수 택배기사" 가 different 로 갈렸다.
      차이 토큰이 A\B={cj, 생수}, B\A={cj생수} 로 나와 양쪽 모두 비어 있지 않았기 때문.
      한국어 공고 제목은 같은 말을 붙여 쓰거나 띄어 쓰는 편차가 매우 크다.
      (docstring 내 역슬래시는 이스케이프 경고를 피하려 raw 문자열로 둔다)
    """
    return "".join(sorted(words_set))


def relation(a, b):
    """두 제목의 관계를 판정한다: merge / review / different.

    [핵심 아이디어] 유사도 숫자 하나로는 아래 두 경우를 못 가른다. 무엇이 다른지를 봐야 한다.
      · 한쪽에만 수식어가 더 붙은 경우 (포함관계)
          "전남북부권지사 실무직 채용" ⊂ "[영·섬/장성] 전남북부권지사 실무직 채용"
          → 같은 공고를 한 사이트가 더 자세히 적은 것. 병합.
      · 양쪽이 서로 다른 값을 가진 경우 (충돌)
          "…울산 건축공사관리…" vs "…군산 건축공사관리…"
          → 지역이 실제로 다른 별개 공고. 병합하면 안 된다.
    """
    wa, wb = words(a), words(b)
    drop = lambda s: {w for w in s if w not in GENERIC and not MONTHISH.match(w)}
    ea, eb = drop(wa - wb), drop(wb - wa)
    # 띄어쓰기 편차 보정: 한쪽의 차이 토큰을 이어붙인 것이 다른 쪽에 그대로 들어 있으면
    # 실질적으로 같은 말이므로 차이에서 제외한다.
    if ea and eb:
        ja, jb = _despace(ea), _despace(eb)
        if ja == jb or ja in jb or jb in ja:
            ea, eb = set(), set()
        else:
            # 개별 토큰 단위로도 확인 ("무선센터" ⊂ "kt고객센터"+"무선")
            ea = {w for w in ea if w not in jb}
            eb = {w for w in eb if w not in ja}
    if ea and eb:
        return "different"                 # 양쪽에 각기 다른 실질 단어 → 별개 공고
    extras = ea or eb
    if any(w in EN_LEVEL for w in extras) and len(extras) <= EN_GLOSS_MAX:
        return "different"                 # "Senior X" vs "X" → 별개 채용으로 취급
    if any(w in SHIFT_WORDS for w in extras):
        return "different"                 # 근무형태·시간대가 다르면 별개 공고
    return "merge"                         # 그 밖의 포함관계 → 같은 공고의 다른 표기


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

class UF:
    def __init__(s): s.p = {}
    def find(s, x):
        s.p.setdefault(x, x)
        while s.p[x] != x:
            s.p[x] = s.p[s.p[x]]; x = s.p[x]
        return x
    def union(s, a, b):
        ra, rb = s.find(a), s.find(b)
        if ra != rb:
            s.p[rb] = ra
        return ra

# 대표행 선택 우선순위: 원 게시처에 가까운 사이트를 앞에 둔다.
SITE_RANK = {"잡코리아": 0, "원티드": 1, "리멤버커리어": 2, "점핏": 3, "캐치": 4,
             "자소설닷컴": 5, "잡플래닛": 6, "링커리어": 7, "게임잡": 8,
             "건설워커": 9, "미디어잡": 10}

def richness(r):
    return sum(1 for k in ("직무", "경력구분", "고용형태표준", "시도", "기술스택", "마감일") if r.get(k))

def main():
    src = BUILD / "공고_정규화.csv"
    rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
    for i, r in enumerate(rows):
        r["_i"] = i
    print(f"입력 {len(rows):,}행")

    uf, reason = UF(), {}
    def link(a, b, why):
        if uf.find(a) != uf.find(b):
            uf.union(a, b)
            reason[(min(a, b), max(a, b))] = why

    # ---- 1단계: 외부원본ID 확정 매칭 -------------------------------------
    by_site_id = {}
    for r in rows:
        if r["원본공고ID"]:
            by_site_id[(r["사이트"], r["원본공고ID"])] = r["_i"]
    n1 = 0
    for r in rows:
        ext = (r.get("외부원본ID") or "").strip()
        if not ext or ":" not in ext:
            continue
        site, oid = ext.split(":", 1)
        tgt = by_site_id.get((site, oid))
        if tgt is not None and tgt != r["_i"]:
            link(r["_i"], tgt, "1단계:외부원본ID")
            n1 += 1
    print(f"  1단계 확정 매칭      {n1:,}쌍")

    # ---- 2단계: 회사키 + 제목키 완전일치 ------------------------------------
    # [수정 1] 키에 시도를 넣었더니, 같은 공고인데 한쪽만 지역이 파싱된 경우
    #   (시도='부산' / 시도='') 병합되지 않았다.
    # [수정 2] 그래서 시도를 키에서 빼고 "base 와 시도가 다르면 건너뛴다" 로 바꿨는데
    #   base 가 그룹의 첫 행이라 **결과가 입력 순서에 좌우됐다.**
    #   ㈜아정네트웍스 "보안 인증 담당자 (부산)" 6행이 서울 2 / 부산 4 로 갈렸는데
    #   base 가 서울 행이라 부산 4행이 전부 단독으로 떨어졌다.
    # → 지역별로 분할해 각 덩어리 안에서 병합한다(입력 순서와 무관).
    #
    # [지역 판정] 제목에 지역명이 있으면 그걸 쓴다.
    #   위 사례는 제목이 "(부산)" 이라고 못박는데 시도는 본사 주소(서울)가 잡힌 것이다.
    #   공고 제목은 고용주가 직접 밝힌 근무지라 파싱된 시도보다 믿을 만하다.
    SIDO_IN_TITLE = re.compile(
        r"(?:^|[\s\[(/·,])(" + "|".join(SIDO_WORDS[:17]) + r")(?:[\s\])/·,]|$)")

    def region_of(r):
        m = SIDO_IN_TITLE.search(r["공고제목"])
        return m.group(1) if m else (r["시도"] or "")

    g = defaultdict(list)
    for r in rows:
        tk = title_key(r["공고제목"])
        r["_tk"] = tk
        if r["회사키"] and tk:
            g[(r["회사키"], tk)].append(r["_i"])
    n2 = 0
    for k, idxs in g.items():
        # [사이트가 하나씩만 올렸으면 같은 공고다]
        #   회사·제목이 같은데 사이트마다 지역이 다르게 적힌 경우가 있다.
        #     TKG태광 "2026 부문별 채용 공고" → 부산잡 대구 / 사람인 부산 / 캐치 경남
        #   전국 공채를 사이트마다 대표 지역 하나만 기록한 것이지 별개 공고가 아니다.
        #   반대로 **한 사이트가 같은 제목을 여러 번** 올렸다면 그건 실제로
        #   권역·근무지가 다른 별개 모집이므로 지역별로 나눈다.
        per_site = defaultdict(int)
        for i in idxs:
            per_site[rows[i]["사이트"]] += 1
        if idxs and max(per_site.values()) == 1:
            parts = {"": idxs}
        else:
            parts = defaultdict(list)
            for i in idxs:
                parts[region_of(rows[i])].append(i)
            blanks = parts.pop("", [])
            if parts:
                biggest = max(parts, key=lambda s: len(parts[s]))
                parts[biggest] += blanks
            elif blanks:
                parts[""] = blanks
        for members in parts.values():
            base = members[0]
            for j in members[1:]:
                if uf.find(base) == uf.find(j):
                    continue
                link(base, j, "2단계:완전일치"); n2 += 1
    print(f"  2단계 완전일치       {n2:,}쌍")

    # ---- 3단계: 같은 회사 안에서 제목 유사도 ------------------------------
    by_co = defaultdict(list)
    for r in rows:
        if r["회사키"]:
            by_co[r["회사키"]].append(r)
    n3, review = 0, []
    for co, group in by_co.items():
        sites = {r["사이트"] for r in group}
        # 같은 사이트 안의 중복은 대상 밖(사이트 내부 중복은 원본 성격이라 보존)
        if len(sites) < 2 or len(group) > 400:
            continue
        toks = {r["_i"]: tokens(r["공고제목"]) for r in group}
        for a in range(len(group)):
            ra = group[a]
            for b in range(a + 1, len(group)):
                rb = group[b]
                # [수정] 초기에는 같은 사이트 쌍을 3단계에서 건너뛰었다. 그 결과
                #   "CJ 생수 택배기사 희망지역근무 초보자환영" 과
                #   "[자율출퇴근] CJ생수 택배기사 희망지역근무 초보자 환영" 처럼
                #   한 사이트 안의 사실상 동일 공고가 남았다.
                #   SHIFT_WORDS 가드를 넣어 근무형태 차이는 보존하므로 같은 사이트도 비교한다.
                if uf.find(ra["_i"]) == uf.find(rb["_i"]):
                    continue
                # 지역이 서로 다르게 명시돼 있으면 다른 공고로 본다
                # ("울산 건축공사관리" vs "군산 건축공사관리" 오병합 방지).
                if ra["시도"] and rb["시도"] and ra["시도"] != rb["시도"]:
                    continue
                sim = jaccard(toks[ra["_i"]], toks[rb["_i"]])
                if sim < SIM_REVIEW:
                    continue
                # 차이나는 단어가 군더더기뿐이면 유사도가 조금 낮아도 같은 공고로 확정.
                # 반대로 유사도가 아무리 높아도 식별어(지역·숫자·직무)가 다르면 자동병합하지 않는다.
                rel = relation(ra["공고제목"], rb["공고제목"])
                if rel == "merge":
                    link(ra["_i"], rb["_i"], f"3단계:포함관계(유사도{sim:.2f})"); n3 += 1
                elif rel == "different":
                    continue                                   # 병합하지 않음
                elif sim >= SIM_AUTO:
                    link(ra["_i"], rb["_i"], f"3단계:유사도{sim:.2f}"); n3 += 1
                else:
                    review.append((sim, ra, rb))
    print(f"  3단계 유사도 자동병합 {n3:,}쌍 / 검수후보 {len(review):,}쌍")

    # ---- 클러스터 확정 ----------------------------------------------------
    clusters = defaultdict(list)
    for r in rows:
        clusters[uf.find(r["_i"])].append(r)
    print(f"\n결과: {len(rows):,}행 → {len(clusters):,}건 "
          f"(중복 {len(rows)-len(clusters):,}행 병합, {100*(len(rows)-len(clusters))/len(rows):.1f}%)")

    # 상세 보강으로 늘어난 컬럼도 통합 결과에 그대로 실어야 한다.
    # 특히 담당업무는 "구체적으로 어떤 일을 하는지" 라 이 데이터셋에서 가장 중요한 값인데,
    # 여기 목록에 없으면 최종 산출물에서 통째로 사라진다.
    DETAIL = ["직무상세", "직무키워드", "담당업무", "자격요건", "우대사항",
              "직종", "업종", "직급직책", "근무시간", "급여",
              "채용인원", "채용인원구분", "학력", "상세주소"]
    OUT = (["통합키", "회사명", "공고제목", "직무"] + DETAIL +
           ["경력구분", "최소연차", "고용형태표준", "시도", "시군구", "기술스택",
            "마감일", "마감구분",
            "게재사이트수", "게재사이트", "대표URL", "전체URL", "수집시각"])
    master, mapping = [], []
    for n, (root, group) in enumerate(sorted(clusters.items()), 1):
        key = f"KR2026090700{n:06d}"
        rep = sorted(group, key=lambda r: (SITE_RANK.get(r["사이트"], 99), -richness(r)))[0]
        sites = sorted({r["사이트"] for r in group}, key=lambda s: SITE_RANK.get(s, 99))
        pick = lambda f: next((r[f] for r in
                               sorted(group, key=lambda x: (SITE_RANK.get(x["사이트"], 99), -richness(x)))
                               if r.get(f)), "")
        detail_vals = {c: pick(c) for c in DETAIL}
        # 채용인원과 채용인원구분은 짝이다. 필드마다 따로 고르면
        # "채용인원은 있는데 구분은 '없음'" 같은 모순이 생긴다(19,535 vs 15,353).
        # 숫자를 고른 뒤 구분을 거기서 다시 만든다.
        hc = detail_vals.get("채용인원", "")
        detail_vals["채용인원구분"] = ("명시" if hc else
                                  ("미정" if any(r.get("채용인원구분") == "미정" for r in group)
                                   else "없음"))
        master.append({
            "통합키": key, "회사명": rep["회사명"], "공고제목": rep["공고제목"],
            "직무": pick("직무"), "경력구분": pick("경력구분"), "최소연차": pick("최소연차"),
            "고용형태표준": pick("고용형태표준"), "시도": pick("시도"), "시군구": pick("시군구"),
            "기술스택": pick("기술스택"), "마감일": pick("마감일"), "마감구분": pick("마감구분"),
            # 같은 공고를 여러 사이트에서 받았으면 값이 있는 쪽을 고른다.
            # 사이트마다 채워지는 필드가 달라서(사람인 담당업무 91%, 잡코리아 근무시간 등)
            # 병합이 오히려 결손을 메운다.
            **detail_vals,
            "게재사이트수": len(sites), "게재사이트": ", ".join(sites),
            "대표URL": rep["공고URL"], "전체URL": " | ".join(r["공고URL"] for r in group),
            "수집시각": rep["수집시각"],
        })
        for r in group:
            pair = (min(r["_i"], root), max(r["_i"], root))
            mapping.append({"통합키": key, "사이트": r["사이트"], "원본공고ID": r["원본공고ID"],
                            "회사명": r["회사명"], "공고제목": r["공고제목"],
                            "공고URL": r["공고URL"],
                            "병합근거": reason.get(pair, "단독" if len(group) == 1 else "동일클러스터")})

    def dump(name, cols, data):
        p = BUILD / name
        with p.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(data)
        print(f"  -> {name} ({len(data):,}행)")

    dump("공고_통합.csv", OUT, master)
    dump("중복매핑.csv", ["통합키", "사이트", "원본공고ID", "회사명", "공고제목", "공고URL", "병합근거"], mapping)
    dump("검수후보.csv", ["유사도", "회사명", "사이트A", "제목A", "URLA", "사이트B", "제목B", "URLB"],
         [{"유사도": f"{s:.2f}", "회사명": a["회사명"], "사이트A": a["사이트"], "제목A": a["공고제목"],
           "URLA": a["공고URL"], "사이트B": b["사이트"], "제목B": b["공고제목"], "URLB": b["공고URL"]}
          for s, a, b in sorted(review, key=lambda x: -x[0])])

    multi = [m for m in master if m["게재사이트수"] > 1]
    print(f"\n2개 이상 사이트에 중복 게재: {len(multi):,}건")

if __name__ == "__main__":
    main()
