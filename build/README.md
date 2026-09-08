# build/ — 파이프라인 산출물

```bash
python3 src/pipeline/normalize.py      # -> 공고_정규화.csv  (200,502행)
python3 src/pipeline/dedup.py          # -> 공고_통합.csv     (157,007건)
                                       # -> 중복매핑.csv      (200,502행)
                                       # -> 검수후보.csv
```

`공고_정규화.csv` 와 `중복매핑.csv` 는 용량이 커서(각 61MB/37MB) git 에 올리지 않습니다.
위 명령으로 재생성됩니다.

스키마는 [../docs/05_데이터_사전.md](../docs/05_데이터_사전.md) 참조.
