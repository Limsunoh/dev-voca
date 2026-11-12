/**
 * 소리 듣기 버튼(SpeakButton)을 브라우저 음성의 나쁜 경우들에 놓고 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 지키는 것:
 * - 서버 마크업과 클라이언트 첫 그림이 같다(버튼을 그려 둔다). 음성이 없는
 *   기기여도 첫 그림은 버튼이고, 숨기는 것은 효과가 돈 뒤다.
 * - 영어 음성 판정. en-US 우선, en_US·en-us 도 같은 것, 없으면 en-GB 같은 다른
 *   영어. 영어가 없으면 숨김. 목록이 비면 voiceschanged 를 기다리고 1.5초에 숨김.
 *   voiceschanged 가 여러 번 와서 영어가 생겼다 없어지면 그대로 따라간다.
 * - 누르면 cancel() 다음 speak(). utterance 에 voice 는 안 넣고 lang(밑줄은
 *   하이픈으로)과 rate 0.9 만 넣는다.
 * - 읽는 동안만 갈색. 연타로 끊긴 앞 문장의 늦은 알림이 순서 뒤섞여 와도 지금
 *   문장의 갈색을 끄지 않는다.
 * - speechSynthesis 가 없거나 addEventListener 가 없는 옛 사파리에서 터지지 않는다.
 * - 화면을 떠나면 리스너를 떼고 타이머를 지우고 cancel() 한다. StrictMode 처럼
 *   효과가 두 번 돌아도 리스너가 쌓이지 않는다.
 * - 상세 히어로: 발음기호 옆에 버튼이 서고, 버튼이 숨고 발음기호도 없으면 감싼
 *   줄이 완전히 빈 div 가 되어 empty:hidden 으로 접힌다.
 *
 * 하네스: 컴포넌트 함수를 직접 부르고 useState/useRef/useEffect 를 칸 배열
 * 대역으로 돌린다(direct). 시계(setTimeout)와 speechSynthesis 도 대역이다.
 * 마크업을 볼 때(renderToStaticMarkup)는 진짜 훅을 쓴다.
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it, mock } from "node:test";
import type { ReactElement } from "react";

const realReact = await import("react");

/**
 * real   진짜 훅
 * direct 칸 배열 대역(효과는 손으로 돌린다)
 * hidden 마크업을 그리되 SpeakButton 의 "쓸 수 있나" 를 false 로 시작(숨은 상태)
 */
let mode: "real" | "direct" | "hidden" = "real";
let cells: unknown[] = [];
let cursor = 0;
let effects: Array<() => void | (() => void)> = [];
let cleanups: Array<() => void> = [];
/** 마운트 때 돈 효과들. StrictMode 흉내에서 다시 돌린다. */
let mountedEffects: Array<() => void | (() => void)> = [];
let unmounted = false;
let setsAfterUnmount = 0;

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useState<T>(init: T) {
      if (mode === "hidden" && init === true) return [false, () => {}];
      if (mode !== "direct") return realReact.useState(init);
      const i = cursor++;
      if (!(i in cells)) cells[i] = init;
      const set = (next: T | ((prev: T) => T)) => {
        if (unmounted) setsAfterUnmount++;
        cells[i] =
          typeof next === "function" ? (next as (prev: T) => T)(cells[i] as T) : next;
      };
      return [cells[i] as T, set];
    },
    useRef<T>(init: T) {
      if (mode !== "direct") return realReact.useRef(init);
      const i = cursor++;
      if (!(i in cells)) cells[i] = { current: init };
      return cells[i];
    },
    useEffect(fn: () => void | (() => void), deps?: unknown[]) {
      if (mode !== "direct") return realReact.useEffect(fn, deps);
      const i = cursor++;
      if (!(i in cells)) {
        cells[i] = true;
        effects.push(fn);
      }
    },
  },
});

