/**
 * 문제 카드가 제한 시간을 보여주는지 **실제로 그려서** 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 한 판은 문제마다 제한 시간이 다르다 - 지문이 단어면 3초, 문장이면 7초다.
 * 그 안에 맞혀야 +1 이고 지나서 맞히면 0 인데, 화면에 없으면 판이 끝나고
 * 점수를 보고서야 안다. 서버는 처음부터 값을 보냈고 화면 타입에 칸이
 * 없어서 버려지고 있었다.
 *
 * **원문을 정규식으로 보지 않는다.** 처음에는 그렇게 썼는데, 코드 리뷰가
 * 사보타주로 깨뜨려 보니 "3000 을 1000 으로 나눈 뒤 60 을 곱해 180초로
 * 만드는" 변형이 그대로 통과했다. 부분 일치라 계산이 더 붙어도 안 걸린다.
 * 여기서는 글자를 뽑아 무엇이 찍히는지 본다(형제 파일
 * wrong-answer-render.test.mts 와 같은 방식).
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { QuestionCard } from "./QuestionCard";
import type { RoundQuestion } from "@/lib/api/rounds";

const base: RoundQuestion = {
  kind: "meaning",
  kind_label: "뜻 고르기",
  question: "이 단어의 뜻은?",
  prompt: "rebase",
  choices: [
    { id: 1, text: "기준을 옮기다" },
    { id: 2, text: "합치다" },
  ],
  category: "git",
  category_label: "git",
};

const draw = (question: RoundQuestion) =>
  renderToStaticMarkup(
    QuestionCard({ question, busy: false, onPick: () => {} }) as never,
  );

describe("문제 카드는 제한 시간을 알려준다", () => {
  it("초로 바꿔 그린다", () => {
    const html = draw({ ...base, time_limit_ms: 3000 });
    assert.match(html, /3초 안에/);
    // ms 를 그대로 쓰면 "3000초", 잘못 곱하면 "180초" 가 된다.
    assert.doesNotMatch(html, /3000초|180초/);
  });

  it("문장 문제는 7초로 그린다", () => {
    const html = draw({ ...base, kind: "situation", time_limit_ms: 7000 });
    assert.match(html, /7초 안에/);
  });

  it("값이 없으면 아무것도 안 그린다", () => {
    // 일일학습·복습은 시간을 안 재고 이 값을 안 받는다. 조건 없이 그리면
    // 그 화면들에 "NaN초 안에" 가 뜬다.
    const html = draw(base);
    assert.doesNotMatch(html, /초 안에/);
    assert.doesNotMatch(html, /NaN/);
  });

  it("유형 이름은 그대로 그린다", () => {
    // 제한 시간을 넣으며 그 줄의 구조를 바꿨다. 원래 있던 것이 빠지면 안 된다.
    const html = draw({ ...base, time_limit_ms: 3000 });
    assert.match(html, /뜻 고르기/);
    assert.match(html, /이 단어의 뜻은\?/);
    assert.match(html, /rebase/);
  });
});
