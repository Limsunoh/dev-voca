/**
 * 소리 듣기 버튼(SpeakButton)과 상세 히어로에 놓이는 자리.
 *
 * 실행: cd frontend && npm test
 *
 * 폰에 들어 있는 음성(speechSynthesis)으로 읽는다(2026-11-12 사용자 결정). 지키려는
 * 것은 넷이다.
 *
 *   - 미국 영어를 먼저 고르고, 없으면 다른 영어, 영어가 없으면 버튼을 숨긴다.
 *     음성은 넘기지 않고 언어만 넘긴다(맥·iOS 의 장난 음성을 피하려고)
 *   - 누르면 앞서 읽던 것을 끊고 처음부터, 조금 천천히(0.9) 읽는다
 *   - 다른 화면으로 가면 읽던 것을 멈춘다
 *   - 단어는 발음기호 줄 오른쪽, 문장은 제목 아래에 버튼이 선다
 *
 * 서버 렌더로는 누를 수 없어서 react 의 useState·useRef·useEffect 를 대역으로 바꾸고,
 * 브라우저의 speechSynthesis 도 가짜를 넣는다(detail-head.test.mts 와 같은 방식).
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it, mock } from "node:test";
import type { ReactElement } from "react";

const realReact = await import("react");

/** 상태 칸들. 그릴 때마다 처음 칸부터 다시 센다. */
let slots: { value: unknown }[] = [];
let cursor = 0;
/** 효과가 돌려준 정리 함수들. */
let cleanups: (() => void)[] = [];
/** 효과는 첫 그리기에서 한 번만 돈다. */
let ranEffect = false;

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useState<T>(init: T) {
      const at = cursor++;
      if (!slots[at]) slots[at] = { value: init };
      const s = slots[at];
      const set = (next: T) => {
        s.value = next;
      };
      return [s.value as T, set];
    },
    useRef<T>(init: T) {
      const at = cursor++;
      if (!slots[at]) slots[at] = { value: { current: init } };
      return slots[at].value as { current: T };
    },
    // 효과는 첫 그리기에서 한 번만 바로 돌린다.
    useEffect(run: () => void | (() => void)) {
      if (ranEffect) return;
      ranEffect = true;
      const cleanup = run();
      if (typeof cleanup === "function") cleanups.push(cleanup);
    },
  },
});

// ---- 가짜 speechSynthesis --------------------------------------------------

type Voice = { lang: string };

class FakeUtterance {
  voice: Voice | null = null;
  lang = "";
  rate = 1;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(readonly text: string) {}
}

let voices: Voice[] = [];
let calls: string[] = [];
let spoken: FakeUtterance[] = [];
let listeners: (() => void)[] = [];

const synth = {
  /** 지금 읽는 중인가. 진짜처럼 cancel 은 끄고 speak 는 켠다. */
  speaking: false,
  pending: false,
  getVoices: () => voices,
  cancel: () => {
    calls.push("cancel");
    synth.speaking = false;
  },
  speak: (u: FakeUtterance) => {
    calls.push("speak");
    spoken.push(u);
    synth.speaking = true;
  },
  addEventListener: (_: string, fn: () => void) => listeners.push(fn),
  removeEventListener: (_: string, fn: () => void) => {
    listeners = listeners.filter((one) => one !== fn);
  },
};

/** 시간 대역: 미뤄 둔 함수를 손으로 돌린다. */
let timers: { fn: () => void; ms: number }[] = [];

Object.assign(globalThis, {
  window: {
    speechSynthesis: synth,
    setTimeout: (fn: () => void, ms: number) => timers.push({ fn, ms }),
    clearTimeout: () => {},
  },
  SpeechSynthesisUtterance: FakeUtterance,
});

const { createElement } = realReact;
const { renderToStaticMarkup } = await import("react-dom/server");
const { SpeakButton, pickEnglishVoice } = await import("./SpeakButton");

beforeEach(() => {
  slots = [];
  cursor = 0;
  cleanups = [];
  ranEffect = false;
  voices = [];
  calls = [];
  spoken = [];
  listeners = [];
  timers = [];
  synth.speaking = false;
});

/** 컴포넌트를 한 번 그린다. 훅 자리를 처음부터 센다. */
function draw(): ReactElement | null {
  cursor = 0;
  return SpeakButton({ text: "slow query", label: "발음 듣기" }) as ReactElement | null;
}

/** 0ms 로 미룬 것을 돌린다(첫 확인). */
const runSoon = () => timers.filter((t) => t.ms === 0).forEach((t) => t.fn());
/** 오래 기다린 뒤의 확인을 돌린다(음성이 끝내 안 온 경우). */
const runLate = () => timers.filter((t) => t.ms > 0).forEach((t) => t.fn());

