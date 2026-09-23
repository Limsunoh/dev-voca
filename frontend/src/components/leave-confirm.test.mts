/**
 * 문제풀기의 네 출구가 푼 것이 있을 때 확인을 묻는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 출구는 넷이다 - 홈(ExitGuard), 분류 고르개(CategoryPicker), 단어·문장
 * 탭(ContentTabs), 머리의 "한 판 풀기"(LeaveLink). 넷 다 누르는 순간 판이
 * 새로 시작돼 푼 점수가 사라진다. 처음에는 분류 하나만 막았고 나머지는
 * 말없이 점수를 버렸다. **넷을 한꺼번에 본다** - 하나만 보면 같은 일이 다른
 * 출구에서 되풀이된다.
 *
 * 창은 실제로 그려서 본다. 어떤 클릭에 묻는지는 quiz-progress.test 가,
 * 출구가 실제로 클릭을 막는지는 leave-exits.test 가 실행해 본다. 여기서는
 * 두 화면이 출구 넷을 다 켰는지만 원문으로 본다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { LeaveConfirm } from "./LeaveConfirm";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (...parts: string[]) =>
  readFileSync(join(HERE, ...parts), "utf8").replace(/\r\n/g, "\n");

const render = (note?: string) =>
  renderToStaticMarkup(
    createElement(LeaveConfirm, {
      openRef: { current: null },
      title: "지금 판을 끝낼까요?",
      detail: "지금까지 푼 2문제가 사라집니다.",
      note,
      confirmLabel: "분류 바꾸기",
      onConfirm: () => {},
    }),
  );

describe("확인 창", () => {
  const html = render();

  it("브라우저 대화상자로 그리고 제목·설명을 잇는다", () => {
    // 포커스 가둠·Esc·낭독을 브라우저가 해준다. div 로 만들면 새어 나간다.
    assert.match(html, /<dialog/);
    const labelled = html.match(/aria-labelledby="([^"]+)"/)?.[1];
    const described = html.match(/aria-describedby="([^"]+)"/)?.[1];
    assert.ok(labelled && html.includes(`id="${labelled}"`), "제목이 안 이어졌다");
    assert.ok(described && html.includes(`id="${described}"`), "설명이 안 이어졌다");
  });

  it("잃는 것과 두 갈래를 보여준다", () => {
    assert.match(html, /2문제가 사라/);
    assert.match(html, /계속 풀기/);
    assert.match(html, /분류 바꾸기/);
  });

  it("되돌아가는 쪽이 먼저 온다", () => {
    // 실수로 연 사람이 대부분이라 손가락이 먼저 닿는 자리에 그쪽이 있어야 한다.
    assert.ok(html.indexOf("계속 풀기") < html.indexOf("분류 바꾸기"));
  });

  it("덧붙일 말이 있으면 설명 뒤에 그린다", () => {
    const withNote = render("시간은 흐릅니다");
    assert.ok(withNote.indexOf("2문제가 사라") < withNote.indexOf("시간은 흐릅니다"));
  });
});

describe("문제풀기 두 화면이 네 출구를 다 켠다", () => {
  for (const page of ["words", "sentences"]) {
    it(page, () => {
      const code = read("..", "app", "test", page, "page.tsx");
      assert.match(code, /<ContentTabs[^>]*warnOnLeave/, "탭");
      assert.match(code, /<ExitGuard[^>]*confirmWhenSolved/, "홈");
      assert.match(code, /<LeaveLink[\s\S]*?href=\{routes\.testRound\}/, "한 판 풀기");
      // 분류 고르개는 켜고 끄는 값 없이 늘 확인을 거친다.
    });
  }
});
