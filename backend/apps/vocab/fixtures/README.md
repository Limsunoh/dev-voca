# 발음 데이터

`readings_word.json` (566건) / `readings_sentence.json` (380건).
`prompts/korean-reading.md` 의 표기 규칙대로 손으로 적은 한글 발음이다.

## 복원

```
python manage.py load_readings apps/vocab/fixtures/readings_word.json --reviewed
python manage.py load_readings apps/vocab/fixtures/readings_sentence.json --kind sentence --reviewed
```

`seed_words` / `seed_sentences` 를 먼저 돌려 pk 가 있어야 한다. pk 로 짝을
맞추므로 시드를 지우고 다시 넣어 pk 가 밀리면 엉뚱한 단어에 붙는다. 그때는
`--dry-run` 으로 건수를 먼저 보고, 몇 개를 눈으로 확인한 뒤 반영한다.

## 왜 seed 안에 안 넣었나

`seed_words.py` 는 한 단어가 8칸짜리 튜플이고 566개가 들어 있다. 여기에
`reading` 을 넣으려면 전 항목의 튜플 모양을 바꿔야 해서, 발음만 고치는 일에
단어 데이터 전체가 diff 에 올라온다. 발음은 규칙이 바뀌면 통째로 다시 적게
되는 값이라 그 빈도도 다르다.

## 왜 파일로 남기나

2026-09-06 에 이 데이터를 한 번 잃었다. 처음 만들 때 세션 임시 디렉터리에만
두고 DB 에 부은 뒤 파일을 안 남겼는데, 컴퓨터를 바꾸자 그 디렉터리가 사라져
946건이 통째로 없어졌다. 코드·마이그레이션·컬럼은 전부 멀쩡했고 값만 비어
있어서, 화면에는 아무 에러 없이 발음란만 조용히 안 보였다.
