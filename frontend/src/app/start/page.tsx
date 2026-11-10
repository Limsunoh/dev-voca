import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { redirect } from "next/navigation";

import logo from "@/app/start/logo.webp";
import { StartChoices } from "@/app/start/StartChoices";
import { getCurrentUser, isGuestChosen } from "@/lib/session";

export const metadata: Metadata = {
  title: "dev-voca",
  description: "개발하면서 마주치는 영어, 매일 보다 보면 익숙해집니다.",
};

/**
 * 앱을 처음 열었을 때.
 *
 * 여기서 한 번은 골라야 홈으로 간다. 웹은 그냥 들어가서 필요할 때
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
export default async function StartPage({
  searchParams,
}: {
  searchParams: Promise<{ deleted?: string }>;
}) {
  // 이미 정한 사람에게 다시 물어볼 이유가 없다. 홈으로 보낸다.
  const [user, guest, { deleted }] = await Promise.all([
    getCurrentUser(),
    isGuestChosen(),
    searchParams,
  ]);
  if (user || guest) redirect("/");

  // 배경 레이어를 깔지 않는다. 크림 바탕(body)이 그대로 이 화면의 배경이다.
  // 다크였을 때는 surface-learn 그라디언트를 깔았는데, 그건 어두운 화면에서
  // 밴딩을 흩고 영역을 가르려던 것이라 크림에서는 얹을 자리가 없다.
  return (
    // 이 화면에는 탭바가 없다(app/start/layout.tsx). 고르기 전에는
    // 갈 곳이 없으므로 이동 수단을 보여주면 빠져나갈 수 있다.
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-between px-6 py-10">
      {/* 계정 삭제를 마치고 온 경우(profile/actions.ts). */}
      {deleted === "1" && (
        <p
          role="status"
          className="p-4 text-sm"
          style={{
            background: "var(--paper)",
            color: "var(--foreground)",
            borderRadius: "var(--radius-xl)",
            boxShadow: "var(--lift-card)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          계정을 삭제했습니다.
        </p>
      )}

      {/* 가운데 정렬. 앱 첫 화면이라 왼쪽 정렬이면 오른쪽이 비어 한쪽으로 쏠려 보인다.
          운영자가 정했다(2026-11-11). design-taste-frontend 의 "첫 화면은 가운데 정렬을 피한다" 의 예외다. */}
      <div className="flex flex-1 flex-col items-center justify-center text-center">
        <p
          className="rise text-sm"
          // 12px 글자도 --brand(크림 위 8.84:1)면 충분하다.
          style={{
            color: "var(--brand)",
            fontWeight: "var(--weight-bold)",
          }}
        >
          개발자를 위한 영어
        </p>
        {/* 로고 그림의 바탕을 화면 바탕(--background)과 같은 색으로 칠해 둬서
            그림의 테두리가 안 보인다. 최적화를 끈 것도 그래서다 - 다시 손실
            압축하면 바탕색이 한두 단계 어긋나 네모가 비친다.

            폭은 내용 폭을 채우되, 높이가 화면 높이의 30% 를 넘지 않게
            한다. 세로가 짧은 폰(375x667, 폴드 접은 416x657)에서 아래 버튼이
            화면 밖으로 밀리지 않게 하는 상한이다. 757/509 는 그림의 가로세로 비다.

            그림은 탭 아이콘과 같은 글자 없는 dv 마크다(운영자 결정, 2026-11-11). */}
        <h1 className="rise mt-4 w-full [animation-delay:80ms]">
          <Image
            src={logo}
            alt="dev-voca"
            loading="eager"
            unoptimized
            className="mx-auto h-auto w-[min(100%,calc(30svh*757/509))]"
          />
        </h1>
        <p
          className="rise mt-4 text-lg leading-relaxed [animation-delay:160ms]"
          style={{ color: "var(--text-muted)" }}
        >
          개발하면서 마주치는 영어,
          <br />
          매일 보다 보면 익숙해집니다.
        </p>
      </div>

      <div className="rise flex flex-col gap-3 [animation-delay:240ms]">
        <StartChoices />

        {/* 로그인은 접어둔다. 앱에서 쓸 주된 길이 아니고, 셋을 나란히 두면
              무엇을 고를지 한 박자 늦어진다. 구글로 가입한 기존 회원도 이
              길로 간다. 로그인 화면의 구글 버튼에는 체크가 없다. */}
        <p
          className="mt-1 text-center text-sm"
          style={{ color: "var(--text-muted)" }}
        >
          이미 계정이 있다면{" "}
          <Link
            href="/login"
            className="underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            style={{
              color: "var(--brand)",
              fontWeight: "var(--weight-bold)",
            }}
          >
            로그인
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
