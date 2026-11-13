/**
 * 구글 버튼(GoogleButton). 구글 스크립트가 그리는 공식 버튼이다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - 처음 그릴 때(서버 렌더, 구글 스크립트가 뜨기 전)는 fallback(구글 화면으로
 *     가는 예전 링크)을 보인다. 누를 수 없는 빈 칸이 남지 않는다.
 *   - 구글 스크립트는 accounts.google.com/gsi/client 하나만 싣는다.
 *   - showGoogleButton 은 화면 아래 계정 창(use_fedcm_for_button)을 켜고, 서버가
 *     정한 nonce 와 클라이언트 ID 를 넘긴다. 폭은 200~400px 안.
 *   - 구글이 돌려준 신분 토큰만 넘긴다. 비었거나 글자가 아니면 부르지 않는다.
 *   - 구글 버튼 iframe 이 크기를 가져야 "보인다" 고 본다. 콘솔에 주소가 없으면
 *     구글이 0x0 으로 남기는데, 그때 예전 링크를 걷으면 누를 것이 없다.
 */
import assert from "node:assert/strict";
import { describe, it, mock } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

const scripts: Record<string, unknown>[] = [];
mock.module("next/script", {
  defaultExport: (props: Record<string, unknown>) => {
    scripts.push(props);
    return null;
  },
});
mock.module("@/app/(auth)/google-actions", {
  namedExports: {
    prepareGoogleButton: async () => null,
    googleCredentialAction: async () => {},
  },
});

const { GoogleButton, isGoogleButtonVisible, showGoogleButton } = await import("./GoogleButton");

function fakeGoogle() {
  const init: Record<string, unknown>[] = [];
  const rendered: Record<string, unknown>[] = [];
  return {
    init,
    rendered,
    id: {
      initialize: (config: Record<string, unknown>) => init.push(config),
      renderButton: (_el: HTMLElement, options: Record<string, unknown>) => rendered.push(options),
    },
  };
}

describe("GoogleButton 처음 그리기", () => {
  it("구글 스크립트가 뜨기 전에는 예전 링크를 보이고, 스크립트는 구글 것 하나만 싣는다", () => {
    scripts.length = 0;
    const html = renderToStaticMarkup(
      createElement(GoogleButton, {
        context: "signin",
        fallback: createElement("a", { href: "/api/auth/google" }, "구글로 계속하기"),
      }),
    );
    assert.match(html, /<a href="\/api\/auth\/google">구글로 계속하기<\/a>/);
    assert.equal(scripts.length, 1);
    assert.equal(scripts[0].src, "https://accounts.google.com/gsi/client");
    assert.equal(typeof scripts[0].onReady, "function");
    // 받는 도중 다시 붙은 버튼에는 Next 가 onReady 를 다시 안 부르고 onLoad 만
    // 부른다. 이게 없으면 그 버튼은 구글 버튼이 영영 안 뜬다.
    assert.equal(typeof scripts[0].onLoad, "function");
    // 확인 중 안내는 아직 없다.
    assert.doesNotMatch(html, /확인하는 중/);
    // 구글 버튼 자리는 나타나기 전까지 누를 수도 읽을 수도 없다.
    assert.match(html, /<div[^>]*inert=""[^>]*>/);
  });
});

describe("showGoogleButton", () => {
  const prep = { clientId: "cid.apps.googleusercontent.com", nonce: "n-123" };

  it("화면 아래 계정 창을 켜고 nonce·클라이언트 ID·문구 종류를 넘긴다", () => {
    const g = fakeGoogle();
    showGoogleButton(g.id, { offsetWidth: 320 } as HTMLElement, prep, {
      context: "signup",
      onCredential: () => {},
    });
    assert.equal(g.init.length, 1);
    const c = g.init[0];
    assert.equal(c.client_id, prep.clientId);
    assert.equal(c.nonce, prep.nonce);
    assert.equal(c.context, "signup");
    assert.equal(c.use_fedcm_for_button, true);
    assert.equal(c.ux_mode, "popup");
    assert.equal(g.rendered.length, 1);
    assert.equal(g.rendered[0].locale, "ko");
    assert.equal(g.rendered[0].width, 320);
  });

  it("폭은 구글이 받는 200~400px 안으로 맞춘다", () => {
    for (const [given, want] of [
      [120, 200],
      [999, 400],
      [287.6, 288],
    ]) {
      const g = fakeGoogle();
      showGoogleButton(g.id, { offsetWidth: given } as HTMLElement, prep, {
        context: "signin",
        onCredential: () => {},
      });
      assert.equal(g.rendered[0].width, want, String(given));
    }
  });

  it("구글이 준 신분 토큰만 넘기고, 비었거나 글자가 아니면 부르지 않는다", () => {
    const g = fakeGoogle();
    const got: string[] = [];
    showGoogleButton(g.id, { offsetWidth: 300 } as HTMLElement, prep, {
      context: "signin",
      onCredential: (c) => got.push(c),
    });
    const callback = g.init[0].callback as (r: unknown) => void;
    callback({ credential: "header.payload.sig" });
    callback({ credential: "" });
    callback({ credential: 42 });
    callback({});
    callback(undefined);
    assert.deepEqual(got, ["header.payload.sig"]);
  });
});

describe("isGoogleButtonVisible", () => {
  const holder = (frame: unknown) => ({ querySelector: () => frame }) as unknown as HTMLElement;

  it("iframe 이 크기를 가졌을 때만 보인다고 본다", () => {
    assert.equal(isGoogleButtonVisible(holder(null)), false);
    assert.equal(isGoogleButtonVisible(holder({ offsetHeight: 0, offsetWidth: 0 })), false);
    assert.equal(isGoogleButtonVisible(holder({ offsetHeight: 40, offsetWidth: 0 })), false);
    assert.equal(isGoogleButtonVisible(holder({ offsetHeight: 40, offsetWidth: 320 })), true);
  });
});
