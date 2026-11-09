/**
 * 고른 사진을 서버로 보내기 전에 거르는 경계를 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 운영(Vercel)의 요청 본문 한도 4.5MB 를 넘는 값이 통과하면 화면이 통째로 죽는다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { isPhotoTooLarge } from "./ProfileForm";

const MB = 1024 * 1024;

describe("isPhotoTooLarge", () => {
  it("4MB 는 보낸다", () => {
    assert.equal(isPhotoTooLarge(4 * MB), false);
  });

  it("4MB 를 1바이트라도 넘으면 막는다", () => {
    assert.equal(isPhotoTooLarge(4 * MB + 1), true);
  });

  it("Vercel 한도를 넘는 크기는 막는다", () => {
    assert.equal(isPhotoTooLarge(4.5 * MB), true);
  });

  it("파일을 안 고르면 막지 않는다", () => {
    assert.equal(isPhotoTooLarge(0), false);
  });
});
