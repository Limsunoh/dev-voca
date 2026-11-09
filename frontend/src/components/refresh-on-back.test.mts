/**
 * 뒤로 가기로 돌아왔을 때 옛 서버 응답으로 화면을 그리지 않는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 같은 renderId 로 다시 마운트되는 것이 뒤로 가기다. 링크로 들어오면 서버가 새로
 * 그려 다른 번호가 온다. react 대역은 consent-gate.test.mts 와 같은 방식이다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { beforeEach, describe, it, mock } from "node:test";
import type { ReactElement } from "react";

const require = createRequire(import.meta.url);
const realReact = require("react") as typeof import("react");

let slots: Array<{ value: unknown }> = [];
let cursor = 0;
let effects: Array<() => void> = [];
const refresh = mock.fn();
const router = { refresh };

mock.module("react", {
  defaultExport: realReact,
  namedExports: {
    ...realReact,
    useState: <T,>(init: T | (() => T)) => {
      const i = cursor++;
      slots[i] ??= { value: typeof init === "function" ? (init as () => T)() : init };
      const slot = slots[i] as { value: T };
      return [slot.value, (next: T) => void (slot.value = next)] as const;
    },
    // 의존성이 바뀔 때만 돈다. 무시하면 [renderId] 를 [] 로 바꿔도 통과한다.
    useEffect: (fn: () => void, deps?: unknown[]) => {
      const i = cursor++;
      const prev = slots[i]?.value as unknown[] | undefined;
      slots[i] = { value: deps };
      if (!deps || !prev || deps.some((dep, k) => dep !== prev[k])) effects.push(fn);
    },
    startTransition: (fn: () => void) => fn(),
  },
});

mock.module("next/navigation", {
  namedExports: { useRouter: () => router },
});

const { RefreshOnBack } = await import("./RefreshOnBack");

const BOARD = "board";
let nextId = 0;
const newId = () => `render-${++nextId}`;

function draw(renderId: string) {
  cursor = 0;
  effects = [];
  return RefreshOnBack({ renderId, children: BOARD }) as ReactElement | string;
}

/** 화면에 새로 들어온 것처럼 그리고 effect 를 돌린다. */
function enter(renderId: string) {
  slots = [];
  const first = draw(renderId);
  for (const run of effects) run();
  return first;
}

beforeEach(() => refresh.mock.resetCalls());

describe("RefreshOnBack", () => {
  it("처음 보는 응답이면 바로 그리고 서버에 다시 묻지 않는다", () => {
    assert.equal(enter(newId()), BOARD);
    assert.equal(refresh.mock.callCount(), 0);
  });

  it("같은 응답으로 다시 들어오면 그리지 않고 새로 받는다", () => {
    const id = newId();
    enter(id);

    const first = enter(id);

    assert.notEqual(first, BOARD);
    assert.equal((first as ReactElement<{ role: string }>).props.role, "status");
    assert.equal(refresh.mock.callCount(), 1);
    assert.equal(draw(newId()), BOARD);
  });

  it("다른 화면에서 뒤로 간 뒤라도 링크로 들어오면 다시 묻지 않는다", () => {
    const old = newId();
    enter(old);
    enter(old);
    refresh.mock.resetCalls();

    assert.equal(enter(newId()), BOARD);
    assert.equal(refresh.mock.callCount(), 0);
  });

  it("새로 받은 응답도 기억해서 두 번째 뒤로 가기를 놓치지 않는다", () => {
    const old = newId();
    enter(old);
    enter(old);
    const fresh = newId();
    draw(fresh);
    for (const run of effects) run();
    refresh.mock.resetCalls();

    assert.notEqual(enter(fresh), BOARD);
    assert.equal(refresh.mock.callCount(), 1);
  });

  it("일일공부 화면은 그릴 때마다 새 번호를 준다", () => {
    const page = readFileSync(new URL("../app/test/daily/page.tsx", import.meta.url), "utf8");

    assert.match(page, /<RefreshOnBack renderId=\{crypto\.randomUUID\(\)\}>/);
  });
});
