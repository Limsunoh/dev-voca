import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { DailyLengthPicker } from "@/components/DailyLengthPicker";
import { getCurrentUser, getGuestDailyLength, isGuestChosen } from "@/lib/session";

import { saveDailyLengthAction } from "./actions";

export const metadata: Metadata = {
  title: "하루 공부량 · dev-voca",
  description: "일일공부를 몇 분씩 할지 고릅니다.",
};

/**
 * 하루 공부량을 처음 한 번 묻는 화면.
 *
 * 로그인했거나 게스트를 고른 뒤 홈으로 가기 전에 여기를 거친다. 홈이 아직 안
 * 고른 사람을 이리로 보낸다(app/page.tsx). 고르면 일일공부가 그 길이로 바로
 * 시작하고, 내정보에서 바꾼다.
 *
 * 건너뛰기를 두지 않는다. 고를 것이 셋뿐이라 한 번 누르면 끝이고, 건너뛰면
 * 일일공부를 열 때 결국 다시 골라야 한다.
 */
export default async function DailyLengthStartPage() {
  const user = await getCurrentUser();
  if (!user && !(await isGuestChosen())) redirect("/start");

  // 이미 골랐으면 다시 묻지 않는다. 주소로 직접 들어와도 같다. 계정에 이 칸이
  // 없는 것(옛 백엔드)도 고른 것으로 친다 - 홈이 묻지 않는 것과 같은 기준이다.
  const asked = user ? user.daily_length === "" : !(await getGuestDailyLength());
  if (!asked) redirect("/");

  return (
    // 이 화면에는 탭바가 없다(TabBar 의 숨김 목록). 고르기 전에는 갈 곳이 없다.
    // 가운데 정렬. 바로 앞 화면(/start)이 가운데 정렬이라 이어서 볼 때 맞춘다.
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-6 py-10 text-center">
      <h1
        className="rise text-[length:var(--text-2xl)] leading-tight"
        style={{
          color: "var(--foreground)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
        }}
      >
        하루에 얼마나 공부할까요
      </h1>
      <p
        className="rise mt-3 leading-relaxed [animation-delay:80ms]"
        style={{ color: "var(--text-muted)" }}
      >
        일일공부가 이 길이로 바로 시작합니다.
        <br />
        내정보에서 언제든 바꿀 수 있습니다.
      </p>
      {/* 게스트는 일일공부를 쓰려면 로그인해야 한다. 지금 고른 값이 그때
          버려지지 않는다는 것을 알려야 고를 이유가 생긴다. */}
      {!user && (
        <p
          className="rise mt-2 text-sm leading-relaxed [animation-delay:120ms]"
          style={{ color: "var(--text-muted)" }}
        >
          로그인하면 고른 공부량이 계정으로 옮겨집니다. 계정에 이미 정해 둔
          공부량이 있으면 그것을 씁니다.
        </p>
      )}

      <div className="rise mt-8 [animation-delay:160ms]">
        <DailyLengthPicker action={saveDailyLengthAction} current={null} from="start" />
      </div>
    </main>
  );
}
