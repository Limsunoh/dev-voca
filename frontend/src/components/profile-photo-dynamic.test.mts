/**
 * 내정보 사진 고르기가 오려 내기 창으로 넘어가는 길과, 닉네임 12자 안내, CSP 의 blob:
 * 를 깨뜨려 본다. 오려 내기 창 자체는 photo-crop-dynamic.test 가 본다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   - 4MB(4*1024*1024 바이트) 이하는 바로 폼을 제출하고 창을 띄우지 않는다.
 *   - 넘으면 제출하지 않고 그 파일로 창(PhotoCropper)을 띄운다.
 *   - 창이 onDone(사진) 하면 창을 닫고 FormData "photo" 에 그 사진을 담아 사진 올리기
 *     액션을 한 번 부른다. onClose(안내) 면 창을 닫고 안내를 내정보에 띄운다.
 *   - 닉네임 칸(가입·내정보)은 maxLength 12 이고 안내에 "12자까지 쓸 수 있고" 가 있다.
 *   - CSP img-src 에 blob: 이 있다(창이 고른 사진을 blob 주소로 그린다). 다른 지시어에는
 *     없다 - script-src 에 들어가면 blob 주소로 스크립트를 돌릴 수 있다.
 *
 * 브라우저 없이 도는 방법은 profile-cards-state.test 와 같다. 창은 상태 없는 대역으로
 * 바꿔 넘겨받은 props 만 잡는다. 창이 조건부로 나타나며 훅을 부르면 호출 순서로 매긴
 * 상태 칸이 밀리기 때문이다.
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { beforeEach, describe, it, mock } from "node:test";
import type { ReactElement } from "react";

const require = createRequire(import.meta.url);
const realReact = require("react") as typeof import("react");
const realJsx = require("react/jsx-runtime");

let slots: { value: unknown }[] = [];
let cursor = 0;
let changed = false;
let actionStates: unknown[] = [];
let actionCursor = 0;
/** useActionState 순서별로, 액션이 받은 FormData. */
let actionCalls: FormData[][] = [];

function useState<T>(init: T | (() => T)) {
  const i = cursor++;
  if (!slots[i]) slots[i] = { value: typeof init === "function" ? (init as () => T)() : init };
  const slot = slots[i];
  const set = (next: T | ((prev: T) => T)) => {
    const value = typeof next === "function" ? (next as (p: T) => T)(slot.value as T) : next;
    if (!Object.is(value, slot.value)) {
      slot.value = value;
      changed = true;
    }
  };
  return [slot.value as T, set] as const;
}

function useActionState<S>(_action: unknown, init: S) {
  const i = actionCursor++;
  if (!(i in actionStates)) actionStates[i] = init;
  actionCalls[i] ??= [];
  const calls = actionCalls[i];
  return [actionStates[i] as S, (data: FormData) => calls.push(data), false] as const;
}

let transitions = 0;

mock.module("react", {
  defaultExport: realReact,
  namedExports: {
    ...realReact,
    useState,
    useActionState,
    useEffect() {},
    startTransition(fn: () => void) {
      transitions++;
      fn();
    },
  },
});

type Host = { type: string; props: Record<string, unknown> };
let hosts: Host[] = [];
const record =
  (fn: (...args: unknown[]) => unknown) =>
  (type: unknown, props: Record<string, unknown>, key?: unknown) => {
    if (typeof type === "string") hosts.push({ type, props });
    return fn(type, props, key);
  };
mock.module("react/jsx-runtime", {
  namedExports: { ...realJsx, jsx: record(realJsx.jsx), jsxs: record(realJsx.jsxs) },
});

mock.module("@/components/Avatar", {
  namedExports: {
    AVATAR_KEYS: ["a1", "a2", "a3", "a4", "a5", "a6"],
    avatarLabel: (key: string) => `아바타 ${key}`,
    Avatar: () => null,
    AvatarMark: () => null,
  },
});
mock.module("@/components/useUnsavedGuard", {
  namedExports: { useUnsavedGuard: () => null },
});

type CropperProps = {
  file: File;
  onClose: (error?: string) => void;
  onDone: (photo: File) => void;
};
/** 마지막 렌더에서 창이 받은 props. 창이 안 그려졌으면 null. */
let cropper: CropperProps | null = null;
mock.module("@/components/PhotoCropper", {
  namedExports: {
    PhotoCropper(props: CropperProps) {
      cropper = props;
      return null;
    },
  },
});

