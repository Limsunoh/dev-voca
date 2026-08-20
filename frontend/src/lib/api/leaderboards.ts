import type { AvatarDisplay } from "@/components/Avatar";

import { request } from "./client";

/**
 * 순위표 API 클라이언트. 공통 규칙은 client.ts 에 있다.
 *
 * 세 종류가 같은 응답 모양을 쓴다. 종류마다 타입을 따로 두면 화면이
 * 종류별로 갈라져, 탭을 하나 늘릴 때 컴포넌트까지 손대게 된다.
 */

const BASE = "/api/learning/leaderboards/";

/** 순위표 종류. URL 조각이자 탭 식별자다. */
export const BOARD_KINDS = ["weekly", "all_time", "streak"] as const;
export type BoardKind = (typeof BOARD_KINDS)[number];

/**
 * 종류별 화면 문구.
 *
 * 한 곳에 모아둔다 - 탭·제목·단위가 화면마다 흩어지면 "판" 과 "일" 이
 * 어긋나 꾸준함 순위표에 "5판" 이 뜬다.
 */
export const BOARD_LABELS: Record<
  BoardKind,
  { tab: string; title: string; note: string; unit: string; scoreUnit: string }
> = {
  weekly: {
    tab: "이번 주",
    title: "이번 주 최고점",
    note: "한 판에서 낸 가장 높은 점수. 월요일에 새로 시작합니다.",
    unit: "판",
    scoreUnit: "점",
  },
  all_time: {
    tab: "전체",
    title: "전체 최고점",
    note: "지금까지 한 판에서 낸 가장 높은 점수.",
    unit: "판",
    scoreUnit: "점",
  },
  streak: {
    tab: "꾸준함",
    title: "꾸준함",
    note: "점수를 얻은 날을 모두 더합니다. 하루라도 쉬면 그날은 빠집니다.",
    unit: "일",
    scoreUnit: "점",
  },
};

/**
 * 아바타. accounts 와 같은 모양이라 Avatar 컴포넌트가 그대로 받는다.
 *
 * 백엔드가 두 칸(avatar/google_picture)이 아니라 하나로 내려주는 이유는
 * leaderboards.Row 주석에 있다 - 화면이 "구글 사진 있으면 그것" 규칙을
 * 따로 들고 있지 않게 하려는 것이다.
 */
export type BoardAvatar = AvatarDisplay;

/** 순위표 한 줄. */
export type BoardRow = {
  rank: number;
  display_name: string;
  avatar: BoardAvatar;
  score: number;
  /** 몇 판 / 며칠. 종류에 따라 단위가 다르다(BOARD_LABELS.unit). */
  entries: number;
  /**
   * 이 줄이 나인가.
   *
   * 백엔드가 pk 대신 이 값을 준다. 화면이 알아야 할 것은 "이게 나인가"
   * 뿐인데 pk 는 순차라 가장 큰 값이 대략 가입자 수가 된다.
   */
  is_me: boolean;
};

export type Board = {
  kind: BoardKind;
  rows: BoardRow[];
  /** 내가 상위 목록 밖일 때만 온다. 안에 있으면 rows 에 is_me 로 있다. */
  me: BoardRow | null;
  /** 주간 순위표에만 온다. "8월 18일 ~ 8월 24일" 을 그리는 데 쓴다. */
  period?: { start: string; end: string };
};

export function isBoardKind(value: string | undefined): value is BoardKind {
  return BOARD_KINDS.includes(value as BoardKind);
}

/**
 * 순위표 하나를 가져온다.
 *
 * 로그인하지 않아도 볼 수 있다 - 순위표는 "나도 저기 오르고 싶다" 를
 * 만드는 화면이라 가입 전에 보여야 의미가 있다. 토큰이 없으면 me 가 null 로
 * 올 뿐 목록은 그대로 온다.
 */
export function fetchBoard(kind: BoardKind, token?: string): Promise<Board> {
  // all_time 만 URL 조각이 다르다. 백엔드가 하이픈을 쓰는데 값은
  // 밑줄이라, 여기서 한 번 바꾼다.
  const path = kind === "all_time" ? "all-time" : kind;
  return request<Board>(`${BASE}${path}/`, { token });
}

/**
 * 세 순위표를 한꺼번에. 마이페이지가 내 줄만 쓴다.
 *
 * **하나가 실패해도 나머지를 보여준다.** 순위는 곁들이는 정보라, 이것
 * 때문에 프로필 화면 전체가 안 뜨면 손해가 더 크다.
 */
export async function fetchMyStandings(
  token: string,
): Promise<Partial<Record<BoardKind, BoardRow>>> {
  const settled = await Promise.allSettled(
    BOARD_KINDS.map((kind) => fetchBoard(kind, token)),
  );

  const standings: Partial<Record<BoardKind, BoardRow>> = {};
  settled.forEach((result, index) => {
    if (result.status !== "fulfilled") {
      console.error("순위표를 불러오지 못했습니다.", result.reason);
      return;
    }
    const board = result.value;
    // 상위에 있으면 rows 안에, 밖이면 me 에 있다.
    const mine = board.me ?? board.rows.find((row) => row.is_me);
    if (mine) standings[BOARD_KINDS[index]] = mine;
  });

  return standings;
}
