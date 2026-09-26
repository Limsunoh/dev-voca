/**
 * 문제 지문과 보기의 글꼴을 유형별로 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 한글을 고정폭으로 그리면 고정폭 글꼴(JetBrains Mono)에 한글이 없어 OS
 * 글꼴로 굵고 뭉툭하게 떨어진다. 한 판·일일공부·복습(QuestionCard)은 한글
 * 뜻·설명 지문을, 문제풀기(QuizBoard)는 한글 상황 보기를 그렇게 그리고
 * 있었다. 영어 보기는 문제풀기만 고정폭이었다.
 *
 * 문제풀기(QuizBoard)는 상태가 많아 그리는 법이 달라 quiz-board-fonts.test.mts
 * 에서 실제로 그려 본다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { RoundQuestion } from "@/lib/api/rounds";
import {
  choicesAreTerms,
  promptIsEnglish,
  promptIsMono,
  promptIsSentence,
  promptIsTerm,
} from "@/lib/quiz-text";

import { QuestionCard } from "./QuestionCard";

function card(
  kind: string,
  prompt: string,
  choices: string[],
  sentenceKind?: string | null,
) {
  const question: RoundQuestion = {
    kind,
    kind_label: kind,
    question: "무엇일까?",
    prompt,
    category: "git",
    category_label: "Git",
    choices: choices.map((text, i) => ({ id: i + 1, text })),
    // 칸이 아예 없는 것(옛 저장분)과 값이 있는 것을 가른다.
    ...(sentenceKind === undefined ? {} : { sentence_kind: sentenceKind as string }),
  };
  return renderToStaticMarkup(
    createElement(QuestionCard, { question, busy: false, onPick: () => {} }),
  );
}

/** 이 글자를 감싼 가장 가까운 여는 태그. */
function tagOf(html: string, text: string): string {
  const at = html.indexOf(text);
  assert.ok(at >= 0, `${text} 를 못 찾았다`);
  const open = html.lastIndexOf("<", at);
  return html.slice(open, html.indexOf(">", open) + 1);
}

const isMono = (tag: string) => /class="[^"]*font-mono/.test(tag);

describe("유형별 규칙", () => {
  it("지문은 뜻 고르기(용어)만 고정폭", () => {
    assert.deepEqual(
      ["meaning", "term", "description", "blank", "situation"].map(promptIsTerm),
      [true, false, false, false, false],
    );
  });

  it("보기는 용어인 유형만 고정폭", () => {
    assert.deepEqual(
      ["meaning", "term", "description", "blank", "situation"].map(choicesAreTerms),
      [false, true, true, true, false],
    );
  });

  it("영어 지문은 용어와 문장 둘 다", () => {
    assert.deepEqual(
      ["meaning", "term", "description", "blank", "situation"].map(promptIsEnglish),
      [true, false, false, true, true],
    );
  });

  it("모르는 유형은 고정폭으로 그리지 않는다", () => {
    assert.equal(promptIsTerm("error"), false);
    assert.equal(choicesAreTerms("error"), false);
  });
});

describe("QuestionCard (한 판·일일공부·복습)", () => {
  it("뜻 고르기: 용어 지문은 고정폭, 한글 보기는 본문체", () => {
    const html = card("meaning", "rebase", ["커밋을 옮기기", "합치기"]);
    assert.ok(isMono(tagOf(html, "rebase")));
    assert.match(tagOf(html, "rebase"), /lang="en"/);
    assert.ok(!isMono(tagOf(html, "커밋을 옮기기")));
  });

  it("단어 고르기: 한글 뜻 지문은 본문체, 용어 보기는 고정폭", () => {
    const html = card("term", "원격 저장소의 변경을 가져오기", ["fetch", "push"]);
    assert.ok(!isMono(tagOf(html, "원격 저장소의 변경을 가져오기")));
    assert.ok(isMono(tagOf(html, "fetch")));
    assert.match(tagOf(html, "fetch"), /lang="en"/);
  });

  it("설명 문제: 여러 줄 한글이라 본문 크기·줄바꿈 유지", () => {
    const html = card("description", "여러 커밋을\n하나로 합친다", ["squash", "merge"]);
    const tag = tagOf(html, "여러 커밋을");
    assert.ok(!isMono(tag));
    assert.match(tag, /whitespace-pre-line/);
    assert.ok(isMono(tagOf(html, "squash")));
  });

  it("상황 고르기: 한글 보기는 본문체, 영어 문장 지문에는 lang", () => {
    const html = card("situation", "Can you rebase onto main?", ["리뷰 전에 정리할 때", "배포할 때"]);
    assert.ok(!isMono(tagOf(html, "리뷰 전에 정리할 때")));
    // 없으면 화면 낭독기가 영어 문장을 한국어 음성으로 읽는다.
    assert.match(tagOf(html, "Can you rebase"), /lang="en"/);
  });
});

