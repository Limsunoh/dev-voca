/**
 * 실제 Sentry SDK 로 오류를 만들어, 밖으로 나가는 봉투(envelope)에 토큰·쿠키·IP 가 없는지 본다.
 *
 * sentry.test.mts 는 scrubEvent 를 손으로 만든 객체에 부른다. 여기서는 SENTRY_OPTIONS 를
 * 그대로 클라이언트에 넣고 전송 계층만 바꿔 끼운다. SDK 가 붙이는 요청 정보·contexts·
 * breadcrumb 까지 봉투 문자열 전체를 검사한다. 가짜 DSN(.invalid) 이라 네트워크로는 안 나간다.
 *
 * 실행: cd frontend && npm test
 */
import assert from "node:assert/strict";
import { afterEach, beforeEach, it } from "node:test";

import {
  addBreadcrumb,
  captureException,
  createStackParser,
  createTransport,
  getCurrentScope,
  getIsolationScope,
  requestDataIntegration,
  setCurrentClient,
  withScope,
} from "@sentry/core";
import type { ErrorEvent } from "@sentry/core";
import { ServerRuntimeClient, nodeStackLineParser } from "@sentry/core/server";
import { captureRequestError } from "@sentry/nextjs";

import { SENTRY_OPTIONS, maskUrl } from "./sentry";

const FAKE_DSN = "https://public@o0.ingest.invalid/1";
const USER_AGENT = "Mozilla/5.0 (Linux; Android 15)";

// 서로 겹치지 않는 영숫자라 봉투 문자열에서 바로 찾을 수 있다.
const COOKIE_TOKEN = "CookieTokZ9k2";
const AUTH_TOKEN = "AuthTokR4t8";
const CLIENT_IP = "203.0.113.77";
const PATH_TOKEN = "PathTokAb3x9";
const QUERY_CODE = "QueryCodeP5n1";
const RELAY_SECRET = "RelaySecretQ7w3";
const PASSWORD = "PasswdX4m8";

const SECRETS = [COOKIE_TOKEN, AUTH_TOKEN, CLIENT_IP, PATH_TOKEN, QUERY_CODE, RELAY_SECRET, PASSWORD];

const REQUEST_HEADERS = {
  "user-agent": USER_AGENT,
  cookie: `devvoca_token=${COOKIE_TOKEN}`,
  authorization: `Token ${AUTH_TOKEN}`,
  "x-forwarded-for": CLIENT_IP,
  "x-next-relay": RELAY_SECRET,
  "x-next-client-ip": CLIENT_IP,
  referer: `https://dev-voca.vercel.app/profile/email/${PATH_TOKEN}?code=${QUERY_CODE}`,
};

let sent: string[] = [];
let client: ServerRuntimeClient;

beforeEach(() => {
  sent = [];
  for (const scope of [getCurrentScope(), getIsolationScope()]) {
    scope.clearBreadcrumbs();
    scope.setUser(null);
  }
  client = new ServerRuntimeClient({
    ...SENTRY_OPTIONS,
    dsn: FAKE_DSN,
    integrations: [requestDataIntegration()],
    stackParser: createStackParser(nodeStackLineParser()),
    transport: (options) =>
      createTransport(options, async (request) => {
        const body = request.body;
        sent.push(typeof body === "string" ? body : new TextDecoder().decode(body));
        return { statusCode: 200 };
      }),
  });
  setCurrentClient(client);
  client.init();
});

afterEach(async () => {
  await client.close(1000);
});

async function envelope(): Promise<string> {
  await client.flush(1000);
  return sent.join("\n");
}

function events(text: string): ErrorEvent[] {
  return text
    .split("\n")
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter((item) => item && item.exception);
}

function assertNoSecret(text: string) {
  const leaked = SECRETS.filter((secret) => text.includes(secret));
  assert.deepEqual(leaked, [], `Sentry 로 나가는 봉투에 실렸다: ${leaked.join(", ")}`);
}

