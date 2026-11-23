/**
 * 로그인 쿠키 값의 꼴("토큰.발급시각").
 *
 * 실행: cd frontend && npm test
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  formatTokenCookie,
  isRenewalDue,
  parseTokenCookie,
  RENEW_AFTER_SECONDS,
  serializeTokenCookie,
  TOKEN_MAX_AGE,
} from "./token-cookie";

describe("token-cookie", () => {
  it("쓰고 읽으면 같은 토큰과 시각이 나온다", () => {
    assert.deepEqual(parseTokenCookie(formatTokenCookie("abc123", 1_900_000_000.9)), {
      token: "abc123",
      issuedAt: 1_900_000_000,
    });
  });

  it("점이 없는 옛 쿠키는 토큰만 있고 시각은 없다", () => {
    assert.deepEqual(parseTokenCookie("abc123"), { token: "abc123", issuedAt: null });
  });

  it("시각 자리가 숫자가 아니면 시각이 없는 것으로 본다", () => {
    for (const value of ["abc.", "abc.12x", "abc.-5", "abc.1e9"]) {
      assert.deepEqual(parseTokenCookie(value), { token: "abc", issuedAt: null }, value);
    }
  });

  it("비었거나 토큰 자리가 비면 쿠키가 없는 것이다", () => {
    for (const value of [undefined, null, "", ".123"]) {
      assert.equal(parseTokenCookie(value), null);
    }
  });

  it("Set-Cookie 한 줄은 tokenCookieOptions 와 같은 설정이다", () => {
    assert.equal(
      serializeTokenCookie("abc.1"),
      `devvoca_token=abc.1; Path=/; Max-Age=${TOKEN_MAX_AGE}; HttpOnly; SameSite=Lax`,
    );
  });

  it("하루가 지났거나 시각이 없거나 앞날이면 이어 갈 때다", () => {
    const now = 2_000_000_000;
    assert.equal(isRenewalDue(now - RENEW_AFTER_SECONDS, now), true);
    assert.equal(isRenewalDue(now - RENEW_AFTER_SECONDS + 1, now), false);
    assert.equal(isRenewalDue(now, now), false);
    assert.equal(isRenewalDue(null, now), true);
    assert.equal(isRenewalDue(now + 60, now), true);
  });
});