/*
 * 문장 지문(빈칸·상황)은 문장 종류로 가른다. 에러 메시지("error")만
 * 고정폭이고, 실무 표현·빈 값·칸 없음·모르는 값은 본문체다.
 * 굵기·줄간격은 문장이면 bold·snug, 용어·뜻 지문이면 black·tight 다.
 */
describe("문장 종류로 가르는 규칙(promptIsMono)", () => {
  it("에러 메시지 문장만 고정폭", () => {
    for (const kind of ["blank", "situation"]) {
      assert.equal(promptIsMono(kind, "error"), true, kind);
      assert.equal(promptIsMono(kind, "phrase"), false, kind);
      assert.equal(promptIsMono(kind, ""), false, kind);
      assert.equal(promptIsMono(kind, undefined), false, kind);
      assert.equal(promptIsMono(kind, null), false, kind);
      assert.equal(promptIsMono(kind), false, kind);
    }
  });

  it("모르는 값은 본문체 - 대소문자·공백까지 정확히 맞아야 고정폭", () => {
    for (const odd of ["ERROR", "Error", " error", "error ", "code", "에러 메시지", "mono"]) {
      assert.equal(promptIsMono("blank", odd), false, odd);
      assert.equal(promptIsMono("situation", odd), false, odd);
    }
  });

  it("뜻 고르기(용어)는 문장 종류와 무관하게 고정폭", () => {
    for (const sk of [undefined, null, "", "phrase", "error", "code"]) {
      assert.equal(promptIsMono("meaning", sk), true, String(sk));
    }
  });

  it("단어 유형·모르는 유형에 error 가 붙어 와도 고정폭이 아니다", () => {
    // 한글 지문(뜻·설명)을 고정폭으로 그리면 한글이 뭉개진다.
    for (const kind of ["term", "description", "error", "Blank", "SITUATION", ""]) {
      assert.equal(promptIsMono(kind, "error"), false, kind);
    }
  });

  it("문장 지문은 빈칸·상황 둘뿐", () => {
    assert.deepEqual(
      ["meaning", "term", "description", "blank", "situation", "Blank", "error"].map(
        promptIsSentence,
      ),
      [false, false, false, true, true, false, false],
    );
  });
});

describe("QuestionCard 문장 지문 (한 판·일일공부·복습)", () => {
  const style = (tag: string) => /style="([^"]*)"/.exec(tag)?.[1] ?? "";

  it("에러 메시지 문장은 고정폭 + lang=en", () => {
    for (const kind of ["blank", "situation"]) {
      const text = `fatal: refusing ____ ${kind}`;
      const tag = tagOf(card(kind, text, ["a", "b"], "error"), text);
      assert.ok(isMono(tag), kind);
      assert.match(tag, /lang="en"/);
      assert.match(style(tag), /letter-spacing:var\(--tracking-tighter\)/);
    }
  });

  it("실무 표현·빈 값·칸 없음·null 은 본문체 + lang=en", () => {
    for (const kind of ["blank", "situation"]) {
      for (const sk of ["phrase", "", undefined, null]) {
        const text = `Could you ____ it ${kind} ${String(sk)}`;
        const tag = tagOf(card(kind, text, ["a", "b"], sk), text);
        assert.ok(!isMono(tag), `${kind} ${String(sk)}`);
        assert.match(tag, /lang="en"/);
        assert.match(style(tag), /letter-spacing:var\(--tracking-tight\)/);
      }
    }
  });

  it("모르는 값(ERROR·code)은 본문체", () => {
    for (const sk of ["ERROR", "code"]) {
      const text = `panic: ${sk}`;
      assert.ok(!isMono(tagOf(card("situation", text, ["a", "b"], sk), text)), sk);
    }
  });

  it("문장 지문은 bold·snug, 에러든 실무 표현이든 같다", () => {
    for (const sk of ["error", "phrase", undefined]) {
      const text = `sentence ${String(sk)}`;
      const s = style(tagOf(card("blank", text, ["a", "b"], sk), text));
      assert.match(s, /font-weight:var\(--weight-bold\)/, String(sk));
      assert.match(s, /line-height:var\(--leading-snug\)/, String(sk));
    }
  });

  it("용어 지문은 그대로 black·tight + 고정폭(문장 종류가 와도)", () => {
    for (const sk of [undefined, "", "phrase"]) {
      const tag = tagOf(card("meaning", "rebase", ["옮기기", "합치기"], sk), "rebase");
      assert.ok(isMono(tag), String(sk));
      const s = style(tag);
      assert.match(s, /font-weight:var\(--weight-black\)/);
      assert.match(s, /line-height:var\(--leading-tight\)/);
    }
  });

  it("단어 고르기 한글 지문은 error 가 붙어 와도 본문체·black", () => {
    const text = "원격 저장소를 가져오기";
    const tag = tagOf(card("term", text, ["fetch", "push"], "error"), text);
    assert.ok(!isMono(tag));
    assert.match(style(tag), /font-weight:var\(--weight-black\)/);
  });
});
