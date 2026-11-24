/**
 * 마이크가 막혔을 때의 안내와 판정을 실제 흐름으로 흔든다.
 *
 * 실행: cd frontend && npm test
 *
 * 지키는 것:
 * - TalkBoard 의 "마이크 켜기/시작하기" 가 실패하면 오류 종류와 다시 읽은
 *   권한 상태를 함께 보고 카드를 고른다. 거절(NotAllowedError)인데 사이트
 *   권한이 "granted" 로 읽히면(크롬 앱의 안드로이드 권한이 막힘) 거절 카드.
 *   권한 창을 닫기만 한 "prompt" 는 다시 물을 수 있게 그대로. 그 밖의 오류와
 *   Error 가 아닌 값(이름만 NotAllowedError 인 객체·문자열 포함)은 다시 읽은
 *   상태를 그대로 쓴다.
 * - 권한 API 가 없거나 조회가 터지는 브라우저에서도 터지지 않고 "prompt".
 * - 거절 카드의 버튼은 새로고침만 하고 권한을 다시 묻지 않는다.
 * - 다시 켜는 길(MIC_UNBLOCK_STEPS)은 네 자리(켜기 전 카드·마이크 확인·결과
 *   안내·새 문장 위 한 줄)에 같은 문구로 나온다. 끝맺음은 그 자리에 있는
 *   버튼을 가리킨다 - 새로고침 버튼이 있는 세 자리는 MIC_BLOCKED_HELP,
 *   새로고침 버튼이 없는 마이크 확인은 '마이크 소리 확인' 을 다시 누르라고 한다.
 * - 마이크 화면 어디에도 PC 안내(주소창·자물쇠·chrome://·윈도우)가 없다.
 *
 * 하네스: jsdom 이 없어 훅을 인스턴스별 칸 배열로 돌린다(talk-speak-dynamic
 * 과 같은 방식). readMicState 는 진짜를 쓰고 navigator·window 를 대역으로
 * 둔다 - 권한 API 가 없는 경우까지 진짜 판정을 거치게 하려는 것이다.
 * listenOnce 만 대역이다.
 *
 * 순서에 기대는 곳이 하나 있다. TalkBoard 는 "이번 방문에 시작했다" 와
 * "이번 방문에 막혔다" 를 모듈 변수로 든다. 한 번 성공하면 소개 카드가 다시
 * 안 뜨므로, 성공해야 하는 시나리오(새 문장 위 한 줄)는 맨 끝에 둔다.
 */
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it, mock } from "node:test";

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

let current: Inst | null = null;
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

/* ---------- 음성 인식: readMicState 는 진짜, listenOnce 만 대역 ---------- */

type Outcome = { type: string; heard?: string[] };
let hearing: ((o: Outcome) => void) | null = null;

const realSpeech = await import("@/lib/speech");
mock.module("@/lib/speech", {
  namedExports: {
    ...realSpeech,
    listenOnce(onDone: (o: Outcome) => void) {
      hearing = onDone;
      return () => {
        hearing = null;
      };
    },
  },
});

const { createElement } = realReact;
const { renderToStaticMarkup } = await import("react-dom/server");
const { TalkBoard } = await import("@/components/TalkBoard");
const { MicGate } = await import("@/components/MicGate");
const { MicCheck } = await import("@/components/MicCheck");
const { MIC_BLOCKED_HELP, MIC_UNBLOCK_STEPS, TalkFeedback } = await import(
  "@/components/TalkFeedback"
);

/* ---------- 브라우저 대역 ---------- */

/** null 이면 navigator.permissions 자체가 없다. "throw" 면 조회가 터진다. */
type PermissionSetting = "granted" | "prompt" | "denied" | "throw" | null;

const env = {
  permission: "prompt" as PermissionSetting,
  hasAudioInput: true,
  /** getUserMedia 가 돌려줄 것. 함수면 그것이 던지거나 약속을 돌려준다. */
  gum: (async () => fakeStream("기본값")) as () => Promise<unknown>,
  gumCalls: 0,
};

function fakeStream(label: string) {
  const track = { label, stop: mock.fn() };
  return { getTracks: () => [track], getAudioTracks: () => [track], track };
}

