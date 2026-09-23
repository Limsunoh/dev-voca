import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { BoardScreen } from "@/app/board/BoardScreen";
import { BOARD_LABELS, isBoardKind } from "@/lib/api/leaderboards";
import { routes } from "@/lib/routes";

// Next 16 에서 params 는 Promise 다. 동기 접근은 런타임 에러.
type PageProps = { params: Promise<{ kind: string }> };

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { kind } = await params;
  if (!isBoardKind(kind)) return { title: "순위표 · devvoca" };

  return {
    title: `${BOARD_LABELS[kind].title} · devvoca`,
    description: BOARD_LABELS[kind].note,
  };
}

export default async function BoardKindPage({ params }: PageProps) {
  const { kind } = await params;

  if (!isBoardKind(kind)) notFound();

  // weekly 는 /board 가 맡는다. 여기서 같은 화면을 그리면 한 화면이 주소
  // 두 개를 갖고, 탭의 aria-current 와 주소가 어긋난다.
  //
  // 막지 않고 보낸다. 전에는 notFound() 였는데, 위 generateMetadata 는
  // weekly 를 정상으로 받아 탭 제목이 "이번 주 최고점" 인 채 본문만 "없는
  // 순위표" 가 됐다. 주소를 손으로 친 사람이 찾던 것은 이번 주 순위다.
  if (kind === "weekly") redirect(routes.board());

  return <BoardScreen kind={kind} />;
}
