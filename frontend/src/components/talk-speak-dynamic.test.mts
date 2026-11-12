/**
 * 일상영어 판(TalkBoard)에 붙은 소리 듣기 버튼을 실제 흐름으로 움직여 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 지키는 것:
 * - "읽기" 를 누르면 마이크를 열기(listenOnce) 전에 읽던 폰 음성을 멈춘다.
 *   멈추지 않으면 마이크가 폰이 읽은 소리를 받아 채점한다.
 * - 듣는 동안에는 버튼을 감추고(떼어 내지 않는다), 결과가 나오거나 "그만" 으로
 *   돌아오면 다시 보인다.
 * - 건너뛰기·다음으로 문제가 바뀌면 읽던 소리가 멈춘다(문제마다 버튼을 새로
 *   만들어 앞 버튼의 정리 단계가 cancel 한다). 같은 문제에서 다시 그려질 때
 *   (불러오는 중, 다음 받기 실패, 채점 강조가 바뀔 때)는 멈추지 않는다.
 * - 버튼이 읽는 글자는 지금 화면의 글자(prompt.term) 그대로다. 개발 용어도.
 * - 영어 음성이 없거나 speechSynthesis 가 없는 기기에서 카드 안에서도 숨고,
 *   "읽기" 가 터지지 않는다.
 * - 화면 낭독기 순서: 읽을 글자 -> 버튼 -> 발음기호 -> 한글 발음 -> 뜻.
 *
 * 하네스: jsdom 이 없어 작은 재조정기를 둔다. TalkBoard 를 함수로 부르고,
 * 나온 트리에서 TalkPromptCard 와 SpeakButton 만 펼쳐 부른다. 훅은 컴포넌트
 * 인스턴스마다 칸 배열로 돌리고(quiz-board-late-grade.test.mts 의 방식에
 * 인스턴스를 더했다), SpeakButton 은 key 로 인스턴스를 가른다 - 이번 그림에
 * 없는 key 는 떼어 내며 정리 단계를 부른다. 그래야 key={prompt.id} 가 실제
 * React 처럼 마운트·언마운트로 드러난다. 버튼을 감싼 div 의 class 를 남겨
 * 듣는 중의 invisible 을 본다.
 * 음성 인식(listenOnce)·fetch·speechSynthesis·시계는 대역이다.
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it, mock } from "node:test";

const realReact = await import("react");

/* ---------- 훅 대역(인스턴스별) ---------- */

type Cleanup = () => void;
type Inst = {
  slots: unknown[];
  cursor: number;
  queued: Array<{ i: number; fn: () => void | Cleanup }>;
  cleanups: Map<number, Cleanup>;
};
const newInst = (): Inst => ({ slots: [], cursor: 0, queued: [], cleanups: new Map() });

/** 지금 그리는 인스턴스. null 이면 진짜 훅(renderToStaticMarkup 용). */
let current: Inst | null = null;
/** 그린 뒤 상태가 바뀌었나. 바뀌었으면 다시 그린다. */
let dirty = false;

function slotOf<T>(init: () => T): [Inst, number] {
  const inst = current!;
  const i = inst.cursor++;
  if (!(i in inst.slots)) inst.slots[i] = init();
  return [inst, i];
}
const sameDeps = (a?: unknown[], b?: unknown[]) =>
  !!a && !!b && a.length === b.length && a.every((x, i) => Object.is(x, b[i]));

