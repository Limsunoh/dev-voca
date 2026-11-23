/**
 * proxy 의 로그인 이어 가기. 백엔드는 fetch 를 바꿔 끼워 흉내 낸다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - 하루 지난 쿠키(또는 발급 시각이 없는 옛 쿠키)만 백엔드에 묻는다. 그 밖에는 부르지 않는다.
 *   - 새 토큰을 받으면 응답 쿠키만 바꾼다. 이번 화면은 옛 토큰으로 그린다. 브라우저가 새 쿠키를
 *     받아 다음 요청에 실어 와야 백엔드가 옛 토큰을 끝낸다(LoginToken.mark_delivered). 이번
 *     화면에 넘기면 응답을 잃은 사람이 로그아웃된다.
 *   - 401 이면 쿠키를 지운다. 백엔드가 늦거나 죽었으면 아무것도 안 바꾼다.
 *   - GET 만 본다(서버 액션은 스스로 쿠키를 쓴다).
 */
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";

import { NextRequest } from "next/server";

import { proxy } from "./proxy";

const ORIGIN = "https://dev-voca.vercel.app";
const OLD = "a".repeat(40);
const NEW = "b".repeat(40);
const DAY = 24 * 60 * 60;

type Call = { url: string; init?: RequestInit };
let calls: Call[];
let reply: () => Promise<Response>;
const realFetch = globalThis.fetch;

beforeEach(() => {
  calls = [];
  reply = async () => Response.json({ token: NEW, issued_at: 1_900_000_000 });
  process.env.API_URL = "http://backend.test";
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return reply();
  }) as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

function now(): number {
  return Math.floor(Date.now() / 1000);
}

function page(cookie?: string, method = "GET") {
  const headers = new Headers();
  if (cookie) headers.set("cookie", cookie);
  return proxy(new NextRequest(`${ORIGIN}/learn/words`, { method, headers }));
}

/** 이번 화면에 넘긴 요청 쿠키. NextResponse.next({ request }) 가 이 이름으로 싣는다. */
function forwardedCookie(res: Response): string | null {
  return res.headers.get("x-middleware-request-cookie");
}

describe("proxy 로그인 이어 가기", () => {
  it("로그인 쿠키가 없으면 백엔드를 부르지 않는다", async () => {
    const res = await page("devvoca_guest=1");
    assert.equal(calls.length, 0);
    assert.equal(res.headers.get("set-cookie"), null);
  });

  it("하루가 안 된 쿠키는 부르지 않는다", async () => {
    const res = await page(`devvoca_token=${OLD}.${now() - DAY + 60}`);
    assert.equal(calls.length, 0);
    assert.equal(res.headers.get("set-cookie"), null);
  });

  it("발급 시각이 없는 옛 쿠키는 바로 이어 가고, 응답 쿠키만 바꾼다", async () => {
    const res = await page(`devvoca_guest=1; devvoca_token=${OLD}; other=x`);

    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "http://backend.test/api/accounts/token/renew/");
    assert.equal(calls[0].init?.method, "POST");
    assert.equal(new Headers(calls[0].init?.headers).get("authorization"), `Token ${OLD}`);

    const setCookie = res.headers.get("set-cookie") ?? "";
    assert.match(setCookie, new RegExp(`^devvoca_token=${NEW}\\.1900000000;`));
    assert.match(setCookie, /HttpOnly/i);
    assert.match(setCookie, /Path=\//);
    assert.match(setCookie, /SameSite=lax/i);

    // 이번 화면은 옛 토큰으로 그린다. Next 가 화면에 쿠키를 넘기는 길은 둘이다. 요청 머리
    // 덮어쓰기(x-middleware-request-cookie)와 response.cookies 로 넣은 값을 합치는 것
    // (x-middleware-set-cookie, request-store.js 의 mergeMiddlewareCookies). 둘 다 옛 토큰이어야 한다.
    assert.equal(forwardedCookie(res), `devvoca_guest=1; devvoca_token=${OLD}; other=x`);
    assert.equal(res.headers.get("x-middleware-set-cookie"), null);
  });

  it("하루 지난 쿠키도 이어 간다", async () => {
    await page(`devvoca_token=${OLD}.${now() - DAY - 1}`);
    assert.equal(calls.length, 1);
  });

  it("401 이면 쿠키를 지우고, 이번 화면도 로그아웃 상태로 그린다", async () => {
    reply = async () => Response.json({ detail: "Invalid token." }, { status: 401 });
    const res = await page(`devvoca_token=${OLD}; devvoca_guest=1`);

    assert.match(res.headers.get("x-middleware-set-cookie") ?? "", /^devvoca_token=;/);

    const setCookie = res.headers.get("set-cookie") ?? "";
    assert.match(setCookie, /^devvoca_token=;/);
    assert.match(setCookie, /Path=\//);
    assert.match(setCookie, /Expires=Thu, 01 Jan 1970/);
  });

  it("백엔드가 500 이거나 연결이 안 되면 쿠키를 건드리지 않는다", async () => {
    for (const fail of [
      async () => new Response("oops", { status: 500 }),
      async () => {
        throw new TypeError("fetch failed");
      },
    ]) {
      reply = fail;
      const res = await page(`devvoca_token=${OLD}`);
      assert.equal(res.headers.get("set-cookie"), null);
      assert.equal(forwardedCookie(res), `devvoca_token=${OLD}`);
    }
  });

  it("응답의 토큰이 16진수가 아니면 받지 않는다", async () => {
    reply = async () => Response.json({ token: "x; Path=/evil", issued_at: 1 });
    const res = await page(`devvoca_token=${OLD}`);
    assert.equal(res.headers.get("set-cookie"), null);
  });

  it("GET 이 아니면 부르지 않는다", async () => {
    await page(`devvoca_token=${OLD}`, "POST");
    assert.equal(calls.length, 0);
  });
});
