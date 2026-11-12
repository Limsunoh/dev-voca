/**
 * 일상영어 카드(TalkPromptCard)에 소리 듣기 버튼이 있는가.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - "발음 듣기" 버튼이 하나 있다(일상 표현·개발 용어 둘 다).
 *   - 화면 낭독기 순서로는 읽을 글자 바로 뒤, 발음 표기·뜻보다 앞이다.
 *   - 버튼은 카드 오른쪽 위에 띄워 둔다. 줄을 따로 차지하면 카드가 길어져 세로가
 *     짧은 폰에서 주 버튼 "읽기" 가 아래 탭바 밑으로 밀린다. 화면이 좁으면
 *     (글자 200%) 띄우지 않고 줄로 내린다.
 *   - 마이크로 듣는 중에는 버튼을 감춘다(자리는 둔다). 폰 음성을 마이크가 받아
 *     채점하지 않게.
 *
 * 소리를 실제로 내는 것(speechSynthesis)은 SpeakButton 의 테스트가 본다.
 * 여기서는 카드에 붙었는지만 본다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { TalkPromptCard } from "./TalkPrompt";

const PHRASE = {
  token: "t",
  id: 7,
  kind: "phrase",
  term: "can I leave my bags here",
  pronunciation: "/kən aɪ ˈliv maɪ ˈbæɡz hɪr/",
  reading: "큰 아이 **l리v** 마이 **백z** 히어r",
  meaning: "여기 가방 맡겨도 되나요",
  difficulty: 1,
  difficulty_label: "쉬움",
  scene: "asking",
  scene_label: "묻기·길찾기",
} as const;

const render = (prompt: Record<string, unknown>) =>
  renderToStaticMarkup(createElement(TalkPromptCard, { prompt } as never));

describe("일상영어 카드의 소리 듣기", () => {
  it("발음 듣기 버튼이 하나 있다", () => {
    const html = render(PHRASE);
    assert.equal(html.match(/aria-label="발음 듣기"/g)?.length, 1);
  });

  it("낭독 순서로 버튼은 읽을 글자 뒤, 발음기호·뜻보다 앞에 온다", () => {
    const html = render(PHRASE);
    const term = html.indexOf(PHRASE.term);
    const button = html.indexOf('aria-label="발음 듣기"');
    const ipa = html.indexOf(PHRASE.pronunciation);
    const meaning = html.indexOf(PHRASE.meaning);
    assert.ok(term >= 0 && term < button, "버튼이 읽을 글자보다 앞에 있다");
    assert.ok(button < ipa && button < meaning, "버튼이 발음기호·뜻보다 뒤에 있다");
  });

  it("개발 용어 문제에도 붙는다", () => {
    const html = render({ ...PHRASE, kind: "word", term: "deploy", scene: "", scene_label: "" });
    assert.equal(html.match(/aria-label="발음 듣기"/g)?.length, 1);
  });

  it("버튼은 카드 오른쪽 위에 띄우고, 좁은 화면에서는 줄로 내린다", () => {
    const html = render(PHRASE);
    assert.match(html, /<section class="relative /);
    const wrap = html.match(/<div class="([^"]*)"><button[^>]*aria-label="발음 듣기"/)?.[1] ?? "";
    assert.ok(wrap.split(" ").includes("absolute"), wrap);
    assert.ok(wrap.split(" ").includes("max-[20rem]:static"), wrap);
  });

  it("마이크로 듣는 중에는 버튼을 감춘다", () => {
    const wrapOf = (listening: boolean) =>
      renderToStaticMarkup(
        createElement(TalkPromptCard, { prompt: PHRASE, listening } as never),
      ).match(/<div class="([^"]*)"><button[^>]*aria-label="발음 듣기"/)?.[1] ?? "";
    assert.ok(wrapOf(true).split(" ").includes("invisible"), wrapOf(true));
    assert.ok(!wrapOf(false).split(" ").includes("invisible"), wrapOf(false));
  });
});
