#!/bin/zsh
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
declare -A M
M[64764]=2025-08; M[64765]=2025-09; M[64766]=2025-10; M[64767]=2025-11
M[64768]=2025-12; M[64769]=2026-01; M[64770]=2026-02; M[64771]=2026-03
M[64772]=2026-04; M[64773]=2026-05; M[64775]=2026-06; M[64776]=2026-07
for sn ym in ${(kv)M}; do
  curl -sL --max-time 40 -A "$UA" "https://www.keis.or.kr/keis/ko/bbs/123/detail.do?pstSn=$sn" -o build/_scrape/d_$sn.html
  # KSCO추가 버전 우선, 없으면 일반 구인구직통계
  url=$(python3 - "$sn" << 'PY'
import re,sys,html
sn=sys.argv[1]
s=open(f'build/_scrape/d_{sn}.html',encoding='utf-8',errors='ignore').read()
cands=re.findall(r'href="(/keis/ko/cmmn/download\.do\?[^"]*\.xlsx[^"]*)"',s)
cands=[html.unescape(c) for c in cands]
pick=[c for c in cands if 'KSCO' in c] or [c for c in cands if '%EA%B5%AC%EC%9D%B8%EA%B5%AC%EC%A7%81' in c] or cands
print(pick[0] if pick else '')
PY
)
  if [[ -n "$url" ]]; then
    curl -sL --max-time 90 -A "$UA" -e "https://www.keis.or.kr/keis/ko/bbs/123/detail.do?pstSn=$sn" "https://www.keis.or.kr$url" -o raw_worknet/$ym.xlsx
    printf "%s %s %s\n" "$ym" "$(file -b --mime-type raw_worknet/$ym.xlsx)" "$(stat -f%z raw_worknet/$ym.xlsx)"
  else
    echo "$ym NO_XLSX"
  fi
done