function button(tree: ReactElement | null): ReactElement<{ onClick: () => void }> {
  assert.ok(tree && (tree as ReactElement).type === "button", "버튼이 없다");
  return tree as ReactElement<{ onClick: () => void }>;
}

describe("pickEnglishVoice", () => {
  const v = (lang: string) => ({ lang });

  it("미국 영어를 먼저 고른다", () => {
    assert.equal(pickEnglishVoice([v("en-GB"), v("ko-KR"), v("en-US")])?.lang, "en-US");
  });

  it("기기마다 다른 표기(en_US, en-us)도 미국 영어로 본다", () => {
    assert.equal(pickEnglishVoice([v("en-GB"), v("en_US")])?.lang, "en_US");
    assert.equal(pickEnglishVoice([v("en-GB"), v("en-us")])?.lang, "en-us");
  });

  it("미국 영어가 없으면 다른 영어", () => {
    assert.equal(pickEnglishVoice([v("ko-KR"), v("en-GB")])?.lang, "en-GB");
  });

  it("영어가 없으면 null", () => {
    assert.equal(pickEnglishVoice([v("ko-KR"), v("ja-JP")]), null);
    assert.equal(pickEnglishVoice([]), null);
  });
});

describe("처음 그릴 때", () => {
  it("버튼을 그려 둔다 - 음성이 있는 대부분의 기기에서 늦게 나타나며 글을 밀지 않게", () => {
    const html = renderToStaticMarkup(draw()!);
    assert.match(html, /<button type="button" aria-label="발음 듣기"/);
    assert.match(html, /<svg aria-hidden="true"/);
    assert.match(html, /size-11/, "누르는 자리는 44px");
  });
});

describe("영어 음성이 있는지 확인", () => {
  it("영어 음성이 있으면 그대로 보인다", () => {
    voices = [{ lang: "ko-KR" }, { lang: "en-US" }];
    draw();
    runSoon();
    runLate();
    assert.ok(draw());
  });

  it("음성은 있는데 영어가 없으면 숨긴다", () => {
    voices = [{ lang: "ko-KR" }];
    draw();
    runSoon();
    assert.equal(draw(), null);
  });

  it("목록이 늦게 오면(voiceschanged) 그때 다시 본다", () => {
    draw();
    runSoon(); // 아직 빈 목록이라 판단하지 않는다
    assert.ok(draw());
    voices = [{ lang: "ko-KR" }];
    listeners.forEach((fn) => fn());
    assert.equal(draw(), null);
  });

  it("끝내 목록이 안 오면 음성이 없는 기기로 보고 숨긴다", () => {
    draw();
    runSoon();
    runLate();
    assert.equal(draw(), null);
  });
});

describe("누르면", () => {
  beforeEach(() => {
    voices = [{ lang: "en-GB" }, { lang: "en-US" }];
  });

  it("앞서 읽던 것을 끊고 미국 영어로, 0.9 빠르기로 읽는다", () => {
    button(draw()).props.onClick();
    assert.deepEqual(calls, ["cancel", "speak"]);
    const u = spoken[0];
    assert.equal(u.text, "slow query");
    assert.equal(u.lang, "en-US");
    assert.equal(u.voice, null, "음성은 기기 기본에 맡긴다");
    assert.equal(u.rate, 0.9);
  });

  it("언어 표기가 en_US 로 와도 en-US 로 넘긴다", () => {
    voices = [{ lang: "en_US" }];
    button(draw()).props.onClick();
    assert.equal(spoken[0].lang, "en-US");
  });

  it("읽는 동안은 갈색, 다 읽으면 원래 색으로 돌아온다", () => {
    button(draw()).props.onClick();
    assert.match(renderToStaticMarkup(draw()!), /background:var\(--brand\)/);
    spoken[0].onend!();
    assert.match(renderToStaticMarkup(draw()!), /background:var\(--background-deep\)/);
  });

  it("읽는 중에 다시 누르면, 끊긴 앞 문장의 늦은 알림이 와도 갈색을 지킨다", () => {
    button(draw()).props.onClick();
    button(draw()).props.onClick();
    assert.deepEqual(calls, ["cancel", "speak", "cancel", "speak"]);
    // 크롬은 끊긴 앞 문장의 error("interrupted")를 새 문장을 읽기 시작한 뒤에 보낸다.
    spoken[0].onerror!();
    assert.match(renderToStaticMarkup(draw()!), /background:var\(--brand\)/);
    spoken[1].onend!();
    assert.match(renderToStaticMarkup(draw()!), /background:var\(--background-deep\)/);
  });

  it("다시 누른 새 문장을 브라우저가 버려 아무것도 안 읽으면, 앞 문장 알림에 원래 색으로 돌아온다", () => {
    button(draw()).props.onClick();
    button(draw()).props.onClick();
    // 일부 크롬은 cancel() 직후의 speak() 를 버린다. 새 문장에서는 알림이 안 온다.
    synth.speaking = false;
    spoken[0].onerror!();
    assert.match(renderToStaticMarkup(draw()!), /background:var\(--background-deep\)/);
  });

  it("읽다가 오류가 나도 원래 색으로 돌아온다", () => {
    button(draw()).props.onClick();
    spoken[0].onerror!();
    assert.match(renderToStaticMarkup(draw()!), /background:var\(--background-deep\)/);
  });

  it("누른 순간 영어 음성이 사라졌으면 읽지 않고 숨긴다", () => {
    const tree = draw();
    voices = [];
    button(tree).props.onClick();
    assert.deepEqual(calls, []);
    assert.equal(draw(), null);
  });
});

