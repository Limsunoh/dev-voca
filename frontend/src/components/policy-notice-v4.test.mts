/**
 * 처리방침 v4(2026-11-13 공고, 2026-11-20 시행)의 날짜를 실제 달력 날짜로 못 박는다.
 *
 * 실행: cd frontend && npx tsx --test --experimental-test-module-mocks src/components/policy-notice-v4.test.mts
 *
 * policy-notice.test.mts 는 PRIVACY_CHANGE 에서 날짜를 계산해 견준다. 그래서 상수를
 * 잘못 적으면(예: firstChange 를 11-20 으로) 같이 틀려 통과한다. 여기서는 v4 동안만
 * 날짜를 글자로 박아 둔다.
 *   - 홈 알림은 한국 시간 11-19 하루 내내 뜨고 "11월 19일부터 바뀝니다" 라고 쓴다.
 *   - 한국 시간 11-20 0시(UTC 11-19 15시)부터 안 뜬다.
 *   - 처리방침 버전 줄과 14절은 v4 공고일·시행일을, 14절은 v3 의 공고일·시행일도 적는다.
 *
 * v4 가 아니면 건너뛴다. 다음 개정 때 이 파일을 지운다.
 */
import assert from "node:assert/strict";
import { afterEach, describe, it, mock } from "node:test";
import type { ReactNode } from "react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

mock.module("next/link", {
  defaultExport: (props: { href: string; children: ReactNode }) =>
    createElement("a", { href: props.href }, props.children),
});

const { DOC_VERSION } = await import("./LegalDoc");
const { PolicyNotice } = await import("./PolicyNotice");
const { default: PrivacyPage } = await import("../app/privacy/page");

const IS_V4 = DOC_VERSION === "v4";
const NOTICE_TEXT = "개인정보 처리방침이 11월 19일부터 바뀝니다";

function renderAt(iso: string): string {
  mock.timers.enable({ apis: ["Date"], now: Date.parse(iso) });
  try {
    return renderToStaticMarkup(createElement(PolicyNotice));
  } finally {
    mock.timers.reset();
  }
}

afterEach(() => mock.timers.reset());

describe("v4 홈 알림의 날짜", { skip: !IS_V4 }, () => {
  for (const iso of [
    "2026-11-13T09:00:00+09:00", // 공고일
    "2026-11-18T23:59:59.999+09:00",
    "2026-11-19T00:00:00+09:00", // v3 내용이 켜지는 날
    "2026-11-19T12:00:00+09:00",
    "2026-11-19T23:59:59.999+09:00",
    "2026-11-19T14:59:59.999Z", // UTC 로는 11-19 낮이고 한국은 11-19 막바지
  ]) {
    it(`${iso} 에는 뜨고 19일이라고 쓴다`, () => {
      const html = renderAt(iso);
      assert.ok(html.includes(NOTICE_TEXT), html);
      assert.match(html, /href="\/privacy#changes"/);
      assert.ok(!html.includes("20일"), html);
    });
  }

  for (const iso of [
    "2026-11-20T00:00:00+09:00",
    "2026-11-19T15:00:00Z", // 한국 11-20 0시. UTC 날짜로 고르면 여기서 뜬다.
    "2026-11-19T23:59:59Z",
    "2026-11-21T09:00:00+09:00",
  ]) {
    it(`${iso} 에는 안 뜬다`, () => {
      assert.equal(renderAt(iso), "");
    });
  }
});

describe("v4 처리방침 본문의 날짜", { skip: !IS_V4 }, () => {
  const privacy = renderToStaticMarkup(createElement(PrivacyPage));
  const changes =
    privacy.match(/<section[^>]*id="changes"[^>]*>([\s\S]*?)<\/section>/)?.[1] ?? "";

  it("버전 줄이 v4 시행일을 쓴다", () => {
    assert.ok(privacy.includes("· 시행일 2026년 11월 20일"), "버전 줄의 시행일");
  });

  it("14절이 v4 공고일·시행일과 v3 의 공고일·시행일을 모두 적는다", () => {
    assert.ok(changes, "14절을 못 찾았다");
    assert.ok(changes.includes("공고일: 2026년 11월 13일"));
    assert.ok(changes.includes("시행일: 2026년 11월 20일"));
    assert.ok(changes.includes("v3(2026년 11월 12일 공고, 2026년 11월 19일 시행)"));
  });

  it("14절의 v4 바뀐 내용이 v3 바뀐 내용보다 먼저 나온다", () => {
    const v4 = changes.indexOf("로그인 토큰을 발급하고 30일");
    const v3 = changes.indexOf("바로 앞 버전 v3");
    assert.ok(v4 >= 0 && v3 >= 0, changes);
    assert.ok(v4 < v3);
  });
});