const g = globalThis as Record<string, unknown>;
let reload = mock.fn();

function installBrowser() {
  reload = mock.fn();
  g.window = {
    SpeechRecognition: class {},
    isSecureContext: true,
    speechSynthesis: undefined,
    location: { reload },
    scrollTo() {},
    setTimeout,
    clearTimeout,
  };
  const permissions =
    env.permission === null
      ? undefined
      : {
          query: async () => {
            if (env.permission === "throw") {
              throw new TypeError("microphone 을 모른다");
            }
            return { state: env.permission };
          },
        };
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: {
      mediaDevices: {
        enumerateDevices: async () =>
          env.hasAudioInput ? [{ kind: "audioinput" }] : [{ kind: "videoinput" }],
        getUserMedia: () => {
          env.gumCalls += 1;
          return env.gum();
        },
      },
      permissions,
    },
  });
}

/* ---------- fetch 대역 ---------- */

let fetchCalls = 0;
const PROMPT = {
  token: "t1",
  id: 11,
  kind: "phrase",
  term: "how much is this",
  pronunciation: "/haʊ mʌtʃ ɪz ðɪs/",
  reading: "하우 머치 이즈 디스",
  meaning: "이거 얼마예요",
  difficulty: 1,
  difficulty_label: "쉬움",
  scene: "shopping",
  scene_label: "쇼핑·주문",
};
globalThis.fetch = (async () => {
  fetchCalls += 1;
  return { ok: true, status: 200, json: async () => ({ ...PROMPT, id: 10 + fetchCalls }) };
}) as unknown as typeof fetch;

/* ---------- 트리 ---------- */

type El = { type: unknown; key: string | null; props: Record<string, unknown> };
const isEl = (x: unknown): x is El =>
  typeof x === "object" && x !== null && "type" in x && "props" in x;

function walk(node: unknown, visit: (el: El) => void) {
  if (Array.isArray(node)) {
    for (const n of node) walk(n, visit);
    return;
  }
  if (!isEl(node)) return;
  visit(node);
  walk(node.props.children, visit);
}

function textOf(node: unknown): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  return isEl(node) ? textOf(node.props.children) : "";
}

const find = (tree: unknown, pred: (el: El) => boolean) => {
  const out: El[] = [];
  walk(tree, (el) => {
    if (pred(el)) out.push(el);
  });
  return out;
};

/** 렌더 결과의 글자. 따옴표가 &#x27; 로 바뀌는 것을 되돌려 문구와 맞춘다. */
const plain = (html: string) =>
  html
    .replace(/<[^>]+>/g, "")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&");

/* ---------- 작은 재조정기: 컴포넌트 하나를 함수로 돌린다 ---------- */

function host<P>(component: (p: P) => unknown, props: P) {
  const inst = newInst();
  let tree: unknown = null;
  const pass = () => {
    inst.cursor = 0;
    current = inst;
    try {
      tree = component(props);
    } finally {
      current = null;
    }
    const queued = inst.queued;
    inst.queued = [];
    for (const { i, fn } of queued) {
      inst.cleanups.get(i)?.();
      inst.cleanups.delete(i);
      const c = fn();
      if (typeof c === "function") inst.cleanups.set(i, c);
    }
  };
  const render = () => {
    let n = 0;
    do {
      dirty = false;
      pass();
    } while (dirty && ++n < 30);
  };
  const settle = async () => {
    for (let k = 0; k < 8; k++) {
      await new Promise((r) => setImmediate(r));
      render();
    }
  };
  return {
    render,
    settle,
    get tree() {
      return tree;
    },
    unmount() {
      for (const c of inst.cleanups.values()) c();
    },
  };
}

/* ---------- TalkBoard 손잡이 ---------- */

type MicState = "prompt" | "granted" | "denied" | "no-device" | "insecure" | "unsupported";

function openBoard() {
  const b = host(TalkBoard as (p: never) => unknown, {
    kind: "daily",
    level: 0,
    scene: "",
  } as never);
  b.render();
  return b;
}

function gateOf(tree: unknown): El {
  assert.ok(isEl(tree) && tree.type === MicGate, "소개 카드(MicGate)가 아니다");
  return tree;
}

