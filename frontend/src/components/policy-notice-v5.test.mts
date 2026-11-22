/**
 * 처리방침 v5(2026-11-21 공고, 2026-11-28 시행)의 날짜를 실제 달력 날짜로 못 박는다.
 *
 * 실행: cd frontend && npx tsx --test --experimental-test-module-mocks src/components/policy-notice-v5.test.mts
 *
 * policy-notice.test.mts 는 PRIVACY_CHANGE 에서 날짜를 계산해 견준다. 그래서 상수를
 * 잘못 적으면(예: effective 를 11-27 로) 같이 틀려 통과한다. 여기서는 v5 동안만
 * 날짜를 글자로 박아 둔다.
 *   - 홈 알림은 한국 시간 11-21 ~ 11-27 내내 뜨고 "11월 28일부터 바뀝니다" 라고 쓴다.
 *   - 한국 시간 11-28 0시(UTC 11-27 15시)부터 안 뜬다.
 *   - 처리방침 버전 줄과 14절은 v5 공고일·시행일을 적는다. 14절에 앞 버전 이력은 없다.
 *
 * v5 가 아니면 건너뛴다. 다음 개정 때 이 파일을 지운다.
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

const IS_V5 = DOC_VERSION === "v5";
const NOTICE_TEXT = "개인정보 처리방침이 11월 28일부터 바뀝니다";

function renderAt(iso: string): string {
  mock.timers.enable({ apis: ["Date"], now: Date.parse(iso) });
  try {
    return renderToStaticMarkup(createElement(PolicyNotice));
  } finally {
    mock.timers.reset();
  }
}

afterEach(() => mock.timers.reset());

describe("v5 홈 알림의 날짜", { skip: !IS_V5 }, () => {
  for (const iso of [
    "2026-11-21T00:00:00+09:00", // 공고일 0시
    "2026-11-21T09:00:00+09:00",
    "2026-11-24T12:00:00+09:00",
    "2026-11-27T00:00:00+09:00",
    "2026-11-27T23:59:59.999+09:00",
    "2026-11-27T14:59:59.999Z", // 한국은 11-27 막바지
  ]) {
    it(`${iso} 에는 뜨고 28일이라고 쓴다`, () => {
      const html = renderAt(iso);
      assert.ok(html.includes(NOTICE_TEXT), html);
      assert.match(html, /href="\/privacy#changes"/);
      // 앞 버전들의 날짜(19일·20일)가 남아 있으면 안 된다.
      assert.ok(!/1[89]일|20일/.test(html), html);
    });
  }

  for (const iso of [
    "2026-11-28T00:00:00+09:00",
    "2026-11-27T15:00:00Z", // 한국 11-28 0시. UTC 날짜로 고르면 여기서 뜬다.
    "2026-11-27T23:59:59Z",
    "2026-11-28T12:00:00+09:00",
    "2026-12-01T09:00:00+09:00",
  ]) {
    it(`${iso} 에는 안 뜬다`, () => {
      assert.equal(renderAt(iso), "");
    });
  }
});

describe("v5 처리방침 본문의 날짜", { skip: !IS_V5 }, () => {
  const privacy = renderToStaticMarkup(createElement(PrivacyPage));
  const changes =
    privacy.match(/<section[^>]*id="changes"[^>]*>([\s\S]*?)<\/section>/)?.[1] ?? "";

  it("버전 줄이 v5 와 v5 시행일을 쓴다", () => {
    assert.ok(privacy.includes("버전 v5 · 시행일 2026년 11월 28일"), "버전 줄");
  });

  it("14절이 v5 공고일·시행일과 v5 바뀐 내용을 적는다", () => {
    assert.ok(changes, "14절을 못 찾았다");
    assert.ok(changes.includes("공고일: 2026년 11월 21일"));
    assert.ok(changes.includes("시행일: 2026년 11월 28일"));
    assert.ok(changes.includes("Sentry(미국)"));
  });

  it("14절에 앞 버전 이력이 없다", () => {
    // 11-22 에 앞 버전 이력을 "이전 버전" 한 줄로 줄였다가, 같은 날 그 줄까지 지웠다.
    // 14절은 이번 버전의 공고일·시행일과 바뀐 내용만 적는다(사용자 결정).
    // 태그의 클래스 이름 등에 걸리지 않게 글자만 본다.
    const text = changes.replace(/<[^>]+>/g, "");
    assert.ok(!text.includes("이전 버전"), text);
    assert.ok(!/v[234]\b/.test(text), text);
  });
});
