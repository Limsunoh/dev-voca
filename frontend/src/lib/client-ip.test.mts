/**
 * lib/client-ip.ts 의 clientIpHeaders: 가입·로그인 요청에 싣는 머리.
 *
 * 실행: cd frontend && npm test
 *
 * 계약.
 *   1. RELAY_SECRET 이 없으면(로컬) 아무것도 싣지 않는다.
 *   2. 있으면 비밀값(X-Next-Relay)은 늘 싣는다. 백엔드가 Next 에서 온 요청을 가르는 표시다.
 *   3. 접속 IP(X-Next-Client-IP)는 처리방침 v3 시행일(IP_FROM, 한국 시간)부터만 싣는다.
 *      x-forwarded-for 의 맨 앞(접속자)만 싣고, 없거나 비면 싣지 않는다.
 *   4. IP_FROM, 백엔드 IP_COUNT_FROM, 처리방침 시행일이 같다(v3 동안).
 *
 * 하네스: client-ip.ts 맨 위의 `import "server-only"` 는 Next 번들러 밖에서 해석되지
 * 않아 CJS 로더에서 그 이름만 빈 객체로 돌려준다(session-stale-token.test.mts 와 같다).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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

const { IP_FROM, clientIpHeaders } = await import("./client-ip");
const { DOC_VERSION, PRIVACY_CHANGE } = await import("../components/LegalDoc");

// 비밀값처럼 생긴 글자를 이름 옆에 적지 않는다(GitGuardian, #169·#170).
const MARK = ["leakmark", "relay"].join("-");
const realSecret = process.env.RELAY_SECRET;

/** 한국 시간 그날 0시와 그 1밀리초 전. */
const kstMidnight = (iso: string) => Date.parse(`${iso}T00:00:00+09:00`);
const ON = kstMidnight(IP_FROM);
const BEFORE = ON - 1;

afterEach(() => {
  incoming = new Headers();
  if (realSecret === undefined) delete process.env.RELAY_SECRET;
  else process.env.RELAY_SECRET = realSecret;
});

describe("clientIpHeaders", () => {
  it("비밀값이 없으면 아무것도 싣지 않는다", async () => {
    delete process.env.RELAY_SECRET;
    incoming = new Headers({ "x-forwarded-for": "203.0.113.7" });
    assert.deepEqual(await clientIpHeaders(ON), {});
  });

  it("시행일 전에는 비밀값만 싣고 IP 는 싣지 않는다", async () => {
    process.env.RELAY_SECRET = MARK;
    incoming = new Headers({ "x-forwarded-for": "203.0.113.7" });
    assert.deepEqual(await clientIpHeaders(BEFORE), { "X-Next-Relay": MARK });
  });

  it("시행일(한국 시간 0시)부터 비밀값과 접속 IP 를 싣는다", async () => {
    process.env.RELAY_SECRET = MARK;
    incoming = new Headers({ "x-forwarded-for": "203.0.113.7" });
    assert.deepEqual(await clientIpHeaders(ON), {
      "X-Next-Relay": MARK,
      "X-Next-Client-IP": "203.0.113.7",
    });
  });

  it("프록시를 거친 꼴이면 맨 앞 접속자만 싣는다", async () => {
    process.env.RELAY_SECRET = MARK;
    incoming = new Headers({ "x-forwarded-for": " 2001:db8::1 , 10.0.0.1" });
    assert.equal((await clientIpHeaders(ON))["X-Next-Client-IP"], "2001:db8::1");
  });

  it("접속 IP 가 없으면 비밀값만 싣는다", async () => {
    process.env.RELAY_SECRET = MARK;
    for (const value of [undefined, "", " , 10.0.0.1"]) {
      incoming = new Headers(value === undefined ? {} : { "x-forwarded-for": value });
      assert.deepEqual(
        await clientIpHeaders(ON),
        { "X-Next-Relay": MARK },
        `x-forwarded-for=${value}`,
      );
    }
  });
});

// v3 에만 해당한다. 날짜 문을 지울 때(client-ip.ts 의 ponytail 주석) 이 절도 지운다.
describe("IP 를 넘기기 시작하는 날", { skip: DOC_VERSION !== "v3" }, () => {
  it("처리방침 v3 시행일과 같다", () => {
    // 먼저 보내면 처리방침이 알리기 전에 IP 가 Railway 로 넘어간다.
    assert.equal(IP_FROM, PRIVACY_CHANGE.effective);
  });

  it("백엔드가 IP 로 세기 시작하는 날과 같다", () => {
    const source = readFileSync(
      new URL("../../../backend/apps/accounts/throttles.py", import.meta.url),
      "utf-8",
    );
    const m = source.match(/^IP_COUNT_FROM = date\((\d+), (\d+), (\d+)\)/m);
    assert.ok(m, "IP_COUNT_FROM 을 못 찾았다");
    const server = [m[1], m[2].padStart(2, "0"), m[3].padStart(2, "0")].join("-");
    assert.equal(server, IP_FROM);
  });
});
