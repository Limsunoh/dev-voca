# 프론트엔드 테스트

순수 로직만 검증한다. 화면과 제스처는 브라우저에서 눈으로 본다.

## 돌리는 법

```
node --experimental-transform-types --import ./tests/ts-resolve.mjs --test tests/*.test.ts
```

디렉터리(`--test tests/`)로 주면 resolve 훅이 그 인자까지 가로채
`ERR_UNSUPPORTED_DIR_IMPORT` 로 죽는다. 글롭으로 파일을 지정한다.

## 실행기 주의

`--experimental-strip-types` 가 아니라 `--experimental-transform-types` 다.
`api/client.ts` 의 `ApiError` 가 TypeScript 의 parameter property
(`readonly status: number`)를 쓰는데, strip-only 모드는 그 문법을 못 읽고
`ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX` 로 죽는다. transform 모드는 읽는다.

`ts-resolve.mjs` 가 하는 일 둘:

- 확장자 없는 상대 import(`"./client"`)와 `@/` 별칭을 실제 `.ts` 로 잇는다
- `"server-only"` 를 빈 모듈로 바꾼다. 번들러 전용 표시라 Node 에 없다

## 무엇을 안 담았나

화면과 제스처는 브라우저에서 눈으로 본다. `spring()` 은 rAF 루프라
Node 에서 못 돌리므로 손을 뗀 순간의 판정에 직접 들어가는
`project`/`rubber` 만 값으로 검증한다.