mock.module("next/navigation", {
  namedExports: {
    notFound: () => {
      throw new Error("notFound");
    },
    redirect: (to: string) => {
      throw new Error(`redirect ${to}`);
    },
    useRouter: () => ({ back() {}, push() {}, replace() {}, prefetch() {} }),
  },
});

const { createElement } = realReact;

mock.module("next/link", {
  defaultExport: ({ href, children }: { href: string; children?: never }) =>
    createElement("a", { href }, children),
});

mock.module("@/lib/api/vocab", {
  namedExports: {
    HOME_WORDS: 7,
    getDailyWords: async () => [],
    getWord: async (id: string) => ({
      id: Number(id),
      term: "slow query",
      pronunciation: id === "1" ? "/ˈsloʊ ˌkwɪri/" : "",
      reading: "",
      reading_note: "",
      meaning: "느린 쿼리",
      category: "database",
      category_label: "데이터베이스",
      difficulty: 1,
      difficulty_label: "쉬움",
      is_exam: false,
      exam_subject: "",
      exam_subject_label: "",
      description: "설명 본문",
      example: "",
      example_translation: "",
      aliases: "",
    }),
  },
});

mock.module("@/lib/api/sentences", {
  namedExports: {
    // id 9 는 에러 메시지 문장, 나머지는 실무 표현.
    getSentence: async (id: string) => ({
      id: Number(id),
      text: "Could you take a look at this PR?",
      reading: "",
      translation: "이 PR 좀 봐 줄래요?",
      kind: id === "9" ? "error" : "expression",
      kind_label: id === "9" ? "에러 메시지" : "실무 표현",
      category: "collab",
      category_label: "협업",
      difficulty: 1,
      difficulty_label: "쉬움",
      context: "",
      description: "",
    }),
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { SpeakButton } = await import("./SpeakButton");
const { DetailHero } = await import("./DetailLayout");
const { default: WordDetailPage } = await import("../app/learn/words/[id]/page");
const { default: SentenceDetailPage } = await import(
  "../app/learn/sentences/[id]/page"
);

/* ---------- 시계 대역 ---------- */

let now = 0;
let nextTimer = 1;
const timers = new Map<number, { at: number; fn: () => void }>();

function setTimeoutFake(fn: () => void, ms = 0): number {
  const id = nextTimer++;
  timers.set(id, { at: now + ms, fn });
  return id;
}
function clearTimeoutFake(id: number) {
  timers.delete(id);
}
/** ms 만큼 시계를 돌리며 그 사이 타이머를 시각 순으로 부른다. */
function advance(ms: number) {
  const target = now + ms;
  for (;;) {
    let hit: [number, { at: number; fn: () => void }] | null = null;
    for (const entry of timers) {
      if (entry[1].at <= target && (!hit || entry[1].at < hit[1].at)) hit = entry;
    }
    if (!hit) break;
    timers.delete(hit[0]);
    now = hit[1].at;
    hit[1].fn();
  }
  now = target;
}

/* ---------- speechSynthesis 대역 ---------- */

type Voice = { lang: string; name: string };
const voice = (lang: string): Voice => ({ lang, name: `v-${lang}` });

class FakeUtterance {
  text: string;
  lang = "";
  rate = 1;
  onend: ((e?: unknown) => void) | null = null;
  onerror: ((e?: unknown) => void) | null = null;
  voiceAssigned = false;
  private _voice: unknown = null;
  constructor(text: string) {
    this.text = text;
  }
  get voice() {
    return this._voice;
  }
  set voice(v: unknown) {
    this.voiceAssigned = true;
    this._voice = v;
  }
}

class FakeSynth {
  voices: Voice[] = [];
  listeners = new Set<() => void>();
  log: string[] = [];
  spoken: FakeUtterance[] = [];
  /** 지금 읽는 중인가. 진짜처럼 cancel 은 끄고 speak 는 켠다. */
  speaking = false;
  pending = false;
  getVoices() {
    return this.voices;
  }
  addEventListener(type: string, fn: () => void) {
    assert.equal(type, "voiceschanged");
    this.listeners.add(fn);
  }
  removeEventListener(type: string, fn: () => void) {
    assert.equal(type, "voiceschanged");
    this.listeners.delete(fn);
  }
  cancel() {
    this.log.push("cancel");
    this.speaking = false;
  }
  speak(u: FakeUtterance) {
    this.log.push(`speak:${u.text}`);
    this.spoken.push(u);
    this.speaking = true;
  }
  /** 목록을 바꾸고 voiceschanged 를 낸다. */
  change(voices: Voice[]) {
    this.voices = voices;
    for (const fn of [...this.listeners]) fn();
  }
}

/** addEventListener 가 없는 iOS 15 이하 사파리. */
class OldSafariSynth extends FakeSynth {}
Object.defineProperty(OldSafariSynth.prototype, "addEventListener", { value: undefined });
Object.defineProperty(OldSafariSynth.prototype, "removeEventListener", { value: undefined });

const g = globalThis as Record<string, unknown>;

function install(synth: FakeSynth | undefined) {
  g.window = {
    speechSynthesis: synth,
    setTimeout: setTimeoutFake,
    clearTimeout: clearTimeoutFake,
  };
  g.SpeechSynthesisUtterance = FakeUtterance;
}

/* ---------- 컴포넌트 대역 렌더 ---------- */

type Props = { text: string; label: string };
type ButtonEl = ReactElement<{
  onClick: () => void;
  style: { background: string; color: string };
  "aria-label": string;
}>;

let props: Props = { text: "slow query", label: "발음 듣기" };

function render(): ButtonEl | null {
  mode = "direct";
  cursor = 0;
  try {
    return SpeakButton(props) as ButtonEl | null;
  } finally {
    mode = "real";
  }
}
function runEffects() {
  const pending = effects;
  effects = [];
  mountedEffects.push(...pending);
  for (const fn of pending) {
    const c = fn();
    if (typeof c === "function") cleanups.push(c);
  }
}
/** 첫 그림을 돌려주고, 그 뒤 효과를 돌린다(React 의 마운트 순서). */
function mount(p: Partial<Props> = {}): ButtonEl | null {
  props = { ...props, ...p };
  const first = render();
  runEffects();
  return first;
}
function unmount() {
  for (const c of cleanups.splice(0)) c();
  unmounted = true;
}
/** 지금 그림의 버튼. 숨었으면 null. */
const view = () => render();
const shown = () => view() !== null;
const bg = () => view()!.props.style.background;
const tap = () => view()!.props.onClick();

const BRAND = "var(--brand)";
const REST = "var(--background-deep)";

beforeEach(() => {
  mode = "real";
  cells = [];
  cursor = 0;
  effects = [];
  cleanups = [];
  mountedEffects = [];
  unmounted = false;
  setsAfterUnmount = 0;
  now = 0;
  timers.clear();
  props = { text: "slow query", label: "발음 듣기" };
  delete g.window;
  delete g.SpeechSynthesisUtterance;
});

function synthWith(voices: Voice[], Kind = FakeSynth) {
  const synth = new Kind();
  synth.voices = voices;
  install(synth);
  return synth;
}

/* ---------- 시나리오 ---------- */

describe("첫 그림", () => {
  it("서버(window 없음)에서도 버튼을 그리고 쉬는 색이다", () => {
    const html = renderToStaticMarkup(
      createElement(SpeakButton, { text: "slow query", label: "발음 듣기" }),
    );
    assert.match(html, /^<button type="button"[^>]*aria-label="발음 듣기"/);
    assert.match(html, /background:var\(--background-deep\)/);
  });

  for (const [name, setup] of [
    ["speechSynthesis 가 없는 브라우저", () => install(undefined)],
    ["영어 음성이 없는 기기", () => synthWith([voice("ko-KR")])],
    ["목록이 아직 빈 크롬", () => synthWith([])],
  ] as const) {
    it(`${name}: 클라이언트 첫 그림이 서버 마크업과 같다`, () => {
      const server = renderToStaticMarkup(createElement(SpeakButton, props));
      setup();
      const first = mount();
      assert.ok(first, "첫 그림에서 버튼이 빠졌다(하이드레이션 불일치)");
      assert.equal(renderToStaticMarkup(first), server);
    });
  }
});

describe("영어 음성 판정", () => {
  it("en-US 가 있으면 1.5초가 지나도 보인다", () => {
    synthWith([voice("ko-KR"), voice("en-US")]);
    mount();
    advance(0);
    assert.ok(shown());
    advance(5000);
    assert.ok(shown());
  });

  it("영어가 en-GB 하나뿐이어도 보이고, 그 언어로 읽는다", () => {
    const synth = synthWith([voice("ko-KR"), voice("en-GB")]);
    mount();
    advance(2000);
    assert.ok(shown());
    tap();
    assert.equal(synth.spoken[0].lang, "en-GB");
  });

  it("en-GB 가 먼저 와도 en_US 를 고르고 lang 은 en-US 로 넘긴다", () => {
    const synth = synthWith([voice("en-GB"), voice("en_US")]);
    mount();
    advance(0);
    tap();
    assert.equal(synth.spoken[0].lang, "en-US");
  });

  it("소문자 en-us 도 미국 영어로 본다(en-AU 보다 먼저)", () => {
    const synth = synthWith([voice("en-AU"), voice("en-us")]);
    mount();
    advance(0);
    tap();
    assert.equal(synth.spoken[0].lang.toLowerCase(), "en-us");
  });

  it("한국어·일본어만 있으면 첫 틱에 숨는다", () => {
    synthWith([voice("ko-KR"), voice("ja-JP")]);
    mount();
    assert.ok(shown(), "효과 직후 바로 숨으면 안 된다(다음 틱)");
    advance(0);
    assert.equal(view(), null);
  });

  it("목록이 비고 voiceschanged 도 안 오면 1499ms 까지 보이고 1500ms 에 숨는다", () => {
    synthWith([]);
    mount();
    advance(1499);
    assert.ok(shown());
    advance(1);
    assert.equal(view(), null);
  });

  it("빈 목록 뒤 500ms 에 영어가 오면 보이고, 1.5초 확인에도 안 숨는다", () => {
    const synth = synthWith([]);
    mount();
    advance(500);
    synth.change([voice("en-US")]);
    advance(5000);
    assert.ok(shown());
  });

  it("빈 목록 뒤 1.6초에야 영어가 오면 1.5초에 숨었다가 다시 나타난다", () => {
    const synth = synthWith([]);
    mount();
    advance(1500);
    assert.equal(view(), null);
    advance(100);
    synth.change([voice("en-US")]);
    assert.ok(shown());
  });

  it("voiceschanged 가 여러 번 와서 영어가 생겼다 없어졌다 하면 그대로 따라간다", () => {
    const synth = synthWith([]);
    mount();
    const seen: boolean[] = [];
    for (const list of [
      [voice("en-US")],
      [voice("ko-KR")],
      [voice("en-GB")],
      [voice("ja-JP"), voice("ko-KR")],
      [voice("en_US")],
    ]) {
      synth.change(list);
      seen.push(shown());
    }
    assert.deepEqual(seen, [true, false, true, false, true]);
    // 빈 목록 알림은 판정을 바꾸지 않는다(크롬이 목록을 다시 읽는 중).
    synth.change([]);
    assert.ok(shown());
    advance(5000);
    assert.equal(view(), null, "1.5초 확인 때 목록이 비어 있으면 숨는다");
  });

  it("voiceschanged 가 첫 틱보다 먼저 와도 판정이 맞다", () => {
    const synth = synthWith([]);
    mount();
    synth.change([voice("ko-KR")]);
    advance(0);
    assert.equal(view(), null);
  });
});

describe("누르기", () => {
  it("cancel 다음 speak, 글은 그대로, voice 는 안 넣고 lang 과 rate 0.9 만", () => {
    const synth = synthWith([voice("en-US")]);
    mount();
    advance(0);
    tap();
    assert.deepEqual(synth.log, ["cancel", "speak:slow query"]);
    const u = synth.spoken[0];
    assert.equal(u.text, "slow query");
    assert.equal(u.lang, "en-US");
    assert.equal(u.rate, 0.9);
    assert.equal(u.voiceAssigned, false, "utterance.voice 를 넣었다");
  });

  it("읽는 동안만 갈색이고 onend 나 onerror 에 돌아온다", () => {
    const synth = synthWith([voice("en-US")]);
    mount();
    advance(0);
    assert.equal(bg(), REST);
    tap();
    assert.equal(bg(), BRAND);
    assert.equal(view()!.props.style.color, "var(--text-on-color)");
    synth.spoken[0].onend!();
    assert.equal(bg(), REST);
    tap();
    assert.equal(bg(), BRAND);
    synth.spoken[1].onerror!({ error: "synthesis-failed" });
    assert.equal(bg(), REST);
  });

  it("3연타 뒤 앞 문장 알림이 뒤섞여 와도 마지막 문장이 끝날 때만 돌아온다", () => {
    const synth = synthWith([voice("en-US")]);
    mount();
    advance(0);
    tap();
    tap();
    tap();
    assert.equal(synth.log.filter((x) => x === "cancel").length, 3);
    assert.equal(synth.spoken.length, 3);
    const [u1, u2, u3] = synth.spoken;
    u2.onerror!({ error: "interrupted" });
    u1.onend!();
    u1.onerror!({ error: "interrupted" });
    u2.onend!();
    assert.equal(bg(), BRAND, "끊긴 앞 문장 알림이 갈색을 껐다");
    u3.onend!();
    assert.equal(bg(), REST);
    // 다시 눌러 읽는 중에 끝난 문장의 늦은 알림이 한 번 더 와도 무시한다.
    tap();
    u3.onerror!({ error: "interrupted" });
    u3.onend!();
    u1.onend!();
    assert.equal(bg(), BRAND);
    synth.spoken[3].onend!();
    assert.equal(bg(), REST);
  });

  it("다시 그리기 전에 같은 onClick 이 세 번 불려도(빠른 연타) 마지막 문장만 산다", () => {
    const synth = synthWith([voice("en-US")]);
    mount();
    advance(0);
    const onClick = view()!.props.onClick;
    onClick();
    onClick();
    onClick();
    synth.spoken[0].onerror!({ error: "interrupted" });
    synth.spoken[1].onerror!({ error: "interrupted" });
    assert.equal(bg(), BRAND);
    synth.spoken[2].onend!();
    assert.equal(bg(), REST);
  });

  it("누르는 순간 영어 음성이 사라졌으면 읽지 않고 버튼을 숨긴다", () => {
    const synth = synthWith([voice("en-US")]);
    mount();
    advance(0);
    synth.voices = [voice("ko-KR")];
    tap();
    assert.equal(synth.spoken.length, 0);
    assert.equal(view(), null);
  });

  it("누르는 순간 목록이 통째로 비어도 터지지 않고 숨는다", () => {
    const synth = synthWith([voice("en-US")]);
    mount();
    advance(0);
    synth.voices = [];
    tap();
    assert.equal(synth.spoken.length, 0);
    assert.equal(view(), null);
  });

  it("읽는 중 음성이 사라져 숨었다가 돌아오면, 앞 문장 끝 알림에 쉬는 색이 된다", () => {
    const synth = synthWith([voice("en-US")]);
    mount();
    advance(0);
    tap();
    synth.voices = [];
    tap();
    assert.equal(view(), null);
    synth.change([voice("en-US")]);
    synth.spoken[0].onend!();
    assert.equal(bg(), REST);
  });

  it("빈 글과 아주 긴 글도 그대로 넘기고 터지지 않는다", () => {
    const synth = synthWith([voice("en-US")]);
    const long = "IntegrityError: UNIQUE constraint failed. ".repeat(500);
    mount({ text: "" });
    advance(0);
    tap();
    props = { ...props, text: long };
    tap();
    assert.equal(synth.spoken[0].text, "");
    assert.equal(synth.spoken[1].text, long);
  });

  it("글이 바뀐 뒤 누르면 새 글을 읽는다", () => {
    const synth = synthWith([voice("en-US")]);
    mount({ text: "index" });
    advance(0);
    props = { ...props, text: "deadlock" };
    tap();
    assert.equal(synth.spoken[0].text, "deadlock");
  });
});

describe("기능이 없거나 옛 브라우저", () => {
  it("speechSynthesis 가 없으면 터지지 않고 첫 틱에 숨는다", () => {
    install(undefined);
    assert.doesNotThrow(() => mount());
    advance(0);
    assert.equal(view(), null);
    assert.doesNotThrow(() => unmount());
  });

  it("speechSynthesis 가 없을 때 첫 틱 전에 떠나면 타이머가 지워진다", () => {
    install(undefined);
    mount();
    unmount();
    assert.equal(timers.size, 0);
    advance(5000);
    assert.equal(setsAfterUnmount, 0);
  });

  it("addEventListener 없는 옛 사파리: 마운트·누르기·떠나기가 터지지 않는다", () => {
    const synth = synthWith([voice("en-US")], OldSafariSynth);
    assert.doesNotThrow(() => mount());
    advance(0);
    assert.ok(shown());
    tap();
    assert.equal(synth.spoken.length, 1);
    assert.doesNotThrow(() => unmount());
    assert.ok(synth.log.at(-1) === "cancel");
  });

  it("옛 사파리에서 목록이 비어 있으면 1.5초에 숨는다", () => {
    synthWith([], OldSafariSynth);
    mount();
    advance(1500);
    assert.equal(view(), null);
  });
});

describe("떠날 때 정리", () => {
  it("읽는 중에 떠나면 cancel 하고 리스너·타이머를 다 지운다", () => {
    const synth = synthWith([]);
    mount();
    synth.change([voice("en-US")]);
    tap();
    const before = synth.log.length;
    unmount();
    assert.deepEqual(synth.log.slice(before), ["cancel"]);
    assert.equal(synth.listeners.size, 0);
    assert.equal(timers.size, 0, "0ms·1.5초 타이머가 남았다");
  });

  it("떠난 뒤 늦은 onend·onerror·voiceschanged 가 와도 터지지 않고 다시 읽지 않는다", () => {
    const synth = synthWith([voice("en-US")]);
    mount();
    advance(0);
    tap();
    tap();
    unmount();
    const logBefore = synth.log.length;
    assert.doesNotThrow(() => {
      synth.spoken[1].onend!();
      synth.spoken[0].onerror!({ error: "interrupted" });
      synth.change([voice("ko-KR")]);
      advance(5000);
    });
    assert.equal(synth.log.length, logBefore);
    // 리스너·타이머는 지워졌으니 판정 쪽 상태 갱신은 없다. 남는 것은 두 끝
    // 알림의 갈색 끄기뿐이다 - 떠나며 cancel() 해 아무것도 안 읽으니 앞 문장
    // 알림도 끈다. 떠난 컴포넌트라 React 가 무시하는 무해한 갱신이다.
    assert.equal(setsAfterUnmount, 2, `떠난 뒤 상태 갱신 ${setsAfterUnmount}번`);
  });

  it("StrictMode 처럼 효과가 붙었다 떨어졌다 다시 붙어도 리스너는 하나다", () => {
    const synth = synthWith([]);
    const first = mount();
    assert.ok(first);
    // 개발 모드의 두 번 돌리기를 흉내 낸다: 정리 후 같은 효과를 다시 돌린다.
    unmount();
    unmounted = false;
    for (const fn of mountedEffects) {
      const c = fn();
      if (typeof c === "function") cleanups.push(c);
    }
    assert.equal(synth.listeners.size, 1);
    assert.equal(timers.size, 2, "0ms 하나와 1.5초 하나만 남아야 한다");
    synth.change([voice("en-US")]);
    advance(5000);
    assert.ok(shown());
  });
});

describe("상세 히어로", () => {
  it("발음기호가 있으면 같은 줄에 발음기호 다음 버튼이 선다", () => {
    const html = renderToStaticMarkup(
      createElement(DetailHero, {
        title: "slow query",
        aside: "/ˈsloʊ ˌkwɪri/",
        speak: { text: "slow query", label: "발음 듣기" },
        meaning: "느린 쿼리",
      }),
    );
    const row = html.match(/<div class="[^"]*empty:hidden[^"]*">([\s\S]*?)<\/div>/);
    assert.ok(row, html);
    assert.match(row[1], /^<p lang="en-US"[^>]*>\/ˈsloʊ ˌkwɪri\/<\/p><button type="button"[^>]*aria-label="발음 듣기"/);
  });

  it("버튼이 숨고 발음기호도 없으면 줄이 완전히 빈 div 라 empty:hidden 이 먹는다", () => {
    mode = "hidden";
    let html: string;
    try {
      html = renderToStaticMarkup(
        createElement(DetailHero, {
          title: "Could you take a look?",
          speak: { text: "Could you take a look?", label: "문장 듣기" },
          meaning: "봐 줄래요?",
          mono: false,
        }),
      );
    } finally {
      mode = "real";
    }
    assert.match(html, /<div class="[^"]*\bempty:hidden\b[^"]*"><\/div>/, html);
    assert.doesNotMatch(html, /<button/);
  });

  it("버튼이 숨어도 발음기호가 있으면 줄은 남는다", () => {
    mode = "hidden";
    let html: string;
    try {
      html = renderToStaticMarkup(
        createElement(DetailHero, {
          title: "slow query",
          aside: "/ˈsloʊ/",
          speak: { text: "slow query", label: "발음 듣기" },
        }),
      );
    } finally {
      mode = "real";
    }
    assert.match(html, /empty:hidden[^"]*"><p lang="en-US"/);
  });

  it("speak 도 발음기호도 없으면 그 줄을 아예 그리지 않는다", () => {
    const html = renderToStaticMarkup(createElement(DetailHero, { title: "x" }));
    assert.doesNotMatch(html, /empty:hidden/);
  });

  it("단어 상세는 단어를 '발음 듣기' 로, 발음기호 없는 단어에도 버튼을 둔다", async () => {
    for (const id of ["1", "2"]) {
      const el = await WordDetailPage({
        params: Promise.resolve({ id }),
        searchParams: Promise.resolve({}),
      });
      const html = renderToStaticMarkup(el);
      assert.equal(html.split('aria-label="발음 듣기"').length - 1, 1, `id=${id}`);
    }
  });

  it("문장 상세는 문장 전체를 '문장 듣기' 로 둔다", async () => {
    const el = await SentenceDetailPage({
      params: Promise.resolve({ id: "5" }),
      searchParams: Promise.resolve({}),
    });
    const html = renderToStaticMarkup(el);
    assert.equal(html.split('aria-label="문장 듣기"').length - 1, 1);
  });

  it("에러 메시지 문장에는 듣기 버튼이 없다(기호를 기기 음성이 어색하게 읽는다)", async () => {
    const el = await SentenceDetailPage({
      params: Promise.resolve({ id: "9" }),
      searchParams: Promise.resolve({}),
    });
    const html = renderToStaticMarkup(el);
    assert.doesNotMatch(html, /aria-label="문장 듣기"/);
    assert.doesNotMatch(html, /empty:hidden/, "버튼이 없으면 빈 줄도 그리지 않는다");
  });
});