/**
 * 소개 카드를 띄우고, 버튼 실패 뒤 다시 읽힐 권한을 맞춘 다음 버튼을 누른다.
 * 그린 카드의 상태를 돌려준다.
 */
async function failAllow(
  err: unknown,
  after: { permission: PermissionSetting; hasAudioInput?: boolean },
  before: PermissionSetting = "granted",
) {
  env.permission = before;
  env.hasAudioInput = true;
  installBrowser();
  const b = openBoard();
  await b.settle();
  const first = gateOf(b.tree);

  env.permission = after.permission;
  env.hasAudioInput = after.hasAudioInput ?? true;
  installBrowser();
  env.gum = async () => {
    throw err;
  };
  const pending = (first.props.onAllow as () => Promise<void>)();
  b.render();
  assert.equal(gateOf(b.tree).props.pending, true, "여는 동안 잠기지 않았다");
  await pending;
  await b.settle();
  const gate = gateOf(b.tree);
  return { board: b, gate, state: gate.props.state as MicState };
}

const domErr = (name: string) => new DOMException("막힘", name);

beforeEach(() => {
  env.permission = "prompt";
  env.hasAudioInput = true;
  env.gum = async () => fakeStream("기본값");
  env.gumCalls = 0;
  fetchCalls = 0;
  hearing = null;
  installBrowser();
});

afterEach(() => {
  restoreErrorCheck();
});

/**
 * 사보타주용. "err instanceof Error" 가 늘 거짓이 되게 해 TalkBoard 의 거절
 * 판별을 끈다. 그러면 판정이 예전처럼 "다시 읽은 상태만 씀" 이 된다.
 */
function disableErrorCheck() {
  Object.defineProperty(Error, Symbol.hasInstance, {
    configurable: true,
    value: () => false,
  });
}
function restoreErrorCheck() {
  delete (Error as unknown as Record<symbol, unknown>)[Symbol.hasInstance];
}

/* ---------- 1. 오류 종류 x 다시 읽은 상태 ---------- */

type Row = {
  err: string;
  make: () => unknown;
  after: PermissionSetting;
  hasAudioInput?: boolean;
  want: MicState;
};

const READ_AFTER: Array<{ label: string; after: PermissionSetting; hasAudioInput?: boolean; plainState: MicState }> = [
  { label: "granted", after: "granted", plainState: "granted" },
  { label: "prompt", after: "prompt", plainState: "prompt" },
  { label: "denied", after: "denied", plainState: "denied" },
  { label: "장치 없음", after: "granted", hasAudioInput: false, plainState: "no-device" },
  { label: "권한 API 없음", after: null, plainState: "prompt" },
  { label: "권한 조회가 터짐", after: "throw", plainState: "prompt" },
];

const ROWS: Row[] = [];
for (const r of READ_AFTER) {
  // 거절: granted 로 읽히면 막힌 것으로 바뀐다. 나머지는 읽은 그대로.
  ROWS.push({
    err: "NotAllowedError(DOMException)",
    make: () => domErr("NotAllowedError"),
    after: r.after,
    hasAudioInput: r.hasAudioInput,
    want: r.plainState === "granted" ? "denied" : r.plainState,
  });
  for (const name of ["NotFoundError", "NotReadableError", "AbortError", "SecurityError", "OverconstrainedError"]) {
    ROWS.push({
      err: `${name}(DOMException)`,
      make: () => domErr(name),
      after: r.after,
      hasAudioInput: r.hasAudioInput,
      want: r.plainState,
    });
  }
  // DOMException 이 아니어도 Error 이고 이름이 NotAllowedError 면 거절로 본다
  // (MicCheck 와 같은 기준).
  ROWS.push({
    err: "NotAllowedError(Error)",
    make: () => Object.assign(new Error("막힘"), { name: "NotAllowedError" }),
    after: r.after,
    hasAudioInput: r.hasAudioInput,
    want: r.plainState === "granted" ? "denied" : r.plainState,
  });
  // Error 가 아닌 것들. 무엇을 던져도 터지지 않고 읽은 상태를 쓴다.
  const odd: Array<[string, () => unknown]> = [
    ["TypeError(getUserMedia 없음)", () => new TypeError("getUserMedia is not a function")],
    ["문자열", () => "NotAllowedError"],
    ["undefined", () => undefined],
    ["null", () => null],
    ["빈 객체", () => ({})],
    ["이름만 NotAllowedError 인 객체", () => ({ name: "NotAllowedError" })],
  ];
  for (const [label, make] of odd) {
    ROWS.push({ err: label, make, after: r.after, hasAudioInput: r.hasAudioInput, want: r.plainState });
  }
}

