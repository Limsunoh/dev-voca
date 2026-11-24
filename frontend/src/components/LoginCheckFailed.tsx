import Link from "next/link";

import { logoutAction } from "@/app/(auth)/actions";

/**
 * 로그인 쿠키는 있는데 백엔드가 답하지 않아 누구인지 확인하지 못했을 때
 * (lib/session.ts 의 getLoginState 가 unreachable). 홈과 내정보가 그린다.
 *
 * 첫 화면(/start)이나 로그인 화면으로 보내지 않는다. 거기서 "게스트로
 * 둘러보기" 를 누르면 멀쩡한 로그인 쿠키가 지워진다.
 *
 * throw 해서 error.tsx 에 맡기지 않는 이유: 코드 오류가 아니라 백엔드가 잠깐
 * 안 받는 것이라 Sentry 에 화면 오류로 쌓을 일이 아니다. 배치와 버튼 둘의
 * 모양은 error.tsx 와 같다. 탭바는 루트 레이아웃에 있어 그대로 남는다. 그래서
 * 탭바가 없는 화면(/start/daily 등)은 이것을 그리지 않고 홈으로 보낸다.
 *
 * "다시 시도" 는 같은 주소로 다시 간다. 동적 화면이라 서버가 다시 그리며
 * 로그인을 다시 묻는다. 미리 받기는 끈다 - 백엔드가 안 받는 동안 미리 받아
 * 봐야 같은 화면이 온다.
 *
 * "로그아웃" 을 두는 이유: 백엔드 전체가 아니라 한 회원의 /me 만 계속 500 을 내면
 * (그 회원 행 때문에 터지는 버그 등) 그 사람은 어느 화면에서도 이 화면으로 돌아와,
 * 로그아웃 버튼이 있는 내정보에도 못 간다. logoutAction 은 백엔드가 답하지 않아도
 * 이 기기의 쿠키를 지운다. 갈색은 "다시 시도" 가 가진다 - 로그아웃은 되돌릴 수 없어
 * 주된 동작으로 보이면 안 된다(내정보의 로그아웃 버튼과 같은 이유).
 */
export function LoginCheckFailed({ retry }: { retry: string }) {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center px-4 py-10 text-center">
      <h1
        style={{
          fontSize: "var(--text-2xl)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
          color: "var(--foreground)",
        }}
      >
        로그인을 확인하지 못했습니다
      </h1>
      <p className="mt-2" style={{ color: "var(--text-muted)" }}>
        서버가 응답하지 않습니다. 로그인은 그대로이니 잠시 뒤 다시
        시도해주세요.
      </p>

      {/* flex-wrap 과 justify-center 는 error.tsx 와 같은 이유다(글자 200% 에서
          버튼 둘이 한 줄에 못 들어갈 때 줄을 바꾼다). */}
      <div className="mt-6 flex flex-wrap justify-center gap-2.5">
        <Link
          href={retry}
          prefetch={false}
          className="dv-btn flex items-center justify-center px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--brand)",
              color: "var(--text-on-color)",
              borderRadius: "var(--radius-pill)",
              fontWeight: "var(--weight-black)",
              textDecoration: "none",
              "--lift": "var(--lift-button)",
            } as React.CSSProperties
          }
        >
          다시 시도
        </Link>
        <form action={logoutAction}>
          <button
            type="submit"
            className="dv-btn px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            style={
              {
                minHeight: "var(--hit-min)",
                background: "var(--paper)",
                color: "var(--foreground)",
                border: 0,
                borderRadius: "var(--radius-pill)",
                fontWeight: "var(--weight-black)",
                "--lift": "var(--lift-button-paper)",
              } as React.CSSProperties
            }
          >
            로그아웃
          </button>
        </form>
      </div>
    </main>
  );
}
