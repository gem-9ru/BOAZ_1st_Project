"""KECO 직종코드 분류 v2 — 공식 마스터 기반.

[v1 과 무엇이 다른가]
v1 은 "고용24가 코드 목록 API 를 안 준다"고 보고, 수집한 공고에서 코드↔명칭을
역산해 311개 표를 만들었다. 그래서 부산 공고에 안 나온 직종은 애초에 붙을 수
없었고, 정확도를 재볼 방법도 없었다.

v2 는 고용24 공용코드 API 산출물(팀 공유)에서 **공식 분류표 전체**를 쓴다.
    data/keco/직종코드_마스터.csv   1,342행 = 대분류 13 · 중분류 114 · 세분류 1,215
(v1 이 역산해 만든 311개 표는 data/keco/직종표_v1_수집역산.csv 로 남겨 뒀다.)
                                    (세분류 고유코드는 1,130개 — 아래 [주의 1])

[주의 1] 마스터는 트리가 아니라 DAG 다
세분류 79개가 중분류 2곳 이상에 걸려 있고, 그중 67개는 **대분류가 갈린다**.
    026502 병원행정 사무원(원무)  →  017 경영지원 사무   (대분류 01 경영·사무)
                                 →  044 그 외 보건·의료 (대분류 04 보건·의료)
이걸 그대로 집계하면 대분류 합이 전체를 넘는다(상호배타 붕괴).

[주의 2] 6자리 코드의 앞자리는 상위코드가 아니다
    133200 응용 소프트웨어 개발자 의 superCd 는 024 다. 1,215개 중 1,212개가
    앞3자리 ≠ superCd. 앞자리로 상위분류를 만들면 전부 틀린다.

[그래서 계층을 두 벌로 낸다]
  ① KECO 자릿수 계층  6자리 코드를 앞에서 잘라 쓴다. 정본.
       1자리 대분류 10 · 2자리 중분류 35 · 3자리 소분류 140 · 4자리 세분류 493
       코드 1개 → 상위 1개. 정의상 MECE 라서 집계가 안전하다.
  ② work24 표시계층   대분류 13 · 중분류 114. 공식 명칭이 붙어 있어 라벨용으로 좋다.
       DAG 라서 **정본부모 규칙**(마스터 파일 최초 등장 부모)을 적용하고,
       부모가 여럿이던 코드는 `직종13대분류중복=Y` 로 표시해 걸러 쓸 수 있게 한다.
  팀 간 조인은 라벨이 아니라 **6자리 코드**로 한다. 라벨 체계는 문서마다 다르다.

[부여 경로]  근거를 `직종코드근거`, 등급을 `직종코드확실도` 에 남긴다
  L0 고용24직접  `직종` 이 공식 명칭과 일치          강   ← 정답. 2,560건
  L1 별칭일치    괄호 안 동의어까지 펼쳐 일치          강
  L2 학습사전    L0 정답에서 학습한 토큰→코드         중
  L3 부분일치    토큰이 공식 명칭을 통째로 포함        중
  L4 상위합의    후보가 세분류에선 갈리나 상위에서 합의 약   ← 상위 코드만 부여
  L5 미분류      근거 없음                          미분류

L4 는 지홍님 지적대로 계층을 쓰는 쪽이다. "매니저" 처럼 세분류를 특정할 수 없는
토큰도 대분류·중분류까지는 특정되는 경우가 많고, 미스매치 시각화는 그 레벨이면 된다.

[정확도 측정]
L0 정답 2,560건에서 `직종` 유래 토큰을 제거하고 L1~L4 만 돌려 실측한다.
누출 제거 기준: 직무 토큰이 `직종` 이 아닌 원본 컬럼(제목·모집분야·직무키워드·
담당업무·자격요건·원본직무) 텍스트에도 나타나야 살린다.
"""
import csv, re, sys, unicodedata, collections
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
MASTER = BASE / "data" / "keco" / "직종코드_마스터.csv"

# KECO 2018 대분류는 6자리 코드의 **앞 1자리**다.
# 앞 2자리를 대분류로 봤다가 304000(간호사)을 농림어업으로 분류한 사고가 v1 에 있었다.
MAJOR10 = {
    "0": "경영·사무·금융·보험", "1": "연구·공학기술",
    "2": "교육·법률·사회복지·경찰·소방·군인", "3": "보건·의료",
    "4": "예술·디자인·방송·스포츠", "5": "미용·여행·숙박·음식·경비·돌봄·청소",
    "6": "영업·판매·운전·운송", "7": "건설·채굴", "8": "설치·정비·생산", "9": "농림어업",
}

