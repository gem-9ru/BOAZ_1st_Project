#!/bin/bash
# 크롤링 진행 상황 확인.  실행:  bash ~/Downloads/크롤링/상태확인.sh
cd "$(dirname "$0")" || exit 1
exec python3 src/status.py
