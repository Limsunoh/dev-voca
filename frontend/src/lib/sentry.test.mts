/**
 * Sentry 로 나가는 오류에서 토큰·쿠키·IP 가 빠지는지 본다.
 *
 * 실행: cd frontend && npm test
 */
import assert from "node:assert/strict";
import { it } from "node:test";

import { maskUrl, scrubBreadcrumb, scrubEvent } from "./sentry";

it("주소의 토큰·번호를 가리고 쿼리와 # 뒤를 버린다", () => {
  assert.equal(
    maskUrl("https://dev-voca.vercel.app/profile/email/Ab3xToken9?x=1#top"),
    "https://dev-voca.vercel.app/profile/email/:id",
  );
  assert.equal(
    maskUrl("/api/auth/google/callback?code=4%2F0secret&state=s"),
    "/api/auth/google/callback",
  );
  assert.equal(maskUrl("/learn/words/123"), "/learn/words/:id");
});

it("헤더는 User-Agent 만 남기고 쿠키·본문·IP 를 지운다", () => {
  const event = scrubEvent({
    request: {
      url: "https://dev-voca.vercel.app/profile/email/tok3n",
      headers: {
        "user-agent": "Mozilla/5.0 (Linux; Android 15)",
        cookie: "devvoca_token=abc",
        "x-forwarded-for": "203.0.113.7",
        referer: "https://dev-voca.vercel.app/profile/email/tok3n",
      },
      cookies: { devvoca_token: "abc" },
      data: { password: "pw" },
      query_string: "code=secret",
    },
    user: { ip_address: "203.0.113.7" },
  });

  assert.deepEqual(event, {
    request: {
      url: "https://dev-voca.vercel.app/profile/email/:id",
      headers: { "user-agent": "Mozilla/5.0 (Linux; Android 15)" },
    },
  });
});

it("Next 서버 오류의 request_path 와 트랜잭션 이름 속 토큰도 가린다", () => {
  const event = scrubEvent({
    transaction: "POST /profile/email/tok3n",
    contexts: { nextjs: { request_path: "/profile/email/tok3n" } },
  });
  assert.equal(event.transaction, "POST /profile/email/:id");
  assert.equal(event.contexts?.nextjs?.request_path, "/profile/email/:id");
});

it("화면 이동과 fetch 기록의 주소도 가린다", () => {
  const crumb = scrubBreadcrumb({
    data: { from: "/profile/email/tok3n", to: "/learn/words/7?q=hi", status_code: 500 },
  });
  assert.deepEqual(crumb.data, {
    from: "/profile/email/:id",
    to: "/learn/words/:id",
    status_code: 500,
  });
});