_PAREN = re.compile(r"\([^()]*\)")
_SEP = re.compile(r"[,·‧・、/;|]+")

# 직무 토큰이 아닌 것. 이게 통과하면 엉뚱한 코드가 붙는다.
#   "직원" 2,415건 · "사원" 1,641건 · "현장" 877건 — 전부 무슨 일인지 안 알려준다.
STOP = {
    "직원", "사원", "경력사원", "신입사원", "신입", "경력", "경력자", "현장", "인력",
    "정규직", "계약직", "인턴", "파견", "프리랜서", "알바", "아르바이트", "촉탁",
    "모집", "채용", "공채", "부산", "무관", "기타", "전체", "상시", "수시",
    "주말", "평일", "오전", "오후", "야간", "주간", "교대", "초보", "우대", "급구",
    "즉시", "다수", "각", "명", "관련", "등", "및", "외", "남", "여", "청년",
    "장애인", "고졸", "대졸", "학력무관", "정년", "본사", "지사", "공장", "사무실",
    "채용공고", "구인", "업무", "담당", "담당자", "파트", "직", "부서", "팀",
}

# 명칭 접미어. 괄호 안 동의어를 별칭으로 쓸지 판단한다.
_JOBSUF = ("원", "사", "자", "가", "공", "수", "관", "장", "인", "부", "병", "님",
           "기사", "보조", "매니저", "엔지니어", "디자이너", "개발자", "강사", "교사",
           "기술자", "조작원", "종사원", "관리자", "전문가", "조종사", "정비원")


def norm(s):
    """비교용 정규화. 공백 제거·구분자 통일·전각 반각 통일."""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("‧", "·").replace("・", "·").replace("∙", "·")
    s = re.sub(r"[\s​]+", "", s)
    return s.lower()


def core_of(name):
    """괄호 예시를 떼어낸 본체. '전기용접원(아크,알곤,티그용접원)' -> '전기용접원'"""
    prev = None
    s = name or ""
    while prev != s:                      # 중첩 괄호까지 벗긴다
        prev, s = s, _PAREN.sub(" ", s)
    return norm(s)


def paren_items(name):
    """괄호 안 항목들. 'A(가,나 등)' -> ['가','나']"""
    out = []
    for m in re.finditer(r"\(([^()]*)\)", name or ""):
        for it in _SEP.split(m.group(1)):
            it = norm(it)
            it = re.sub(r"(등|이상|미만|포함|제외)$", "", it)
            it = re.sub(r"^(예|예시|주로)", "", it)
            if len(it) >= 2:
                out.append(it)
    return out