mock.module("react", {
  defaultExport: realReact.default,
  namedExports: {
    ...realReact,
    useState<T>(init: T | (() => T)) {
      if (!current) return realReact.useState(init);
      const [inst, i] = slotOf(() => ({
        v: typeof init === "function" ? (init as () => T)() : init,
      }));
      const box = inst.slots[i] as { v: T };
      const set = (next: T | ((prev: T) => T)) => {
        const v = typeof next === "function" ? (next as (p: T) => T)(box.v) : next;
        if (!Object.is(v, box.v)) dirty = true;
        box.v = v;
      };
      return [box.v, set];
    },
    useRef<T>(init: T) {
      if (!current) return realReact.useRef(init);
      const [inst, i] = slotOf(() => ({ current: init }));
      return inst.slots[i];
    },
    useCallback<T>(fn: T, deps?: unknown[]) {
      if (!current) return realReact.useCallback(fn as never, deps ?? []);
      const [inst, i] = slotOf(() => ({ fn, deps }));
      const box = inst.slots[i] as { fn: T; deps?: unknown[] };
      if (!sameDeps(box.deps, deps)) {
        box.fn = fn;
        box.deps = deps;
      }
      return box.fn;
    },
    useEffect(fn: () => void | Cleanup, deps?: unknown[]) {
      if (!current) return realReact.useEffect(fn, deps);
      const [inst, i] = slotOf(() => ({ deps: undefined as unknown[] | undefined, ran: false }));
      const box = inst.slots[i] as { deps?: unknown[]; ran: boolean };
      if (!box.ran || !sameDeps(box.deps, deps)) {
        box.ran = true;
        box.deps = deps;
        inst.queued.push({ i, fn });
      }
    },
  },
});

/* ---------- 음성 인식 대역 ---------- */

type Outcome = { type: string; heard?: string[] };
/** 지금 듣는 중인 판의 끝내기 손잡이. */
let hearing: ((o: Outcome) => void) | null = null;
let listenCalls = 0;

mock.module("@/lib/speech", {
  namedExports: {
    speechSupported: () => true,
    readMicState: async () => "granted",
    listenOnce(onDone: (o: Outcome) => void) {
      listenCalls += 1;
      // 마이크가 열리는 순간을 음성 기록에 같이 남겨 순서를 본다.
      synth?.log.push("listen");
      hearing = onDone;
      return () => {
        synth?.log.push("stop-listen");
        hearing = null;
        onDone({ type: "cancelled" });
      };
    },
  },
});

const { createElement } = realReact;
const { renderToStaticMarkup } = await import("react-dom/server");
const { TalkBoard } = await import("@/components/TalkBoard");
const { TalkPromptCard } = await import("@/components/TalkPrompt");
const { SpeakButton } = await import("@/components/SpeakButton");

/* ---------- 시계 대역 ---------- */

let now = 0;
let nextTimer = 1;
const timers = new Map<number, { at: number; fn: () => void }>();
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
  renderLoop();
}

/* ---------- speechSynthesis 대역 ---------- */

type Voice = { lang: string; name: string };
const voice = (lang: string): Voice => ({ lang, name: `v-${lang}` });

class FakeUtterance {
  text: string;
  lang = "";
  rate = 1;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(text: string) {
    this.text = text;
  }
}

class FakeSynth {
  voices: Voice[] = [voice("en-US")];
  listeners = new Set<() => void>();
  log: string[] = [];
  spoken: FakeUtterance[] = [];
  speaking = false;
  pending = false;
  getVoices() {
    return this.voices;
  }
  addEventListener(_t: string, fn: () => void) {
    this.listeners.add(fn);
  }
  removeEventListener(_t: string, fn: () => void) {
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
}

let synth: FakeSynth | undefined;
const g = globalThis as Record<string, unknown>;

function installWindow(s: FakeSynth | undefined) {
  synth = s;
  g.window = {
    speechSynthesis: s,
    setTimeout(fn: () => void, ms = 0) {
      const id = nextTimer++;
      timers.set(id, { at: now + ms, fn });
      return id;
    },
    clearTimeout(id: number) {
      timers.delete(id);
    },
    scrollTo() {},
    location: { reload() {} },
  };
  g.SpeechSynthesisUtterance = FakeUtterance;
}

Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: {
    mediaDevices: { getUserMedia: async () => ({ getTracks: () => [] }) },
  },
});

/* ---------- fetch 대역 ---------- */

type Prompt = {
  token: string;
  id: number;
  kind: "phrase" | "word";
  term: string;
  pronunciation: string;
  reading: string;
  meaning: string;
  difficulty: number;
  difficulty_label: string;
  scene: string;
  scene_label: string;
};

