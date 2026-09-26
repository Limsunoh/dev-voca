/**
 * 내정보 화면 세 카드가 **결과가 새로 올 때** 입력칸과 안내를 어떻게
 * 정리하는지 본다. 사용자가 칸에 친 뒤 서버 결과가 오는 순서를 그대로
 * 흉내 낸다.
 *
 * 실행: cd frontend && npm test
 *
 * 계약:
 *   PasswordCard  세 칸은 제어 입력. 결과마다 passwordsAfter 로 정리한다 -
 *                 saved 면 셋 다, current_password 면 그 칸만, new_password
 *                 면 새+확인, new_password_confirm 이면 확인만 비운다. 오류는
 *                 role=alert, 성공은 role=status 상자.
 *   EmailCard     새 이메일은 제어 입력. sentTo 가 오면 비우고, 실패하면 남긴다.
 *   ProfileForm   아바타·이름을 저장값과 다르게 바꾸면 "...은 아직 저장하지
 *                 않았습니다." 가 뜨고 "저장했습니다" 는 숨는다. 저장에
 *                 성공하면 사라진다. 사진 올리기·지우기 직후에는 안 뜬다.
 *
 * 브라우저 없이 상태를 이어가는 방법: 서버 렌더는 매번 새로 그려 상태가
 * 안 남는다. 그래서 react 의 useState·useActionState 만 대역으로 바꾼다.
 * useState 는 호출 순서대로 칸을 두고 렌더 사이에 값을 들고 있으며, 렌더
 * 중에 값이 바뀌면 다시 그린다(React 가 렌더 중 setState 에 하는 일과
 * 같다). useActionState 는 테스트가 넣어 준 "서버 결과" 를 돌려준다.
 *
 * 칸에 치는 것은 jsx 런타임을 감싸 그려진 input 의 props 를 모아 두고,
 * 그 onChange 를 직접 부른다. 사람이 칸에 친 것과 같은 길을 탄다.
 *
 * 상태 칸이 호출 순서로 매겨지므로, 조건부로 나타나는 자식이 useState 를
 * 쓰면 순서가 밀린다. 그래서 Avatar(사진 실패 시 useState)는 상태 없는
 * 대역으로 바꾼다. useUnsavedGuard 는 따로 unsaved-guard.test 가 보므로
 * 여기서는 넘겨받은 값(dirty·문구)만 기록하는 대역으로 둔다.
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { beforeEach, describe, it, mock } from "node:test";
import type { ReactElement } from "react";

const require = createRequire(import.meta.url);
const realReact = require("react") as typeof import("react");
const realJsx = require("react/jsx-runtime");

// ---------------------------------------------------------------------------
// 상태를 이어 주는 react 대역
// ---------------------------------------------------------------------------

type Slot = { value: unknown };
let slots: Slot[] = [];
let cursor = 0;
let changed = false;

/** 카드가 useActionState 를 부르는 순서대로 돌려줄 서버 결과. */
let actionStates: unknown[] = [];
let actionCursor = 0;

function useState<T>(init: T | (() => T)) {
  const i = cursor++;
  if (!slots[i]) {
    slots[i] = {
      value: typeof init === "function" ? (init as () => T)() : init,
    };
  }
  const slot = slots[i];
  const set = (next: T | ((prev: T) => T)) => {
    const value =
      typeof next === "function" ? (next as (p: T) => T)(slot.value as T) : next;
    if (!Object.is(value, slot.value)) {
      slot.value = value;
      changed = true;
    }
  };
  return [slot.value as T, set] as const;
}

function useActionState<S>(_action: unknown, init: S) {
  const i = actionCursor++;
  // 처음 값도 칸에 붙잡아 둔다. 카드가 `{}` 를 매 렌더 새로 만들어 넘기는데,
  // 진짜 React 는 처음 것 하나를 계속 돌려준다. 그대로 돌려주면 매번 "새 결과"
  // 로 보여 렌더가 끝나지 않는다.
  if (!(i in actionStates)) actionStates[i] = init;
  return [actionStates[i] as S, () => {}] as const;
}

