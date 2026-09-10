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
        {/* 흰 종이 + 두께. 테두리를 쓰지 않는다 - 이 디자인은 경계를
            아래 두께가 맡는다(가이드 shape-lift). */}
        <div
          className="rise px-5 py-10 text-center dv-card"
          style={
            {
              background: "var(--paper)",
              borderRadius: "var(--radius-2xl)",
              "--lift": "var(--lift-card)",
            } as React.CSSProperties
          }
        >
          <p
            style={{
              color: "var(--foreground)",
              fontWeight: "var(--weight-bold)",
            }}
          >
            순위표를 불러오지 못했습니다.
          </p>
          <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
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
