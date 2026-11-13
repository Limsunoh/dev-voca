"use client";

import Script from "next/script";
import { type ReactNode, useEffect, useRef, useState, useTransition } from "react";

import { googleCredentialAction, prepareGoogleButton } from "@/app/(auth)/google-actions";

/** 구글 스크립트(Google Identity Services) 중 여기서 쓰는 것만. */
export type GoogleId = {
  initialize(config: Record<string, unknown>): void;
  renderButton(parent: HTMLElement, options: Record<string, unknown>): void;
};
declare global {
  interface Window {
    google?: { accounts?: { id?: GoogleId } };
  }
}

/** 구글 버튼의 가장 넓은 폭(px). 구글 스크립트가 받는 상한이다. */
const MAX_WIDTH = 400;

/** 구글 버튼이 나타나길 기다리는 시간(ms). 넘기면 예전 링크를 그대로 둔다. */
const BUTTON_WAIT_MS = 10_000;

/**
 * 구글이 그린 버튼이 보이는가. 구글 스크립트는 el 안에 iframe 을 넣고, 버튼이
 * 그려지면 그 크기를 키운다. 주소가 허용되지 않으면 0x0 으로 남는다.
 */
export function isGoogleButtonVisible(el: Pick<HTMLElement, "querySelector">): boolean {
  const frame = el.querySelector("iframe");
  return !!frame && frame.offsetHeight > 0 && frame.offsetWidth > 0;
}

/**
 * 구글 스크립트에 설정을 넘기고 el 안에 공식 버튼을 그린다.
 *
 * use_fedcm_for_button 이 있어야 폰 Chrome 에서 화면 아래 계정 창(FedCM)을
 * 쓴다. 없으면 구글이 작은 창(팝업)을 띄운다. 폭은 자리에 맞추되 구글이 받는
 * 범위(200~400px) 안으로.
 */
export function showGoogleButton(
  id: GoogleId,
  el: HTMLElement,
  prep: { clientId: string; nonce: string },
  opts: { context: "signin" | "signup"; onCredential: (credential: string) => void },
): void {
  id.initialize({
    client_id: prep.clientId,
    nonce: prep.nonce,
    context: opts.context,
    use_fedcm_for_button: true,
    ux_mode: "popup",
    callback: (response: { credential?: unknown }) => {
      if (typeof response?.credential === "string" && response.credential) {
        opts.onCredential(response.credential);
      }
    },
  });
  renderGoogleButton(id, el);
}

/** 버튼의 폭(px). 자리에 맞추되 구글이 받는 범위(200~400px) 안으로. */
export function buttonWidth(el: Pick<HTMLElement, "offsetWidth">): number {
  return Math.min(MAX_WIDTH, Math.max(200, Math.round(el.offsetWidth)));
}

/**
 * el 안에 공식 버튼을 (다시) 그린다. 구글은 그릴 때의 폭을 고정하므로, 폴드를
 * 펼친 채 그리고 접으면 버튼이 옆으로 넘친다. 폭이 바뀌면 다시 부른다.
 */
export function renderGoogleButton(id: GoogleId, el: HTMLElement): void {
  id.renderButton(el, {
    type: "standard",
    theme: "outline",
    size: "large",
    shape: "pill",
    text: "continue_with",
    logo_alignment: "center",
    locale: "ko",
    width: buttonWidth(el),
  });
}

/**
 * 구글 로그인 버튼. 구글 스크립트가 그리는 공식 버튼이다.
 *
 * 폰 Chrome(앱 포함)에서는 누르면 화면 아래에서 계정 선택 창(FedCM)이 올라오고
 * 페이지를 떠나지 않는다. 그래서 방문 기록에 구글 칸이 남지 않아, 로그인한 뒤
 * 홈에서 뒤로 한 번이면 앱이 닫힌다(예전에는 구글 화면을 다녀와 뒤로 가기가
 * 구글 화면으로 갔다). FedCM 이 없는 브라우저에서는 구글 스크립트가 작은 창을
 * 띄운다. 어느 쪽이든 구글이 신분 토큰을 주고, googleCredentialAction 이
 * 백엔드에 넘겨 확인받는다.
 *
 * 화면 아래 창 방식을 구글이 공식으로 지원하는 것은 구글이 직접 그리는 이
 * 버튼뿐이라 모양을 우리 것으로 바꾸지 않는다(11-13 사용자 결정).
 *
 * 구글 스크립트가 뜨기 전, 못 뜨면(차단·끊김), 서버에 클라이언트 ID 가 없으면,
 * 구글이 버튼을 그리지 못하면(구글 콘솔의 "승인된 자바스크립트 원본" 에 이
 * 주소가 없으면) fallback(구글 화면으로 가는 예전 링크)을 그 자리에 보인다.
 * 누를 수 없는 빈 칸이 남지 않는다.
 *
 * consent 는 가입 동의 세 항목을 켠 뒤 그린 버튼에서만 true 다. 새 계정은 그
 * 값이 있어야 만들어진다.
 */
