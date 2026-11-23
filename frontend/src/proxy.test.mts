/**
 * 화면 응답에 CSP 를 싣는 proxy 를 본다. CSP 문자열 자체는 lib/csp.test.mts.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - 요청 머리(Next 가 nonce 를 읽는 곳)와 응답 머리에 같은 CSP 를 싣고, 요청마다 nonce 가 바뀐다.
 *   - 화면 주소는 모두 proxy 를 지난다. 경로에 점을 넣어도 빠지지 않는다. 빠지면 그 화면은
 *     CSP 없이 나간다.
 *   - 빼는 것은 api 중계, 빌드 파일, 실제 정적 파일(sw.js 등)과 링크 미리 받기뿐이다.
 *   - 루트 layout 이 요청 때 그리게 한다(connection). 빠지면 미리 만든 화면의 HTML 에 nonce 가
 *     없어 그 화면의 스크립트가 전부 막히는데, 빌드와 다른 테스트는 초록이다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
import { NextRequest } from "next/server";

import { config, proxy } from "./proxy";

const ORIGIN = "https://dev-voca.vercel.app";

/** Next 가 실제로 쓰는 판정(path-to-regexp, missing 조건 포함)으로 본다. */
function matches(path: string, headers?: Record<string, string>): boolean {
  return unstable_doesMiddlewareMatch({ config, url: `${ORIGIN}${path}`, headers });
}

describe("proxy", () => {
  it("요청 머리와 응답 머리에 같은 CSP 를 싣고, 요청마다 nonce 가 바뀐다", async () => {
    const nonceOf = async () => {
      const res = await proxy(new NextRequest(`${ORIGIN}/learn/words`));
      const csp = res.headers.get("content-security-policy");
      // NextResponse.next({ request: { headers } }) 는 바꾼 요청 머리를 이 이름으로 넘긴다.
      // Next 내부 이름이라 Next 를 올리면 가장 먼저 깨질 수 있다.
      const forwarded = res.headers.get("x-middleware-request-content-security-policy");
      assert.ok(csp);
      assert.equal(forwarded, csp);
      assert.ok(!csp.includes("'unsafe-eval'"), "운영 정책에 eval 이 열렸다");
      return csp.match(/'nonce-([^']+)'/)?.[1];
    };
    const first = await nonceOf();
    assert.ok(first);
    assert.notEqual(first, await nonceOf());
  });

  it("화면 주소는 점이 들어가도 proxy 를 지난다", () => {
    for (const path of [
      "/",
      "/learn/words/12",
      "/privacy",
      "/start",
      "/profile/email/abc-_Z",
      // 점 하나로 CSP 를 벗기던 주소들. 없는 주소(404)도 화면이다.
      "/learn/words/1.5",
      "/learn/sentences/1.5",
      "/board/a.b",
      "/profile/email/a.b",
      "/x.y",
      "/sw.js.html",
    ]) {
      assert.ok(matches(path), path);
    }
  });

  it("api 중계, 빌드 파일, 실제 정적 파일, 링크 미리 받기는 뺀다", () => {
    for (const path of [
      "/api/accounts/photo/abc/",
      "/_next/static/chunks/main.js",
      "/_next/image",
      "/sw.js",
      "/offline.html",
      "/manifest.webmanifest",
      "/icon.png",
      "/apple-icon.png",
      "/icons/icon-192.png",
      "/icons/icon-512.png",
      "/icons/maskable-512.png",
      "/.well-known/assetlinks.json",
    ]) {
      assert.ok(!matches(path), path);
    }
    assert.ok(!matches("/learn/words", { "next-router-prefetch": "1" }));
  });

  it("빼는 이름과 닮기만 한 주소는 빼지 않는다", () => {
    // 제외는 앞머리 글자 비교라, 슬래시나 끝($)이 하나 빠지면 닮은 주소의 화면이 CSP 없이
    // 나간다. 접두 혼동, 대소문자, 끝 슬래시, 인코딩, 하위 폴더의 같은 이름을 본다.
    for (const path of [
      "/api",
      "/apix",
      "/API/accounts",
      "/%61pi/x",
      "/api%2fx",
      "/iconsx/a",
      "/.well-knownx",
      "/%2ewell-known/x",
      "/SW.JS",
      "/sw.js/",
      "/sw%2ejs",
      "/offline.html/",
      "/icon.pngx",
      "/apple-icon.png.html",
      "/learn/sw.js",
      "/learn/icon.png",
      "/x/offline.html",
      "/a/manifest.webmanifest",
      "/favicon.ico",
      "/_next/data/build/learn/words.json",
      "/learn/words?next=/api/x",
      // 빼는 폴더 아래의 없는 주소. 404 화면이 CSP 없이 나가던 자리다(/api/ 아래는 일부러 남김).
      "/_next/staticx",
      "/_next/imagex",
      "/_next/image/x",
      "/icons/nope",
      "/icons/icon-192.png.html",
      "/.well-known/nope",
      "/.well-known/assetlinks.json/x",
      // 이름 끝($)과 점(\.)을 지키는지. 하나라도 빠지면 이 주소의 404 가 CSP 없이 나간다.
      "/manifest.webmanifest/",
      "/manifest.webmanifestx",
      "/swxjs",
      "/iconxpng",
    ]) {
      assert.ok(matches(path), path);
    }
  });

  it("미리 받기와 닮은 머리는 빼지 않는다", () => {
    // 브라우저의 미리 그리기(speculation rules prerender)는 sec-purpose 로 오고, 그 HTML 이
    // 그대로 화면에 뜬다. 이것까지 빼면 CSP 없는 화면이 사용자에게 간다.
    assert.ok(matches("/learn/words", { "sec-purpose": "prefetch;prerender" }));
    assert.ok(matches("/learn/words", { purpose: "prefetch, x" }));
    // 옛 브라우저가 보내던 purpose 머리는 빼지 않는다. Next 의 미리 받기는 next-router-prefetch 다.
    assert.ok(matches("/learn/words", { purpose: "prefetch" }));
    // 빈 머리는 없는 것으로 친다.
    assert.ok(matches("/learn/words", { "next-router-prefetch": "" }));
  });

  it("루트 layout 이 요청 때 그리게 한다", () => {
    const layout = readFileSync(new URL("./app/layout.tsx", import.meta.url), "utf8");
    assert.match(layout, /^\s*await connection\(\);/m);
  });
});
