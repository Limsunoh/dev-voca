/**
 * lib/client-ip.ts 의 날짜 문을 한국 시간 0시 경계에서, 서버 시각대를 바꿔 가며 본다.
 *
 * 실행: cd frontend && npm test
 *
 * Vercel 서버는 UTC 로 돈다. 날짜를 서버 시각대로 세면 한국 시간 0시~9시 사이에 하루가
 * 어긋나 처리방침 시행 전에 IP 가 넘어가거나 시행 뒤에도 안 넘어간다. 시행일 0시(KST)는
 * UTC 로 전날 15:00 이다.
 *
 * 하네스는 client-ip.test.mts 와 같다(`server-only` 를 CJS 로더에서 빈 객체로).
 */
import assert from "node:assert/strict";
import Module from "node:module";
import { after, describe, it, mock } from "node:test";

mock.module("next/headers", {
  namedExports: {
    async headers() {
      return new Headers({ "x-forwarded-for": "203.0.113.7" });
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

const realSecret = process.env.RELAY_SECRET;
const realTz = process.env.TZ;
after(() => {
  if (realSecret === undefined) delete process.env.RELAY_SECRET;
  else process.env.RELAY_SECRET = realSecret;
  if (realTz === undefined) delete process.env.TZ;
  else process.env.TZ = realTz;
});

/** 시행일 전날 UTC 15:00(= 시행일 한국 시간 0시). */
const opening = (() => {
  const d = new Date(`${IP_FROM}T00:00:00Z`);
  d.setUTCHours(-9);
  return d.getTime();
})();

describe("IP 를 싣기 시작하는 순간(한국 시간 0시)", () => {
  for (const tz of ["UTC", "America/Los_Angeles", "Pacific/Kiritimati", "Asia/Seoul"]) {
    it(`서버 시각대가 ${tz} 여도 같다`, async () => {
      process.env.TZ = tz;
      process.env.RELAY_SECRET = ["leakmark", "relay"].join("-");
      const before = await clientIpHeaders(opening - 1);
      const on = await clientIpHeaders(opening);
      assert.equal(before["X-Next-Client-IP"], undefined, "23:59:59.999 에 IP 를 실었다");
      assert.equal(on["X-Next-Client-IP"], "203.0.113.7", "0시에 IP 를 안 실었다");
      assert.ok(before["X-Next-Relay"], "비밀값은 시행 전에도 실어야 한다");
    });
  }

  it("경계는 UTC 전날 15:00 이다", () => {
    assert.equal(new Date(opening).toISOString().slice(11, 19), "15:00:00");
  });
});
