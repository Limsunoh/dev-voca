import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { logoutAction } from "@/app/(auth)/actions";
import {
  changePasswordAction,
  deletePhotoAction,
  requestEmailChangeAction,
  updateProfileAction,
  uploadPhotoAction,
} from "@/app/profile/actions";
import { EmailCard } from "@/components/EmailCard";
import { PasswordCard } from "@/components/PasswordCard";
import { MyStandings } from "@/components/MyStandings";
import { ProfileForm } from "@/components/ProfileForm";
import { fetchMyStandings } from "@/lib/api/leaderboards";
import { getCurrentUser, getToken } from "@/lib/session";

export const metadata: Metadata = {
  title: "내정보 · devvoca",
};

/**
 * 내정보.
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
      <h1
        className="text-[length:var(--text-2xl)] tracking-[var(--tracking-tight)]"
        style={{
          color: "var(--foreground)",
          fontWeight: "var(--weight-black)",
        }}
      >
        내정보
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
          uploadPhoto={uploadPhotoAction}
          deletePhoto={deletePhotoAction}
          uploadedPhoto={user.uploaded_photo}
        />
      </section>

      {/* 구획선(border-t)을 쓰지 않는다. 이 디자인은 영역을 선이 아니라
          카드의 두께로 가른다 - 크림 바탕에 가로선을 그으면 그것만 다른
          시대의 화면처럼 보인다. 절 제목은 카드 위에 작은 라벨로 둔다. */}
      <section className="mt-8" aria-labelledby="records">
        <h2
          id="records"
          className="text-xs tracking-[var(--tracking-wide)]"
          style={{
            color: "var(--text-dim)",
            fontWeight: "var(--weight-black)",
          }}
        >
          학습 기록
        </h2>
        <div className="mt-3">
          <MyStandings standings={standings} />
        </div>
      </section>

      <section className="mt-8" aria-labelledby="account">
        <h2
          id="account"
          className="text-xs tracking-[var(--tracking-wide)]"
          style={{
            color: "var(--text-dim)",
            fontWeight: "var(--weight-black)",
          }}
        >
          계정
        </h2>

        <dl
          className="mt-3 grid gap-2 p-5 text-sm"
          style={{
            background: "var(--paper)",
            borderRadius: "var(--radius-2xl)",
            boxShadow: "var(--lift-card)",
          }}
        >
          <div className="flex justify-between gap-4">
            <dt style={{ color: "var(--text-muted)" }}>이메일</dt>
            {/* min-w-0 이 없으면 truncate 가 아예 발동하지 않는다. flex 항목의
                min-width 는 auto = min-content 인데, truncate 가 건
                white-space: nowrap 때문에 min-content 가 이메일 전체 폭이
                되어 칸이 줄지 않고 행이 그대로 넘친다. */}
            <dd
              className="min-w-0 truncate font-mono"
              style={{ color: "var(--text-body)" }}
            >
              {user.email}
            </dd>
          </div>
        </dl>

        {/* 이메일 변경은 표 아래 접어둔다. 표는 "지금 무엇인가" 를 보는
            자리라, 바꾸는 칸을 그 안에 섞으면 읽는 것과 고치는 것이
            한 덩어리가 된다. */}
        <div className="mt-3 grid gap-3">
          <EmailCard
            action={requestEmailChangeAction}
            currentEmail={user.email}
            hasPassword={user.has_password}
          />
          <PasswordCard
            action={changePasswordAction}
            hasPassword={user.has_password}
            email={user.email}
          />
        </div>

        {/* 로그아웃은 흰 버튼이다. 코랄은 이 화면에서 저장 버튼이 가진다 -
            둘 다 코랄이면 되돌릴 수 없는 쪽(로그아웃)이 주된 동작으로 보인다. */}
        <form action={logoutAction} className="mt-4">
          <button
            type="submit"
            className="dv-btn w-full rounded-[var(--radius-pill)] px-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus sm:w-auto sm:px-8"
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
            로그아웃
          </button>
        </form>
      </section>
    </main>
  );
}
