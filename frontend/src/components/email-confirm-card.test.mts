/**
 * 이메일 변경을 마친 뒤 카드가 어디로 보내는지 본다(EmailConfirmCard).
 *
 * 실행: cd frontend && npm test
 *
 * 계약: 액션이 이 기기에 새 토큰을 넣었으면(signedIn) "내정보로"(/profile),
 * 아니면 "로그인하러 가기"(/login) 와 다시 로그인하라는 안내다. 로그인 없이
 * 열었거나 다른 계정으로 로그인해 있던 기기에서 내정보로 보내면, 앞은 로그인
 * 화면으로 튕기고 뒤는 그 다른 사람의 정보가 떠 무엇이 바뀌었는지 헷갈린다.
 * 쿠키를 못 넣은 경우도 액션이 signedIn 없이 돌려주므로 같은 길이다.
 *
 * 서버 결과는 react 의 useActionState 만 대역으로 바꿔 넣는다
 * (profile-cards-state.test.mts 와 같다). 링크는 next/link 대역이 넘긴
 * props 를 모아 본다(board-login-next.test.mts 와 같다).
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { beforeEach, describe, it, mock } from "node:test";
import type { ReactNode } from "react";

const require = createRequire(import.meta.url);
const realReact = require("react") as typeof import("react");

let cardState: Record<string, unknown> = {};
mock.module("react", {
  defaultExport: realReact,
  namedExports: {
    ...realReact,
    useActionState: () => [cardState, () => {}, false],
  },
});

type LinkProps = { href: string; children?: ReactNode };
let links: LinkProps[] = [];
mock.module("next/link", {
  defaultExport: (props: LinkProps) => {
    links.push(props);
    return realReact.createElement("a", { href: props.href }, props.children);
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { EmailConfirmCard } = await import("./EmailConfirmCard");

function render(state: Record<string, unknown>): string {
  cardState = state;
  return renderToStaticMarkup(
    realReact.createElement(EmailConfirmCard, {
      action: async () => ({}),
      token: "a:b:c",
    }),
  );
}

beforeEach(() => {
  links = [];
});

describe("이메일을 바꾼 뒤의 버튼", () => {
  it("이 기기가 로그인을 이어 가면 내정보로 보낸다", () => {
    const html = render({ changedTo: "new@example.com", signedIn: true });
    assert.deepEqual(
      links.map((l) => [l.href, l.children]),
      [["/profile", "내정보로"]],
    );
    assert.match(html, /이 기기는 그대로 쓰시면 됩니다/);
    assert.doesNotMatch(html, /다시 로그인해 주세요/);
  });

  it("이 기기에 새 토큰을 넣지 않았으면 로그인 화면으로 보낸다", () => {
    const html = render({ changedTo: "new@example.com" });
    assert.deepEqual(
      links.map((l) => [l.href, l.children]),
      [["/login", "로그인하러 가기"]],
    );
    assert.match(html, /새 주소로 다시 로그인해 주세요/);
    assert.doesNotMatch(html, /이 기기는 그대로/);
    assert.doesNotMatch(html, /href="\/profile"/);
  });

  it("바뀐 주소를 보여 준다", () => {
    const html = render({ changedTo: "new@example.com" });
    assert.match(html, /new@example\.com/);
  });

  it("바꾸기 전에는 링크 없이 확인 버튼만 있다", () => {
    const html = render({});
    assert.deepEqual(links, []);
    assert.match(html, /이메일 바꾸기/);
    assert.match(html, /name="token" value="a:b:c"/);
  });
});
