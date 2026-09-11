#!/bin/bash
# 부산 수집 진행 현황.  실행: bash ~/Downloads/크롤링/진행상황.sh
#   -w 를 붙이면 5초마다 갱신:  bash 진행상황.sh -w
cd "$(dirname "$0")" || exit 1
exec python3 src/busan_status.py "$@"
