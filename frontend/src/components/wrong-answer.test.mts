/**
 * 틀렸을 때 정답의 뜻까지 그리는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함은 "**서버는 보내는데 화면이 안 그린다**" 이다. 채점 응답에는
 * 처음부터 정답의 뜻이 실려 왔는데(answer_extra) 세 화면이 영어만 그리고
 * 버렸다. 뜻을 고르는 문제에서 틀리면, 정작 고르려던 뜻을 끝내 못 봤다.
 *
 * 이런 결함은 타입검사도 빌드도 안 잡는다. 안 쓰는 값이 하나 남아 있을
 * 뿐이라 화면은 멀쩡히 돌아간다. 그래서 "호출부가 두 값을 다 넘겼는가" 를
 * 원문으로 본다 - 브라우저를 띄우는 테스트 판이 이 저장소에 없다
 * (reaction-overlay.test.mts 가 같은 이유로 같은 방식이다).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

/** 한 줄짜리 결과만 알리는 화면들. 해설 카드가 없어 여기가 유일한 자리다. */
const BOARDS = ["RoundBoard.tsx", "DailyStudyBoard.tsx", "ReviewBoard.tsx"] as const;

function read(name: string): string {
  // 윈도우 체크아웃은 CRLF 라 줄 경계로 찾는 검사가 어긋난다.
  return readFileSync(join(HERE, name), "utf8").replace(/\r\n/g, "\n");
}

describe("틀렸을 때 정답의 뜻까지 보여준다", () => {
  for (const name of BOARDS) {
    const code = read(name);

    it(`${name} 은 오답 줄을 WrongAnswer 에 맡긴다`, () => {
      // 한 판은 두 자리다 - 틀린 것과 넘긴 것. 서버가 둘 다에 정답을
      // 실어 보낸다(session._skip_result).
      const used = code.match(/<WrongAnswer[\s\S]*?\/>/g) ?? [];
      const expected = name === "RoundBoard.tsx" ? 2 : 1;
      assert.equal(used.length, expected, "오답 줄을 그리는 자리 수");
      for (const one of used) {
        assert.match(one, /text=\{result\.answer_text\}/);
        assert.match(
          one,
          /extra=\{result\.answer_extra\}/,
          "뜻을 안 넘기면 서버가 보낸 값이 화면에서 사라진다",
        );
      }
    });

    it(`${name} 은 정답 글자를 직접 찍지 않는다`, () => {
      // 직접 찍으면 그 자리만 뜻이 빠진 채로 남는다.
      assert.doesNotMatch(code, /오답 · \$?\{result\.answer_text\}/);
    });
  }

  // 이 조각이 **무엇을 그리는지**는 형제 파일 wrong-answer-render.test.mts
  // 가 실제로 그려서 본다. 여기는 호출부만 본다 - 같은 것을 두 군데서
  // 검사하면 한쪽만 고쳐질 때 어느 쪽이 맞는지 알 수 없다.
});
