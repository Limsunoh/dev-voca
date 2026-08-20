import type { Metadata } from "next";

import { RoundBoard } from "@/components/RoundBoard";
import { getToken } from "@/lib/session";

export const metadata: Metadata = {
  title: "한 판 · devvoca",
  description: "90초 안에 몇 문제나 맞히는지. 점수가 순위표에 오릅니다.",
};

/**
 * 90초 한 판.
 *
 * 분류 필터가 없다. 판은 점수가 남는 승부라 낼 문제를 고를 수 있으면
 * 쉬운 분류만 골라 점수를 올릴 수 있다. 분류를 골라 연습하려면 옆의
 * 낱개 모드(/test/words)를 쓴다 - 그쪽은 점수가 안 남는다.
 */
export default async function RoundPage() {
  // 로그인 안 해도 풀 수 있다. 기록만 안 된다.
  const token = await getToken();

  return (
    // 세로 가운데. 시작 카드 하나뿐이라 위에 붙이면 데스크톱에서
    // 아래가 통째로 빈다. 판이 시작되면 내용이 길어져 자연히 위로 붙는다.
    // 세로 정렬은 RoundBoard 가 정한다. 시작 카드는 하나뿐이라 가운데가
    // 맞지만, 판이 도는 중에는 타이머와 점수가 화면 맨 위에 붙어야 한다 -
    // 게임의 상태 표시는 가장자리에 고정되는 것이 관례다. 가운데 두면
    // 위쪽에 죽은 여백이 생기고 "게임 화면" 이 아니라 "가운데 정렬된
    // 웹 카드" 로 보인다(실측: 폰에서 타이머가 top 119px 에 떴다).
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-4 py-8">
      {/* 머리말은 RoundBoard 가 그린다. 판이 도는 중에는 나가기 버튼만
          남아야 하고, 그건 지금 어느 단계인지 아는 쪽만 판단할 수 있다.
          여기서 그리면 푸는 중에도 "연습 모드" 링크가 남아 탭바를 없앤
          의미가 사라진다. */}
      <RoundBoard isGuest={!token} />
    </main>
  );
}
