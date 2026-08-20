import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { BoardScreen } from "@/app/board/BoardScreen";
import { BOARD_LABELS, isBoardKind } from "@/lib/api/leaderboards";

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

  // weekly 는 /board 가 맡는다. 여기로도 오게 두면 같은 화면이 주소 두
  // 개를 갖고, 탭의 aria-current 와 주소가 어긋난다.
  if (!isBoardKind(kind) || kind === "weekly") notFound();

  return <BoardScreen kind={kind} />;
}
