# 부산 청년 유출 분석

BOAZ 27기 1차 프로젝트 / DX Challenge 2026 Big Data
주제 **「인재 배출과 기업 수요의 엇갈린 결 — 부산 지역 청년 유출 원인 분석」**

```
├── data/              원본 데이터 (전부 공개 자료 · 재현 가능)
│   ├── 채용공고/       직접 크롤링 25,135건 (2026-09-07 스냅샷)
│   ├── 취업통계/       교육부·KEDI 졸업자 취업통계 2024
│   ├── 고용24/         구인구직통계 월간 12개 (2025.08~2026.07)
│   ├── 인구이동/       국내인구이동통계 2022~25 + 수도권 20년 특별분석
│   ├── goms/          대졸자직업이동경로조사 2016~19 4개 코호트
│   ├── 산업임금/       전국사업체조사·사업체노동력조사 (KOSIS)
│   └── 부산데이터/     부산 Big-데이터웨이브 청년정책 + 시행계획 원문
│
├── build/             재현 스크립트 (원자료 → 결과 전부 재생성)
├── out/               분석 결과 CSV · 핵심은 대시보드_13계열.csv
├── viz/               시각화 시안 (최종은 Tableau)
├── docs/              문서 · docs/참고에 인용 자료
└── 선행작업_부산EDA/   초기 EDA 폴더 (Big-데이터웨이브 6종 · 성별격차 분석 포함)
```

## 먼저 읽을 것

| 목적 | 문서 |
|---|---|
| **브리핑 한 번에** | `docs/브리핑.md` |
| 팀원에게 공유 | `docs/팀원설명_한장.md` |
| 그림 해설 | `docs/그림6장_해설.md` |
| 남은 과제 | `docs/최종감사.md` |

## 재현

```bash
python3 build/parse_worknet.py        # 고용24 12개월 파싱
python3 build/core_table.py           # 직종별 수요·공급
python3 build/mismatch.py             # 배출 vs 수요
python3 build/parse_migration.py      # 인구이동
python3 build/goms_pool.py            # GOMS 4코호트 풀링
python3 build/build13.py              # 13계열 통합 테이블 ★
python3 build/housing.py              # 주거비 실측 (임금 격차 반론 검증)
```
