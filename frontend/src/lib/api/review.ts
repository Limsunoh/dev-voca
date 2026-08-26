import { request } from "./client";
import type { RoundQuestion } from "./rounds";

/**
 * 복습. 공통 규칙은 client.ts 에 있다.
 *
 *   GET  /review/         남은 개수. 시작 버튼을 그릴지 정한다
 *   POST /review/         판을 연다
 *   POST /review/answer/  답 하나. 다음 문제가 같이 온다
 *
 * **점수가 없는 판이다.** 순위표에 안 들어가고 제한 시간도 없다. 정답을
 * 이미 본 문제가 나오는 자리라 점수를 주면 아는 것만 골라 푸는 길이
 * 열린다. 대신 하루 횟수 제한이 없다 - 이득이 없으니 막을 이유도 없다.
 *
 * **로그인이 필요하다.** 무엇을 틀렸는지가 계정에 쌓여야 하는 기능이다.
 *
 * 이어 풀기가 없다. 판을 DB 에 안 남기기 때문인데, 남길 것이 연속 횟수
 * 뿐이고 그건 답할 때마다 이미 반영된다 - 중간에 나가도 그때까지 맞힌
 * 것은 남아 있고, 다시 시작하면 남은 것부터 나온다.
 *
 * **이 모듈은 서버에서만 부른다.** 백엔드 주소는 서버 전용 환경변수다.
 * 화면은 같은 출처 중계(/api/review)를 부르고 그 중계가 이 함수들을 쓴다.
 */

const BASE = "/api/learning/review/";

export type ReviewDue = {
  /** 지금 복습할 것이 몇 개인가. */
  due: number;
  /** 한 판의 최대 문제 수. due 가 이보다 크면 이만큼만 낸다. */
  round_size: number;
  /**
   * 연속 몇 번 맞혀야 목록에서 빠지나.
   *
   * 화면이 "한 번 더 맞히면 끝" 을 그리는 근거다. 이 값을 화면에
   * 박아두면 기준이 바뀐 날 화면만 옛말을 계속한다.
   */
  graduate_streak: number;
};

/** 복습 문제 하나. 자유 문제풀이의 문제에 진행이 실려 온다. */
export type ReviewQuestion = RoundQuestion & {
  /**
   * 지금 내는 문제의 자리. 0 부터 센다.
   *
   * **이름과 달리 "답한 개수" 가 아니다.** 첫 문제에서 0, 마지막 문제
   * 에서 total-1 이다. 그래서 화면 진행률이 0 / 20 으로 시작한다.
   *
   * **화면이 직접 세면 안 된다.** 대상이 검수에서 내려가거나 지워지면
   * 서버가 건너뛰므로(review._question_at) 답한 횟수로 세면 그만큼
   * 어긋나, 20개짜리 판이 17/20 에서 끝난다.
   *
   * 여기에 1 을 더해 "답한 개수" 로 바꾸지 마라 - 끝난 뒤 화면이
   * 분모로 쓰는 값이 어긋난다. 마지막 답에는 이 필드가 아예 안 오고
   * (다음 문제가 없다) 그때만 화면이 하나를 올린다.
   */
  answered: number;
  /** 이 판의 문제 수. */
  total: number;
};

export type ReviewStarted = {
  token: string;
  // 판의 크기와 진행은 question 안에 있다. 백엔드가 total 을 따로도
  // 보내지만 받지 않는다 - 두 자리에 두면 짧은 쪽을 집게 되고, 그러면
  // 진행 순번과 출처가 갈려 건너뛴 만큼 어긋난다.
  question: ReviewQuestion;
};

/** 복습 답 하나의 채점 결과. */
export type ReviewResult = {
  correct: boolean;
  /**
   * 이 항목을 복습에서 연속 몇 번 맞혔나.
   *
   * ReviewDue.graduate_streak 만큼 채우면 목록에서 빠진다. 남은 횟수를
   * 세는 데 쓴다.
   */
  streak: number;
  /** 이번 답으로 목록에서 빠졌나. */
  graduated: boolean;
  answer_type: string;
  answer_text: string;
  answer_extra: string;
};

export type ReviewAnswered = {
  result: ReviewResult;
  /** 다음 문제의 토큰. 마지막이었으면 null. */
  token: string | null;
  question: ReviewQuestion | null;
  finished: boolean;
};

export function fetchDue(token: string): Promise<ReviewDue> {
  return request<ReviewDue>(BASE, { token });
}

export function startReview(token: string): Promise<ReviewStarted> {
  return request<ReviewStarted>(BASE, { method: "POST", token, body: {} });
}

export function answerReview(
  token: string,
  roundToken: string,
  choiceId: number,
): Promise<ReviewAnswered> {
  return request<ReviewAnswered>(`${BASE}answer/`, {
    method: "POST",
    token,
    body: { token: roundToken, choice_id: choiceId },
  });
}