const P1: Prompt = {
  token: "t1",
  id: 11,
  kind: "phrase",
  term: "how much is this",
  pronunciation: "/haʊ mʌtʃ ɪz ðɪs/",
  reading: "하우 **머치** 이즈 디스",
  meaning: "이거 얼마예요",
  difficulty: 1,
  difficulty_label: "쉬움",
  scene: "shopping",
  scene_label: "쇼핑·주문",
};
const P2: Prompt = {
  ...P1,
  token: "t2",
  id: 12,
  term: "where is the restroom",
  pronunciation: "/wɛr ɪz ðə ˈrɛstrum/",
  reading: "웨어r 이즈 더 **레**스트룸",
  meaning: "화장실이 어디예요",
};
const DEV: Prompt = {
  ...P1,
  token: "d1",
  id: 11,
  kind: "word",
  term: "race condition",
  pronunciation: "/reɪs kənˈdɪʃən/",
  reading: "레이스 컨**디**션",
  meaning: "경쟁 상태",
  scene: "",
  scene_label: "",
};

type Reply = Prompt | { status: number; detail: string };
/** start 에 차례로 돌려줄 것. */
let serve: Reply[] = [];
/** 참이면 다음 start 응답을 붙잡아 둔다. release() 로 푼다. */
let holdStart = false;
let release: (() => void) | null = null;
/** start 로 보낸 몸통들. */
let startBodies: Array<Record<string, unknown>> = [];
/** 채점 응답의 wrong_at. */
let gradeWrongAt: number[] | null = [1];

function json(status: number, body: unknown): Response {
  return { ok: status < 400, status, json: async () => body } as Response;
}

globalThis.fetch = (async (_input: string, init?: RequestInit) => {
  const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
  if (body.action === "grade") {
    return json(200, {
      ok: false,
      reason: "mismatch",
      heard: [],
      answer: "",
      near: null,
      wrong_at: gradeWrongAt,
    });
  }
  startBodies.push(body);
  const next = serve.shift() ?? { status: 404, detail: "다 봤습니다" };
  const res =
    "status" in next ? json(next.status, { detail: next.detail }) : json(200, next);
  if (!holdStart) return res;
  return new Promise<Response>((resolve) => {
    release = () => resolve(res);
  });
}) as typeof fetch;

/* ---------- 재조정기 ---------- */

type El = { type: unknown; key: string | null; props: Record<string, unknown> };
const isEl = (x: unknown): x is El =>
  typeof x === "object" && x !== null && "type" in x && "props" in x;

function walk(node: unknown, visit: (el: El) => boolean) {
  if (Array.isArray(node)) {
    for (const n of node) walk(n, visit);
    return;
  }
  if (!isEl(node)) return;
  // visit 가 true 면 그 요소가 스스로 펼쳤다(자식은 거기서 본다).
  if (visit(node)) return;
  walk(node.props.children, visit);
}

let root: () => unknown = () => null;
let board = newInst();
/** key -> SpeakButton 인스턴스. */
let speakers = new Map<string, Inst>();
/** 이번 그림의 SpeakButton 결과. 버튼이 숨었으면 null, 없으면 undefined. */
let speakView: El | null | undefined;
/** 이번 그림의 SpeakButton 이 받은 props. */
let speakProps: { text: string; label: string } | undefined;
let cardProps: Record<string, unknown> | undefined;
/** 소리 듣기 버튼을 감싼 div 의 class. 듣는 중이면 invisible 이 붙는다. */
let speakWrapClass = "";
const speakHidden = () => speakWrapClass.split(" ").includes("invisible");
let tree: unknown;
/** 마운트·언마운트 기록. */
let lifecycle: string[] = [];

function runQueued(inst: Inst) {
  const queued = inst.queued;
  inst.queued = [];
  for (const { i, fn } of queued) {
    inst.cleanups.get(i)?.();
    inst.cleanups.delete(i);
    const c = fn();
    if (typeof c === "function") inst.cleanups.set(i, c);
  }
}

