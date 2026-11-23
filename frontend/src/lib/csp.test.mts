/**
 * 화면 응답의 CSP 문자열을 본다. 그것을 싣는 proxy 는 src/proxy.test.mts.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - nonce 는 요청마다 다르다. 같으면 한 번 본 값으로 스크립트를 넣을 수 있다.
 *   - 스크립트는 nonce 와 strict-dynamic 으로만 돈다. script-src 에 'unsafe-inline' 이
 *     들어가면 끼어든 <script> 가 돈다.
 *   - 스타일은 'unsafe-inline' 이고 nonce 가 없다. nonce 가 있으면 브라우저가
 *     'unsafe-inline' 을 무시해 화면의 style 속성이 전부 막힌다.
 *   - 다른 사이트의 iframe 에 못 들어가고, 플러그인(object)은 없다.
 *   - Sentry 주소는 DSN 에서 뽑고, DSN 이 없으면 뺀다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildCsp, newNonce, sentryOrigin } from "./csp";

const DSN = "https://abc123@o4507.ingest.us.sentry.io/4508";

/** "script-src a b; style-src c" 를 { "script-src": ["a","b"], ... } 로. */
function parse(csp: string): Record<string, string[]> {
  return Object.fromEntries(
    csp.split(";").map((part) => {
      const [name, ...values] = part.trim().split(/\s+/);
      return [name, values];
    }),
  );
}

describe("buildCsp", () => {
  it("nonce 가 요청마다 다르고 script-src 에 그대로 들어간다", () => {
    const nonces = new Set(Array.from({ length: 50 }, () => newNonce()));
    assert.equal(nonces.size, 50);
    const nonce = newNonce();
    assert.ok(parse(buildCsp(nonce))["script-src"].includes(`'nonce-${nonce}'`));
  });

  it("스크립트는 nonce 와 strict-dynamic 으로만 돈다", () => {
    const script = parse(buildCsp("n"))["script-src"];
    assert.ok(script.includes("'strict-dynamic'"));
    assert.ok(!script.includes("'unsafe-inline'"));
    assert.ok(!script.includes("'unsafe-eval'"));
    // 개발 서버에서만 eval 을 연다.
    assert.ok(parse(buildCsp("n", { dev: true }))["script-src"].includes("'unsafe-eval'"));
  });

  it("스타일은 unsafe-inline 이고 nonce 가 없다", () => {
    const style = parse(buildCsp("n"))["style-src"];
    assert.ok(style.includes("'unsafe-inline'"));
    assert.ok(!style.some((v) => v.startsWith("'nonce-")));
  });

  it("iframe 에 못 들어가고 object·base 를 막는다", () => {
    const d = parse(buildCsp("n"));
    assert.deepEqual(d["frame-ancestors"], ["'none'"]);
    assert.deepEqual(d["object-src"], ["'none'"]);
    assert.deepEqual(d["base-uri"], ["'self'"]);
    assert.deepEqual(d["form-action"], ["'self'"]);
    assert.deepEqual(d["default-src"], ["'self'"]);
    assert.deepEqual(d["worker-src"], ["'self'"]);
  });

  it("그림은 우리 주소, data:, 구글 프로필 사진만 받는다", () => {
    // 순위표·내 정보가 구글이 준 사진 주소(lh3.googleusercontent.com)를 그대로 그린다.
    // 빠지면 구글로 가입한 사람의 사진이 전부 빈칸이 된다. data: 는 구글 로그인 버튼 로고.
    assert.deepEqual(parse(buildCsp("n"))["img-src"], [
      "'self'",
      "data:",
      "https://*.googleusercontent.com",
    ]);
  });

  it("구글 로그인은 /gsi/ 아래만 연다", () => {
    const d = parse(buildCsp("n"));
    assert.deepEqual(d["frame-src"], ["https://accounts.google.com/gsi/"]);
    assert.ok(d["script-src"].includes("https://accounts.google.com/gsi/client"));
    assert.ok(d["connect-src"].includes("https://accounts.google.com/gsi/"));
  });

  it("Sentry 주소는 DSN 에서 키를 빼고 뽑는다", () => {
    const connect = parse(buildCsp("n", { sentryDsn: DSN }))["connect-src"];
    assert.ok(connect.includes("https://o4507.ingest.us.sentry.io"));
    assert.ok(!connect.join(" ").includes("abc123"));
  });

  it("Sentry 주소는 브라우저가 비교하는 모양(소문자 호스트, 포트 유지, 경로 없음)이다", () => {
    // 브라우저는 보낼 주소를 소문자 호스트로 맞춰 비교한다. 포트를 떨구면 자체 호스팅
    // Sentry 로 가는 전송이 막히고, 경로가 남으면 그 아래만 열린다.
    assert.equal(sentryOrigin("HTTPS://k@O1.Ingest.Sentry.io/2"), "https://o1.ingest.sentry.io");
    assert.equal(sentryOrigin("https://k@sentry.example.com:8443/1"), "https://sentry.example.com:8443");
    assert.equal(sentryOrigin("https://k@sentry.example.com/sub/1"), "https://sentry.example.com");
  });

  it("개발 모드여도 eval 말고는 열지 않는다", () => {
    const prod = parse(buildCsp("n"));
    const dev = parse(buildCsp("n", { dev: true }));
    assert.deepEqual(dev["script-src"].filter((v) => v !== "'unsafe-eval'"), prod["script-src"]);
    for (const name of Object.keys(prod).filter((n) => n !== "script-src")) {
      assert.deepEqual(dev[name], prod[name], name);
    }
  });

  it("DSN 이 없거나 이상하면 Sentry 주소를 넣지 않는다", () => {
    for (const dsn of [
      undefined,
      "",
      "not a url",
      "http://k@o1.ingest.sentry.io/2",
      // URL 은 호스트에 ";" 를 허락한다. 그대로 넣으면 정책에 sandbox 지시어가 끼어든다.
      "https://k@a.com;sandbox/1",
    ]) {
      assert.equal(sentryOrigin(dsn), null, String(dsn));
      assert.deepEqual(
        parse(buildCsp("n", { sentryDsn: dsn }))["connect-src"],
        ["'self'", "https://accounts.google.com/gsi/"],
      );
    }
  });
});