describe("켜기 실패 뒤 카드 판정(오류 종류 x 다시 읽은 상태)", () => {
  for (const row of ROWS) {
    const label = READ_AFTER.find(
      (r) => r.after === row.after && (r.hasAudioInput ?? true) === (row.hasAudioInput ?? true),
    )!.label;
    it(`${row.err} + ${label} -> ${row.want}`, async () => {
      const { state, gate } = await failAllow(row.make(), {
        permission: row.after,
        hasAudioInput: row.hasAudioInput,
      });
      assert.equal(state, row.want);
      assert.equal(gate.props.pending, false, "실패 뒤 버튼이 잠긴 채 남았다");
      assert.equal(fetchCalls, 0, "실패했는데 문장을 받으러 갔다");
      assert.equal(env.gumCalls, 1);
    });
  }

  it("처음이 prompt 였어도(마이크 켜기) 거절 + granted 면 거절 카드", async () => {
    const { state } = await failAllow(
      domErr("NotAllowedError"),
      { permission: "granted" },
      "prompt",
    );
    assert.equal(state, "denied");
  });

  it("권한 창을 닫기만 했으면(prompt) 다시 '마이크 켜기' 로 물을 수 있다", async () => {
    const { gate } = await failAllow(domErr("NotAllowedError"), { permission: "prompt" }, "prompt");
    const buttons = find(MicGate(gate.props as never), (el) => el.type === "button");
    assert.deepEqual(buttons.map((b) => textOf(b.props.children)), ["마이크 켜기"]);
    assert.equal(buttons[0].props.onClick, gate.props.onAllow, "다시 묻지 않고 새로고침한다");
  });
});

/* ---------- 2. 거절 카드의 새로고침 ---------- */

describe("거절로 바뀐 카드", () => {
  it("새로고침만 하고 권한을 다시 묻지 않는다", async () => {
    const { gate } = await failAllow(domErr("NotAllowedError"), { permission: "granted" });
    const rendered = MicGate(gate.props as never);
    const buttons = find(rendered, (el) => el.type === "button");
    assert.deepEqual(buttons.map((b) => textOf(b.props.children)), ["새로고침"]);
    assert.equal(buttons[0].props.disabled, false);

    (buttons[0].props.onClick as () => void)();

    assert.equal(reload.mock.callCount(), 1);
    assert.equal(env.gumCalls, 1, "새로고침 버튼이 마이크를 다시 열었다");
  });

  it("안내가 MIC_BLOCKED_HELP 를 그대로 담는다", async () => {
    const { gate } = await failAllow(domErr("NotAllowedError"), { permission: "granted" });
    const body = textOf(find(MicGate(gate.props as never), (el) => el.type === "p")[0]);
    assert.ok(body.includes(MIC_BLOCKED_HELP), body);
    assert.match(textOf(find(MicGate(gate.props as never), (el) => el.type === "h2")[0]), /막혀/);
  });
});

/* ---------- 3. 사보타주: 판정을 "다시 읽은 상태만" 으로 되돌리면 ---------- */

describe("사보타주", () => {
  it("거절 판별을 끄면 거절 + granted 가 '시작하기' 로 되돌아간다", async () => {
    // 구현을 건드리지 않고 방어만 끈다. TalkBoard 는 err instanceof Error 로
    // 거절을 알아보는데, Error 의 instanceof 가 늘 거짓이면 거절이 안 보여
    // "다시 읽은 상태만" 쓰던 예전 판정이 된다. 위 표의
    // "NotAllowedError + granted -> denied" 가 이 방어에 기대고 있다는 것을
    // 보인다. 같은 조건에서 방어를 켠 채로 돌린 결과와 나란히 비교한다.
    const err = domErr("NotAllowedError");

    const guarded = await failAllow(err, { permission: "granted" });
    assert.equal(guarded.state, "denied");

    env.permission = "granted";
    installBrowser();
    const b = openBoard();
    await b.settle();
    env.gum = async () => {
      throw err;
    };
    disableErrorCheck();
    try {
      await (gateOf(b.tree).props.onAllow as () => Promise<void>)();
    } finally {
      restoreErrorCheck();
    }
    await b.settle();
    assert.equal(gateOf(b.tree).props.state, "granted");
  });
});

