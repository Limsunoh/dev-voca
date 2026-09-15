/**
 * listenOnce 가 **이벤트가 오는 순서** 에 흔들리지 않는지 본다.
 *
 * 실행: cd frontend && npm test
 *
 * speech.test.mts 는 "어디까지 갔나" 로 이유를 가르는지 본다. 여기는 그
 * 판정이 인식기 구현의 순서 버릇에 따라 뒤집히지 않는지를 본다.
 *
 * 전부 한 번씩 빨간불이었다. 이유를 정하기 전에 abort() 를 부르고 있어서,
 * abort 안에서 onend·onerror 를 곧바로 부르는 구현에서는 그쪽이 먼저
 * 끝냈다 - 사용자가 "그만" 을 눌렀는데 "마이크에 소리가 안 들어와요" 가
 * 뜨는 식이다. 크롬은 이벤트를 미뤄 보내서 지금은 안 드러나지만, 다른
 * 엔진이나 크롬의 다음 버전이 순서를 바꾸면 조용히 드러난다.
 *
 * speech.test.mts 와 파일을 나눈 이유: 둘 다 window.SpeechRecognition 을
 * 가짜로 바꿔 끼우는데 가짜의 버릇(abort 에서 무엇을 곧바로 부르나)이
 * 다르다. node 테스트 러너가 파일마다 따로 돌리므로 섞이지 않는다.
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it } from "node:test";

import { listenOnce, type ListenOutcome } from "./speech";

type Handler = (() => void) | null;

class Fake {
  static last: Fake | null = null;
  static endOnAbort = false;
  static errorOnAbort = false;
  onresult: ((event: { results: unknown }) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: Handler = null;
  onaudiostart: Handler = null;
  onsoundstart: Handler = null;
  onspeechstart: Handler = null;
  lang = "";
  continuous = false;
  interimResults = false;
  maxAlternatives = 1;
  constructor() {
    Fake.last = this;
  }
  start() {}
  stop() {}
  abort() {
    if (Fake.errorOnAbort) this.onerror?.({ error: "aborted" });
    if (Fake.endOnAbort) this.onend?.();
  }
}

(globalThis as unknown as { window: unknown }).window = { SpeechRecognition: Fake };

beforeEach(() => {
  Fake.endOnAbort = false;
  Fake.errorOnAbort = false;
});

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function run(timeoutMs: number) {
  const calls: ListenOutcome[] = [];
  const stop = listenOnce((o) => calls.push(o), undefined, timeoutMs);
  return { calls, stop, r: Fake.last! };
}

describe("이벤트 순서에 흔들리지 않는다", () => {
  it("마이크가 열린 신호 없이 no-speech 가 오면 말로 안 들림이 아니다", () => {
    // 말을 한 번도 못 잡은 상태를 "소리는 들어왔는데 말이 아님" 이라고 하면 반대다.
    const { calls, r } = run(60_000);
    r.onerror?.({ error: "no-speech" });
    assert.notDeepEqual(calls, [{ type: "no-speech" }]);
  });

  it("abort 가 onend 를 동기로 부르는 인식기에서도 취소는 cancelled 다(열리기 전)", () => {
    // "그만" 은 실패가 아니다. abort 가 onend 를 곧바로 불러도 cancelled 여야 한다.
    Fake.endOnAbort = true;
    const { calls, stop } = run(60_000);
    stop();
    assert.deepEqual(calls, [{ type: "cancelled" }]);
  });

  it("같은 조건, 마이크가 열린 뒤 취소도 cancelled 다(MicCheck 가 뜨면 안 된다)", () => {
    Fake.endOnAbort = true;
    const { calls, stop, r } = run(60_000);
    r.onaudiostart?.();
    stop();
    assert.deepEqual(calls, [{ type: "cancelled" }]);
  });

  it("타임아웃 abort 가 aborted 에러를 동기로 줘도 간 자리의 이유다", async () => {
    // 끊을 때 aborted 에러가 곧바로 와도, 간 자리(마이크 열림)의 이유가 남아야 한다.
    Fake.errorOnAbort = true;
    Fake.endOnAbort = true;
    const { calls, r } = run(50);
    r.onaudiostart?.();
    await wait(120);
    assert.deepEqual(calls, [{ type: "no-sound" }]);
  });

  it("빈 results 이벤트에서 던지지 않고 곧바로 끝낸다", () => {
    // 빈 결과를 짚으면 던지고, 끝낼 사람이 없어 8초 동안 "듣는 중" 이 돈다.
    const { calls, r } = run(60_000);
    r.onaudiostart?.();
    assert.doesNotThrow(() => r.onresult?.({ results: [] }));
    assert.equal(calls.length, 1);
  });
});
