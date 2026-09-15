/**
 * listenOnce 를 기존 두 파일이 안 흔든 순서로 흔든다.
 *
 * 실행: cd frontend && npm test
 *
 * 모든 경우에 onDone 이 **정확히 한 번** 불리는지 타이머가 다 돈 뒤에 센다.
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it } from "node:test";

import {
  listenOnce,
  type ListenOutcome,
  type ListenStage,
} from "./speech";

type Handler = (() => void) | null;

class Fake {
  static last: Fake | null = null;
  /** abort() 안에서 곧바로 부를 것. */
  static onAbort: ((r: Fake) => void) | null = null;
  lang = "";
  continuous = true;
  interimResults = true;
  maxAlternatives = 1;
  aborted = 0;
  onresult: ((event: unknown) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: Handler = null;
  onaudiostart: Handler = null;
  onsoundstart: Handler = null;
  onspeechstart: Handler = null;
  constructor() {
    Fake.last = this;
  }
  start() {}
  stop() {}
  abort() {
    this.aborted += 1;
    Fake.onAbort?.(this);
  }
  say(...alts: string[]) {
    const first = alts.map((transcript) => ({ transcript }));
    this.onresult?.({ results: [Object.assign(first, { length: first.length })] });
  }
}

(globalThis as unknown as { window: unknown }).window = { SpeechRecognition: Fake };

beforeEach(() => {
  Fake.last = null;
  Fake.onAbort = null;
});

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function run(timeoutMs = 60_000) {
  const calls: ListenOutcome[] = [];
  const stages: ListenStage[] = [];
  const stop = listenOnce(
    (o) => calls.push(o),
    (s) => stages.push(s),
    timeoutMs,
  );
  return { calls, stages, stop, r: Fake.last! };
}

describe("설정", () => {
  it("인식기를 영어·후보 다섯·한 번 듣기로 맞춘다", () => {
    const { r, stop } = run();
    assert.equal(r.lang, "en-US");
    assert.equal(r.maxAlternatives, 5);
    assert.equal(r.continuous, false);
    assert.equal(r.interimResults, false);
    stop();
  });
});

describe("같은 틱에 몰려 오는 신호", () => {
  it("soundstart·speechstart 가 연달아 온 뒤 결과면 heard 하나", async () => {
    const { calls, stages, r } = run(50);
    r.onaudiostart?.();
    r.onsoundstart?.();
    r.onspeechstart?.();
    r.say("thank you");
    await wait(120);
    assert.deepEqual(calls, [{ type: "heard", heard: ["thank you"] }]);
    assert.deepEqual(stages, ["open", "sound", "speech"]);
  });

  it("audiostart 없이 speechstart 부터 와도 시작 감시가 끼어들지 않는다", async () => {
    // 일부 엔진은 audiostart 를 안 쏜다. 말까지 갔는데 not-started 가 뜨면 반대다.
    const { calls, r } = run(3_000);
    r.onspeechstart?.();
    await wait(2_700);
    assert.equal(calls.length, 0, "시작 감시(2.5초)가 말하는 중에 끊었다");
    r.say("hello");
    assert.deepEqual(calls, [{ type: "heard", heard: ["hello"] }]);
  });
});

describe("끝이 결과보다 먼저 올 때", () => {
  it("onend 가 먼저면 간 자리의 이유가 남고 늦은 결과는 버린다", async () => {
    const { calls, r } = run(50);
    r.onaudiostart?.();
    r.onsoundstart?.();
    r.onspeechstart?.();
    r.onend?.();
    r.say("late");
    await wait(120);
    assert.deepEqual(calls, [{ type: "silent" }]);
  });

  it("error 뒤 end 가 와도 에러 이유 하나만", async () => {
    const { calls, r } = run(50);
    r.onaudiostart?.();
    r.onerror?.({ error: "no-speech" });
    r.onend?.();
    await wait(120);
    assert.deepEqual(calls, [{ type: "no-sound" }]);
  });

  it("모르는 에러 코드(aborted·language-not-supported)는 간 자리의 이유 하나", async () => {
    // 코드만 보고 silent 로 두면 마이크가 열리기도 전에 온 에러에도 "못
    // 알아들었어요" 가 뜬다. 끝난 자리로 가르는 onend 와 같은 기준이다.
    for (const code of ["aborted", "language-not-supported", "bad-grammar"]) {
      const cases: [string[], ListenOutcome["type"]][] = [
        [[], "not-started"],
        [["audio"], "no-sound"],
        [["audio", "sound", "speech"], "silent"],
      ];
      for (const [reached, expected] of cases) {
        const { calls, r } = run(30);
        if (reached.includes("audio")) r.onaudiostart?.();
        if (reached.includes("sound")) r.onsoundstart?.();
        if (reached.includes("speech")) r.onspeechstart?.();
        r.onerror?.({ error: code });
        r.onend?.();
        await wait(60);
        assert.deepEqual(calls, [{ type: expected }], `${code} / ${reached.join(",")}`);
      }
    }
  });
});