/* ---------- 4. MicCheck ---------- */

type Frame = () => void;
let frames: Frame[] = [];
let level = 128;

class FakeAudioContext {
  state = "running";
  createAnalyser() {
    return {
      fftSize: 0,
      getByteTimeDomainData(arr: Uint8Array) {
        arr.fill(level);
      },
    };
  }
  createMediaStreamSource() {
    return { connect() {} };
  }
  close() {
    return Promise.resolve();
  }
  resume() {
    return Promise.resolve();
  }
}

function installAudio() {
  frames = [];
  level = 128;
  g.AudioContext = FakeAudioContext;
  g.requestAnimationFrame = (fn: Frame) => {
    frames.push(fn);
    return frames.length;
  };
  g.cancelAnimationFrame = () => {};
}

async function micCheckAfterStart() {
  installAudio();
  const c = host(MicCheck as (p: never) => unknown, {} as never);
  c.render();
  const button = find(c.tree, (el) => el.type === "button")[0];
  await (button.props.onClick as () => Promise<void>)();
  await c.settle();
  return c;
}

const alertText = (tree: unknown) =>
  find(tree, (el) => el.props.role === "alert").map((el) => textOf(el.props.children));

describe("마이크 확인(MicCheck)", () => {
  for (const [label, make] of [
    ["DOMException", () => domErr("NotAllowedError")],
    ["Error", () => Object.assign(new Error("막힘"), { name: "NotAllowedError" })],
  ] as const) {
    it(`거절(${label})이면 다시 켜는 길과 이 화면의 버튼을 말한다`, async () => {
      env.gum = async () => {
        throw make();
      };
      const c = await micCheckAfterStart();
      assert.deepEqual(alertText(c.tree), [
        `마이크가 막혀 있습니다. ${MIC_UNBLOCK_STEPS} 그런 다음 '마이크 소리 확인'을 다시 눌러주세요.`,
      ]);
    });
  }

  it("거절 안내가 가리키는 버튼이 실패 화면에 실제로 있고, 없는 새로고침은 말하지 않는다", async () => {
    // 이 화면에는 새로고침 버튼이 없다. MIC_BLOCKED_HELP 의 "'새로고침'을
    // 눌러주세요" 를 그대로 쓰면 누를 것이 없다.
    env.gum = async () => {
      throw domErr("NotAllowedError");
    };
    const c = await micCheckAfterStart();
    const [msg] = alertText(c.tree);
    assert.ok(!msg.includes(MIC_BLOCKED_HELP));
    assert.doesNotMatch(msg, /새로고침/);
    const buttons = find(c.tree, (el) => el.type === "button").map((el) => textOf(el.props.children));
    assert.deepEqual(buttons, ["마이크 소리 확인"]);

    // 그 버튼을 다시 누르면 마이크를 다시 연다(설정을 고친 뒤).
    env.gum = async () => fakeStream("기본값");
    const before = env.gumCalls;
    const button = find(c.tree, (el) => el.type === "button")[0];
    await (button.props.onClick as () => Promise<void>)();
    await c.settle();
    assert.equal(env.gumCalls, before + 1);
    assert.deepEqual(alertText(c.tree), []);
    c.unmount();
  });

  it("거절이 아닌 실패는 막힘 안내를 섞지 않는다", async () => {
    for (const name of ["NotFoundError", "NotReadableError", "AbortError"]) {
      env.gum = async () => {
        throw domErr(name);
      };
      const c = await micCheckAfterStart();
      const [msg] = alertText(c.tree);
      assert.equal(msg, "마이크를 열지 못했습니다. 장치가 연결돼 있는지 봐주세요.", name);
      assert.ok(!msg.includes(MIC_BLOCKED_HELP), name);
    }
  });

  it("오류 객체가 아닌 값이 던져져도 터지지 않고 일반 실패 문구", async () => {
    for (const thrown of ["NotAllowedError", undefined, null, { name: "NotAllowedError" }]) {
      env.gum = async () => {
        throw thrown;
      };
      const c = await micCheckAfterStart();
      assert.deepEqual(alertText(c.tree), [
        "마이크를 열지 못했습니다. 장치가 연결돼 있는지 봐주세요.",
      ]);
    }
  });

  it("조용할 때 장치 안내는 이어폰과 다시 확인 두 줄이고 PC 안내가 없다", async () => {
    env.gum = async () => fakeStream("기본값");
    const c = await micCheckAfterStart();
    frames.shift()?.();
    c.render();
    const text = textOf(c.tree);
    assert.match(text, /지금 쓰는 장치: 기본값/);
    assert.match(text, /다른 마이크로 바꾸려면/);
    const items = find(c.tree, (el) => el.type === "li").map((el) => textOf(el.props.children));
    assert.equal(items.length, 2);
    assert.match(items[0], /이어폰/);
    assert.equal(items[1], "2. '그만 보기'를 누르고 '마이크 소리 확인'을 다시 눌러 봅니다.");
    // 안내가 가리키는 두 버튼이 실제 이름과 같다.
    const button = () => find(c.tree, (el) => el.type === "button")[0];
    assert.equal(textOf(button().props.children), "그만 보기");
    (button().props.onClick as () => void)();
    c.render();
    assert.equal(textOf(button().props.children), "마이크 소리 확인");
    assert.match(items[0], /^1\./);
    assert.match(items[1], /^2\./);
    assert.doesNotMatch(text, PC_WORDS);
    c.unmount();
  });

  it("소리가 들어오면 장치 바꾸기 안내가 빠진다", async () => {
    env.gum = async () => fakeStream("기본값");
    const c = await micCheckAfterStart();
    level = 255;
    frames.shift()?.();
    c.render();
    const text = textOf(c.tree);
    assert.match(text, /소리가 들어오고 있습니다/);
    assert.doesNotMatch(text, /다른 마이크로 바꾸려면/);
    c.unmount();
  });
});

