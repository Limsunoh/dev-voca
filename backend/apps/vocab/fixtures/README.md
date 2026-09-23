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

## 고쳐서 다시 넣기

이 파일에서 발음 몇 개를 고쳐도 **이미 DB 에 검수된 채 들어간 줄은 안
바뀐다.** `load_readings` 가 검수된 발음을 덮지 않기 때문이다(사람이 Admin
에서 고친 것을 지키려고). 그래서 셋을 차례로 한다.

1. Admin 에서 고친 줄들의 발음 검수를 푼다. 고친 pk 만 걸러 보려면 목록
   주소에 `?id__in=14,65,112` 처럼 붙인다. 전체 선택 뒤 동작 "선택한 문장의
   발음 검수를 취소"(단어는 "선택한 단어의 발음 검수를 취소")
2. `--reviewed` 없이 다시 넣는다. 푼 줄만 채워지고 나머지는 "이미 검수됐습니다"
   로 건너뛴다. 먼저 `--dry-run` 으로 채워질 건수가 1 에서 푼 수와 같은지 본다.
   다르면 멈춘다 - 파일 안에 원래 미검수였던 다른 줄이 있으면 그 줄도 같이
   덮이니, 어느 pk 가 더 잡혔는지부터 확인한다
   ```
   python manage.py load_readings apps/vocab/fixtures/readings_sentence.json --kind sentence --dry-run
   python manage.py load_readings apps/vocab/fixtures/readings_sentence.json --kind sentence
   ```
3. 같은 주소에서 줄을 하나씩 열어 원문과 새 발음을 나란히 본다. 문장
   목록에는 발음 칸이 없어서 목록만 보고는 확인할 수 없다(상세 화면의 "발음"
   묶음에 있다). 다 봤으면 목록으로 돌아와 전체 선택 뒤 "선택한 문장의
   발음을 검수 완료로 표시"(단어는 "선택한 단어의 발음을 검수 완료로 표시").
   그 전까지 이 줄들은 화면에 발음이 안 나온다.
   여기서 Admin 으로 발음을 고쳤으면 **이 파일에도 같은 값을 적는다.** 안
   적으면 다음 복원 때 고치기 전 값이 되살아난다

위 "복원" 은 `--reviewed` 를 붙이고 여기서는 안 붙이는 이유: 복원은 머지된
파일 전체를 빈 DB 에 되살리는 일이고, 그 파일은 PR 에서 사람이 diff 로 한 번
본 값이다. 여기서 넣는 것은 그 값을 운영 DB 의 원문과 나란히 놓고 보기 전이다.
붙이면 원문과 맞춰 보지 않은 채 바로 화면에 나간다. 그래서 발음을 고치는
PR 은 리뷰할 때 이 파일의 diff 를 원문과 함께 본다.

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