function renderPass() {
  board.cursor = 0;
  current = board;
  try {
    tree = root();
  } finally {
    current = null;
  }
  speakView = undefined;
  speakProps = undefined;
  cardProps = undefined;
  speakWrapClass = "";
  const seen = new Set<string>();
  walk(tree, (el) => {
    if (el.type === TalkPromptCard) {
      cardProps = el.props;
      const out = (TalkPromptCard as (p: never) => unknown)(el.props as never);
      walk(out, (inner) => {
        const cls = (inner.props as { className?: unknown } | undefined)?.className;
        if (inner.type === "div" && typeof cls === "string" && cls.includes("absolute")) {
          speakWrapClass = cls;
        }
        if (inner.type !== SpeakButton) return false;
        const key = String(inner.key);
        seen.add(key);
        let inst = speakers.get(key);
        if (!inst) {
          inst = newInst();
          speakers.set(key, inst);
          lifecycle.push(`mount:${key}`);
        }
        inst.cursor = 0;
        current = inst;
        try {
          speakProps = inner.props as typeof speakProps;
          speakView = (SpeakButton as (p: never) => El | null)(inner.props as never);
        } finally {
          current = null;
        }
        return true;
      });
      return true;
    }
    return false;
  });
  for (const [key, inst] of speakers) {
    if (seen.has(key)) continue;
    for (const c of inst.cleanups.values()) c();
    speakers.delete(key);
    lifecycle.push(`unmount:${key}`);
  }
  // React 처럼 자식 효과 다음 부모 효과.
  for (const inst of speakers.values()) runQueued(inst);
  runQueued(board);
}

function renderLoop() {
  let n = 0;
  do {
    dirty = false;
    renderPass();
  } while (dirty && ++n < 30);
}

async function flush() {
  for (let k = 0; k < 6; k++) {
    await new Promise((r) => setImmediate(r));
    renderLoop();
  }
}

/** 판 전체를 떼어 낸다(화면을 떠남). */
function unmountAll() {
  root = () => null;
  renderPass();
  for (const c of board.cleanups.values()) c();
}

/* ---------- 손잡이 ---------- */

const textOf = (node: unknown): string => {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isEl(node)) return textOf(node.props.children);
  return "";
};

function boardButton(label: string): El | undefined {
  let hit: El | undefined;
  walk(tree, (el) => {
    if (el.type === "button" && textOf(el.props.children) === label) hit = el;
    return false;
  });
  return hit;
}

async function press(label: string) {
  const btn = boardButton(label);
  assert.ok(btn, `"${label}" 버튼이 없다`);
  (btn.props.onClick as () => void)();
  renderLoop();
  await flush();
}

function tapSpeak() {
  assert.ok(speakView, "소리 듣기 버튼이 보이지 않는다");
  (speakView.props.onClick as () => void)();
  renderLoop();
}

async function finishListening(o: Outcome) {
  assert.ok(hearing, "듣는 중이 아니다");
  const done = hearing;
  hearing = null;
  done(o);
  await flush();
}

/** 판을 띄워 첫 문제가 뜬 ready 까지 간다. 소개 화면이면 "허용" 을 누른다. */
async function openBoard(kind: "daily" | "dev" = "daily") {
  // 판은 인스턴스가 하나라 요소로 감싸지 않고 함수를 직접 부른다.
  root = () => (TalkBoard as (p: never) => unknown)({ kind, level: 0, scene: "" } as never);
  renderLoop();
  await flush();
  let gate: El | undefined;
  walk(tree, (el) => {
    if (typeof el.props.onAllow === "function") gate = el;
    return false;
  });
  if (!gate && isEl(tree) && typeof tree.props.onAllow === "function") gate = tree;
  if (gate) {
    await (gate.props.onAllow as () => Promise<void>)();
    await flush();
  }
  advance(0);
  assert.ok(boardButton("읽기"), "ready 에 이르지 못했다");
}

const cancelsSince = (from: number) =>
  synth!.log.slice(from).filter((x) => x === "cancel").length;