class Master:
    """공식 분류표. 코드 조회 · 명칭 사전 · 별칭 사전 · 부분일치 인덱스."""

    def __init__(self, path=MASTER):
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
        self.rows = rows
        self.d1 = {r["jobsCd"]: r["jobsNm"].strip() for r in rows if r["depth"] == "1"}
        self.d2 = {}
        for r in rows:
            if r["depth"] == "2":
                self.d2[r["jobsCd"]] = (r["jobsNm"].strip(), r["superCd"])

        # 세분류 — 코드가 79개 중복이라 최초 등장 부모를 정본으로 삼는다
        self.name, self.parent, self.multi = {}, {}, {}
        for r in rows:
            if r["depth"] != "3":
                continue
            c = r["jobsCd"]
            if c not in self.name:
                self.name[c] = r["jobsNm"].strip()
                self.parent[c] = r["superCd"]
                self.multi[c] = "N"
            elif r["superCd"] != self.parent[c]:
                self.multi[c] = "Y"

        self._build_dicts()
        self._build_index()

    # ------------------------------------------------------------------ 사전
    @staticmethod
    def _resolve(codes):
        """같은 이름에 코드가 여럿 붙을 때 하나를 고른다.

        마스터는 `...00` 이 일반형, `...01`·`...02` 가 그 특수화다.
            550100 요양보호사 · 550101 요양보호사(노인요양사)
            027200 경리 사무원 · 027201 경리 사무원(무역) · ... 027207
        괄호를 뗀 본체명이 같아지므로 충돌이 생기는데, 이건 모호한 게 아니라
        **일반형이 정답**인 경우다. 같은 세분류(앞4자리) 안이면 일반형을 준다.
        세분류가 갈리면 진짜 모호한 것이라 버린다.
        """
        codes = sorted(set(codes))
        if len(codes) == 1:
            return codes[0]
        if len({c[:4] for c in codes}) == 1:
            gen = codes[0][:4] + "00"
            return gen if gen in codes else codes[0]
        return None

    def _build_dicts(self):
        # 명칭 사전 — 전체명 우선, 본체명 차선. 둘을 섞으면
        # '요양보호사'(전체명 550100)가 '요양보호사(노인요양사)'의 본체와 충돌해 버려진다.
        full, core = collections.defaultdict(set), collections.defaultdict(set)
        for c, nm in self.name.items():
            k = norm(nm)
            if len(k) >= 2 and k not in STOP:
                full[k].add(c)
            k = core_of(nm)
            if len(k) >= 2 and k not in STOP:
                core[k].add(c)
        exact, dropped = {}, 0
        for d in (core, full):                       # 전체명이 나중 = 덮어쓴다
            for k, cs in d.items():
                c = self._resolve(cs)
                if c:
                    exact[k] = c
                elif k not in exact:
                    dropped += 1
        self.exact = exact
        self.exact_dup = dropped

        # 별칭 사전 — 괄호 안 동의어를 펼친다.
        #   '전기용접원(아크,알곤,티그용접원)' -> 티그용접원(접미어 O) · 아크+용접원(머리말 결합)
        # 머리말(head) 은 손으로 적지 않고, 본체명들의 뒤쪽 n-gram 중
        # 여러 명칭에 공통으로 나타나는 것만 자동 수집한다.
        tail = collections.Counter()
        cores = [core_of(nm) for nm in self.name.values()]
        for cr in cores:
            for L in range(2, 7):
                if len(cr) > L:
                    tail[cr[-L:]] += 1
        heads = {t for t, n in tail.items() if n >= 5}
        self.heads = heads

        cand = collections.defaultdict(set)
        for c, nm in self.name.items():
            cr = core_of(nm)
            for it in paren_items(nm):
                ks = [it] if (it.endswith(_JOBSUF) or len(it) >= 4) else []
                for L in range(6, 1, -1):          # 긴 머리말 우선
                    if len(cr) > L and cr[-L:] in heads:
                        ks.append(it + cr[-L:])
                        break
                for k in ks:
                    if len(k) >= 3 and k not in STOP and k not in self.exact:
                        cand[k].add(c)
        alias, adup = {}, 0
        for k, cs in cand.items():
            c = self._resolve(cs)
            if c:
                alias[k] = c
            else:
                adup += 1
        self.alias = alias
        self.alias_dup = adup

    # ------------------------------------------------------------------ 인덱스
    def _build_index(self):
        # 부분일치용. 본체명 3자 이상만. 긴 것 우선 매칭하도록 정렬해 둔다.
        self.cores = sorted(
            {(core_of(nm), c) for c, nm in self.name.items() if len(core_of(nm)) >= 3},
            key=lambda x: -len(x[0]))
        self._memo = {}

    def scan_text(self, txt):
        """자유 텍스트에 공식 명칭이 통째로 들어 있으면 그 코드를 준다.

        분류기가 `직무` 토큰만 보던 탓에, 직무 칸은 비었는데 담당업무·자격요건에
        `간호사면허소지` `치위생사 구인합니다` 처럼 직업명이 그대로 적힌 공고가
        미분류로 남았다. 긴 명칭부터 찾아 가장 구체적인 것을 고른다.
        """
        t = norm(txt)[:400]
        if len(t) < 3:
            return None
        for cr, c in self.cores:                # 이미 긴 순
            if len(cr) >= 3 and cr in t:
                return c, cr
        return None

    def lookup_partial(self, tok):
        """토큰 하나가 내는 후보. 토큰당 1회만 계산하고 캐시한다.

        ("부분일치", 코드)      토큰이 공식 명칭을 통째로 포함 — 가장 긴 명칭이 정답
        ("단일합의", 코드)      토큰을 품은 공식 명칭이 딱 하나
        ("상위합의", (코드…))   토큰을 품은 명칭이 여럿 — 대분류 표결에 넘긴다

        [왜 후보를 미리 접지 않나]
        전 버전은 여기서 후보들의 공통 앞자리를 계산해 반환했다. 그러면 "영업"
        처럼 경영(0)·영업(6)에 걸친 토큰은 공통 앞자리가 빈 문자열이 되어 그냥
        버려졌다. 실제로 미분류 9,857건 안에 영업 709·간호 502·생산 445가
        들어앉아 있었다. 후보를 그대로 넘겨서 **분포로 표결**해야 한다.
        """
        if tok in self._memo:
            return self._memo[tok]
        res = None
        for cr, c in self.cores:                    # 이미 긴 순
            if cr in tok:
                res = ("부분일치", c); break
        if res is None and len(tok) >= 2:
            hit = tuple(sorted({c for cr, c in self.cores if tok in cr}))
            if len(hit) == 1:
                res = ("단일합의", hit[0])
            elif hit:
                res = ("상위합의", hit)
        self._memo[tok] = res
        return res

    # ------------------------------------------------------------------ 계층
    def levels(self, code):
        """부여된 코드(6자리 또는 상위 접두)를 계층 컬럼으로 펼친다."""
        full = self.name.get(code)
        d = len(code)
        out = {
            "직종코드": code if full else "",
            "직종명": full or "",
            "직종코드깊이": 6 if full else d,
            "직종코드부분": "" if full else code,
            "직종대분류코드": code[:1], "직종대분류명": MAJOR10.get(code[:1], ""),
            "직종중분류코드": code[:2] if d >= 2 else "",
            "직종소분류코드": code[:3] if d >= 3 else "",
            "직종세분류코드": code[:4] if d >= 4 else "",
            "직종13대분류코드": "", "직종13대분류명": "",
            "직종114중분류코드": "", "직종114중분류명": "",
            "직종13대분류중복": "",
        }
        if full:
            p = self.parent[code]
            nm2, sup = self.d2.get(p, ("", ""))
            out["직종114중분류코드"], out["직종114중분류명"] = p, nm2
            out["직종13대분류코드"], out["직종13대분류명"] = sup, self.d1.get(sup, "")
            out["직종13대분류중복"] = self.multi[code]
        return out


