import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { logoutAction } from "@/app/(auth)/actions";
import { updateProfileAction } from "@/app/profile/actions";
import { MyStandings } from "@/components/MyStandings";
import { ProfileForm } from "@/components/ProfileForm";
import { fetchMyStandings } from "@/lib/api/leaderboards";
import { getCurrentUser, getToken } from "@/lib/session";

export const metadata: Metadata = {
  title: "내 프로필 · devvoca",
};

/**
 * 내 프로필.
 *
 * 사진과 이름을 바꾸고, 순위를 보고, 계정 정보를 보고, 로그아웃한다.
 *
 * 순위는 세 종류(주간·전체·꾸준함)의 내 줄만 본다 - 여기는 남과 비교하러
 * 오는 자리가 아니라 자기 상태를 보러 오는 자리라 스무 줄 목록이 필요
 * 없다. 아직 못 오른 종류는 0 이 아니라 - 로 둔다. 0 은 "0점을 냈다" 로
 * 읽혀서 안 한 것과 구분되지 않는다.
 */
export default async function ProfilePage() {
  const user = await getCurrentUser();

  // 로그인해야 볼 수 있다. 돌아올 곳을 넘겨 로그인 뒤 여기로 오게 한다.
  if (!user) redirect("/login?next=/profile");

  // 순위는 곁들이는 정보라 하나가 실패해도 나머지를 보여준다
  // (fetchMyStandings 가 안에서 처리한다).
  const token = await getToken();
  const standings = token ? await fetchMyStandings(token) : {};

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-8">
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
        내 프로필
      </h1>

      <section className="mt-6" aria-labelledby="profile-edit">
        <h2 id="profile-edit" className="sr-only">
          사진과 이름
        </h2>
        <ProfileForm
          action={updateProfileAction}
          initialName={user.display_name}
          initialAvatar={user.avatar}
          shown={user.avatar_display}
          googlePicture={user.google_picture}
        />
      </section>

      {/* dark: 쌍을 안 쓴다. 이 앱은 어두운 화면 하나로 가고(globals.css
          첫머리), 파일에 남은 라이트 전용 클래스는 걷어낼 잔재다. */}
      <section
        className="mt-10 border-t border-white/15 pt-6"
        aria-labelledby="records"
      >
        <h2 id="records" className="text-sm font-medium text-slate-300">
          학습 기록
        </h2>
        <div className="mt-3">
          <MyStandings standings={standings} />
        </div>
      </section>

      <section
        className="mt-10 border-t border-slate-200 pt-6 dark:border-white/15"
        aria-labelledby="account"
      >
        <h2
          id="account"
          className="text-sm font-medium text-slate-700 dark:text-slate-300"
        >
          계정
        </h2>

        <dl className="mt-3 grid gap-2 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-slate-500 dark:text-slate-400">이메일</dt>
            {/* 이메일은 로그인 키라 바꿀 수 없다. 바꾸려면 본인 확인이
                먼저인데 그 절차가 아직 없다. */}
            {/* min-w-0 이 없으면 truncate 가 아예 발동하지 않는다. flex 항목의
                min-width 는 auto = min-content 인데, truncate 가 건
                white-space: nowrap 때문에 min-content 가 이메일 전체 폭이
                되어 칸이 줄지 않고 행이 그대로 넘친다. */}
            <dd className="min-w-0 truncate font-mono text-slate-700 dark:text-slate-300">
              {user.email}
            </dd>
          </div>
        </dl>

        <form action={logoutAction} className="mt-4">
          <button
            type="submit"
            className="w-full rounded-md border border-slate-300 px-4 py-2.5 text-slate-700 transition-[scale,border-color] duration-[120ms] ease-press hover:border-slate-400 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus sm:w-auto sm:px-6 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-500"
          >
            로그아웃
          </button>
        </form>
      </section>
    </main>
  );
}