describe("옛 사파리(speechSynthesis 에 addEventListener 가 없음)", () => {
  it("알림을 못 받는 사이 영어 없는 목록이 왔으면 1.5초 확인에서 숨긴다", () => {
    const { addEventListener, removeEventListener } = synth;
    Object.assign(synth, { addEventListener: undefined, removeEventListener: undefined });
    try {
      draw();
      runSoon(); // 아직 빈 목록
      voices = [{ lang: "ko-KR" }];
      runLate();
      assert.equal(draw(), null);
    } finally {
      Object.assign(synth, { addEventListener, removeEventListener });
    }
  });

  it("터지지 않고, 목록을 바로 받아 판단한다", () => {
    const { addEventListener, removeEventListener } = synth;
    Object.assign(synth, { addEventListener: undefined, removeEventListener: undefined });
    try {
      voices = [{ lang: "ko-KR" }];
      draw();
      runSoon();
      assert.equal(draw(), null);
      cleanups.forEach((fn) => fn());
    } finally {
      Object.assign(synth, { addEventListener, removeEventListener });
    }
  });
});

describe("다른 화면으로 가면", () => {
  it("읽던 것을 멈추고 음성 목록 듣기를 그만둔다", () => {
    voices = [{ lang: "en-US" }];
    draw();
    assert.equal(listeners.length, 1);
    cleanups.forEach((fn) => fn());
    assert.ok(calls.includes("cancel"));
    assert.equal(listeners.length, 0);
  });
});

// ---- 상세 히어로에 놓이는 자리 ------------------------------------------------

const { DetailHero } = await import("./DetailLayout");

/** 히어로를 그린다. 안의 SpeakButton 도 대역 훅으로 그려진다. */
function hero(props: { aside?: string; speak?: { text: string; label: string } }): string {
  cursor = 0;
  ranEffect = true; // 히어로 안의 버튼은 효과를 돌리지 않고 첫 모양만 본다
  return renderToStaticMarkup(
    createElement(DetailHero, { title: "slow query", meaning: "느린 쿼리", ...props }),
  );
}

describe("상세 히어로", () => {
  it("단어: 발음기호 줄 오른쪽에 버튼이 선다(같은 줄, 발음기호가 먼저)", () => {
    const html = hero({ aside: "/ˈsloʊ ˌkwɪri/", speak: { text: "slow query", label: "발음 듣기" } });
    const row = html.match(/<div class="([^"]*flex-wrap[^"]*)">([\s\S]*?)<\/div>/);
    assert.ok(row, html);
    assert.ok(row[2].indexOf('lang="en-US"') < row[2].indexOf("<button"), row[2]);
    assert.ok(html.indexOf("<h1") < html.indexOf("<button"), "버튼이 제목 아래에 있어야 한다");
  });

  it("문장: 발음기호가 없어도 제목 아래에 버튼만 선다", () => {
    const html = hero({ speak: { text: "slow query", label: "문장 듣기" } });
    // 영어 음성이 없어 버튼이 숨으면 빈 줄을 접는다.
    assert.match(html, /<div class="[^"]*empty:hidden[^"]*">/);
    assert.match(html, /aria-label="문장 듣기"/);
    assert.doesNotMatch(html, /lang="en-US"/);
    assert.ok(html.indexOf("<h1") < html.indexOf("<button"));
  });

  it("speak 를 안 넘기면 버튼이 없다(발음기호만)", () => {
    const html = hero({ aside: "/ˈsloʊ/" });
    assert.doesNotMatch(html, /<button/);
    assert.match(html, /lang="en-US"/);
  });
});
