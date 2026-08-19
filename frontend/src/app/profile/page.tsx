import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { logoutAction } from "@/app/(auth)/actions";
import { updateProfileAction } from "@/app/profile/actions";
import { ProfileForm } from "@/components/ProfileForm";
import { getCurrentUser } from "@/lib/session";

export const metadata: Metadata = {
  title: "내 프로필 · devvoca",
};

/**
 * 내 프로필.
 *
 * 사진과 이름을 바꾸고, 계정 정보를 보고, 로그아웃한다. 학습 기록(최고점,
 * 푼 문제 수, 출석)은 아직 저장하는 곳이 없어서 자리만 잡아뒀다. 없는
 * 숫자를 0 으로 채워두지 않는 이유: 0 은 "아직 안 함" 으로 읽혀서, 기능이
 * 없는 것인지 내가 안 한 것인지 구분되지 않는다.
 */
export default async function ProfilePage() {
  const user = await getCurrentUser();

  // 로그인해야 볼 수 있다. 돌아올 곳을 넘겨 로그인 뒤 여기로 오게 한다.
  if (!user) redirect("/login?next=/profile");

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

      <Records />

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

/**
 * 학습 기록.
 *
 * 지금은 안내만 있다. 3단계에서 값을 받아 이 자리에 꽂는다 - 그때 화면을
 * 다시 짜지 않도록 칸을 미리 잡아둔다.
 */
function Records() {
  const slots = [
    { label: "최고 점수", hint: "문제풀기 한 판의 최고점" },
    { label: "푼 문제", hint: "지금까지 푼 문제 수" },
    { label: "출석", hint: "학습한 날의 수" },
    { label: "연속", hint: "하루도 빠지지 않은 날" },
  ];

  return (
    <section
      className="mt-10 border-t border-slate-200 pt-6 dark:border-white/15"
      aria-labelledby="records"
    >
      <h2
        id="records"
        className="text-sm font-medium text-slate-700 dark:text-slate-300"
      >
        학습 기록
      </h2>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        문제풀기 기록을 저장하기 시작하면 여기에 쌓입니다.
      </p>

      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {slots.map((slot) => (
          <div
            key={slot.label}
            // 이 칸은 배경 채움이 없어서 테두리 하나로만 구분된다.
            // slate-800 은 따뜻한 배경 위에서 1:1 에 가까워 칸이 사라지고,
            // 그러면 위 주석대로 살려둔 "-" 가 아무 구획 없이 떠 있게 된다.
            className="rounded-lg border border-slate-200 p-3 dark:border-white/25"
          >
            <dt className="text-xs text-slate-500 dark:text-slate-400">
              {slot.label}
            </dt>
            {/* 0 이 아니라 - 로 둔다. 0 은 "내가 안 한 것" 으로 읽힌다. */}
            <dd
              // slate-700 은 어두운 배경에서 대비가 1.84:1 이라 - 가 아예 안
              // 보인다. 그러면 0 도 - 도 아닌 빈 칸이 되어 위 주석의 의도가
              // 무산된다.
              className="mt-1 text-xl font-semibold text-slate-300 dark:text-slate-400"
              title={slot.hint}
            >
              -
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
