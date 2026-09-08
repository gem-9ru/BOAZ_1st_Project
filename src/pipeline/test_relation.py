# -*- coding: utf-8 -*-
"""중복제거 판정 규칙 회귀 테스트.

검수후보 16건을 사람이 직접 보고 내린 판단을 그대로 고정해 둔다.
규칙을 손댈 때마다 `python3 test_relation.py` 로 돌려 예전 판단이 깨지지 않았는지 확인한다.
(중복제거는 임계값 하나만 건드려도 조용히 품질이 무너져서, 눈으로 본 사례를 남겨두는 게 중요하다.)
"""
import importlib.util, sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("dedup", Path(__file__).with_name("dedup.py"))
dedup = importlib.util.module_from_spec(spec)
sys.modules["dedup"] = dedup
spec.loader.exec_module(dedup)

CASES = [
    # (설명, 제목A, 제목B, 기대)
    ("괄호 안 직급 상세화",     "[Laka] 아마존 이커머스 운영 (파트장)",
                              "[Laka] 아마존 이커머스 운영 (파트장/책임)", "merge"),
    ("한국어 직급 생략",        "글로벌 인플루언서 마케팅 팀장",
                              "글로벌 인플루언서 마케팅", "merge"),
    ("직급 범위 표기 차이",     "해외운영 담당 (대리~과장급)",
                              "해외운영 담당 (과장급) 채용", "merge"),
    ("매니저 표기 생략",        "업무지원직 콜센터 매니저(원무팀) 채용",
                              "업무지원직 콜센터(원무팀) 채용", "merge"),
    ("영문 Senior 유무",       "B2B Senior Data Engineer(B2B 시니어 데이터 엔지니어) - Databricks",
                              "B2B Data Engineer(B2B 데이터 엔지니어) - Databricks", "different"),
    ("영문 Senior 유무2",      "[Solution] Senior AI Engineer",
                              "[Solution] AI Engineer", "different"),
    ("영문 Senior 유무3",      "Brand Manager (CPG)",
                              "Senior Brand Manager (CPG)", "different"),
    ("영문 병기 주석은 예외",   "[ESTsoft] Perso Interactive 서비스 기획리드",
                              "[ESTsoft] Perso Interactive 서비스 기획리드 (Project Lead / Planning Manager)", "merge"),
    ("경력수준 괄호 표기",      "[자빈드서울] 온라인 MD (신입~주니어)",
                              "[자빈드서울]온라인 MD 채용공고", "merge"),
    ("팀장 vs 담당자는 별개",   "[아정당] 협력사 운영/영업 팀장 (서울)",
                              "[아정당] 협력사 운영/영업 담당자 (서울)", "different"),
    ("영문 Senior 유무4",      "AI Engineer", "Senior AI Engineer", "different"),
    ("시니어 괄호 표기",        "상품기획 MD (시니어)", "상품기획 MD", "merge"),
    ("어순만 다름",            "Account Manager (고객전략/법인영업)",
                              "[핀테크] 고객전략/법인영업 매니저 (Account Manager)", "merge"),
    ("연차표기 vs 시니어",      "[개발부문] 방산 개발 PM (3~9년)",
                              "[개발부문] 방산 개발 시니어 PM", "merge"),
    # 1차 설계에서 오병합했던 사례 — 다시 깨지지 않도록 고정
    ("지역 충돌",              "현대엔지니어링 건축사업본부 울산 건축공사관리 경력직(계약직) 인재영입",
                              "현대엔지니어링 건축사업본부 군산 건축공사관리 경력직(계약직) 인재영입", "different"),
    ("직무 충돌",              "동광종합토건(주) 건설안전부 (안전관리자) 신입 및 경력 직원모집",
                              "동광종합토건(주) 건설안전부 (보건관리자) 신입 및 경력 직원 모집", "different"),
    ("고용형태 태그 차이",      "백엔드 개발자(3년 이상 or 전문연구요원 편입/전직 가능)",
                              "백엔드 개발자(경력 3년 이상 or 전문연구요원 편입/전직 가능)", "merge"),
    ("인턴 태그 위치 차이",     "[리필드] 글로벌 인플루언서 마케터",
                              "[리필드] 글로벌 인플루언서 마케터 (인턴)", "merge"),
]

def main():
    fail = 0
    for desc, a, b, want in CASES:
        got = dedup.relation(a, b)
        if got != want:
            fail += 1
            print(f"  FAIL  {desc}\n        기대={want} 실제={got}\n        A: {a}\n        B: {b}")
    total = len(CASES)
    print(f"\n{total - fail}/{total} 통과" + ("" if fail else "  ✔"))
    return 1 if fail else 0

if __name__ == "__main__":
    sys.exit(main())
