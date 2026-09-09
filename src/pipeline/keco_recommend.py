"""공고 텍스트로 직종코드 후보를 추천한다 — 수작업 분류를 돕기 위해.

[왜 필요한가]
`약`·미분류 공고의 추정은 **직무 토큰**에서 나온다. 그런데 미분류 2,666건 중
토큰이 아예 없는 공고가 상당수고(직무없음 627 · 무정보토큰 312), 그런 공고도
제목과 담당업무에는 단서가 있다.

    제목    2026년 청룡초등학교 당직전담사 채용 공고
    담당업무 터널관리팀 풀베기 노인일자리사업 참여자 모집 - 근무 예정 터널지소…

이 텍스트를 공식 명칭 1,130개와 대조해 후보를 뽑는다.
**추천이지 확정이 아니다.** 사람이 고르는 걸 돕는 것이 목적이다.

[어떻게 뽑나 — 근거가 남는 방식으로만]
① 명칭 포함     공식 명칭(괄호 뗀 본체)이 텍스트에 통째로 있으면 가장 강하다.
                긴 명칭이 짧은 명칭보다 구체적이라 길이로 가중한다.
② 별칭 포함     괄호 안 동의어(`티그용접원`·`노인요양사`)도 같이 본다.
③ 사전 토큰     직무사전의 토큰이 텍스트에 있으면 그 코드에 가점.
                사전은 정답에서 학습했거나 사람이 등재한 것이라 근거가 명확하다.
④ 핵심어 결합   명칭의 **머리말**(`용접원`·`조작원`·`간호사`)이 텍스트에 있으면
                약한 가점. 분야가 안 맞을 수 있어 단독으로는 못 쓴다.

점수를 매기고 상위 4개만 남긴다. 각 후보에 **어디서(제목/담당업무/자격요건)
어떤 글자가 걸렸는지**를 함께 싣는다.

    140206 건축안전·환경·품질·에너지관리 기술자   담당업무 「안전관리」
    541300 시설 및 특수 경비원                제목 「경비」

실행:  python3 src/pipeline/keco_recommend.py        품질 측정 (정답 세트)
"""
import csv, collections, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keco_v2 import Master, norm, core_of, paren_items, STOP, _JOBSUF  # noqa: E402
import keco_lexicon                                             # noqa: E402

csv.field_size_limit(10 ** 9)
BASE = Path(__file__).resolve().parents[2]
SRC = ["직무", "공고제목", "담당업무", "자격요건", "직무상세", "업종"]
SRC_TAG = {"직무": "직무태그", "공고제목": "제목", "담당업무": "담당업무",
           "자격요건": "자격요건", "직무상세": "모집분야", "업종": "업종"}