beforeEach(() => {
  now = 0;
  timers.clear();
  board = newInst();
  speakers = new Map();
  lifecycle = [];
  tree = null;
  serve = [P1, P2];
  holdStart = false;
  release = null;
  startBodies = [];
  gradeWrongAt = [1];
  hearing = null;
  listenCalls = 0;
  installWindow(new FakeSynth());
});

/* ---------- 시나리오 ---------- */

describe("읽기를 누르면", () => {
  it("마이크를 열기 전에 읽던 폰 음성을 멈춘다", async () => {
    await openBoard();
    tapSpeak();
    assert.equal(synth!.speaking, true);
    const speakAt = synth!.log.lastIndexOf(`speak:${P1.term}`);
    await press("읽기");
    const listenAt = synth!.log.indexOf("listen");
    assert.ok(listenAt > speakAt, synth!.log.join(","));
    const firstCancel = synth!.log.indexOf("cancel", speakAt);
    assert.ok(
      firstCancel > speakAt && firstCancel < listenAt,
      `마이크가 열릴 때 폰 음성이 아직 읽는 중이다: ${synth!.log.join(",")}`,
    );
  });

  it("듣는 동안에는 버튼을 감추고 떼어 내지 않으며, 결과가 나오면 다시 보인다", async () => {
    await openBoard();
    assert.equal(speakHidden(), false);
    await press("읽기");
    assert.ok(speakHidden(), "듣는 중에 소리 듣기 버튼이 보인다");
    // 떼어 냈다 다시 붙이면 영어 음성 확인을 처음부터 다시 해 깜빡인다.
    assert.deepEqual(lifecycle, ["mount:11"]);
    assert.ok(boardButton("그만"));

    await finishListening({ type: "heard", heard: ["how much is it"] });
    advance(0);
    assert.ok(boardButton("다시 읽기"), "결과 화면이 아니다");
    assert.ok(speakView, "결과 뒤에 버튼이 없다");
    assert.equal(speakHidden(), false, "결과 뒤에도 버튼이 감춰져 있다");
    assert.deepEqual(lifecycle, ["mount:11"]);
    // 채점 강조가 카드에 들어가도 버튼은 같은 글자를 읽는다.
    assert.deepEqual(cardProps!.wrongAt, [1]);
    tapSpeak();
    assert.equal(synth!.spoken.at(-1)!.text, P1.term);
  });

  it("다시 읽기도 마이크보다 먼저 멈춘다", async () => {
    await openBoard();
    await press("읽기");
    await finishListening({ type: "no-sound" });
    advance(0);
    tapSpeak();
    const from = synth!.log.length;
    await press("다시 읽기");
    const after = synth!.log.slice(from);
    assert.ok(after.indexOf("cancel") > -1 && after.indexOf("cancel") < after.indexOf("listen"), after.join(","));
  });

  it("그만 을 누르면 ready 로 돌아오며 버튼이 다시 생긴다", async () => {
    await openBoard();
    await press("읽기");
    await press("그만");
    advance(0);
    assert.ok(boardButton("읽기"));
    assert.ok(speakView, "그만 뒤에 버튼이 없다");
    assert.equal(speakHidden(), false, "그만 뒤에도 버튼이 감춰져 있다");
  });

  it("인식이 실패로 끝나도(글자 없음) 결과 화면에 버튼이 있다", async () => {
    await openBoard();
    for (const type of ["no-sound", "not-started", "network", "silent"]) {
      await press(boardButton("읽기") ? "읽기" : "다시 읽기");
      assert.ok(speakHidden(), type);
      await finishListening({ type });
      advance(0);
      assert.ok(speakView, `${type} 뒤에 버튼이 없다`);
      assert.equal(speakHidden(), false, `${type} 뒤에도 버튼이 감춰져 있다`);
    }
  });

  it("speechSynthesis 가 없는 브라우저에서 읽기가 터지지 않는다", async () => {
    installWindow(undefined);
    await openBoard();
    assert.equal(speakView, null, "기능이 없는데 버튼이 보인다");
    await press("읽기");
    assert.equal(listenCalls, 1);
    await finishListening({ type: "heard", heard: ["x"] });
    advance(0);
    assert.equal(speakView, null);
  });
});

