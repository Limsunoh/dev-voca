/**
 * lib/client-ip.ts 의 clientIpHeaders: 가입·로그인 요청에 싣는 머리.
 *
 * 실행: cd frontend && npm test
 *
 * 계약.
 *   1. RELAY_SECRET 이 없으면(로컬) 아무것도 싣지 않는다.
 *   2. 있으면 비밀값(X-Next-Relay)은 늘 싣는다. 백엔드가 Next 에서 온 요청을 가르는 표시다.
 *   3. 접속 IP(X-Next-Client-IP)는 x-forwarded-for 의 맨 앞(접속자)만 싣고, 없거나 비면
 *      싣지 않는다.
 *
 * 하네스: client-ip.ts 맨 위의 `import "server-only"` 는 Next 번들러 밖에서 해석되지
 * 않아 CJS 로더에서 그 이름만 빈 객체로 돌려준다(session-stale-token.test.mts 와 같다).
 */
import assert from "node:assert/strict";
import Module from "node:module";
import { afterEach, describe, it, mock } from "node:test";

let incoming = new Headers();
mock.module("next/headers", {
  namedExports: {
    async headers() {
      return incoming;
    },
  },
});

const loader = Module as unknown as {
  _load: (request: string, ...rest: unknown[]) => unknown;
};
const realLoad = loader._load;
loader._load = function (this: unknown, request: string, ...rest: unknown[]) {
  if (request === "server-only") return {};
  return realLoad.call(this, request, ...rest);
};

const { clientIpHeaders } = await import("./client-ip");

// 비밀값처럼 생긴 글자를 이름 옆에 적지 않는다(GitGuardian, #169·#170).
const MARK = ["leakmark", "relay"].join("-");
const realSecret = process.env.RELAY_SECRET;

afterEach(() => {
  incoming = new Headers();
  if (realSecret === undefined) delete process.env.RELAY_SECRET;
  else process.env.RELAY_SECRET = realSecret;
});

describe("clientIpHeaders", () => {
  it("비밀값이 없으면 아무것도 싣지 않는다", async () => {
    delete process.env.RELAY_SECRET;
    incoming = new Headers({ "x-forwarded-for": "203.0.113.7" });
    assert.deepEqual(await clientIpHeaders(), {});
  });

  it("비밀값과 접속 IP 를 싣는다", async () => {
    process.env.RELAY_SECRET = MARK;
    incoming = new Headers({ "x-forwarded-for": "203.0.113.7" });
    assert.deepEqual(await clientIpHeaders(), {
      "X-Next-Relay": MARK,
      "X-Next-Client-IP": "203.0.113.7",
    });
  });

  it("프록시를 거친 꼴이면 맨 앞 접속자만 싣는다", async () => {
    process.env.RELAY_SECRET = MARK;
    incoming = new Headers({ "x-forwarded-for": " 2001:db8::1 , 10.0.0.1" });
    assert.equal((await clientIpHeaders())["X-Next-Client-IP"], "2001:db8::1");
  });

  it("접속 IP 가 없으면 비밀값만 싣는다", async () => {
    process.env.RELAY_SECRET = MARK;
    for (const value of [undefined, "", " , 10.0.0.1"]) {
      incoming = new Headers(value === undefined ? {} : { "x-forwarded-for": value });
      assert.deepEqual(
        await clientIpHeaders(),
        { "X-Next-Relay": MARK },
        `x-forwarded-for=${value}`,
      );
    }
  });
});