class Recommender:
    def __init__(self, master=None, lexicon=None):
        self.m = master or Master()
        self.lex = lexicon if lexicon is not None else keco_lexicon.load_lexicon()
        # 본체명 · 별칭 → 코드. 긴 것부터 본다(긴 명칭이 더 구체적이다).
        # 괄호 안 항목은 두 종류가 섞여 있다. 버리지 말고 무게를 달리 준다.
        #   동의어   `전기용접원(아크,알곤,티그용접원)` -> 티그용접원   직업 접미어로 끝난다
        #   한정어   `자재·구매 사무원(기계·자동차·금속)` -> 자동차     분야를 좁히는 말
        # 한정어를 동의어와 같이 취급하면 `자동차` 한 단어가 자재·구매/생산관리/
        # 품질관리 사무원을 다 몰고 온다(실제로 그랬다). 그렇다고 버리면 회수율이
        # 390 -> 1,133건 후보없음으로 떨어진다. 그래서 가중치로 가른다.
        idx = collections.defaultdict(set)      # 본체명·동의어 — 제 무게
        qual = collections.defaultdict(set)     # 한정어 — 1/4 무게
        for c, nm in self.m.name.items():
            cr = core_of(nm)
            if len(cr) >= 3:
                idx[cr].add(c)
            for a in paren_items(nm):
                if len(a) < 3 or a in STOP:
                    continue
                (idx if a.endswith(_JOBSUF) else qual)[a].add(c)
        self.names = sorted(idx.items(), key=lambda x: -len(x[0]))
        self.quals = sorted(qual.items(), key=lambda x: -len(x[0]))
        # ⑤ 폴백용 글자 겹침 인덱스. 명칭마다 2글자 조각 집합을 미리 만든다.
        #   문자열이 통째로 안 걸리는 공고(미분류 2,666건 중 1,857건)에도
        #   출발점을 주기 위한 것이다. 가장 약한 신호라 폴백으로만 쓴다.
        self.bg = {}
        for c, nm in self.m.name.items():
            cr = core_of(nm)
            self.bg[c] = {cr[i:i + 2] for i in range(len(cr) - 1)} or {cr}
        # 사전 토큰 → 코드 (6자리만)
        self.lextok = {t: v[0] for t, v in self.lex.items() if v[0] and len(t) >= 2}
        # 머리말 — 본체명의 뒤쪽 n-gram 중 여러 명칭에 공통으로 나타나는 것.
        #   `용접원`·`조작원`·`간호사` 처럼 직업의 종류를 말한다.
        # 3글자 이상만 쓰고, **한 머리말이 25개 넘는 코드에 걸리면 버린다** —
        # `종사원`·`사무원` 처럼 너무 흔한 말은 후보를 몰고 오기만 한다.
        tail = collections.Counter()
        for c, nm in self.m.name.items():
            cr = core_of(nm)
            for L in range(3, 7):
                if len(cr) > L:
                    tail[cr[-L:]] += 1
        self.heads = collections.defaultdict(set)
        for h, n in tail.items():
            if n < 3 or n > 25:
                continue
            for c, nm in self.m.name.items():
                if core_of(nm).endswith(h):
                    self.heads[h].add(c)

    def _fields(self, row, drop_gold=False):
        """drop_gold — 정답 세트 평가용. `직종` 유래 토큰을 뺀다(누출 방지).

        `직무` 칸은 1순위 출처가 `직종` 이라 정답이 그대로 들어 있다.
        `직종` 이 아닌 원본 컬럼 텍스트에도 나타나는 토큰만 살린다.
        """
        out = []
        blob = norm(" ".join((row.get(c) or "") for c in SRC if c != "직무"))
        for c in SRC:
            v = (row.get(c) or "").strip()
            if not v:
                continue
            if c == "직무" and drop_gold:
                keep = [t.strip() for t in v.split(",")
                        if t.strip() and norm(t.strip()) in blob]
                if not keep:
                    continue
                v = ", ".join(keep)
            out.append((SRC_TAG[c], norm(v)[:400]))
        return out

    def top(self, row, k=4, drop_gold=False):
        """[(코드, 점수, 출처, 걸린글자)] — 점수 내림차순 상위 k개."""
        fields = self._fields(row, drop_gold)
        if not fields:
            return []
        score = collections.defaultdict(float)
        why = {}

        def bump(code, pts, tag, frag):
            score[code] += pts
            # 근거는 가장 강한 것 하나만 남긴다
            if code not in why or why[code][0] < pts:
                why[code] = (pts, tag, frag)

        # 제목이 담당업무보다 직무를 직접 말한다. 출처별 가중치.
        # 직무 태그는 사이트가 분류한 값이라 가장 직접적이다.
        # 업종은 산업이지 직업이 아니다 — 병원 원무과가 `의료` 로 끌려간다.
        # 그래서 **후보를 새로 만들지는 못하게** 하고, 이미 있는 후보에만 가점한다.
        W = {"직무태그": 1.3, "제목": 1.0, "모집분야": 1.0,
             "담당업무": 0.85, "자격요건": 0.5}
        ind = ""
        for tag, txt in fields:
            if tag == "업종":
                ind = txt
                continue
            w = W[tag]
            # ①② 명칭·별칭 포함 — 길이로 가중
            for nm, codes in self.names:
                if nm in txt:
                    pts = w * (2.0 + 0.25 * len(nm))
                    for c in codes:
                        bump(c, pts / len(codes) ** 0.5, tag, nm)
            # ①' 한정어 포함 — 분야만 맞는 것이라 1/4 무게
            for nm, codes in self.quals:
                if nm in txt and len(codes) <= 30:
                    pts = w * (0.5 + 0.06 * len(nm))
                    for c in codes:
                        bump(c, pts / len(codes) ** 0.6, tag, nm)
            # ③ 사전 토큰
            for t, c in self.lextok.items():
                if t in txt:
                    bump(c, w * (0.8 + 0.3 * len(t)), tag, t)
            # ④ 머리말 결합 — 약한 가점. 분야가 안 맞을 수 있어 단독으로는 못 쓴다
            for h, codes in self.heads.items():
                if h in txt:
                    pts = w * (0.6 + 0.1 * len(h)) / len(codes) ** 0.6
                    for c in codes:
                        bump(c, pts, tag, h)
        # ⑤ 아무것도 안 걸렸으면 글자 겹침으로라도 출발점을 준다.
        if not score:
            txt = " ".join(t for _, t in fields if _ != "업종")
            bag = {txt[i:i + 2] for i in range(len(txt) - 1)}
            if bag:
                sims = []
                for c, b in self.bg.items():
                    inter = len(bag & b)
                    if inter >= 2:
                        sims.append((inter / (len(b) + 2), c))
                sims.sort(reverse=True)
                for sim, c in sims[:k]:
                    bump(c, round(sim, 3), "글자겹침", "명칭과 겹치는 글자")
        # 업종은 이미 뽑힌 후보의 순위만 흔든다. 업종 어휘가 명칭에 들어 있으면 가점.
        if ind:
            for c in list(score):
                cr = core_of(self.m.name[c])
                if any(w2 in cr for w2 in re.findall(r"[가-힣]{2,}", ind)):
                    score[c] += 0.4
        best = sorted(score.items(), key=lambda x: (-x[1], x[0]))[:k]
        return [(c, round(s, 2), why[c][1], why[c][2]) for c, s in best]