/* ---------- 5. PC 안내가 마이크 화면 어디에도 없다 ---------- */

const PC_WORDS = /주소창|자물쇠|슬라이더|chrome:\/\/|윈도우|Windows|settings\/content|프로그램|다른 탭/i;
const STATES: MicState[] = ["prompt", "granted", "denied", "no-device", "insecure", "unsupported"];
const OUTCOMES: Outcome[] = [
  { type: "not-started" },
  { type: "no-sound" },
  { type: "no-speech" },
  { type: "no-mic" },
  { type: "denied" },
  { type: "network" },
  { type: "silent" },
  { type: "cancelled" },
];

describe("PC 안내가 남지 않았다", () => {
  it("안내 문구 자체에 PC 안내가 없고 폰 설정을 말한다", () => {
    assert.doesNotMatch(MIC_UNBLOCK_STEPS, PC_WORDS);
    assert.doesNotMatch(MIC_BLOCKED_HELP, PC_WORDS);
    assert.ok(MIC_BLOCKED_HELP.startsWith(MIC_UNBLOCK_STEPS));
    assert.match(MIC_UNBLOCK_STEPS, /폰 설정/);
    // 다시 켜는 길에는 끝맺음(어느 버튼을 누를지)이 섞이지 않는다.
    assert.doesNotMatch(MIC_UNBLOCK_STEPS, /새로고침|마이크 소리 확인/);
    assert.match(MIC_BLOCKED_HELP, /폰 설정/);
    assert.match(MIC_BLOCKED_HELP, /새로고침/);
  });

  for (const state of STATES) {
    it(`소개 카드 ${state}`, () => {
      const html = renderToStaticMarkup(
        createElement(MicGate, { state, onAllow: () => {}, pending: false }),
      );
      assert.doesNotMatch(plain(html), PC_WORDS);
    });
  }

  for (const outcome of OUTCOMES) {
    it(`결과 안내 ${outcome.type}`, () => {
      const html = renderToStaticMarkup(
        createElement(TalkFeedback, { outcome: outcome as never, result: null, heardRaw: [] }),
      );
      assert.doesNotMatch(plain(html), PC_WORDS);
    });
  }

  it("마이크 확인의 처음·거절·실패 화면", async () => {
    const c0 = host(MicCheck as (p: never) => unknown, {} as never);
    c0.render();
    assert.doesNotMatch(textOf(c0.tree), PC_WORDS);
    for (const name of ["NotAllowedError", "NotFoundError"]) {
      env.gum = async () => {
        throw domErr(name);
      };
      const c = await micCheckAfterStart();
      assert.doesNotMatch(textOf(c.tree), PC_WORDS, name);
    }
  });
});