export function GoogleButton({
  next,
  consent = false,
  context,
  fallback,
}: {
  next?: string;
  consent?: boolean;
  /** 구글 버튼과 계정 창의 문구 종류. 로그인 화면은 signin, 가입은 signup. */
  context: "signin" | "signup";
  fallback: ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [scriptReady, setScriptReady] = useState(false);
  const [shown, setShown] = useState(false);
  const [pending, startTransition] = useTransition();
  /** 신분 토큰을 이미 보냈나. 두 번째부터는 버린다. */
  const sentRef = useRef(false);

  useEffect(() => {
    if (!scriptReady) return;
    let cancelled = false;
    let poll: ReturnType<typeof setInterval> | undefined;
    let stopPoll: ReturnType<typeof setTimeout> | undefined;
    let resize: ResizeObserver | undefined;

    // 구글이 준 신분 토큰을 서버로 보낸다. 한 번만 보낸다. 확인하는 사이 다시
    // 눌러 토큰이 또 오면, 첫 번째가 이미 쓴 쿠키 값이 없어 실패하고 로그인
    // 화면으로 가 돌아갈 곳을 잃는다.
    //
    // 액션은 끝나면 redirect 로 화면을 옮긴다. 호출 자체가 실패하면(망이
    // 끊겼거나, 배포 직후라 열려 있던 화면의 액션이 서버에 없거나) 오류가 화면
    // 전체의 오류 화면으로 올라가므로, 여기서 받아 로그인 화면의 안내로 보낸다.
    const send = (credential: string) => {
      if (sentRef.current) return;
      sentRef.current = true;
      startTransition(async () => {
        let failed = false;
        try {
          failed = !!(await googleCredentialAction({ credential, next, consent }))?.failed;
        } catch (error) {
          console.error("구글 로그인을 보내지 못했습니다", error);
          failed = true;
        }
        // 라우터가 아니라 문서를 새로 받는다. 같은 로그인 화면이어도 버튼이 새로
        // 붙어 새 nonce 를 받고, 배포 직후라면 새 화면이 필요하다. 바꿔치기라
        // 기록이 늘지 않는다.
        if (failed) window.location.replace("/login?error=google");
      });
    };

    prepareGoogleButton()
      .then((prep) => {
        const id = window.google?.accounts?.id;
        const el = box.current;
        if (cancelled || !prep || !id || !el) return;
        showGoogleButton(id, el, prep, { context, onCredential: send });
        // 구글 버튼이 실제로 크기를 갖고 나타난 뒤에만 예전 링크를 걷는다.
        // 구글 콘솔에 이 주소가 등록되지 않았으면 구글이 버튼을 0x0 으로
        // 그리고 끝난다. 그때 링크까지 걷으면 누를 것이 없는 화면이 된다
        // (11-13 localhost 에서 실제로 그랬다).
        poll = setInterval(() => {
          if (isGoogleButtonVisible(el)) {
            clearInterval(poll);
            setShown(true);
          }
        }, 200);
        stopPoll = setTimeout(() => clearInterval(poll), BUTTON_WAIT_MS);
        // 폭이 바뀌면(폴드를 접고 펴면) 다시 그린다.
        let width = buttonWidth(el);
        resize = new ResizeObserver(() => {
          const now = buttonWidth(el);
          if (Math.abs(now - width) < 8) return;
          width = now;
          renderGoogleButton(id, el);
        });
        resize.observe(el);
      })
      .catch((error) => {
        // 준비가 실패하면 예전 링크가 그대로 남는다. 원인은 기록만 한다.
        console.warn("구글 버튼을 준비하지 못했습니다", error);
      });
    return () => {
      cancelled = true;
      clearInterval(poll);
      clearTimeout(stopPoll);
      resize?.disconnect();
    };
  }, [scriptReady, next, consent, context]);

  return (
    // min-w-0: 시작 화면 동의 창처럼 그리드 안에 놓이면 안의 iframe 폭 아래로
    // 줄지 않아, 폴드를 접어도 다시 그리지 못하고 창이 화면 밖으로 넘쳤다.
    <div className="relative min-w-0" style={{ minHeight: "var(--hit-min)" }}>
      <Script
        src="https://accounts.google.com/gsi/client"
        strategy="afterInteractive"
        onReady={() => setScriptReady(true)}
      />
      {/* 구글 스크립트가 버튼을 그려 넣는 자리. 폭을 재야 해서 처음부터
          보이게 두고, 그려지기 전에는 예전 링크를 그 위에 덮는다. */}
      <div
        ref={box}
        className="flex min-w-0 justify-center"
        // 나타나기 전에는 숨기고 누를 수도 읽을 수도 없게 한다. 구글은 주소가
        // 허용되지 않아도 버튼 글자를 여기 넣어 두는데, 그러면 예전 링크 밑에
        // 동작하지 않는 버튼이 하나 더 그려지고 읽힌다(11-13 impeccable 이 잡았다).
        // visibility 는 자리를 그대로 두어 폭과 iframe 크기를 재는 데 지장이 없다.
        style={{
          minHeight: "var(--hit-min)",
          alignItems: "center",
          visibility: shown ? undefined : "hidden",
        }}
        inert={!shown}
      />
      {!shown && <div className="absolute inset-0">{fallback}</div>}
      {/* 확인하는 동안 구글 버튼을 덮어 다시 누르지 못하게 한다. */}
      {pending && <div className="absolute inset-0" aria-hidden />}
      {pending && (
        <p
          role="status"
          className="mt-2 text-center text-sm"
          style={{ color: "var(--text-muted)" }}
        >
          구글 계정을 확인하는 중입니다.
        </p>
      )}
    </div>
  );
}
