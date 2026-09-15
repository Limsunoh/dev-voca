/**
 * listenOnce 가 실패를 어떤 이유로 가르는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * ## 왜 이걸 테스트하나
 *
 * 사용자가 "마이크에 소리가 안 들어간다" 고 알려 왔는데, 화면은 **"잘 못
 * 알아들었어요"** 라고만 했다. 그 문구는 발음을 탓하는 말이라 사용자가
 * 계속 다시 읽었다. 실제로는 인식기가 시작조차 안 한 상태였다.
 *
 * 인식기는 단계마다 신호를 준다.
 *
 *     audiostart   마이크가 열렸다
 *     soundstart   소리가 들어왔다
 *     speechstart  그 소리가 말로 판정됐다
 *     result       글자가 나왔다
 *
 * 어디까지 갔는지에 따라 **사용자가 할 수 있는 일이 정반대**다. 마이크가
 * 안 열렸으면 다시 읽어봐야 소용없고, 소리가 안 들어오면 장치를 봐야 하고,
 * 말로 안 들렸으면 또렷하게 다시 읽으면 된다. 그래서 셋을 가른다.
 *
 * 마이크 없이 재려고 가짜 인식기를 끼운다. 가르는 규칙이 **신호가 오는
 * 순서** 만 보므로 가짜로 충분하다.
 *
 * **다만 크롬은 이 가짜처럼 순서를 나눠 보내지 않는다.** soundstart 와
 * speechstart 를 음성 구간이 잡힌 순간 한꺼번에 쏜다. 그래서 아래의
 * "소리는 들어왔는데 말이 아님(audio 다음 sound 만)" 순서는 크롬에서는
 * 안 나온다. 그 경우를 지우지 않는 것은 둘을 나눠 보내는 엔진이 있을 때
 * 판정이 틀리지 않게 하려는 것이고, 크롬 사용자에게 보이는 실패는 사실상
 * not-started 와 no-sound 둘이다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it } from "node:test";

import { listenOnce, type ListenOutcome, type ListenStage } from "./speech";

type Handler = (() => void) | null;

/** 브라우저 인식기 흉내. 이벤트를 손으로 쏜다. */
class FakeRecognition {
  static last: FakeRecognition | null = null;
  /** start() 가 던지게 한다. 이미 돌고 있는 인식기를 또 시작한 경우다. */
  static throwOnStart = false;
  /** start() 안에서 onend 를 곧바로 부른다. 시작하자마자 죽는 구현이다. */
  static endOnStart = false;
  /** abort() 안에서 onend 를 곧바로 부른다. 이벤트를 미루지 않는 구현이다. */
  static endOnAbort = false;

  lang = "";
  continuous = false;
  interimResults = false;
  maxAlternatives = 1;
  started = false;
  aborted = false;

