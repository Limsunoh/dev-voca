/**
 * 처리방침 v6(2026-11-25 공고, 2026-12-02 시행)의 날짜를 실제 달력 날짜로 못 박는다.
 *
 * 실행: cd frontend && npx tsx --test --experimental-test-module-mocks src/components/policy-notice-v6.test.mts
 *
 * policy-notice.test.mts 는 PRIVACY_CHANGE 에서 날짜를 계산해 견준다. 그래서 상수를
 * 잘못 적으면(예: effective 를 12-01 로) 같이 틀려 통과한다. 여기서는 v6 동안만
 * 날짜를 글자로 박아 둔다.
 *   - v6 은 v5 시행(11-28) 전에 공고했다. 홈 알림은 가장 먼저 바뀌는 날인 v5 시행일을
 *     써서 "11월 28일부터 바뀝니다" 라고 쓰고, 한국 시간 11-25 ~ 12-01 내내 뜬다.
 *   - 한국 시간 12-02 0시(UTC 12-01 15시)부터 안 뜬다.
 *   - 처리방침 버전 줄과 14절은 v6 공고일·시행일을 적는다. 14절에 v2~v4 이력은 없다.
 *
 * v6 이 아니면 건너뛴다. 다음 개정 때 이 파일을 지운다.
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

const IS_V6 = DOC_VERSION === "v6";
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

describe("v6 홈 알림의 날짜", { skip: !IS_V6 }, () => {
  for (const iso of [
    "2026-11-25T00:00:00+09:00", // 공고일 0시
    "2026-11-27T23:59:59.999+09:00",
    "2026-11-28T00:00:00+09:00", // v5 시행일에도 v6 시행 전이라 뜬다
    "2026-12-01T00:00:00+09:00",
    "2026-12-01T23:59:59.999+09:00",
    "2026-12-01T14:59:59.999Z", // 한국은 12-01 막바지
  ]) {
    it(`${iso} 에는 뜨고 28일이라고 쓴다`, () => {
      const html = renderAt(iso);
      assert.ok(html.includes(NOTICE_TEXT), html);
      assert.match(html, /href="\/privacy#changes"/);
    });
  }

  for (const iso of [
    "2026-12-02T00:00:00+09:00",
    "2026-12-01T15:00:00Z", // 한국 12-02 0시. UTC 날짜로 고르면 여기서 뜬다.
    "2026-12-01T23:59:59Z",
    "2026-12-02T12:00:00+09:00",
    "2026-12-10T09:00:00+09:00",
  ]) {
    it(`${iso} 에는 안 뜬다`, () => {
      assert.equal(renderAt(iso), "");
    });
  }
});

describe("v6 처리방침 본문의 날짜", { skip: !IS_V6 }, () => {
  const privacy = renderToStaticMarkup(createElement(PrivacyPage));
  const changes =
    privacy.match(/<section[^>]*id="changes"[^>]*>([\s\S]*?)<\/section>/)?.[1] ?? "";

  it("버전 줄이 v6 과 v6 시행일을 쓴다", () => {
    assert.ok(privacy.includes("버전 v6 · 시행일 2026년 12월 2일"), "버전 줄");
  });

  it("14절이 v6 공고일·시행일과 바뀐 내용을 적는다", () => {
    assert.ok(changes, "14절을 못 찾았다");
    assert.ok(changes.includes("공고일: 2026년 11월 25일"));
    assert.ok(changes.includes("시행일: 2026년 12월 2일"));
    assert.ok(changes.includes("Sentry(미국)"));
  });

  it("14절에 v2~v4 이력이 없다", () => {
    // 11-22 에 앞 버전 이력을 "이전 버전" 한 줄로 줄였다가, 같은 날 그 줄까지 지웠다.
    // 아직 시행 전인 v5 의 공고일·시행일 한 줄만 둔다(사용자 결정 11-24).
    // 태그의 클래스 이름 등에 걸리지 않게 글자만 본다.
    const text = changes.replace(/<[^>]+>/g, "");
    assert.ok(!text.includes("이전 버전"), text);
    assert.ok(!/v[234]\b/.test(text), text);
  });
});