mock.module("react", {
  defaultExport: realReact,
  namedExports: {
    ...realReact,
    useState,
    useActionState,
    useEffect() {},
  },
});

/** 마지막 렌더에서 그려진 태그와 props. */
type Host = { type: string; props: Record<string, unknown> };
let hosts: Host[] = [];

const record =
  (fn: (...args: unknown[]) => unknown) =>
  (type: unknown, props: Record<string, unknown>, key?: unknown) => {
    if (typeof type === "string") hosts.push({ type, props });
    return fn(type, props, key);
  };

mock.module("react/jsx-runtime", {
  namedExports: {
    ...realJsx,
    jsx: record(realJsx.jsx),
    jsxs: record(realJsx.jsxs),
  },
});

// Avatar 는 상태 없는 대역. 그림이 무엇인지는 이 테스트의 관심이 아니다.
mock.module("@/components/Avatar", {
  namedExports: {
    AVATAR_KEYS: ["a1", "a2", "a3", "a4", "a5", "a6"],
    avatarLabel: (key: string) => `아바타 ${key}`,
    Avatar: () => null,
    AvatarMark: () => null,
  },
});

type GuardArgs = {
  dirty: boolean;
  detail: string;
  cancelLabel: string;
  confirmLabel: string;
};
let guard: GuardArgs | undefined;

mock.module("@/components/useUnsavedGuard", {
  namedExports: {
    useUnsavedGuard(args: GuardArgs) {
      guard = args;
      return null;
    },
  },
});

const { renderToStaticMarkup } = await import("react-dom/server");
const { createElement } = realReact;
const { PasswordCard } = await import("./PasswordCard");
const { EmailCard } = await import("./EmailCard");
const { ProfileForm } = await import("./ProfileForm");

// ---------------------------------------------------------------------------
// 도구
// ---------------------------------------------------------------------------

let element: ReactElement;
let html = "";

/** 상태가 가라앉을 때까지 다시 그린다. */
function draw(): string {
  for (let pass = 0; pass < 20; pass += 1) {
    cursor = 0;
    actionCursor = 0;
    changed = false;
    hosts = [];
    html = renderToStaticMarkup(element);
    if (!changed) return html;
  }
  throw new Error("렌더가 가라앉지 않는다(렌더 중 setState 무한 반복)");
}

function mount(el: ReactElement): void {
  slots = [];
  actionStates = [];
  guard = undefined;
  element = el;
  draw();
}

function input(name: string, value?: string): Record<string, unknown> {
  const found = hosts.filter(
    (h) =>
      h.type === "input" &&
      h.props.name === name &&
      (value === undefined || h.props.value === value),
  );
  assert.equal(found.length, 1, `input[name=${name}] 이 하나가 아니다: ${found.length}`);
  return found[0].props;
}

/** 사람이 칸에 친 것처럼 onChange 를 부르고 다시 그린다. */
function typeInto(name: string, value: string): void {
  const onChange = input(name).onChange as (e: unknown) => void;
  assert.ok(onChange, `${name} 이 제어 입력이 아니다(onChange 없음)`);
  onChange({ target: { value }, currentTarget: { value } });
  draw();
}

/** 서버 결과가 도착한 것처럼 k 번째 useActionState 값을 바꾸고 다시 그린다. */
function arrive(k: number, state: unknown): void {
  actionStates[k] = state;
  draw();
}

const valueOf = (name: string) => input(name).value;

// ---------------------------------------------------------------------------
// PasswordCard
// ---------------------------------------------------------------------------