describe("끊는 도중에 들어오는 것", () => {
  it("취소하는 abort 안에서 결과가 동기로 와도 cancelled 하나", () => {
    Fake.onAbort = (r) => {
      r.say("commit");
      r.onend?.();
    };
    const { calls, stop, r } = run();
    r.onaudiostart?.();
    r.onspeechstart?.();
    stop();
    assert.deepEqual(calls, [{ type: "cancelled" }]);
    assert.equal(r.aborted, 1);
  });

  it("타임아웃 abort 안에서 결과가 동기로 와도 간 자리의 이유 하나", async () => {
    Fake.onAbort = (r) => r.say("commit");
    const { calls, r } = run(40);
    r.onaudiostart?.();
    await wait(100);
    assert.deepEqual(calls, [{ type: "no-sound" }]);
    assert.equal(r.aborted, 1);
  });

  it("타임아웃과 결과가 같은 틱이면 한 번만, 인식기는 끊는다", async () => {
    const { calls, r } = run(30);
    r.onaudiostart?.();
    // listenOnce 의 타이머보다 뒤에 만든 같은 지연 타이머 - 같은 틱에 뒤따라 돈다.
    setTimeout(() => r.say("commit"), 30);
    await wait(100);
    assert.equal(calls.length, 1);
    assert.equal(r.aborted, 1);
  });

  it("시작 감시보다 전체 타임아웃이 짧으면 전체 쪽이 not-started 하나", async () => {
    const { calls, r } = run(30);
    await wait(2_700);
    assert.deepEqual(calls, [{ type: "not-started" }]);
    assert.equal(r.aborted, 1, "시작 감시가 한 번 더 끊었다");
  });
});

describe("모양이 이상한 결과 이벤트", () => {
  for (const [name, event] of [
    ["results 가 없음", {}],
    ["후보 배열이 비었음", { results: [Object.assign([], { length: 0 })] }],
    ["transcript 가 없음", { results: [Object.assign([{}], { length: 1 })] }],
    ["후보가 공백뿐", { results: [Object.assign([{ transcript: "   " }], { length: 1 })] }],
  ] as const) {
    it(`${name} 이면 던지지 않고 no-speech 하나`, async () => {
      const { calls, r } = run(30);
      r.onaudiostart?.();
      r.onspeechstart?.();
      assert.doesNotThrow(() => r.onresult?.(event));
      await wait(60);
      assert.deepEqual(calls, [{ type: "no-speech" }]);
    });
  }
});

describe("단계가 뒤로 가거나 끝난 뒤에 오는 신호", () => {
  it("말까지 간 뒤 audiostart 가 늦게 와도 이유가 no-sound 로 떨어지지 않는다", async () => {
    // 떨어지면 말을 한 사람에게 MicCheck 가 뜬다(TalkBoard 는 no-sound 에만 띄운다).
    const { calls, r } = run(60_000);
    r.onaudiostart?.();
    r.onsoundstart?.();
    r.onspeechstart?.();
    r.onaudiostart?.();
    r.onend?.();
    assert.deepEqual(calls, [{ type: "silent" }]);
  });

  it("끝난 뒤에 온 단계 신호를 화면에 알리지 않는다", () => {
    // TalkBoard 는 onStage 를 setStage 로 곧바로 넘긴다. 끊긴 인식기의 늦은
    // 이벤트가 알리면, 곧바로 다시 누른 다음 판의 "마이크를 여는 중" 을 덮는다.
    const { calls, stages, stop, r } = run(60_000);
    stop();
    r.onaudiostart?.();
    r.onspeechstart?.();
    assert.deepEqual(calls, [{ type: "cancelled" }]);
    assert.deepEqual(stages, []);
  });
});
