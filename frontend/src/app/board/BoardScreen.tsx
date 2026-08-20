import { Leaderboard } from "@/components/Leaderboard";
import type { BoardKind } from "@/lib/api/leaderboards";
import { fetchBoard } from "@/lib/api/leaderboards";
import { ApiError } from "@/lib/api/client";
import { getToken } from "@/lib/session";

/**
 * 순위표 화면 본체.
 *
 * /board 와 /board/[kind] 가 같은 화면이라 여기로 모은다. 두 파일에
 * 나눠 쓰면 안내 문구나 오류 처리가 한쪽만 바뀐다.
 */
export async function BoardScreen({ kind }: { kind: BoardKind }) {
  // 로그인 안 해도 볼 수 있다. 토큰이 없으면 내 줄만 안 온다.
  const token = await getToken();

  let board;
  try {
    board = await fetchBoard(kind, token ?? undefined);
  } catch (error) {
    // 순위표가 안 뜨는 것과 백엔드가 죽은 것을 사용자가 구분할 수는
    // 없지만, 다시 시도해볼 수 있는지는 알려준다.
    const offline = error instanceof ApiError && error.status === 0;
    return (
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-8">
        <div className="rise rounded-xl border border-white/10 bg-slate-950/40 px-5 py-10 text-center">
          <p className="text-slate-200">순위표를 불러오지 못했습니다.</p>
          <p className="mt-1 text-sm text-slate-500">
            {offline
              ? "서버에 연결할 수 없습니다. 잠시 뒤 다시 시도해주세요."
              : "잠시 뒤 다시 시도해주세요."}
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-8">
      <Leaderboard board={board} isGuest={!token} />
    </main>
  );
}
