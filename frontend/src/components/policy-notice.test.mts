/**
 * 홈의 처리방침 변경 알림(PolicyNotice)과 처리방침·약관의 날짜.
 *
 * 실행: cd frontend && npx tsx --test --experimental-test-module-mocks src/components/policy-notice.test.mts
 *
 * 계약:
 *   - 알림은 한국 시간으로 시행일 0시 직전까지 뜨고, 0시부터 사라진다. 서버(Vercel)는
 *     UTC 로 돌아서, 날짜를 UTC 로 고르면 9시간 늦게 사라진다.
 *   - 알림 글의 날짜는 PRIVACY_CHANGE.effective 에서 나온다.
 *   - 처리방침 버전 줄은 처리방침 시행일, 약관은 약관 시행일(EFFECTIVE_DATE)을 쓴다.
 *   - 처리방침이 적은 메시지 길이 상한이 서버의 MESSAGE_LIMIT 과 같다.
 *
 * 날짜는 PRIVACY_CHANGE 에서 계산하므로 시행일이 지나도 저절로 깨지지 않는다.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterEach, describe, it, mock } from "node:test";
import type { ReactNode } from "react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

// 여기서 볼 것은 주소뿐이다. next/link 는 브라우저 라우터를 기대한다.
mock.module("next/link", {
  defaultExport: (props: { href: string; children: ReactNode }) =>
    createElement("a", { href: props.href }, props.children),
});

const { EFFECTIVE_DATE, koreanDate, PRIVACY_CHANGE } = await import("./LegalDoc");
const { PolicyNotice, seoulToday } = await import("./PolicyNotice");
const { default: TermsPage } = await import("../app/terms/page");
const { default: PrivacyPage } = await import("../app/privacy/page");

/** 한국 시간 시행일 0시의 UTC 밀리초. */
const KST_MIDNIGHT = Date.parse(`${PRIVACY_CHANGE.effective}T00:00:00+09:00`);

let timersOn = false;

function at(ms: number) {
  if (timersOn) {
    mock.timers.setTime(ms);
  } else {
    mock.timers.enable({ apis: ["Date"], now: ms });
    timersOn = true;
  }
}

afterEach(() => {
  mock.timers.reset();
  timersOn = false;
});

describe("홈의 처리방침 알림", () => {
  it("한국 시간으로 날짜를 고른다", () => {
    at(KST_MIDNIGHT - 1);
    const before = seoulToday();
    at(KST_MIDNIGHT);
    assert.equal(seoulToday(), PRIVACY_CHANGE.effective);
    assert.ok(before < PRIVACY_CHANGE.effective, before);
  });

  it("시행일 0시 1밀리초 전에는 뜨고, 0시부터는 안 뜬다(오늘 값을 넘기지 않을 때)", () => {
    at(KST_MIDNIGHT - 1);
    const html = renderToStaticMarkup(createElement(PolicyNotice));
    assert.match(html, /href="\/privacy#changes"/);

    at(KST_MIDNIGHT);
    assert.equal(renderToStaticMarkup(createElement(PolicyNotice)), "");
    // UTC 로는 아직 전날이다. UTC 날짜로 고르면 여기서 뜬다.
    at(KST_MIDNIGHT + 8 * 60 * 60 * 1000);
    assert.equal(renderToStaticMarkup(createElement(PolicyNotice)), "");
  });

  it("알림 글의 날짜가 시행일과 같다", () => {
    const [, m, d] = PRIVACY_CHANGE.effective.split("-").map(Number);
    const html = renderToStaticMarkup(
      createElement(PolicyNotice, { today: PRIVACY_CHANGE.announced }),
    );
    assert.ok(
      html.includes(`개인정보 처리방침이 ${m}월 ${d}일부터 바뀝니다`),
      html,
    );
  });

  it("해가 넘어가도 문자열 비교가 맞다", () => {
    // YYYY-MM-DD 문자열 비교라 자릿수가 어긋나면(예: 2026-9-1) 틀린다.
    assert.match(PRIVACY_CHANGE.effective, /^\d{4}-\d{2}-\d{2}$/);
    assert.match(PRIVACY_CHANGE.announced, /^\d{4}-\d{2}-\d{2}$/);
    const year = Number(PRIVACY_CHANGE.effective.slice(0, 4));
    const render = (today: string) =>
      renderToStaticMarkup(createElement(PolicyNotice, { today }));
    assert.equal(render(`${year + 1}-01-01`), "");
    assert.notEqual(render(`${year - 1}-12-31`), "");
  });
});

describe("문서의 날짜", () => {
  it("koreanDate 는 앞의 0 을 뗀다", () => {
    assert.equal(koreanDate("2026-01-05"), "2026년 1월 5일");
    assert.equal(koreanDate("2026-11-19"), "2026년 11월 19일");
  });

  const privacy = renderToStaticMarkup(createElement(PrivacyPage));
  const terms = renderToStaticMarkup(createElement(TermsPage));
  const privacyDate = koreanDate(PRIVACY_CHANGE.effective);

  // 약관과 처리방침의 시행일이 다를 때만 뜻이 있다. 다음 개정에서 둘이 같은
  // 날 바뀌면 이 두 테스트는 건너뛴다.
  const datesDiffer = EFFECTIVE_DATE !== privacyDate;

  it("약관의 시행일은 약관 시행일 그대로이고 처리방침 시행일이 없다", {
    skip: !datesDiffer,
  }, () => {
    assert.ok(terms.includes(`· 시행일 ${EFFECTIVE_DATE}`));
    assert.ok(terms.includes(`이 약관은 ${EFFECTIVE_DATE}부터 시행합니다`));
    assert.ok(!terms.includes(privacyDate), "약관에 처리방침 시행일이 있다");
  });

  it("처리방침 버전 줄은 처리방침 시행일을 쓴다", { skip: !datesDiffer }, () => {
    assert.ok(privacy.includes(`· 시행일 ${privacyDate}`));
    assert.ok(!privacy.includes(`· 시행일 ${EFFECTIVE_DATE}`));
  });

  it("처리방침 2절 사목이 서버의 메시지 길이 상한과 시작일을 적는다", () => {
    const source = readFileSync(
      new URL("../../../backend/apps/accounts/error_mail.py", import.meta.url),
      "utf-8",
    );
    const limit = source.match(/^MESSAGE_LIMIT = (\d+)/m)?.[1];
    assert.ok(limit, "MESSAGE_LIMIT 을 못 찾았다");
    assert.ok(privacy.includes(`${limit}자까지만`), `처리방침에 ${limit}자가 없다`);
    // 시작일은 v3 시행일로 박혀 있다. 다음 개정에서 PRIVACY_CHANGE 를 고쳐도
    // 바뀌면 안 된다(실제로 그날부터 남기고 있으므로).
    assert.ok(privacy.includes("2026년 11월 19일부터 남기며"));
  });
});
