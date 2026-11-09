/**
 * 마이크 소개 카드가 상태마다 맞는 안내와 버튼을 내는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 잡으려는 결함은 이렇다.
 *
 *   막힌 상태에서 권한을 다시 물음   브라우저가 안 묻는 상태라 버튼이 아무 일도 안 한다
 *   물어볼 상태에서 새로고침함       권한 창이 영영 안 뜨고 화면만 깜빡인다
 *   고칠 수 없는 상태에 버튼이 있음  눌러도 달라지는 것이 없다
 *   고지가 빠짐                      음성이 어디로 가는지 모르고 마이크를 켠다
 *   여는 동안 안 잠김                두 번 눌러 권한 요청이 겹친다
 *   소개가 "단어" 로 돌아감          문장·대화도 읽는 화면인데 단어만 읽는 줄 안다
 *
 * MicGate 는 훅이 없어 함수로 바로 불러 트리를 읽고, 버튼의 onClick 을 진짜로
 * 부른다. 글자는 서버 렌더 결과로 한 번 더 본다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { afterEach, beforeEach, describe, it, mock } from "node:test";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { MicState } from "@/lib/speech";

import { MicGate } from "./MicGate";

const SOURCE = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "MicGate.tsx"),
  "utf8",
);

type Case = {
  state: MicState;
  title: string;
  action: string | null;
  privacy: boolean;
};

const CASES: Case[] = [
  { state: "prompt", title: "소리내어 읽어봅니다", action: "마이크 켜기", privacy: true },
  { state: "granted", title: "소리내어 읽어봅니다", action: "시작하기", privacy: true },
  { state: "denied", title: "마이크가 막혀 있습니다", action: "새로고침", privacy: false },
  { state: "no-device", title: "마이크를 찾지 못했습니다", action: "새로고침", privacy: false },
  { state: "insecure", title: "안전한 연결에서만 됩니다", action: null, privacy: false },
  { state: "unsupported", title: "이 브라우저에서는 아직 안 됩니다", action: null, privacy: false },
];

const WITH_BUTTON = CASES.filter((c) => c.action !== null);
const ASKS: MicState[] = ["prompt", "granted"];
const RELOADS: MicState[] = ["denied", "no-device"];
const DEAD_ENDS: MicState[] = ["insecure", "unsupported"];
const PRIVACY_MARK = "브라우저가 글자로 바꿉니다";

/* ---- 트리 읽기 ---- */

type El = { type: unknown; props: Record<string, unknown> };

const isElement = (node: unknown): node is El =>
  typeof node === "object" && node !== null && "type" in node && "props" in node;

function flatten(node: unknown, out: El[] = []): El[] {
  if (Array.isArray(node)) {
    for (const child of node) flatten(child, out);
  } else if (isElement(node)) {
    out.push(node);
    flatten(node.props.children, out);
  }
  return out;
}

function textOf(node: unknown): string {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(textOf).join("");
  return isElement(node) ? textOf(node.props.children) : "";
}

function gate(state: MicState, pending = false, onAllow: () => void = () => {}) {
  const all = flatten(MicGate({ state, onAllow, pending }));
  const byType = (type: string) => all.filter((el) => el.type === type);
  return {
    all,
    headings: byType("h2"),
    paragraphs: byType("p"),
    buttons: byType("button"),
    body: textOf(byType("p")[0]),
  };
}

const html = (state: MicState, pending = false) =>
  renderToStaticMarkup(createElement(MicGate, { state, onAllow: () => {}, pending }));

const click = (button: El) => (button.props.onClick as () => void)();

/* ---- window 대역 ---- */

type G = { window?: unknown };
const realWindow = (globalThis as G).window;

function fakeWindow() {
  const location = { reload: mock.fn() };
  (globalThis as G).window = { location };
  return location;
}

afterEach(() => {
  (globalThis as G).window = realWindow;
});

describe("상태마다 제목·버튼·고지가 맞다", () => {
  for (const c of CASES) {
    describe(c.state, () => {
      it("제목", () => {
        const { headings } = gate(c.state);
        assert.equal(headings.length, 1);
        assert.equal(textOf(headings[0]), c.title);
      });

      it(c.action ? `버튼은 "${c.action}" 하나` : "버튼이 없다", () => {
        const { buttons } = gate(c.state);
        assert.deepEqual(buttons.map(textOf), c.action ? [c.action] : []);
      });

      it(c.privacy ? "음성 고지가 있다" : "음성 고지가 없다", () => {
        const { paragraphs } = gate(c.state);
        assert.equal(paragraphs.length, c.privacy ? 2 : 1);
        assert.equal(html(c.state).includes(PRIVACY_MARK), c.privacy);
      });
    });
  }

  for (const state of ASKS) {
    it(`${state}: 고지는 버튼 바로 앞에 온다`, () => {
      // 누르기 직전에 읽혀야 알고 누르는 것이 된다.
      const rendered = html(state);
      const notice = rendered.indexOf(PRIVACY_MARK);
      const button = rendered.indexOf("<button");
      assert.ok(notice !== -1 && button !== -1 && notice < button);
      assert.equal(rendered.indexOf("<p", notice), -1, "고지와 버튼 사이에 다른 문단이 끼었다");
    });
  }

  for (const c of WITH_BUTTON) {
    it(`${c.state}: 폼 안에서도 제출되지 않는 버튼이다`, () => {
      assert.equal(gate(c.state).buttons[0].props.type, "button");
    });
  }
});