// AuthForm 이 부르는 서버 액션들(auth-form-guest.test 와 같은 대역).
mock.module("@/app/(auth)/google-actions", {
  namedExports: { prepareGoogleButton: async () => null, googleCredentialAction: async () => {} },
});
mock.module("@/app/start/actions", {
  namedExports: { continueAsGuestAction: async () => {} },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { createElement } = realReact;
const { ProfileForm } = await import("./ProfileForm");
const { AuthForm } = await import("./AuthForm");
const { buildCsp } = await import("@/lib/csp");

const MB = 1024 * 1024;
const UPLOAD = 1; // ProfileForm 의 useActionState 순서: 이름, 사진 올리기, 사진 지우기
const CANNOT_OPEN = "이 사진은 열 수 없습니다. 다른 사진을 골라주세요.";
const TOO_BIG = "사진이 너무 커서 열 수 없습니다. 다른 사진을 골라주세요.";

let element: ReactElement;
let html = "";

function draw(): string {
  for (let pass = 0; pass < 20; pass += 1) {
    cursor = 0;
    actionCursor = 0;
    changed = false;
    hosts = [];
    cropper = null;
    html = renderToStaticMarkup(element);
    if (!changed) return html;
  }
  throw new Error("렌더가 가라앉지 않는다");
}

function mountProfile(): void {
  slots = [];
  actionStates = [];
  actionCalls = [];
  transitions = 0;
  element = createElement(ProfileForm, {
    action: async () => ({}),
    initialName: "초롱",
    initialAvatar: "a1",
    shown: { type: "preset", key: "a1" },
    googlePicture: "",
    uploadPhoto: async () => ({}),
    deletePhoto: async () => ({}),
    uploadedPhoto: "",
  } as never);
  draw();
}

/** 사진 칸에서 파일을 고른다. 제출(requestSubmit) 횟수와 비운 값을 돌려준다. */
function choose(file: File | undefined): { submits: number; value: string } {
  const found = hosts.filter((h) => h.type === "input" && h.props.type === "file");
  assert.equal(found.length, 1);
  const target = {
    files: file ? [file] : [],
    value: file ? "C:\\fakepath\\x.jpg" : "",
    form: { submits: 0, requestSubmit() { this.submits++; } },
  };
  (found[0].props.onChange as (e: unknown) => void)({ currentTarget: target, target });
  draw();
  return { submits: target.form.submits, value: target.value };
}

/** size 바이트로 보이는 파일. 실제 바이트를 채우지 않고 size 만 바꾼다. */
function fileOf(size: number, name = "p.jpg"): File {
  const f = new File(["x"], name, { type: "image/jpeg" });
  Object.defineProperty(f, "size", { value: size });
  return f;
}

const alerts = () => [...html.matchAll(/role="alert"[^>]*>([^<]*)</g)].map((m) => m[1]);

// ---------------------------------------------------------------------------

describe("ProfileForm: 사진 크기에 따라 바로 보내기 / 오려 내기 창", () => {
  beforeEach(() => mountProfile());

  it("정확히 4MB 는 바로 제출하고 창을 띄우지 않는다", () => {
    const r = choose(fileOf(4 * MB));
    assert.equal(r.submits, 1);
    assert.equal(cropper, null);
  });

  it("4MB+1 바이트는 제출하지 않고 그 파일로 창을 띄운다", () => {
    const big = fileOf(4 * MB + 1, "big.jpg");
    const r = choose(big);
    assert.equal(r.submits, 0);
    assert.ok(cropper);
    assert.equal(cropper.file, big);
    assert.equal(actionCalls[UPLOAD].length, 0);
  });

  it("13MB 사진도 제출하지 않는다", () => {
    assert.equal(choose(fileOf(13 * MB)).submits, 0);
    assert.ok(cropper);
  });

  it("고른 뒤 칸을 비운다(같은 사진을 다시 골라도 onChange 가 난다)", () => {
    assert.equal(choose(fileOf(100)).value, "");
    assert.equal(choose(fileOf(5 * MB)).value, "");
  });

  it("파일 없이 change 가 와도 제출하지도 창을 띄우지도 않는다", () => {
    const r = choose(undefined);
    assert.equal(r.submits, 0);
    assert.equal(cropper, null);
  });

  it("예전 거절 문구(4MB 까지)는 더 안 뜬다", () => {
    choose(fileOf(5 * MB));
    assert.doesNotMatch(html, /4MB 까지 올릴 수 있습니다/);
  });
});

describe("ProfileForm: 창이 끝난 뒤", () => {
  beforeEach(() => {
    mountProfile();
    choose(fileOf(6 * MB));
    assert.ok(cropper);
  });

  it("onDone -> 창을 닫고 FormData photo 에 그 사진을 담아 한 번 올린다", () => {
    const photo = new File(["jpg"], "photo.jpg", { type: "image/jpeg" });
    cropper!.onDone(photo);
    draw();
    assert.equal(cropper, null);
    assert.equal(actionCalls[UPLOAD].length, 1);
    const sent = actionCalls[UPLOAD][0].get("photo");
    assert.ok(sent instanceof File);
    assert.equal(sent.type, "image/jpeg");
    assert.equal(sent.size, photo.size);
    // 이름 저장·사진 지우기 액션은 부르지 않는다.
    assert.equal(actionCalls[0].length, 0);
    assert.equal(actionCalls[2].length, 0);
    assert.equal(transitions, 1);
  });

  it("못 여는 사진 안내가 내정보에 뜨고 창은 닫힌다", () => {
    cropper!.onClose(CANNOT_OPEN);
    draw();
    assert.equal(cropper, null);
    assert.ok(alerts().includes(CANNOT_OPEN), html);
    assert.equal(actionCalls[UPLOAD].length, 0);
  });

  it("너무 큰 사진 안내가 내정보에 뜬다", () => {
    cropper!.onClose(TOO_BIG);
    draw();
    assert.ok(alerts().includes(TOO_BIG));
  });

  it("취소(안내 없음)면 아무 안내도 없고 올리지 않는다", () => {
    cropper!.onClose();
    draw();
    assert.equal(cropper, null);
    assert.deepEqual(alerts(), []);
    assert.equal(actionCalls[UPLOAD].length, 0);
  });

  it("안내가 뜬 뒤 작은 사진을 고르면 안내가 지워진다", () => {
    cropper!.onClose(CANNOT_OPEN);
    draw();
    choose(fileOf(1000));
    assert.deepEqual(alerts(), []);
  });

  it("안내가 뜬 뒤 큰 사진을 또 고르면 안내가 지워지고 창이 다시 뜬다", () => {
    cropper!.onClose(TOO_BIG);
    draw();
    const again = fileOf(7 * MB, "again.jpg");
    choose(again);
    assert.deepEqual(alerts(), []);
    assert.equal(cropper!.file, again);
  });
});

// ---------------------------------------------------------------------------

describe("닉네임 칸: 12자 안내와 maxLength", () => {
  it("내정보: maxLength 12, 안내에 12자", () => {
    mountProfile();
    const name = hosts.filter((h) => h.type === "input" && h.props.name === "display_name");
    assert.equal(name.length, 1);
    assert.equal(name[0].props.maxLength, 12);
    assert.match(html, /12자까지 쓸 수 있고/);
  });

  it("가입: maxLength 12, 안내에 12자", () => {
    slots = [];
    actionStates = [];
    element = createElement(AuthForm, { mode: "signup", action: async () => ({}) } as never);
    draw();
    assert.match(html, /<input[^>]*name="display_name"[^>]*maxLength="12"|<input[^>]*maxLength="12"[^>]*name="display_name"/);
    assert.match(html, /12자까지 쓸 수 있고/);
  });

  it("로그인 화면에는 닉네임 칸이 없다", () => {
    slots = [];
    actionStates = [];
    element = createElement(AuthForm, { mode: "login", action: async () => ({}) } as never);
    draw();
    assert.doesNotMatch(html, /name="display_name"/);
  });
});

// ---------------------------------------------------------------------------

function directives(csp: string): Record<string, string[]> {
  return Object.fromEntries(
    csp.split(";").map((part) => {
      const [name, ...values] = part.trim().split(/\s+/);
      return [name, values];
    }),
  );
}

describe("CSP: blob: 은 img-src 에만", () => {
  const variants = [
    buildCsp("n1"),
    buildCsp("n2", { dev: true }),
    buildCsp("n3", { sentryDsn: "https://k@o1.ingest.us.sentry.io/2" }),
  ];

  it("img-src 에 blob: 이 있다", () => {
    for (const csp of variants) assert.ok(directives(csp)["img-src"].includes("blob:"), csp);
  });

  it("다른 지시어(script-src·default-src·connect-src 등)에는 blob: 이 없다", () => {
    for (const csp of variants) {
      for (const [name, values] of Object.entries(directives(csp))) {
        if (name === "img-src") continue;
        assert.ok(!values.some((v) => v.startsWith("blob")), `${name} 에 blob: ${csp}`);
      }
    }
  });
});