describe("PasswordCard: 결과가 오면 틀린 칸만 비운다", () => {
  const fill = () => {
    typeInto("current_password", "old-1");
    typeInto("new_password", "new-1");
    typeInto("new_password_confirm", "new-1");
  };

  beforeEach(() => {
    mount(
      createElement(PasswordCard, {
        action: async () => ({}),
        hasPassword: true,
        email: "a@b.c",
      }),
    );
  });

  it("처음에는 세 칸이 비어 있고 제어 입력이다", () => {
    for (const name of ["current_password", "new_password", "new_password_confirm"]) {
      assert.equal(valueOf(name), "");
      assert.equal(typeof input(name).onChange, "function");
    }
  });

  it("친 값이 칸에 남는다", () => {
    fill();
    assert.equal(valueOf("current_password"), "old-1");
    assert.equal(valueOf("new_password"), "new-1");
    assert.equal(valueOf("new_password_confirm"), "new-1");
  });

  it("current_password 오류 -> 그 칸만 비운다", () => {
    fill();
    arrive(0, { error: "현재 비밀번호가 올바르지 않습니다.", field: "current_password" });
    assert.equal(valueOf("current_password"), "");
    assert.equal(valueOf("new_password"), "new-1");
    assert.equal(valueOf("new_password_confirm"), "new-1");
  });

  it("new_password 오류 -> 새 비밀번호와 확인을 비운다", () => {
    fill();
    arrive(0, { error: "너무 짧습니다.", field: "new_password" });
    assert.equal(valueOf("current_password"), "old-1");
    assert.equal(valueOf("new_password"), "");
    assert.equal(valueOf("new_password_confirm"), "");
  });

  it("new_password_confirm 오류 -> 확인만 비운다", () => {
    fill();
    arrive(0, { error: "새 비밀번호가 서로 다릅니다.", field: "new_password_confirm" });
    assert.equal(valueOf("current_password"), "old-1");
    assert.equal(valueOf("new_password"), "new-1");
    assert.equal(valueOf("new_password_confirm"), "");
  });

  it("칸 탓이 아닌 오류 -> 아무 칸도 안 비운다", () => {
    fill();
    arrive(0, { error: "서버에 연결할 수 없습니다." });
    assert.equal(valueOf("current_password"), "old-1");
    assert.equal(valueOf("new_password"), "new-1");
    assert.equal(valueOf("new_password_confirm"), "new-1");
  });

  it("성공 -> 셋 다 비운다", () => {
    fill();
    arrive(0, { saved: true, created: false });
    for (const name of ["current_password", "new_password", "new_password_confirm"]) {
      assert.equal(valueOf(name), "", name);
    }
  });

  it("같은 오류가 두 번 와도 두 번째에 다시 비운다", () => {
    fill();
    arrive(0, { error: "틀림", field: "current_password" });
    typeInto("current_password", "old-2");
    arrive(0, { error: "틀림", field: "current_password" });
    assert.equal(valueOf("current_password"), "");
  });

  it("결과가 새로 오지 않으면 다시 그려도 친 값을 안 지운다", () => {
    fill();
    arrive(0, { error: "틀림", field: "current_password" });
    typeInto("current_password", "old-2");
    draw();
    assert.equal(valueOf("current_password"), "old-2");
  });

  it("오류는 role=alert 상자, 성공 문구는 없다", () => {
    arrive(0, { error: "현재 비밀번호가 올바르지 않습니다.", field: "current_password" });
    assert.match(html, /<p role="alert"[^>]*>현재 비밀번호가 올바르지 않습니다\.<\/p>/);
    assert.doesNotMatch(html, /role="status"/);
  });

  it("성공은 aria-live 자리 안의 상자, 오류 상자는 없다", () => {
    arrive(0, { saved: true, created: false });
    assert.match(html, /<div aria-live="polite"><p[^>]*>비밀번호를 바꿨습니다\./);
    assert.doesNotMatch(html, /role="alert"/);
  });

  it("처음 설정 성공은 설정 문구", () => {
    arrive(0, { saved: true, created: true });
    assert.match(html, /<div aria-live="polite"><p[^>]*>비밀번호를 설정했습니다\./);
  });

  it("결과가 없어도 알림 자리(aria-live)는 미리 있다", () => {
    // 리전이 내용과 함께 새로 생기면 낭독기가 대부분 안 읽는다.
    assert.doesNotMatch(html, /role="(alert|status)"/);
    assert.match(html, /<div aria-live="polite"><\/div>/);
  });
});

