import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { continueAsGuestAction } from "@/app/start/actions";
import { getCurrentUser, isGuestChosen } from "@/lib/session";

export const metadata: Metadata = {
  title: "devvoca",
  description: "개발하면서 마주치는 영어, 하나씩 익혀봅니다.",
};

/**
 * 앱을 처음 열었을 때.
 *
 * **여기서 한 번은 골라야 홈으로 간다.** 웹은 그냥 들어가서 필요할 때
 * 로그인 버튼을 찾지만, 앱은 열자마자 "누구로 시작할지" 를 묻는다.
 * 그 차이가 앱처럼 보이느냐를 크게 가른다.
 *
 * 게스트를 위에 두지 않는다. 점수와 순위가 남는 쪽이 이 앱의 본래
 * 모습이고, 게스트는 "일단 둘러보고 싶다" 는 사람을 위한 우회로다.
 * 다만 막지는 않는다 - 가입을 강요하면 그냥 지운다.
 *
 * 한 번 고르면 30일 동안 다시 안 묻는다. 로그아웃하면 그 표시도 지워져
 * 여기로 돌아온다(session.clearToken).
 */
export default async function StartPage() {
  // 이미 정한 사람에게 다시 물어볼 이유가 없다. 홈으로 보낸다.
  const [user, guest] = await Promise.all([getCurrentUser(), isGuestChosen()]);
  if (user || guest) redirect("/");

  // 배경 레이어를 깔지 않는다. 크림 바탕(body)이 그대로 이 화면의 배경이다.
  // 다크였을 때는 surface-learn 그라디언트를 깔았는데, 그건 어두운 화면에서
  // 밴딩을 흩고 영역을 가르려던 것이라 크림에서는 얹을 자리가 없다.
  return (
    // 이 화면에는 탭바가 없다(app/start/layout.tsx). 고르기 전에는
    // 갈 곳이 없으므로 이동 수단을 보여주면 빠져나갈 수 있다.
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-between px-6 py-10">
      <div className="flex flex-1 flex-col justify-center">
        <p
          className="rise text-sm"
          // 12px 글자라 --coral(3.15:1)이 아니라 --coral-deep(4.93:1).
          style={{
            color: "var(--coral-deep)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          개발자를 위한 영어
        </p>
        <h1
          className="rise mt-3 font-mono text-[2.75rem] leading-none tracking-[var(--tracking-tighter)] [animation-delay:80ms]"
          style={{
            color: "var(--foreground)",
            fontWeight: "var(--weight-black)",
          }}
        >
          devvoca
        </h1>
        <p
          className="rise mt-4 text-lg leading-relaxed [animation-delay:160ms]"
          style={{ color: "var(--text-muted)" }}
        >
          개발하면서 마주치는 영어,
          <br />
          하나씩 익혀봅니다.
        </p>
      </div>

      <div className="rise flex flex-col gap-3 [animation-delay:240ms]">
        {/* 구글을 먼저 둔다. 점수와 순위가 남는 쪽이 본래 모습이다. */}
        <a
          href="/api/auth/google"
          className="dv-btn flex items-center justify-center rounded-[var(--radius-pill)] px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          style={
            {
              minHeight: "var(--hit-min)",
              background: "var(--coral)",
              color: "var(--text-on-color)",
              "--lift": "var(--lift-button)",
              fontWeight: "var(--weight-black)",
              letterSpacing: "var(--tracking-tight)",
            } as React.CSSProperties
          }
        >
          구글로 시작하기
        </a>

        <form action={continueAsGuestAction}>
          <button
            type="submit"
            className="dv-btn flex w-full items-center justify-center rounded-[var(--radius-pill)] px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            style={
              {
                minHeight: "var(--hit-min)",
                background: "var(--paper)",
                color: "var(--foreground)",
                border: 0,
                "--lift": "var(--lift-button-paper)",
                fontWeight: "var(--weight-bold)",
              } as React.CSSProperties
            }
          >
            게스트로 둘러보기
          </button>
        </form>

        {/* 이메일 로그인은 접어둔다. 앱에서 쓸 주된 길이 아니고, 셋을
              나란히 두면 무엇을 고를지 한 박자 늦어진다. */}
        <p
          className="mt-1 text-center text-sm"
          style={{ color: "var(--text-muted)" }}
        >
          이미 계정이 있다면{" "}
          <Link
            href="/login"
            className="underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            style={{
              color: "var(--coral-deep)",
              fontWeight: "var(--weight-bold)",
            }}
          >
            이메일로 로그인
          </Link>
        </p>

        <p
          className="mt-2 text-center text-xs leading-relaxed"
          // 읽어야 하는 문장이다. 게스트로 시작하면 무엇을 잃는지가
          // 여기에만 적혀 있어서, 흐리면 그것을 모르고 고르게 된다.
          style={{ color: "var(--text-muted)" }}
        >
          게스트로 시작하면 점수와 순위가 남지 않습니다.
          <br />
          나중에 로그인하면 그때부터 쌓입니다.
        </p>
      </div>
    </main>
  );
}