  onresult: ((event: { results: unknown }) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: Handler = null;
  onaudiostart: Handler = null;
  onsoundstart: Handler = null;
  onspeechstart: Handler = null;

  constructor() {
    FakeRecognition.last = this;
  }

  start(): void {
    if (FakeRecognition.throwOnStart) throw new Error("이미 돌고 있다");
    this.started = true;
    if (FakeRecognition.endOnStart) this.onend?.();
  }

  stop(): void {}

  abort(): void {
    this.aborted = true;
    if (FakeRecognition.endOnAbort) this.onend?.();
  }

  /** 마이크가 열렸다. */
  audio(): void {
    this.onaudiostart?.();
  }

  /** 소리가 들어왔다. */
  sound(): void {
    this.onsoundstart?.();
  }

  /** 말로 판정됐다. */
  speech(): void {
    this.onspeechstart?.();
  }

  fail(code: string): void {
    this.onerror?.({ error: code });
  }

  end(): void {
    this.onend?.();
  }

  say(...alternatives: string[]): void {
    const first = alternatives.map((transcript) => ({ transcript }));
    this.onresult?.({ results: [Object.assign(first, { length: first.length })] });
  }
}

const globals = globalThis as unknown as {
  window?: { SpeechRecognition?: unknown };
};
const hadWindow = "window" in globals;
const savedWindow = globals.window;

globals.window = { SpeechRecognition: FakeRecognition };

after(() => {
  if (hadWindow) globals.window = savedWindow;
  else delete globals.window;
});

beforeEach(() => {
  FakeRecognition.last = null;
  FakeRecognition.throwOnStart = false;
  FakeRecognition.endOnStart = false;
  FakeRecognition.endOnAbort = false;
});

/** 한 번 듣고, 가짜 인식기를 몰아 결과를 받는다. */
function listen(
  drive: (recognition: FakeRecognition) => void,
  timeoutMs = 200,
): Promise<{ outcome: ListenOutcome; stages: ListenStage[] }> {
  return new Promise((resolve) => {
    const stages: ListenStage[] = [];
    listenOnce(
      (outcome) => resolve({ outcome, stages }),
      (stage) => stages.push(stage),
      timeoutMs,
    );
    const recognition = FakeRecognition.last;
    assert.ok(recognition, "인식기가 안 만들어졌다");
    drive(recognition);
  });
}

describe("어디까지 갔는지로 실패를 가른다", () => {
  it("마이크가 열린 신호가 아예 없으면 시작 못 함이다", async () => {
    // 크롬에서 실제로 있는 경로다. start() 를 불러도 아무 이벤트가 안 온다.
    // 자체 시작 감시(2.5초)가 잡는다.
    const { outcome, stages } = await listen(() => {}, 60_000);
    assert.deepEqual(outcome, { type: "not-started" });
    assert.deepEqual(stages, []);
    assert.ok(FakeRecognition.last?.aborted, "시작을 못 했으면 끊어야 한다");
  });

  it("start() 가 던져도 시작 못 함이다", async () => {
    FakeRecognition.throwOnStart = true;
    const { outcome } = await listen(() => {});
    assert.deepEqual(outcome, { type: "not-started" });
  });

  it("마이크는 열렸는데 소리가 안 들어오면 소리 없음이다", async () => {
    const { outcome, stages } = await listen((r) => {
      r.audio();
      r.end();
    });
    assert.deepEqual(outcome, { type: "no-sound" });
    assert.deepEqual(stages, ["open"]);
  });

  it("소리가 안 들어온 채 no-speech 가 와도 소리 없음이다", async () => {
    // 인식기는 이 둘을 "말이 없었다" 하나로 뭉뚱그린다. 우리가 가른다.
    const { outcome } = await listen((r) => {
      r.audio();
      r.fail("no-speech");
    });
    assert.deepEqual(outcome, { type: "no-sound" });
  });

  it("소리는 들어왔는데 말이 아니면 말로 안 들림이다", async () => {
    const { outcome, stages } = await listen((r) => {
      r.audio();
      r.sound();
      r.fail("no-speech");
    });
    assert.deepEqual(outcome, { type: "no-speech" });
    assert.deepEqual(stages, ["open", "sound"]);
  });

  it("말까지 갔는데 결과가 없으면 못 알아들은 것이다", async () => {
    const { outcome, stages } = await listen((r) => {
      r.audio();
      r.sound();
      r.speech();
      r.end();
    });
    assert.deepEqual(outcome, { type: "silent" });
    assert.deepEqual(stages, ["open", "sound", "speech"]);
  });

  it("타임아웃도 간 자리에 맞는 이유를 고른다", async () => {
    const { outcome } = await listen((r) => {
      r.audio();
      r.sound();
    }, 150);
    assert.deepEqual(outcome, { type: "silent" });
  });
});

describe("성공과 기계 쪽 실패", () => {
  it("글자를 받으면 후보를 순서대로 넘긴다", async () => {
    const { outcome } = await listen((r) => {
      r.audio();
      r.sound();
      r.speech();
      r.say("cache", "cash", "  ");
    });
    // 빈 후보는 뺀다. 화면이 near 안내를 만들 때 빈 칸이 끼면 안 된다.
    assert.deepEqual(outcome, { type: "heard", heard: ["cache", "cash"] });
  });

  it("결과 뒤에 오는 end 가 결과를 덮지 않는다", async () => {
    const { outcome } = await listen((r) => {
      r.audio();
      r.sound();
      r.say("commit");
      r.end();
    });
    assert.deepEqual(outcome, { type: "heard", heard: ["commit"] });
  });

  for (const [code, type] of [
    ["audio-capture", "no-mic"],
    ["not-allowed", "denied"],
    ["service-not-allowed", "denied"],
    ["network", "network"],
  ] as const) {
    it(`${code} 는 ${type} 으로 옮긴다`, async () => {
      const { outcome } = await listen((r) => {
        r.audio();
        r.fail(code);
      });
      assert.deepEqual(outcome, { type });
    });
  }
});

describe("끊기", () => {
  it("돌려준 함수로 끊으면 인식기도 끊는다", () => {
    const calls: ListenOutcome[] = [];
    const stop = listenOnce((outcome) => calls.push(outcome), undefined, 60_000);
    stop();

    /*
     * **사용자가 "그만" 을 누른 것은 실패가 아니다.** 마이크가 열리기 전에
     * 끊겨도 "시작하지 못했어요" 라고 하면 안 된다 - 그건 고치라는 안내인데
     * 고칠 것이 없다. silent 로 두어도 안 된다 - 화면이 "못 알아들었어요"
     * 를 띄운다. 어디까지 갔든 cancelled 다.
     */
    assert.deepEqual(calls, [{ type: "cancelled" }]);
    // 끊었는지는 콜백 **뒤에** 본다. 이유를 먼저 정하고 그다음에 끊는
    // 순서라(speech.order.test.mts 가 그 순서를 지킨다), 콜백 안에서
    // 보면 아직 안 끊긴 것이 정상이다.
    assert.ok(FakeRecognition.last?.aborted, "인식기를 안 끊었다");
  });
});

/**
 * 한 번 듣고, 모든 onDone 호출을 모은다.
 *
 * listen() 은 첫 호출에서 약속을 풀어 버려서 **두 번 불린 것**을 못 본다.
 * 여기서는 타이머가 다 돌 때까지 기다린 뒤 몇 번 불렸는지를 센다.
 */
function listenAll(timeoutMs: number) {
  const calls: ListenOutcome[] = [];
  const stages: ListenStage[] = [];
  const stop = listenOnce(
    (outcome) => calls.push(outcome),
    (stage) => stages.push(stage),
    timeoutMs,
  );
  const recognition = FakeRecognition.last;
  assert.ok(recognition, "인식기가 안 만들어졌다");
  return { calls, stages, stop, recognition };
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

describe("이벤트가 한꺼번에·동기로 올 때", () => {
  it("start() 안에서 곧바로 끝나도 시작 못 함이 한 번만 온다", async () => {
    // onDone 이 listenOnce 가 돌아오기 **전에** 불리는 경로다. 타이머를
    // 못 치우면 타임아웃이 한 번 더 부른다.
    FakeRecognition.endOnStart = true;
    const { calls, stages } = listenAll(50);
    await wait(120);
    assert.deepEqual(calls, [{ type: "not-started" }]);
    assert.deepEqual(stages, []);
  });

  it("시작 감시가 끊을 때 onend 가 동기로 와도 한 번만 온다", async () => {
    FakeRecognition.endOnAbort = true;
    const { calls, recognition } = listenAll(60_000);
    await wait(2_700);
    assert.deepEqual(calls, [{ type: "not-started" }]);
    assert.ok(recognition.aborted);
  });

  it("결과·에러·끝이 연달아 와도 첫 결과 하나만 남는다", async () => {
    const { calls, recognition } = listenAll(50);
    recognition.audio();
    recognition.sound();
    recognition.say("commit");
    recognition.fail("network");
    recognition.end();
    await wait(120);
    assert.deepEqual(calls, [{ type: "heard", heard: ["commit"] }]);
  });

  it("끝난 뒤에 취소를 눌러도 결과가 바뀌지 않는다", async () => {
    // 화면은 끝난 뒤에도 취소 함수를 들고 있다가 떠날 때 부른다.
    const { calls, stop, recognition } = listenAll(60_000);
    recognition.audio();
    recognition.end();
    stop();
    stop();
    assert.deepEqual(calls, [{ type: "no-sound" }]);
  });
});