describe("문제가 바뀌면", () => {
  it("건너뛰기: 새 문제가 뜨는 순간 읽던 소리가 멈추고, 새 버튼은 새 글자를 읽는다", async () => {
    await openBoard();
    tapSpeak();
    const from = synth!.log.length;
    await press("건너뛰기");
    assert.equal(cardProps!.prompt, P2);
    assert.ok(cancelsSince(from) >= 1, "앞 문제 소리가 멈추지 않았다");
    // 기록 순서는 하네스가 그리는 순서다(새 것을 그린 뒤 옛 것을 뗀다).
    assert.deepEqual([...lifecycle].sort(), ["mount:11", "mount:12", "unmount:11"]);
    assert.deepEqual([...speakers.keys()], ["12"]);
    advance(0);
    tapSpeak();
    assert.equal(synth!.spoken.at(-1)!.text, P2.term);
  });

  it("다음: 결과 화면에서 읽던 소리도 새 문제에서 멈춘다", async () => {
    await openBoard();
    await press("읽기");
    await finishListening({ type: "heard", heard: ["how much"] });
    advance(0);
    tapSpeak();
    const from = synth!.log.length;
    await press("다음");
    assert.equal(cardProps!.prompt, P2);
    assert.ok(cancelsSince(from) >= 1);
    assert.equal(cardProps!.wrongAt, null, "새 문제에 앞 채점 강조가 남았다");
  });

  it("다음을 불러오는 동안(같은 문제, 강조만 지워짐)은 멈추지 않는다", async () => {
    await openBoard();
    await press("읽기");
    await finishListening({ type: "heard", heard: ["how much"] });
    advance(0);
    tapSpeak();
    const from = synth!.log.length;
    holdStart = true;
    await press("다음");
    // 아직 앞 문제. 강조는 지워졌고 같은 버튼이다.
    assert.equal(cardProps!.prompt, P1);
    assert.equal(cardProps!.wrongAt, null);
    assert.equal(cancelsSince(from), 0, "같은 문제인데 소리를 끊었다");
    // 듣는 동안 감추기만 하고 떼어 내지 않으므로, 이 문제의 버튼은 처음 붙은 그대로 하나다.
    assert.equal(lifecycle.filter((x) => x.startsWith("mount")).length, 1);
    release!();
    await flush();
    assert.equal(cardProps!.prompt, P2);
    assert.ok(cancelsSince(from) >= 1);
  });

  it("다음 받기가 실패해 같은 문제가 남으면 버튼도 그대로고 소리도 안 끊는다", async () => {
    serve = [P1, { status: 404, detail: "다 봤습니다" }];
    await openBoard();
    tapSpeak();
    const from = synth!.log.length;
    await press("건너뛰기");
    assert.equal(cardProps!.prompt, P1);
    assert.equal(cancelsSince(from), 0);
    assert.deepEqual(lifecycle, ["mount:11"]);
    assert.equal(synth!.speaking, true);
  });

  it("같은 문제에서 채점 강조(wrongAt)가 바뀌며 다시 그려져도 같은 버튼이고 멈추지 않는다", () => {
    let wrongAt: number[] | null = null;
    root = () => createElement(TalkPromptCard, { prompt: P1 as never, wrongAt });
    renderLoop();
    advance(0);
    tapSpeak();
    const from = synth!.log.length;
    for (const next of [[0], [], [1, 3], null]) {
      wrongAt = next;
      renderLoop();
      assert.ok(speakView, `wrongAt=${JSON.stringify(next)} 에서 버튼이 사라졌다`);
    }
    assert.equal(cancelsSince(from), 0);
    assert.deepEqual(lifecycle, ["mount:11"]);
  });

  it("읽는 중에 화면을 떠나면(판이 사라짐) 소리가 멈춘다", async () => {
    await openBoard();
    tapSpeak();
    const from = synth!.log.length;
    unmountAll();
    assert.ok(cancelsSince(from) >= 1);
    assert.equal(synth!.speaking, false);
  });
});