describe("PasswordCard: 비밀번호가 없는 계정", () => {
  it("현재 비밀번호 칸이 없고, 새 비밀번호 오류는 두 칸을 비운다", () => {
    mount(
      createElement(PasswordCard, {
        action: async () => ({}),
        hasPassword: false,
        email: "a@b.c",
      }),
    );
    assert.equal(hosts.filter((h) => h.props.name === "current_password").length, 0);
    typeInto("new_password", "n");
    typeInto("new_password_confirm", "n");
    arrive(0, { error: "짧다", field: "new_password" });
    assert.equal(valueOf("new_password"), "");
    assert.equal(valueOf("new_password_confirm"), "");
  });
});

// ---------------------------------------------------------------------------
// EmailCard
// ---------------------------------------------------------------------------

describe("EmailCard: 새 이메일은 성공할 때만 비운다", () => {
  beforeEach(() => {
    mount(
      createElement(EmailCard, {
        action: async () => ({}),
        currentEmail: "old@devvoca.local",
        hasPassword: true,
      } as never),
    );
    typeInto("new_email", "new@devvoca.local");
  });

  it("친 새 이메일이 칸에 남는다(제어 입력)", () => {
    assert.equal(valueOf("new_email"), "new@devvoca.local");
  });

  it("실패하면 새 이메일은 그대로다", () => {
    arrive(0, { error: "비밀번호가 올바르지 않습니다." });
    assert.equal(valueOf("new_email"), "new@devvoca.local");
  });

  it("sentTo 가 오면 비운다", () => {
    arrive(0, { sentTo: "new@devvoca.local" });
    assert.equal(valueOf("new_email"), "");
  });

  it("보낸 뒤 다시 친 값은 다음 렌더에 안 지운다", () => {
    arrive(0, { sentTo: "new@devvoca.local" });
    typeInto("new_email", "again@devvoca.local");
    draw();
    assert.equal(valueOf("new_email"), "again@devvoca.local");
  });

  it("비밀번호 칸은 제어 입력이 아니다(실패해도 React 가 비운다)", () => {
    assert.equal(input("current_password").value, undefined);
  });
});

// ---------------------------------------------------------------------------
// ProfileForm
// ---------------------------------------------------------------------------

const HINT = /은 아직 저장하지 않았습니다\./;
const SAVED = /저장했습니다\./;

/** 저장 안 한 변경 안내 줄의 문장. 없으면 null. */
const hint = () => html.match(/>([^<>]*은 아직 저장하지 않았습니다\.)</)?.[1] ?? null;

/** 지금 골라진 아바타 라디오의 값. */
const checkedAvatar = () =>
  hosts.find(
    (h) => h.type === "input" && h.props.name === "avatar_choice" && h.props.checked,
  )?.props.value;

/** 서버로 가는 아바타. 라디오가 아니라 hidden 칸이 든다. */
const sentAvatar = () => input("avatar").value;

function pick(value: string): void {
  const onChange = input("avatar_choice", value).onChange as () => void;
  onChange();
  draw();
}

const PROFILE = 0;
const UPLOAD = 1;
const DELETE = 2;

function mountProfile(over: Record<string, unknown> = {}): void {
  mount(
    createElement(ProfileForm, {
      action: async () => ({}),
      initialName: "초롱",
      initialAvatar: "a1",
      shown: { type: "preset", key: "a1" },
      googlePicture: "",
      uploadPhoto: async () => ({}),
      deletePhoto: async () => ({}),
      uploadedPhoto: "",
      ...over,
    } as never),
  );
}

