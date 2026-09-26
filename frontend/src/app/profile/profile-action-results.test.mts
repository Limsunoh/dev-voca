/**
 * 이름 저장·사진 지우기 액션이 화면에 돌려주는 기준값을 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 화면(ProfileForm)은 이 값으로 "저장 안 한 변경" 을 가른다.
 *   - updateProfileAction: savedAvatar(서버에 저장된 아바타), sentName(보낸
 *     그대로의 이름). 결과가 온 순간의 화면 값으로 대신하면 저장이 도는 사이
 *     바꾼 것까지 저장된 것으로 잡힌다.
 *   - deletePhotoAction: savedAvatar. 서버가 avatar 를 비웠으면(""), 그때
 *     그리는 것(아바타 이름 또는 구글 사진)을 화면의 선택지 이름으로 옮긴다.
 *
 * 대역 방식은 password-action-field.test.mts 와 같다.
 */
import assert from "node:assert/strict";
import { after, beforeEach, describe, it, mock } from "node:test";

mock.module("next/navigation", {
  namedExports: {
    redirect(to: string): never {
      throw new Error(`NEXT_REDIRECT ${to}`);
    },
  },
});

mock.module("next/cache", {
  namedExports: { revalidatePath() {} },
});

mock.module("@/lib/session", {
  namedExports: {
    async setToken() {},
    async clearToken() {},
    async getToken() {
      return "tok";
    },
  },
});

const { deletePhotoAction, updateProfileAction } = await import("./actions");

const realFetch = globalThis.fetch;
after(() => {
  globalThis.fetch = realFetch;
});

function backend(json: unknown): void {
  globalThis.fetch = (async () =>
    new Response(JSON.stringify(json), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })) as typeof fetch;
}

function user(over: Record<string, unknown>): Record<string, unknown> {
  return {
    email: "a@b.c",
    display_name: "초롱",
    avatar: "",
    avatar_display: { type: "preset", key: "a1" },
    google_picture: "",
    uploaded_photo: "",
    has_password: true,
    ...over,
  };
}

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

beforeEach(() => {
  globalThis.fetch = realFetch;
});

describe("updateProfileAction", () => {
  it("서버에 저장된 아바타와 보낸 그대로의 이름을 돌려준다", async () => {
    backend(user({ display_name: "초롱 3", avatar: "a3" }));
    const result = await updateProfileAction(
      {},
      form({ display_name: " 초롱  3 ", avatar: "a3" }),
    );
    assert.deepEqual(result, {
      saved: true,
      savedName: "초롱 3",
      savedAvatar: "a3",
      sentName: " 초롱  3 ",
    });
  });
});

describe("deletePhotoAction", () => {
  it("서버가 비운 뒤 아바타를 그리면 그 이름을 돌려준다", async () => {
    // 계정마다 정해진 아바타는 화면이 짐작할 수 없다(서버가 계정 번호로 고른다).
    backend(user({ avatar: "", avatar_display: { type: "preset", key: "a4" } }));
    const result = await deletePhotoAction();
    assert.equal(result.photoUrl, "");
    assert.equal(result.savedAvatar, "a4");
  });

  it("서버가 비운 뒤 사진을 그리면 구글 사진이다", async () => {
    backend(
      user({
        avatar: "",
        avatar_display: { type: "photo", url: "https://g/pic.jpg" },
        google_picture: "https://g/pic.jpg",
      }),
    );
    const result = await deletePhotoAction();
    assert.equal(result.savedAvatar, "google");
  });

  it("서버가 선택을 그대로 뒀으면 그 값을 돌려준다", async () => {
    // 저장된 것이 photo 가 아니면 서버는 avatar 를 안 비운다.
    backend(user({ avatar: "a2", avatar_display: { type: "preset", key: "a2" } }));
    const result = await deletePhotoAction();
    assert.equal(result.savedAvatar, "a2");
  });
});
