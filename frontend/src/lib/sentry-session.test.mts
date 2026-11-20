/**
 * 폰 화면 SDK(@sentry/nextjs 의 브라우저 판)를 SENTRY_OPTIONS 로 실제로 init 해서, 오류가
 * 없으면 아무것도 안 나가고 오류가 나면 그 오류 하나만 나가는지 본다.
 *
 * 처리방침 2절 사목이 "앱 화면에서는 오류가 났을 때만 보낸다" 고 적는다. 화면 SDK 는 기본으로
 * 화면을 열 때마다 "세션 시작" 봉투(session)를 보내서, SENTRY_OPTIONS.integrations 가
 * BrowserSession 을 뺀다. sentry.test.mts 는 그 함수에 이름 목록을 넣어 볼 뿐이라, SDK 가
 * 이름을 바꾸거나 다른 길로 세션을 보내면 모른다. 여기서는 SDK 가 고른 기본 기능 전부로
 * 돌리고 전송 계층만 가로챈다.
 *
 * Node 에는 브라우저가 없어서 SDK 가 보는 만큼만 window·document·history 를 흉내 낸다.
 * document 가 없으면 BrowserSession 이 스스로 꺼지므로, 마지막 테스트가 integrations 를 뺀
 * 설정으로 session 봉투가 실제로 잡히는지 확인한다(이 하네스가 세션을 볼 수 있다는 대조군).
 *
 * 실행: cd frontend && npx tsx --test --experimental-test-module-mocks src/lib/sentry-session.test.mts
 */
import assert from "node:assert/strict";
import { afterEach, beforeEach, it } from "node:test";

import { createTransport, getCurrentScope, getIsolationScope } from "@sentry/core";

import { SENTRY_OPTIONS } from "./sentry";

// 패키지의 exports 는 Node 에서 서버 판을 고른다. 폰 화면이 받는 판을 파일로 직접 연다.
const Sentry = await import(
  new URL("../../node_modules/@sentry/nextjs/build/esm/index.client.js", import.meta.url).href
);

const FAKE_DSN = "https://public@o0.ingest.invalid/1";
const PAGE_TOKEN = "PageTokM3v8";
const QUERY_CODE = "QueryCodeK2j6";
const REFERRER_TOKEN = "RefTokW5q1";
const COOKIE_VALUE = "CookieValH7d4";
const USER_EMAIL = "probe-user@example.com";
const USER_IP = "198.51.100.23";

const SECRETS = [PAGE_TOKEN, QUERY_CODE, REFERRER_TOKEN, COOKIE_VALUE, USER_EMAIL, USER_IP];

// SDK 가 브라우저에서 읽는 것만 둔다. 이벤트는 Node 의 EventTarget 으로 실제로 전달한다.
const windowEvents = new EventTarget();
const fakeWindow = {
  document: Object.assign(new EventTarget(), {
    visibilityState: "visible",
    prerendering: false,
    readyState: "complete",
    referrer: `https://dev-voca.vercel.app/profile/email/${REFERRER_TOKEN}`,
    cookie: `devvoca_token=${COOKIE_VALUE}`,
    // Next 경로 계측이 __NEXT_DATA__ 를 찾는다. App Router 화면에는 없다.
    getElementById() {
      return null;
    },
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  }),
  location: {
    href: `https://dev-voca.vercel.app/profile/email/${PAGE_TOKEN}?code=${QUERY_CODE}`,
    origin: "https://dev-voca.vercel.app",
    protocol: "https:",
    host: "dev-voca.vercel.app",
    pathname: `/profile/email/${PAGE_TOKEN}`,
  },
  history: { pushState() {}, replaceState() {} },
  // App Router 가 window.next.router 에 둔다. 없으면 SDK 가 20ms 마다 10초 동안 찾는다.
  next: {
    router: {
      push(href: string) {
        globalThis.history.pushState(null, "", href);
      },
      replace(href: string) {
        globalThis.history.replaceState(null, "", href);
      },
      back() {},
      forward() {},
    },
  },
  addEventListener: windowEvents.addEventListener.bind(windowEvents),
  removeEventListener: windowEvents.removeEventListener.bind(windowEvents),
  // 브라우저는 한가할 때 부른다. 기다리는 시간 없이 바로 불러 결과를 고정한다.
  requestIdleCallback(fn: () => void) {
    fn();
  },
};
Object.assign(fakeWindow.document, { location: fakeWindow.location });
for (const [key, value] of Object.entries(fakeWindow)) {
  Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
}
Object.defineProperty(globalThis, "navigator", {
  value: { userAgent: "Mozilla/5.0 (Linux; Android 15)", language: "ko-KR" },
  configurable: true,
});

let sent: string[] = [];

function init(options: Record<string, unknown>) {
  sent = [];
  return Sentry.init({
    ...options,
    dsn: FAKE_DSN,
    // release 가 없으면 SDK 가 session 을 스스로 버린다. 운영 빌드는 Sentry 빌드 도구가
    // 넣어 준다. 없이 돌리면 첫 테스트가 세션을 끄지 않아도 통과한다.
    release: "test-release",
    transport: (transportOptions: Parameters<typeof createTransport>[0]) =>
      createTransport(transportOptions, async (request) => {
        const body = request.body;
        sent.push(typeof body === "string" ? body : new TextDecoder().decode(body));
        return { statusCode: 200 };
      }),
  });
}

