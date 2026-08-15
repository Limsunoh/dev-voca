import Link from "next/link";

import { logoutAction } from "@/app/(auth)/actions";
import { Avatar } from "@/components/Avatar";
import { getCurrentUser } from "@/lib/session";

/**
 * 모든 화면 위에 놓이는 머리말.
 *
 * 서버 컴포넌트라 로그인 여부를 직접 확인한다. 클라이언트에서 확인하면
 * 화면이 한 번 로그아웃 상태로 그려졌다가 바뀌어 깜빡인다.
 */
export async function SiteHeader() {
  const user = await getCurrentUser();

  return (
    <header className="border-b border-slate-200 dark:border-slate-800">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-4 py-3">
        <Link
          href="/"
          className="font-mono text-lg font-bold text-slate-900 dark:text-slate-100"
        >
          devvoca
        </Link>

        {user ? (
          <nav aria-label="계정" className="flex items-center gap-2 text-sm">
            {/* 이름과 사진이 프로필로 가는 입구다. 폰에서는 이름이 길면
                줄바꿈이 나서 머리말 높이가 튀므로 한 줄로 자른다. */}
            <Link
              href="/profile"
              className="flex min-w-0 items-center gap-2 rounded-md px-2 py-1.5 transition hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus dark:hover:bg-slate-800"
            >
              <Avatar shown={user.avatar_display} size={28} />
              <span className="max-w-28 truncate text-slate-700 sm:max-w-40 dark:text-slate-300">
                {user.name}
              </span>
            </Link>
            {/* 로그아웃은 상태를 바꾸는 동작이라 링크가 아니라 폼이다.
                링크로 두면 브라우저나 확장이 미리 눌러볼 수 있다. */}
            <form action={logoutAction}>
              <button
                type="submit"
                className="rounded-md border border-slate-300 px-3 py-1.5 text-slate-700 transition hover:border-slate-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-500"
              >
                로그아웃
              </button>
            </form>
          </nav>
        ) : (
          <nav aria-label="계정" className="flex items-center gap-2 text-sm">
            <Link
              href="/login"
              className="rounded-md px-3 py-1.5 text-slate-700 transition hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus dark:text-slate-300 dark:hover:bg-slate-800"
            >
              로그인
            </Link>
            <Link
              href="/signup"
              className="rounded-md bg-slate-900 px-3 py-1.5 font-medium text-white transition hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
            >
              가입하기
            </Link>
          </nav>
        )}
      </div>
    </header>
  );
}