# --------------------------------------------------------------------- 토큰
_TOKSPLIT = re.compile(r"[,/|]+")


def tokens(job_field):
    """`직무` 칸을 토큰으로. 앞쪽 토큰이 더 신뢰도 높은 출처에서 왔다(정규화 단계 규칙)."""
    out, seen = [], set()
    for raw in _TOKSPLIT.split(job_field or ""):
        t = raw.strip()
        if not t:
            continue
        for v in (t, re.sub(r"\(.*", "", t)):      # '용접원 모집(스텐박판)' -> '용접원 모집'
            k = norm(v)
            k = re.sub(r"\d+명$", "", k)        # "사원 1명" 처럼 모집인원이 붙어 온다
            k = re.sub(r"(모집|채용|공고|구인)$", "", k)
            if len(k) < 2 or k in STOP or k.isdigit() or k in seen:
                continue
            seen.add(k)
            out.append(k)
    return out


class Classifier:
    """토큰 → 직종코드. 전 과정이 결정적(deterministic)이라 몇 번 돌려도 같은 결과다."""

    # 6자리 코드까지 내는 경로는 이 둘뿐이다.
    # 부분일치·단일합의도 처음엔 여기 뒀는데, 홀드아웃에서 세분류 정확도가
    # 59% · 23% 로 나왔다. 대분류는 88% · 58% 로 쓸 만하니 버리지 않고
    # 표결로 넘겨 대분류만 받는다. 깊이를 못 믿으면 깊이를 내지 않는다.
    GRADE = {"별칭일치": "강", "학습사전": "중"}
    ORDER = ["별칭일치", "학습사전"]

    def __init__(self, master=None, learned=None, learned_prefix=None, lexicon=None):
        self.m = master or Master()
        self.learned = learned or {}
        # 정답에서 배웠지만 세세분류까지는 못 정한 토큰. 표결보다 먼저 쓴다.
        self.learned_prefix = learned_prefix or {}
        # 직무 사전 — `약` 등급의 추정 근거. {토큰: (6자리, 13분류, 근거문장)}
        # 둘 다 빈 행은 "이 토큰으로는 추정하지 않는다" 는 뜻이다(직급·범용어).
        self.lex = lexicon or {}

    def propose(self, toks):
        """(확정후보, 표결후보). 확정후보는 (순위, 토큰위치, 코드, 근거, 토큰)."""
        strong, weak = [], []
        for i, t in enumerate(toks):
            c = self.m.exact.get(t) or self.m.alias.get(t)
            if c:
                strong.append((0, i, c, "별칭일치", t)); continue
            c = self.learned.get(t)
            if c:
                strong.append((1, i, c, "학습사전", t)); continue
            c = self.learned_prefix.get(t)
            if c:
                # 상위 접두라 세세분류로는 못 쓴다. 표결 후보로 넣되
                # 그 접두에 속한 코드 전체를 후보로 준다 — 표결이 그 방향으로 쏠린다.
                sub = tuple(x for x in self.m.name if x.startswith(c))
                if sub:
                    weak.append((i, sub, t))
                    continue
            r = self.m.lookup_partial(t)
            if not r:
                continue
            why, val = r
            # 부분일치(코드 1개) · 단일합의(코드 1개) · 상위합의(코드 여러개)
            # 모두 표결로 보낸다. 코드 1개짜리는 그 대분류에 100% 쏠린 표가 된다.
            weak.append((i, (val,) if isinstance(val, str) else val, t))
        strong.sort()
        return strong, weak

    def _estimate(self, toks):
        """(추정 6자리, 추정 13분류, 근거) — **직무 사전**으로만 추정한다.

        처음엔 "표결에서 가중치가 가장 큰 후보"를 추정값으로 썼다. 숫자는 나오지만
        왜 그 코드인지 설명할 수 없고, 홀드아웃 정확도도 7% 였다.
        사전 방식은 근거가 한 줄로 나온다.
            토큰 "원무과" -> 026502  근거: 사전(수동) 원무과: 병원행정 사무원(원무)
        사전에 없으면 추정하지 않는다. 근거 없는 값은 싣지 않는다.
        사전의 코드가 빈 행(`실장`·`팀장`·`엔지니어`)은 "직급·범용어라 특정 불가" 다.
        """
        # 6자리를 주는 항목이 우선. 없으면 13분류만 주는 항목을 쓴다.
        # 사전에 있으나 둘 다 빈 항목(직급·범용어)을 만나면 그 자리에서 멈춘다 —
        # "이 토큰으로는 추정하지 않는다" 가 명시된 판단이기 때문이다.
        #
        # [긴 토큰 먼저] `데이터엔지니어` 와 `엔지니어` 가 둘 다 사전에 있으면 긴 쪽이
        # 이겨야 한다. 짧은 쪽이 "추정하지 않는다" 라서, 순서를 안 정하면 `엔지니어` 가
        # 먼저 걸려 데이터 엔지니어 공고가 통째로 미분류로 남는다(실제로 그랬다).
        toks = sorted(toks, key=lambda t: (-len(t), toks.index(t)))
        fallback = None
        for t in toks:
            hit = self.lex.get(t)
            if hit is None:
                continue
            code, c13, why = hit
            if code:
                return code, c13, why
            if not c13:
                return "", "", why              # 추정 안 함 — 이유는 남긴다
            if fallback is None:
                fallback = ("", c13, why)
        return fallback or ("", "", "")

    @staticmethod
    def _vote13(weak, key):
        """13대분류를 같은 표결로 정한다.

        `약` 등급은 KECO 1자리만 나오는데, 그 1자리가 13분류로 갈리는 경우가 있다
        (1→연구/정보통신, 6→영업판매/운전운송, 8→설치정비생산/재료화학/정보통신).
        그래서 1자리에서 파생하려 하면 실패한다. 후보 코드들의 13분류를 직접
        표결하면 그 갈림을 표가 정해 준다. 가중치 규칙은 대분류 표결과 같다.
        """
        score, first = collections.defaultdict(float), {}
        for pos, codes, _ in weak:
            cnt = collections.Counter()
            for c in codes:
                k = key(c)
                if k:
                    cnt[k] += 1
            if not cnt:
                continue
            tot = sum(cnt.values())
            for k, v in cnt.items():
                score[k] += (1.0 / (1 + pos)) * v / tot
                first.setdefault(k, pos)
        if not score:
            return ""
        return max(score, key=lambda k: (score[k], -first[k]))

    @staticmethod
    def _vote(weak):
        """표결후보를 대분류 단위로 모은다.

        [왜 표결인가]  첫 토큰의 후보를 그냥 쓰면 대분류 정확도가 64.5% 였다.
        "안전관리" 하나로는 건설·제조·경영을 못 가리는데, 같은 공고의 다른 토큰이
        어느 쪽인지 말해주는 경우가 많다.

        가중치 = 1/(1+토큰위치) × (그 대분류에 속한 후보 비율)
          · 토큰위치 — `직무` 칸은 앞쪽이 더 믿을 만한 출처에서 왔다
            (직종 > 직무키워드 > 모집분야 > 원본직무 > 제목 > 담당업무)
          · 후보 비율 — 후보가 한 대분류에 쏠린 토큰일수록 강하게 센다.
            "간호"는 거의 전부 보건·의료(3)라 강하고, "관리"는 전 대분류에
            흩어져서 약하다. 별도 가중치 표를 손으로 만들지 않아도 된다.
        """
        score, owner = collections.defaultdict(float), {}
        for pos, codes, tok in weak:
            w = 1.0 / (1 + pos)
            cnt = collections.Counter(c[:1] for c in codes)
            for k, v in cnt.items():
                sc = w * v / len(codes)
                score[k] += sc
                if sc > owner.get(k, (0, ""))[0]:
                    owner[k] = (sc, tok)
        if not score:
            return "", ""
        top = max(score, key=lambda k: (score[k], -min(
            p for p, cs, _ in weak if any(c[:1] == k for c in cs))))
        return top, owner[top][1]

    def assign(self, toks, gold_name=None, text="", k13=None):
        """(코드, 근거, 확실도, 매칭토큰, 후보코드들, 추정6자리, 추정13분류, 추정근거)

        `k13` 은 13대분류를 6자리 코드에서 뽑는 함수다(keco13.of). 주면 `약` 등급의
        13대분류를 후보 표결로 정한다.

        `text` 는 담당업무·자격요건·제목을 이어붙인 자유 텍스트다. 토큰으로
        확정하지 못했을 때만 본다 — 토큰이 더 신뢰도 높은 출처다.
        """
        if gold_name:
            c = self.m.exact.get(norm(gold_name)) or self.m.exact.get(core_of(gold_name))
            if c:
                return c, "고용24직접", "강", gold_name, [], "", "", ""
        strong, weak = self.propose(toks)
        cand = []
        for _, _, c, _, _ in strong:
            if c not in cand:
                cand.append(c)
        if strong:
            _, _, code, why, tok = strong[0]
            return code, why, self.GRADE[why], tok, cand[:6], "", "", ""
        # 토큰으로 세세분류를 못 정했다. 본문에 공식 명칭이 통째로 있으면 표결 후보로 넣는다.
        #
        # [왜 확정으로 안 쓰나] 처음엔 이걸 6자리 확정(중급)으로 썼더니 홀드아웃에서
        # 세세분류 2% · 대분류 73% 가 나왔다. 자격요건의 `간호사면허소지` 가
        # 간호조무사 공고에 걸리는 식이다. 자유 텍스트에 직업명이 나온다는 것은
        # "그 직업이다" 가 아니라 "그 직업과 관련 있다" 는 뜻일 때가 많다.
        # 대분류 방향 정도만 쓸 수 있으므로 표결에 넘긴다.
        if text:
            hit = self.m.scan_text(text)
            if hit:
                weak.append((len(toks) + 1, (hit[0],), hit[1]))
        code, tok = self._vote(weak)
        if not code:
            est, e13, ebasis = self._estimate(toks)
            if not e13 and k13:
                v = self._vote13(weak, k13)
                if v:
                    e13 = v
                    ebasis = ebasis or f"후보 표결 — 13대분류가 {v} 로 모였다"
            return "", "", "미분류", "", cand[:6], est, e13, ebasis
        # 표결은 **대분류(1자리)까지만** 낸다.
        # 홀드아웃 실측으로 그 아래는 못 믿는다(중분류 55.7% · 소분류 35.1% · 세분류 23.6%).
        # 24% 정확도의 세분류를 데이터에 실으면 쓰는 사람을 속이는 셈이다.
        est, e13, ebasis = self._estimate(toks)
        if not e13 and k13:
            v = self._vote13(weak, k13)
            if v:
                e13 = v
                ebasis = ebasis or f"후보 표결 — 지지 후보들의 13대분류가 {v} 로 모였다"
        return code, "상위합의", "약", tok, cand[:6], est, e13, ebasis