describe("ProfileForm: 저장 안 한 변경 안내", () => {
  beforeEach(() => mountProfile());

  it("처음에는 안내가 없고 가드도 꺼져 있다", () => {
    assert.equal(hint(), null);
    assert.equal(guard?.dirty, false);
    assert.equal(guard?.cancelLabel, "계속 고치기");
    assert.equal(guard?.confirmLabel, "나가기");
  });

  it("이름을 바꾸면 '바꾼 이름은' 이 뜨고 가드가 켜진다", () => {
    typeInto("display_name", "초롱2");
    assert.equal(hint(), "바꾼 이름은 아직 저장하지 않았습니다.");
    assert.equal(guard?.dirty, true);
    assert.equal(guard?.detail, "바꾼 이름이 저장되지 않습니다.");
  });

  it("사진을 고르면 '고른 사진은'", () => {
    pick("a3");
    assert.equal(hint(), "고른 사진은 아직 저장하지 않았습니다.");
    assert.equal(guard?.detail, "고른 사진이 저장되지 않습니다.");
  });

  it("둘 다 바꾸면 '고른 사진과 바꾼 이름은'", () => {
    pick("a3");
    typeInto("display_name", "새이름");
    assert.equal(hint(), "고른 사진과 바꾼 이름은 아직 저장하지 않았습니다.");
    assert.equal(guard?.detail, "고른 사진과 바꾼 이름이 저장되지 않습니다.");
  });

  it("저장값으로 되돌리면 안내가 사라진다", () => {
    pick("a3");
    typeInto("display_name", "새이름");
    pick("a1");
    typeInto("display_name", "초롱");
    assert.equal(hint(), null);
    assert.equal(guard?.dirty, false);
  });

  it("뒤 공백 하나도 저장 안 한 변경이다", () => {
    typeInto("display_name", "초롱 ");
    assert.equal(hint(), "바꾼 이름은 아직 저장하지 않았습니다.");
  });

  it("안내는 저장 버튼보다 위에 있다", () => {
    typeInto("display_name", "초롱2");
    const at = html.search(HINT);
    const button = html.lastIndexOf("<button");
    assert.ok(at >= 0 && at < button, "안내가 저장 버튼 뒤에 있다");
  });

  it("저장에 성공하면 안내가 사라지고 '저장했습니다' 가 뜬다", () => {
    pick("a3");
    typeInto("display_name", " 초롱3 ");
    arrive(PROFILE, { saved: true, savedName: "초롱3" });
    assert.equal(hint(), null);
    assert.match(html, SAVED);
    assert.equal(guard?.dirty, false);
    // 서버가 다듬은 이름으로 칸을 맞춘다.
    assert.equal(valueOf("display_name"), "초롱3");
    assert.equal(checkedAvatar(), "a3");
  });

  it("저장한 뒤 또 바꾸면 '저장했습니다' 를 내리고 안내를 띄운다", () => {
    typeInto("display_name", "초롱3");
    arrive(PROFILE, { saved: true, savedName: "초롱3" });
    typeInto("display_name", "초롱4");
    assert.doesNotMatch(html, SAVED);
    assert.equal(hint(), "바꾼 이름은 아직 저장하지 않았습니다.");
  });

  it("저장한 뒤 바꾼 비교 기준은 새로 저장된 값이다", () => {
    typeInto("display_name", "초롱3");
    arrive(PROFILE, { saved: true, savedName: "초롱3" });
    // 처음 이름으로 돌아가는 것도 이제는 변경이다.
    typeInto("display_name", "초롱");
    assert.equal(hint(), "바꾼 이름은 아직 저장하지 않았습니다.");
  });

  it("저장에 실패하면 안내가 남고 오류 상자가 뜬다", () => {
    typeInto("display_name", "초롱2");
    arrive(PROFILE, { error: "이미 쓰고 있는 이름입니다." });
    assert.equal(hint(), "바꾼 이름은 아직 저장하지 않았습니다.");
    assert.match(html, /role="alert"[^>]*>이미 쓰고 있는 이름입니다\./);
    assert.doesNotMatch(html, SAVED);
    assert.equal(guard?.dirty, true);
  });

  it("사진을 올린 직후에는 안내가 없다(고른 아바타가 있었어도)", () => {
    pick("a3");
    arrive(UPLOAD, { at: 1000, photoUrl: "/media/p.webp" });
    assert.equal(checkedAvatar(), "photo");
    assert.equal(hint(), null);
    assert.equal(guard?.dirty, false);
  });

  it("사진을 올려도 바꾼 이름은 여전히 안내한다", () => {
    typeInto("display_name", "초롱2");
    arrive(UPLOAD, { at: 1000, photoUrl: "/media/p.webp" });
    assert.equal(hint(), "바꾼 이름은 아직 저장하지 않았습니다.");
  });

  it("서버로 가는 아바타는 hidden 칸이 들고, 고른 것을 따라간다", () => {
    // 라디오로 보내면 React 가 폼을 비울 때 체크가 처음 것으로 돌아가,
    // 다음 저장에 옛 아바타가 실린다.
    assert.equal(sentAvatar(), "a1");
    pick("a3");
    assert.equal(sentAvatar(), "a3");
    arrive(PROFILE, { saved: true, savedName: "초롱", savedAvatar: "a3" });
    assert.equal(sentAvatar(), "a3");
  });

  it("저장이 도는 사이 더 친 이름은 지우지 않는다", () => {
    typeInto("display_name", "초롱3");
    // 저장을 누른 뒤 응답 전에 한 글자를 더 쳤다. 서버에는 "초롱3" 이 들어갔다.
    typeInto("display_name", "초롱34");
    arrive(PROFILE, { saved: true, savedName: "초롱3", sentName: "초롱3" });
    assert.equal(valueOf("display_name"), "초롱34");
    assert.equal(hint(), "바꾼 이름은 아직 저장하지 않았습니다.");
    assert.equal(guard?.dirty, true);
  });

  it("보낸 그대로면 서버가 다듬은 이름으로 맞춘다", () => {
    // 서버는 가운데 공백도 합친다. 화면에서 앞뒤만 다듬어 비교하면 못 맞춘다.
    typeInto("display_name", " 초롱  3 ");
    arrive(PROFILE, { saved: true, savedName: "초롱 3", sentName: " 초롱  3 " });
    assert.equal(valueOf("display_name"), "초롱 3");
    assert.equal(hint(), null);
  });

  it("저장이 도는 사이 고른 것은 저장된 것으로 치지 않는다", () => {
    pick("a3");
    // 저장을 누른 뒤 응답 전에 a4 를 골랐다. 서버에는 a3 이 들어갔다.
    pick("a4");
    arrive(PROFILE, { saved: true, savedName: "초롱", savedAvatar: "a3" });
    assert.equal(checkedAvatar(), "a4");
    assert.equal(hint(), "고른 사진은 아직 저장하지 않았습니다.");
    assert.equal(guard?.dirty, true);
  });
});

