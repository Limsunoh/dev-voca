/**
 * 고른 사진을 그대로 보낼지, 오려 내기 창(PhotoCropper)으로 넘길지 가르는 경계를 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 운영(Vercel)의 요청 본문 한도 4.5MB 를 넘는 값을 그대로 보내면 화면이 통째로 죽는다.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { isPhotoTooLarge } from "./ProfileForm";

const MB = 1024 * 1024;

describe("isPhotoTooLarge", () => {
  it("4MB 는 보낸다", () => {
    assert.equal(isPhotoTooLarge(4 * MB), false);
  });

  it("4MB 를 1바이트라도 넘으면 그대로 보내지 않는다", () => {
    assert.equal(isPhotoTooLarge(4 * MB + 1), true);
  });

  it("Vercel 한도를 넘는 크기는 그대로 보내지 않는다", () => {
    assert.equal(isPhotoTooLarge(4.5 * MB), true);
  });

  it("파일을 안 고르면 크다고 보지 않는다", () => {
    assert.equal(isPhotoTooLarge(0), false);
  });
});
