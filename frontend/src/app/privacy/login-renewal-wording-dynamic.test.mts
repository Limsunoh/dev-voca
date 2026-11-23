/**
 * 처리방침의 로그인 이어 가기 문구가 실제 상수와 맞는지 렌더해서 본다.
 *
 * 실행: cd frontend && npx tsx --test --experimental-test-module-mocks src/app/privacy/login-renewal-wording-dynamic.test.mts
 *
 * 계약:
 *   - 3절·10절의 "30일" 은 lib/token-cookie.ts 의 TOKEN_MAX_AGE, 백엔드 LoginToken.LIFETIME 과 같다.
 *   - 3절·10절·14절의 "하루에 한 번" 은 RENEW_AFTER_SECONDS, 백엔드 LoginToken.RENEW_AFTER 와 같다.
 *   - 3절 로그인 쿠키는 고정 30일이 아니라 "로그인하거나 새 토큰을 받은 때부터" 센다.
 *   - 2절 계정 정보에 이어 받은 토큰을 묶는 값과 바뀐 시각이 적혀 있다.
 *   - 10절에 devvoca_token 항목이 있고, 14절 넷째 바뀐 내용의 시작일은 2026년 11월 23일이다.
 *
 * 상수를 바꾸면 이 테스트가 처리방침 문구도 같이 고치라고 알린다(token-cookie.ts 주석의 약속).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it, mock } from "node:test";
import type { ReactNode } from "react";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

// next/link 는 브라우저 라우터를 기대한다. 여기서 볼 것은 글자뿐이다.
mock.module("next/link", {
  defaultExport: (props: { href: string; children: ReactNode }) =>
    createElement("a", { href: props.href }, props.children),
});

const { default: PrivacyPage } = await import("./page");
const { TOKEN_MAX_AGE, RENEW_AFTER_SECONDS, TOKEN_COOKIE } = await import(
  "../../lib/token-cookie"
);

const DAY = 60 * 60 * 24;
const html = renderToStaticMarkup(createElement(PrivacyPage));

function sectionText(id: string): string {
  const match = html.match(new RegExp(`<section[^>]*id="${id}"[^>]*>([\\s\\S]*?)</section>`));
  assert.ok(match, `${id} section 이 렌더돼야 한다`);
  return match[1].replace(/<[^>]+>/g, "").replace(/\s+/g, " ");
}

function items(id: string): string[] {
  const match = html.match(new RegExp(`<section[^>]*id="${id}"[^>]*>([\\s\\S]*?)</section>`));
  assert.ok(match);
  return [...match[1].matchAll(/<li[^>]*>([\s\S]*?)<\/li>/g)].map((m) =>
    m[1].replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim(),
  );
}

function itemStarting(id: string, prefix: string): string {
  const found = items(id).filter((item) => item.startsWith(prefix));
  assert.equal(found.length, 1, `${id} 에 "${prefix}" 항목이 하나여야 한다`);
  return found[0];
}

const lifetimeDays = TOKEN_MAX_AGE / DAY;
const renewPhrase = RENEW_AFTER_SECONDS === DAY ? "하루에 한 번" : null;

describe("처리방침의 로그인 이어 가기 문구", () => {
  it("상수가 문구가 쓰는 단위로 떨어진다", () => {
    assert.ok(Number.isInteger(lifetimeDays), `TOKEN_MAX_AGE ${TOKEN_MAX_AGE} 가 일 단위가 아니다`);
    assert.ok(renewPhrase, `RENEW_AFTER_SECONDS ${RENEW_AFTER_SECONDS} 가 하루가 아니다. 문구를 고쳐라`);
  });

  it("백엔드 LoginToken 의 LIFETIME·RENEW_AFTER 가 프론트 상수와 같다", () => {
    const models = readFileSync(
      new URL("../../../../backend/apps/accounts/models.py", import.meta.url),
      "utf8",
    );
    const lifetime = models.match(/LIFETIME = timedelta\(days=(\d+)\)/);
    const renew = models.match(/RENEW_AFTER = timedelta\(days=(\d+)\)/);
    assert.ok(lifetime && renew, "models.py 에서 LIFETIME·RENEW_AFTER 를 못 찾았다");
    assert.equal(Number(lifetime[1]), lifetimeDays);
    assert.equal(Number(renew[1]) * DAY, RENEW_AFTER_SECONDS);
  });

  it("3절 로그인 토큰 항목이 수명과 하루 한 번 이어 가기를 적는다", () => {
    const item = itemStarting("retention", "로그인 토큰:");
    assert.match(item, new RegExp(`발급 후 ${lifetimeDays}일이 지나면`));
    assert.ok(item.includes(`${renewPhrase} 새 토큰으로 바꿔`), item);
    assert.match(item, new RegExp(`${lifetimeDays}일 동안 이용하지 않으면 로그인이 끝납니다\\.$`));
  });

  it("3절 로그인 쿠키는 로그인하거나 새 토큰을 받은 때부터 센다", () => {
    const item = itemStarting("retention", "로그인 쿠키:");
    assert.equal(item, `로그인 쿠키: 로그인하거나 새 토큰을 받은 때부터 ${lifetimeDays}일`);
  });

  it("2절 계정 정보에 같은 로그인을 묶는 값과 바뀐 시각이 있다", () => {
    const text = sectionText("items");
    assert.ok(
      text.includes("로그인 토큰과 발급 시각(같은 로그인인지 알아보는 값, 새 토큰을 받았는지와 바뀐 시각 포함)"),
      "2절 괄호 문구가 없다",
    );
  });

  it("10절에 로그인 쿠키 항목이 수명·이어 가기와 함께 있다", () => {
    const item = itemStarting("cookies", TOKEN_COOKIE);
    assert.ok(item.includes("자바스크립트로 읽을 수 없음"), item);
    assert.ok(item.includes(`${lifetimeDays}일(이용하는 동안 ${renewPhrase} 새로 받아 이어짐)`), item);
  });

  it("14절 넷째 바뀐 내용이 로그인 이어 가기이고 2026년 11월 23일부터다", () => {
    const list = items("changes").filter((item) => !/^(공고일|시행일)/.test(item));
    assert.equal(list.length, 4, list.join("\n"));
    const fourth = list[3];
    assert.ok(fourth.startsWith("서비스를 이용하는 동안 로그인을 이어 갑니다."), fourth);
    assert.ok(fourth.includes(`${renewPhrase} 새 로그인 토큰으로 바꾸고`), fourth);
    assert.ok(fourth.includes(`${lifetimeDays}일 동안 이용하지 않으면`), fourth);
    assert.ok(fourth.includes("(2절 라목, 3절, 10절)"), fourth);
    assert.ok(fourth.includes("2026년 11월 23일부터"), fourth);
  });
});
