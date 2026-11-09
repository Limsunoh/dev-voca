/**
 * 제출에 실패했을 때 입력 중인 칸의 초점을 뺏지 않는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 효과는 서버 렌더에서 안 돌아서 react 를 대역으로 바꿔 직접 부른다.
 */
import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";

let effects: Array<() => void> = [];

mock.module("react", {
  namedExports: {
    useRef: (current: unknown) => ({ current }),
    useEffect: (run: () => void) => void effects.push(run),
  },
});

const { useFocusOnError } = await import("./useFocusOnError");

const realDocument = (globalThis as { document?: unknown }).document;
afterEach(() => {
  effects = [];
  (globalThis as { document?: unknown }).document = realDocument;
});

let selector = "";

function useScenario(typing: boolean, state: { error?: string }) {
  (globalThis as { document?: unknown }).document = {
    activeElement: {
      matches: (asked: string) => {
        selector = asked;
        return typing;
      },
    },
  };
  const focus = mock.fn();
  const scrollIntoView = mock.fn();
  const ref = useFocusOnError(state) as unknown as { current: unknown };
  ref.current = { focus, scrollIntoView };
  for (const effect of effects) effect();
  return { focus: focus.mock.callCount(), scroll: scrollIntoView.mock.callCount() };
}

describe("useFocusOnError", () => {
  it("입력칸에 초점이 있으면 뺏지 않고 문구만 화면으로 가져온다", () => {
    assert.deepEqual(useScenario(true, { error: "틀렸습니다." }), { focus: 0, scroll: 1 });
  });

  it("입력칸 밖이면 문구로 초점을 옮긴다", () => {
    assert.deepEqual(useScenario(false, { error: "틀렸습니다." }), { focus: 1, scroll: 0 });
  });

  it("라디오·체크박스·파일 칸은 글자를 치는 칸으로 보지 않는다", () => {
    useScenario(true, { error: "틀렸습니다." });

    for (const kind of ["radio", "checkbox", "file"]) {
      assert.match(selector, new RegExp(`:not\\([^)]*type=${kind}`));
    }
  });

  it("오류가 없으면 아무것도 안 한다", () => {
    assert.deepEqual(useScenario(false, {}), { focus: 0, scroll: 0 });
  });
});