describe("버튼을 누르면", () => {
  for (const state of RELOADS) {
    describe(state, () => {
      it("새로고침만 하고 권한을 다시 묻지 않는다", () => {
        const location = fakeWindow();
        const onAllow = mock.fn();
        const { buttons } = gate(state, false, onAllow);

        click(buttons[0]);

        assert.equal(location.reload.mock.callCount(), 1);
        assert.equal(onAllow.mock.callCount(), 0);
      });

      it("location 에 붙여 부른다", () => {
        // 떼어 내 넘기면 브라우저에서 Illegal invocation 으로 터진다.
        const location = fakeWindow();
        click(gate(state).buttons[0]);
        assert.equal(location.reload.mock.calls[0].this, location);
      });

      it("그리는 것만으로는 새로고침하지 않는다", () => {
        const location = fakeWindow();
        gate(state);
        html(state);
        assert.equal(location.reload.mock.callCount(), 0);
      });

      it("안내문이 버튼과 같은 말로 시킨다", () => {
        assert.match(gate(state).body, /새로고침/);
      });
    });
  }

  for (const state of ASKS) {
    it(`${state}: 권한을 묻고 새로고침하지 않는다`, () => {
      const location = fakeWindow();
      const onAllow = mock.fn();
      const { buttons } = gate(state, false, onAllow);

      click(buttons[0]);

      assert.equal(onAllow.mock.callCount(), 1);
      assert.equal(location.reload.mock.callCount(), 0);
    });
  }

  for (const state of DEAD_ENDS) {
    it(`${state}: 누를 것이 없어 아무것도 불리지 않는다`, () => {
      const location = fakeWindow();
      const onAllow = mock.fn();
      const { all } = gate(state, false, onAllow);

      assert.equal(all.filter((el) => typeof el.props.onClick === "function").length, 0);
      assert.equal(onAllow.mock.callCount(), 0);
      assert.equal(location.reload.mock.callCount(), 0);
    });
  }
});

describe("서버에서 그릴 때", () => {
  beforeEach(() => {
    (globalThis as G).window = undefined;
  });

  for (const { state } of CASES) {
    it(`${state}: window 가 없어도 터지지 않는다`, () => {
      assert.doesNotThrow(() => html(state));
    });
  }

  for (const state of RELOADS) {
    it(`${state}: window 는 누르는 순간에 읽는다`, () => {
      const { buttons } = gate(state);
      const location = fakeWindow();
      click(buttons[0]);
      assert.equal(location.reload.mock.callCount(), 1);
    });
  }
});

describe("여는 중", () => {
  for (const c of WITH_BUTTON) {
    describe(c.state, () => {
      it("잠기고 이름이 바뀐다", () => {
        const { buttons } = gate(c.state, true);
        assert.equal(buttons.length, 1);
        assert.equal(buttons[0].props.disabled, true);
        assert.equal(textOf(buttons[0]), "여는 중");
        assert.match(html(c.state, true), /<button[^>]* disabled=""/);
      });

      it("아닐 때는 안 잠긴다", () => {
        assert.equal(gate(c.state, false).buttons[0].props.disabled, false);
        assert.doesNotMatch(html(c.state, false), /<button[^>]* disabled=""/);
        assert.doesNotMatch(html(c.state, false), /여는 중/);
      });
    });
  }

  for (const state of DEAD_ENDS) {
    it(`${state}: 버튼이 없으니 여는 중도 안 뜬다`, () => {
      assert.doesNotMatch(html(state, true), /여는 중/);
      assert.doesNotMatch(html(state, true), /<button/);
    });
  }
});

describe("문구", () => {
  for (const state of ASKS) {
    it(`${state}: 소개가 "단어" 가 아니라 "말" 이다`, () => {
      // 고지 문단의 "말한 내용" 에 속지 않게 소개 문단만 본다.
      const { body } = gate(state);
      assert.match(body, /화면에 뜨는 말을 소리내어 읽으면/);
      assert.doesNotMatch(body, /단어/);
    });
  }

  for (const { state } of CASES) {
    it(`${state}: 화면 어디에도 "단어" 가 없다`, () => {
      assert.doesNotMatch(html(state), /단어/);
    });

    it(`${state}: 화면에 이모지가 없다`, () => {
      assert.doesNotMatch(html(state), /\p{Extended_Pictographic}/u);
      assert.doesNotMatch(html(state, true), /\p{Extended_Pictographic}/u);
    });
  }

  it("원문 전체에 이모지가 없다", () => {
    assert.doesNotMatch(SOURCE, /\p{Extended_Pictographic}/u);
  });
});