/** 보낸 봉투를 [머리, 항목머리, 항목, ...] 줄로 풀어 항목 종류(event, session ...)를 고른다. */
function itemTypes(): string[] {
  return sent.flatMap((envelope) =>
    envelope
      .split("\n")
      .filter((line, index) => index % 2 === 1 && line)
      .map((line) => JSON.parse(line).type as string),
  );
}

/** 앱을 내리거나 다른 앱으로 넘어갈 때. SDK 는 이때 모아 둔 것을 내보낸다. */
async function hideApp() {
  fakeWindow.document.visibilityState = "hidden";
  fakeWindow.document.dispatchEvent(new Event("visibilitychange"));
  await new Promise<void>((resolve) => queueMicrotask(resolve));
}

function errorEvents(): Record<string, unknown>[] {
  return sent
    .flatMap((envelope) => envelope.split("\n"))
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter((item) => item && item.exception);
}

function navigate(path: string) {
  // <Link> 와 useRouter().push 가 부르는 길 그대로: router.push 가 history.pushState 를 부른다.
  (globalThis as unknown as { next: { router: { push(href: string): void } } }).next.router.push(path);
}

beforeEach(() => {
  fakeWindow.document.visibilityState = "visible";
  // 앞 테스트가 시작한 세션이 남으면 오류와 함께 session 갱신이 나간다.
  getIsolationScope().setSession();
  getCurrentScope().setSession();
  getIsolationScope().setUser(null);
  getCurrentScope().setUser(null);
});

afterEach(async () => {
  await Sentry.getClient()?.close(1000);
});

it("오류 없이 시작하고 화면을 옮기기만 하면 아무것도 안 나간다(session 봉투 없음)", async () => {
  const client = init(SENTRY_OPTIONS);
  assert.ok(client, "init 이 클라이언트를 만들지 않았다");
  assert.equal(client.getIntegrationByName("BrowserSession"), undefined);
  // 나머지 기본 기능은 살아 있어야 오류를 잡는다.
  assert.ok(client.getIntegrationByName("GlobalHandlers"));
  assert.ok(client.getIntegrationByName("Breadcrumbs"));

  navigate("/learn/words");
  navigate("/test/quick");
  navigate("/board");
  await hideApp();
  await client.flush(1000);

  assert.deepEqual(itemTypes(), []);
  assert.equal(sent.length, 0, sent.join("\n---\n"));
});

it("잡히지 않은 오류가 나면 event 하나만 나가고 쿠키·사용자·이메일·IP 가 없다", async () => {
  const client = init(SENTRY_OPTIONS);
  Sentry.setUser({ id: "7", email: USER_EMAIL, ip_address: USER_IP });
  navigate("/learn/words");

  // 브라우저가 잡히지 않은 오류를 window.onerror 로 넘기는 모양 그대로.
  const error = new Error("probe browser failure");
  const onerror = (globalThis as unknown as { onerror: (...args: unknown[]) => void }).onerror;
  assert.equal(typeof onerror, "function", "GlobalHandlers 가 onerror 를 걸지 않았다");
  onerror(error.message, "https://dev-voca.vercel.app/_next/static/chunks/app.js", 1, 1, error);
  await client.flush(1000);

  assert.deepEqual(itemTypes(), ["event"]);
  const [event] = errorEvents();
  const exc = (event.exception as { values: { value: string }[] }).values[0];
  assert.equal(exc.value, "probe browser failure");

  assert.equal(event.user, undefined);
  const request = event.request as { url?: string; headers?: Record<string, string>; cookies?: unknown };
  assert.equal(request?.cookies, undefined);
  assert.equal(request?.url, "https://dev-voca.vercel.app/profile/email/:id");
  assert.deepEqual(Object.keys(request?.headers ?? {}).map((k) => k.toLowerCase()), ["user-agent"]);

  const text = sent.join("\n");
  const leaked = SECRETS.filter((secret) => text.includes(secret));
  assert.deepEqual(leaked, [], `봉투에 실렸다: ${leaked.join(", ")}`);
  assert.ok(!text.includes("{{auto}}"), "IP 를 서버가 채우라는 표시가 있다");
  // 봉투 머리의 SDK 설정. "never" 면 Sentry 서버도 접속 IP 를 채워 넣지 않는다.
  assert.match(text, /"infer_ip":"never"/);
  assert.ok(!/"ip_address"/.test(text), "ip_address 칸이 있다");
  assert.ok(!/"email"/.test(text), "email 칸이 있다");
  assert.ok(!/"cookies?"/i.test(text), "cookie 칸이 있다");
});

it("대조군: integrations 를 빼면 화면을 열자마자 session 봉투가 나간다", async () => {
  // 이 테스트가 실패하면 위 두 테스트의 "안 나간다" 는 하네스가 세션을 못 봐서일 수 있다.
  const withoutFilter: Record<string, unknown> = { ...SENTRY_OPTIONS };
  delete withoutFilter.integrations;
  const client = init(withoutFilter);
  assert.ok(client.getIntegrationByName("BrowserSession"));
  navigate("/learn/sentences");
  await client.flush(1000);

  assert.ok(itemTypes().includes("session"), `session 봉투가 없다: ${itemTypes().join(",")}`);
  assert.ok(!itemTypes().includes("event"));
});