describe("버튼이 읽는 글자", () => {
  it("일상 표현: 지금 화면의 글자 그대로, 이름은 '발음 듣기'", async () => {
    await openBoard();
    assert.equal(speakProps!.text, P1.term);
    assert.equal(speakView!.props["aria-label"], "발음 듣기");
    tapSpeak();
    assert.equal(synth!.spoken.at(-1)!.text, P1.term);
    assert.equal(synth!.spoken.at(-1)!.lang, "en-US");
  });

  it("개발 용어(?kind=dev): 서버에 dev 로 묻고 받은 용어를 읽는다", async () => {
    serve = [DEV];
    await openBoard("dev");
    assert.equal(startBodies[0].kind, "dev");
    assert.equal(speakProps!.text, DEV.term);
    tapSpeak();
    assert.equal(synth!.spoken.at(-1)!.text, "race condition");
  });

  it("채점 강조로 글자가 낱말별로 쪼개져 그려져도 원문 전체를 읽는다", async () => {
    gradeWrongAt = [0, 2];
    await openBoard();
    await press("읽기");
    await finishListening({ type: "heard", heard: ["cow much is kiss"] });
    advance(0);
    tapSpeak();
    assert.equal(synth!.spoken.at(-1)!.text, P1.term);
  });
});

describe("영어 음성이 없는 기기", () => {
  it("한국어 음성만 있으면 카드에서도 첫 틱에 숨고, 결과 뒤 새로 생겨도 다시 숨는다", async () => {
    synth!.voices = [voice("ko-KR")];
    await openBoard();
    assert.equal(speakView, null);
    await press("읽기");
    await finishListening({ type: "heard", heard: ["x"] });
    advance(0);
    assert.equal(speakView, null);
    await press("다음");
    advance(0);
    assert.equal(cardProps!.prompt, P2);
    assert.equal(speakView, null);
  });

  it("음성 목록이 끝내 비어 있으면 1.5초 안에 숨는다(새로 생긴 버튼도)", async () => {
    synth!.voices = [];
    await openBoard();
    advance(1500);
    assert.equal(speakView, null);
    await press("읽기");
    await finishListening({ type: "heard", heard: ["x"] });
    advance(1500);
    assert.equal(speakView, null);
  });
});

describe("화면 낭독기 순서", () => {
  const markup = (prompt: Prompt, listening = false) =>
    renderToStaticMarkup(
      createElement(TalkPromptCard, { prompt: prompt as never, listening }),
    );

  for (const p of [P1, DEV]) {
    it(`${p.kind}: 읽을 글자 -> 버튼 -> 발음기호 -> 한글 발음 -> 뜻`, () => {
      const html = markup(p);
      const at = (needle: string) => {
        const i = html.indexOf(needle);
        assert.ok(i >= 0, `${needle} 이 없다`);
        return i;
      };
      const order = [
        at(`>${p.term}</p>`),
        at('aria-label="발음 듣기"'),
        at(p.pronunciation),
        at(p.meaning),
      ];
      assert.deepEqual([...order].sort((a, b) => a - b), order, html);
      assert.equal(html.split("<button").length - 1, 1);
    });
  }

  it("발음기호·한글 발음이 비어도 버튼은 글자 뒤, 뜻 앞이다", () => {
    const html = markup({ ...DEV, pronunciation: "", reading: "" });
    const term = html.indexOf(">race condition</p>");
    const btn = html.indexOf('aria-label="발음 듣기"');
    const meaning = html.indexOf("경쟁 상태");
    assert.ok(term >= 0 && term < btn && btn < meaning, html);
  });

  it("듣는 중(listening)이면 버튼을 감싼 자리에 invisible 이 붙는다", () => {
    assert.match(markup(P1, true), /<div class="[^"]*\binvisible\b[^"]*"><button/);
    assert.doesNotMatch(markup(P1, false), /\binvisible\b/);
  });
});
