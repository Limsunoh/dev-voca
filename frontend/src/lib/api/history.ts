import { buildQuery, request, type Paginated } from "./client";

/**
 * 오답 노트와 학습 기록. 공통 규칙은 client.ts 에 있다.
 *
 *   GET /learning/mistakes/   마지막에 틀린 것 목록
 *   GET /learning/history/    최근 14일 하루 점수와 최근 판
 *
 * **복습과 목록이 다르다.** 복습(`/test/review`)은 "지금 볼 것" 이라 틀린
 * 것에 더해 오래된 것(마지막 정답에서 7일)까지 낸다. 오답 노트는 이름
 * 그대로 **틀린 것만**이다. 그래서 두 화면의 개수가 다르고, 화면이 그
 * 사실을 한 줄로 알린다 - 안 알리면 사용자가 버그로 읽는다.
 *
 * **로그인이 필요하다.** 무엇을 틀렸는지는 계정에 쌓이는 것이다.
 *
 * **이 모듈은 서버에서만 부른다.** 백엔드 주소는 서버 전용 환경변수다.
 */

const BASE = "/api/learning/mistakes/";

/** 오답 노트 한 줄. */
export type Mistake = {
  id: number;
  /** 단어인가 문장인가. 누를 때 어느 상세로 보낼지 가른다. */
  target_type: "word" | "sentence";
  /** 그 단어·문장의 id. 상세 주소를 만드는 데 쓴다. */
  target_id: number;
  /** 영어 본문. 단어면 단어, 문장이면 문장이다. */
  text: string;
  /** 한글 뜻 또는 해석. */
  meaning: string;
  // 틀린 날짜는 없다. 담을 칸이 없어서 서버가 안 보낸다 - 이유는
  // views_history 주석에 있다.
};

/**
 * 틀린 것 목록.
 *
 * 페이지 번호는 기존 목록과 같은 방식이다. 화면도 같은 Pagination 을 쓴다.
 */
export function getMistakes(
  token: string,
  page?: string,
): Promise<Paginated<Mistake>> {
  return request(`${BASE}${buildQuery({ page })}`, { token });
}

/** 하루 한 칸. 서버가 한국 날짜로 잘라 보낸다. */
export type HistoryDay = {
  /** "2026-09-23". 시각이 아니라 날짜다 - 화면에서 다시 자르지 않는다. */
  day: string;
  /** 그날 점수. 꾸준함 순위표와 같은 값이라 0 밑으로 안 간다. */
  total: number;
  /**
   * 그날 기록이 있나. total 이 0 인 날을 "0점" 과 "안 함" 으로 가르는 데
   * 쓴다. best_round·daily_study 로 짐작하지 않는다 - 일일공부를 다 틀린
   * 날은 두 칸이 안 한 날과 똑같다.
   */
  recorded: boolean;
  /** 그날 가장 잘한 판. 판을 안 했으면 null(0 은 "0점 판" 이다). */
  best_round: number | null;
  /** 그날 일일공부 점수. */
  daily_study: number;
};

/** 끝낸 판 하나. 자유 문제풀이만 온다. */
export type HistoryRound = {
  day: string;
  score: number;
  answered: number;
  correct: number;
};

export type History = {
  /** 늘 14칸. 오래된 날부터, 마지막이 오늘. */
  days: HistoryDay[];
  /** 최근 것부터 최대 10개. */
  rounds: HistoryRound[];
};

/**
 * 내 학습 기록(GET /learning/history/).
 *
 * 실패해도 던지지 않고 null 을 낸다. 내정보에서 곁들이는 정보라, 이것
 * 하나 못 불러왔다고 화면 전체가 오류가 되면 과하다(순위를 부르는
 * fetchMyStandings 와 같은 태도).
 */
export async function fetchMyHistory(token: string): Promise<History | null> {
  try {
    return await request<History>("/api/learning/history/", { token });
  } catch (error) {
    console.error("학습 기록을 불러오지 못했습니다.", error);
    return null;
  }
}