describe("ProfileForm: 사진 올리기 버튼", () => {
  it("label 이 inline-flex 라 최소 높이(52px)가 먹는다", () => {
    // label 은 인라인이라 min-height 가 안 먹는다. 빠지면 글자 높이로 줄어든다.
    mountProfile();
    const label = html.match(/<label class="([^"]*)"[^>]*>(?:(?!<\/label>).)*사진 올리기/)?.[1];
    assert.ok(label, "사진 올리기 label 을 못 찾았다");
    assert.match(label, /(^| )inline-flex( |$)/);
    assert.match(label, /(^| )items-center( |$)/);
    assert.match(html, /min-height:var\(--hit-min\)[^"]*"[^>]*>(?:(?!<\/label>).)*사진 올리기/);
  });
});

describe("ProfileForm: 사진 지우기 직후", () => {
  it("올린 사진을 쓰던 계정이 지우면 안내가 없다", () => {
    mountProfile({
      initialAvatar: "photo",
      uploadedPhoto: "/media/p.webp",
      shown: { type: "photo", url: "/media/p.webp" },
    });
    assert.equal(checkedAvatar(), "photo");
    arrive(DELETE, { at: 2000, photoUrl: "" });
    assert.equal(hint(), null);
    assert.equal(guard?.dirty, false);
  });

  it("올렸다가 지워도 안내가 없다", () => {
    mountProfile();
    arrive(UPLOAD, { at: 1000, photoUrl: "/media/p.webp" });
    arrive(DELETE, { at: 2000, photoUrl: "" });
    assert.equal(hint(), null);
  });

  it("구글 사진이 있는 계정이 올린 사진을 지우면 구글 사진으로 간다", () => {
    // 서버는 photo 를 비우고, 비면 구글 사진을 그린다. 아바타로 옮기면
    // 머리말과 링이 갈리고, 그대로 저장하면 a1 이 실제로 저장된다.
    mountProfile({
      initialAvatar: "photo",
      uploadedPhoto: "/media/p.webp",
      googlePicture: "https://g/pic.jpg",
      shown: { type: "photo", url: "/media/p.webp" },
    });
    arrive(DELETE, { at: 2000, photoUrl: "" });
    assert.equal(checkedAvatar(), "google");
    assert.equal(sentAvatar(), "google");
    assert.equal(hint(), null);
  });

  it("지운 뒤의 선택은 서버가 알려준 값을 쓴다", () => {
    // 구글 사진이 없으면 서버는 계정마다 정해진 아바타를 그린다. 화면은
    // 그것이 무엇인지 짐작할 수 없어서 결과로 받는다.
    mountProfile({
      initialAvatar: "photo",
      uploadedPhoto: "/media/p.webp",
      shown: { type: "photo", url: "/media/p.webp" },
    });
    arrive(DELETE, { at: 2000, photoUrl: "", savedAvatar: "a4" });
    assert.equal(checkedAvatar(), "a4");
    assert.equal(sentAvatar(), "a4");
    assert.equal(hint(), null);
  });

  it("구글 사진을 골라 둔 채 올린 사진을 지우면 선택이 그대로다", () => {
    // 서버는 저장된 것이 photo 일 때만 비운다.
    mountProfile({
      initialAvatar: "google",
      uploadedPhoto: "/media/p.webp",
      googlePicture: "https://g/pic.jpg",
      shown: { type: "photo", url: "https://g/pic.jpg" },
    });
    arrive(DELETE, { at: 2000, photoUrl: "" });
    assert.equal(checkedAvatar(), "google");
    assert.equal(hint(), null);
    assert.equal(guard?.dirty, false);
  });
});

describe("ProfileForm: 저장된 선택지가 화면에 없을 때", () => {
  it("사진 없이 photo 면 서버가 그리는 것을 고른다", () => {
    // Admin 에서 고치면 생긴다. 그대로 두면 골라진 칸 없이 photo 를 보내
    // 저장할 때마다 막힌다.
    mountProfile({
      initialAvatar: "photo",
      uploadedPhoto: "",
      shown: { type: "preset", key: "a2" },
    });
    assert.equal(checkedAvatar(), "a2");
    assert.equal(sentAvatar(), "a2");
    assert.equal(hint(), null);
  });

  it("구글 사진 없이 google 이어도 같다", () => {
    mountProfile({
      initialAvatar: "google",
      googlePicture: "",
      shown: { type: "preset", key: "a5" },
    });
    assert.equal(checkedAvatar(), "a5");
    assert.equal(sentAvatar(), "a5");
  });
});