/* ---------- 6. 같은 문구가 네 자리에 ---------- */

describe("다시 켜는 길은 어디서나 같은 문구", () => {
  it("소개 카드", () => {
    const html = renderToStaticMarkup(
      createElement(MicGate, { state: "denied", onAllow: () => {}, pending: false }),
    );
    assert.ok(plain(html).includes(MIC_BLOCKED_HELP));
  });

  it("결과 안내(denied)", () => {
    const html = renderToStaticMarkup(
      createElement(TalkFeedback, { outcome: { type: "denied" }, result: null, heardRaw: [] }),
    );
    assert.ok(plain(html).includes(MIC_BLOCKED_HELP));
  });

  it("막힘 안내는 막힌 카드·결과에만 나오고 다른 상태에는 안 나온다", () => {
    for (const state of STATES.filter((s) => s !== "denied")) {
      const html = renderToStaticMarkup(
        createElement(MicGate, { state, onAllow: () => {}, pending: false }),
      );
      assert.ok(!plain(html).includes(MIC_BLOCKED_HELP), state);
    }
    for (const outcome of OUTCOMES.filter((o) => o.type !== "denied")) {
      const html = renderToStaticMarkup(
        createElement(TalkFeedback, { outcome: outcome as never, result: null, heardRaw: [] }),
      );
      assert.ok(!plain(html).includes(MIC_BLOCKED_HELP), outcome.type);
    }
  });

  // 이 시나리오는 마이크 켜기에 성공한다(모듈 변수 startedThisVisit 이 켜진다).
  // 그래서 맨 끝에 둔다.
  it("읽다가 막힌 뒤 새 문장 위 한 줄과 결과 안내", async () => {
    env.permission = "prompt";
    installBrowser();
    const b = openBoard();
    await b.settle();
    await (gateOf(b.tree).props.onAllow as () => Promise<void>)();
    await b.settle();

    const read = find(b.tree, (el) => el.type === "button" && textOf(el.props.children) === "읽기")[0];
    assert.ok(read, "읽기 버튼이 없다");
    (read.props.onClick as () => void)();
    b.render();
    assert.ok(hearing, "듣기를 시작하지 않았다");
    hearing!({ type: "denied" });
    await b.settle();

    const feedback = find(b.tree, (el) => el.type === TalkFeedback)[0];
    assert.ok(feedback, "결과 안내가 없다");
    const fbHtml = renderToStaticMarkup(createElement(TalkFeedback, feedback.props as never));
    assert.ok(plain(fbHtml).includes(MIC_BLOCKED_HELP));

    const next = find(b.tree, (el) => el.type === "button" && textOf(el.props.children) === "다음")[0];
    (next.props.onClick as () => void)();
    await b.settle();

    const lines = find(b.tree, (el) => el.type === "p").map((el) => textOf(el.props.children));
    assert.ok(lines.includes(`마이크가 막혀 있어요. ${MIC_BLOCKED_HELP}`), lines.join(" | "));
    assert.ok(lines.every((l) => !PC_WORDS.test(l)));

    const main = find(b.tree, (el) => el.type === "button" && textOf(el.props.children) === "새로고침")[0];
    assert.ok(main, "주 버튼이 새로고침이 아니다");
    (main.props.onClick as () => void)();
    assert.equal(reload.mock.callCount(), 1);
  });
});