def evaluate():
    """정답 세트로 품질을 잰다. `직종` 은 정답이라 입력에서 뺀다."""
    m = Master()
    r = Recommender(m)
    rows = list(csv.DictReader((BASE / "부산" / "부산_공고_직종분류.csv")
                               .open(encoding="utf-8-sig")))
    gold = []
    for x in rows:
        c = m.exact.get(norm(x["직종"] or "")) or m.exact.get(core_of(x["직종"] or ""))
        if c:
            gold.append((x, c))
    hit = collections.Counter()
    for x, truth in gold:
        cand = r.top(x, k=4, drop_gold=True)
        hit["n"] += 1
        if not cand:
            hit["후보없음"] += 1
            continue
        codes = [c for c, _, _, _ in cand]
        for lab, n in (("top1", 1), ("top4", 4)):
            sub = codes[:n]
            hit[lab + "_세세"] += any(c == truth for c in sub)
            hit[lab + "_세분류"] += any(c[:4] == truth[:4] for c in sub)
            hit[lab + "_대분류"] += any(c[:1] == truth[:1] for c in sub)
    n = hit["n"]
    print(f"정답 세트 {n:,}건 · 후보 못 낸 것 {hit['후보없음']:,}건\n")
    print(f"  {'':<8}{'세세분류':>9}{'세분류':>9}{'대분류':>9}")
    for lab in ("top1", "top4"):
        print(f"  {lab:<8}" + "".join(
            f"{100*hit[lab+'_'+k]/n:8.1f}%" for k in ("세세", "세분류", "대분류")))
    print("\n  top4 = 추천 4개 안에 정답이 있는 비율. 사람이 고르는 걸 돕는 게 목적이니")
    print("        이 숫자가 실제 도움 정도에 가깝다.")


if __name__ == "__main__":
    evaluate()