it("서버 요청 정보와 함께 난 오류에 쿠키·인증·IP·토큰 주소가 없다", async () => {
  withScope((scope) => {
    scope.setSDKProcessingMetadata({
      normalizedRequest: {
        method: "POST",
        url: `https://dev-voca.vercel.app/profile/email/${PATH_TOKEN}?code=${QUERY_CODE}`,
        query_string: `code=${QUERY_CODE}`,
        headers: REQUEST_HEADERS,
        cookies: { devvoca_token: COOKIE_TOKEN },
        data: { password: PASSWORD },
      },
      ipAddress: CLIENT_IP,
    });
    scope.setUser({ ip_address: CLIENT_IP, email: "probe@example.com" });
    captureException(new Error("probe failure"));
  });

  const text = await envelope();
  assertNoSecret(text);
  assert.ok(!text.includes("probe@example.com"));

  const [event] = events(text);
  const exc = event.exception!.values![0];
  assert.equal(exc.type, "Error");
  assert.equal(exc.value, "probe failure");
  assert.ok(exc.stacktrace!.frames!.length > 0);
  assert.equal(event.request?.url, "https://dev-voca.vercel.app/profile/email/:id");
  assert.deepEqual(event.request?.headers, { "user-agent": USER_AGENT });
  assert.equal(event.user, undefined);
});

it("Next 의 onRequestError(captureRequestError) 가 싣는 요청 경로에도 토큰이 없다", async () => {
  captureRequestError(
    new Error("render failure"),
    {
      path: `/profile/email/${PATH_TOKEN}?code=${QUERY_CODE}`,
      method: "GET",
      headers: REQUEST_HEADERS,
    },
    { routerKind: "App Router", routePath: "/profile/email/[token]", routeType: "render" },
  );

  const text = await envelope();
  assert.equal(events(text).length, 1);
  assertNoSecret(text);
});

it("화면 이동·fetch breadcrumb 의 토큰·쿼리가 봉투에 없다", async () => {
  addBreadcrumb({
    category: "navigation",
    data: { from: `/profile/email/${PATH_TOKEN}`, to: `/learn/words?code=${QUERY_CODE}` },
  });
  addBreadcrumb({
    category: "fetch",
    type: "http",
    data: { method: "GET", url: `/api/accounts/email/${PATH_TOKEN}/?code=${QUERY_CODE}`, status_code: 500 },
  });
  captureException(new Error("after navigation"));

  const text = await envelope();
  assertNoSecret(text);
  const crumbs = events(text)[0].breadcrumbs ?? [];
  assert.deepEqual(
    crumbs.map((c) => c.data),
    [
      { from: "/profile/email/:id", to: "/learn/words" },
      { method: "GET", url: "/api/accounts/email/:id/", status_code: 500 },
    ],
  );
});

it("maskUrl 경계: 대문자·숫자·25자 이상·인코딩·한글 조각은 가리고 영어 소문자 이름은 남긴다", () => {
  assert.equal(maskUrl("/Profile/email"), "/:id/email");
  assert.equal(maskUrl("/learn/words2"), "/learn/:id");
  assert.equal(maskUrl(`/x/${"a".repeat(24)}`), `/x/${"a".repeat(24)}`);
  assert.equal(maskUrl(`/x/${"a".repeat(25)}`), "/x/:id");
  assert.equal(maskUrl("/x/%41bc"), "/x/:id");
  assert.equal(maskUrl("/x/a%2Fb"), "/x/:id");
  assert.equal(maskUrl("/learn/한글"), "/learn/:id");
  assert.equal(maskUrl("/learn/daily-study_x"), "/learn/daily-study_x");
  assert.equal(maskUrl("/-x/_y"), "/:id/:id");
});

it("maskUrl 경계: 상대 주소·잘못된 주소·사용자 정보·백슬래시", () => {
  assert.equal(maskUrl("profile/email/Tok3n"), "/profile/email/:id");
  assert.equal(maskUrl("?code=secret#frag"), "/");
  assert.equal(maskUrl(""), "/");
  assert.equal(maskUrl("http://[::1"), ":url");
  // 주소에 든 아이디·비밀번호는 남기지 않는다.
  assert.equal(maskUrl("https://user:pw@dev-voca.vercel.app:8443/a/B"), "https://dev-voca.vercel.app:8443/a/:id");
  // 백슬래시는 http 주소에서 / 로 읽힌다. 그 사이 토큰도 가린다.
  assert.equal(maskUrl("https://dev-voca.vercel.app/profile\\email\\Tok3n"), "https://dev-voca.vercel.app/profile/email/:id");
  // .. 는 정리된 뒤 가린다.
  assert.equal(maskUrl("/a/../profile/email/Tok3n"), "/profile/email/:id");
});
