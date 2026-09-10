"use client";

import type { MicState } from "@/lib/speech";

/**
 * 마이크를 켜기 전에 먼저 보는 카드.
 *
 * **권한 창을 바로 띄우지 않는 것이 이 화면의 전부다.** 왜 필요한지 말하지
 * 않고 물으면 거절당하고, 브라우저는 한 번 거절한 뒤로는 다시 묻지 않는다.
 * 그러면 사용자가 스스로 되돌릴 방법이 화면에 없다 - 주소창 자물쇠를 눌러
 * 바꿔야 하는데 그걸 아는 사람이 많지 않다.
 *
 * 그래서 상태를 먼저 읽고(readMicState, 권한 창이 안 뜬다) 그에 맞는 것만
 * 보여준다. 물어봐도 되는 상태일 때만 버튼이 권한을 요청한다.
 */

export function MicGate({
  state,
  onAllow,
  pending,
}: {
  state: MicState;
  /** "마이크 켜기" 를 눌렀을 때. 이때 처음으로 권한 창이 뜬다. */
  onAllow: () => void;
  pending: boolean;
}) {
  const copy = COPY[state];

  return (
    <section
      className="grid gap-4 p-5"
      style={{
        background: "var(--paper)",
        borderRadius: "var(--radius-2xl)",
        boxShadow: "var(--lift-card)",
      }}
    >
      <div className="grid gap-2">
        <h2
          className="text-[length:var(--text-lg)]"
          style={{
            color: "var(--foreground)",
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-tight)",
          }}
        >
          {copy.title}
        </h2>
        <p
          className="text-sm leading-relaxed"
          style={{ color: "var(--text-body)" }}
        >
          {copy.body}
        </p>
      </div>

      {/* 구글로 음성이 간다는 것을 켜기 전에 알린다.

          우리 서버에 음성이 안 온다는 것과 **별개 사실**이다. 브라우저가
          글자로 바꾸려고 구글에 보낸다. 마이크는 사용자가 가장 경계하는
          권한이라, 이걸 안 적고 켜게 하면 나중에 알았을 때 배신이 된다.

          작게 흘려 쓰지 않고 버튼 바로 위에 둔다 - 누르기 직전에 읽혀야
          알고 누르는 것이 된다. */}
      {copy.showPrivacy && (
        <p
          className="rounded-[var(--radius-xl)] p-3 text-xs leading-relaxed"
          style={{
            background: "var(--background-deep)",
            color: "var(--text-muted)",
          }}
        >
          말한 내용은 브라우저가 글자로 바꿉니다. 그 과정에서 음성이 구글
          서버를 거칩니다. devvoca 서버에는 바뀐 글자만 오고 목소리는 저장하지
          않습니다.
        </p>
      )}

      {copy.action && (
        <button
          type="button"
          onClick={onAllow}
          disabled={pending}
          // 이 화면의 유일한 코랄. 주된 동작이 하나여야 무엇을 눌러야 할지
          // 한눈에 보인다.
          className="dv-btn w-full rounded-[var(--radius-pill)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-60 sm:w-auto sm:justify-self-start sm:px-8"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--coral)",
              color: "var(--text-on-color)",
              border: 0,
              // 두께는 인라인 boxShadow 로 주지 않는다. 그러면 :active 눌림이
              // 죽어서 버튼이 안 내려간다.
              "--lift": "var(--lift-button)",
              fontWeight: "var(--weight-black)",
              letterSpacing: "var(--tracking-tight)",
            } as React.CSSProperties
          }
        >
          {pending ? "여는 중" : copy.action}
        </button>
      )}
    </section>
  );
}

/**
 * 상태마다 다른 안내.
 *
 * "마이크를 쓸 수 없습니다" 하나로 뭉치지 않는 이유: 사용자가 할 수 있는
 * 일이 상태마다 다르다. 마이크가 없으면 꽂아야 하고, 거절한 상태면 주소창에서
 * 풀어야 하고, 브라우저가 못 하면 다른 브라우저로 와야 한다. 뭉쳐 놓으면
 * 셋 다 "안 되네" 로 끝난다.
 */
const COPY: Record<
  MicState,
  { title: string; body: string; action?: string; showPrivacy?: boolean }
> = {
  prompt: {
    title: "소리내어 읽어봅니다",
    body: "화면에 뜨는 단어를 소리내어 읽으면 맞게 읽었는지 알려줍니다. 마이크를 한 번 켜야 합니다.",
    action: "마이크 켜기",
    showPrivacy: true,
  },
  granted: {
    title: "소리내어 읽어봅니다",
    body: "화면에 뜨는 단어를 소리내어 읽으면 맞게 읽었는지 알려줍니다.",
    action: "시작하기",
    showPrivacy: true,
  },
  denied: {
    title: "마이크가 막혀 있습니다",
    body: "이 사이트의 마이크 사용이 거절된 상태입니다. 브라우저 주소창 왼쪽의 자물쇠(또는 슬라이더) 아이콘을 눌러 마이크를 허용으로 바꾸고 화면을 새로고침해주세요.",
  },
  "no-device": {
    title: "마이크를 찾지 못했습니다",
    body: "이 기기에 마이크가 없거나 연결되지 않았습니다. 마이크를 연결한 뒤 화면을 새로고침해주세요. 이어폰에 달린 마이크도 됩니다.",
  },
  insecure: {
    title: "안전한 연결에서만 됩니다",
    body: "마이크는 https 로 접속했을 때만 열 수 있습니다. 주소가 http 로 시작한다면 https 로 다시 들어와주세요.",
  },
  unsupported: {
    title: "이 브라우저에서는 아직 안 됩니다",
    body: "소리내어 읽기는 크롬·엣지 계열 브라우저에서 동작합니다. 다른 기능은 그대로 쓸 수 있고, 이 화면만 크롬에서 열어주세요.",
  },
};
