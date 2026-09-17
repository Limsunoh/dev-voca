import { request } from "./client";

/**
 * 문제풀이 한 판. 공통 규칙은 client.ts 에 있다.
 *
 * 한 판은 세 번의 요청이다.
 *
 *   POST /rounds/         판을 연다. 첫 문제가 같이 온다
 *   POST /rounds/answer/  답하거나 넘긴다. 다음 문제가 같이 온다
 *   POST /rounds/finish/  판을 닫는다. 로그인했으면 기록된다
 *
 * **판 상태는 token 에 담겨 오간다.** 서버가 판을 저장하지 않으므로,
 * 화면은 매 응답의 새 token 을 들고 다음 요청에 그대로 실어야 한다.
 * 옛 token 을 보내면 되돌리기로 거절된다(서버가 순번을 태운다).
 *
 * **이 모듈은 서버에서만 부른다.** 백엔드 주소(API_URL)는 서버 전용
 * 환경변수다. 문제풀이 화면은 클라이언트 컴포넌트라 브라우저에서 같은
 * 출처의 중계(/api/rounds)를 부르고, 그 중계가 이 함수들을 쓴다.
 */

/** 보기 하나. */
export type RoundChoice = { id: number; text: string };

/**
 * 문제 하나.
 *
 * 정답 id 가 없다. 응답에 담으면 개발자도구로 미리 보인다 - 정답은
 * 서명된 token 안에 있고 읽을 수 없다.
 */
export type RoundQuestion = {
  kind: string;
  kind_label: string;
  question: string;
  prompt: string;
  choices: RoundChoice[];
  category: string;
  category_label: string;
  /**
   * 이 문제의 제한 시간(ms). 이 안에 맞히면 +1, 지나서 맞히면 0 이다.
   *
   * 읽을 것의 길이로 정해진다 - 지문이 단어 하나면 3초, 문장이면 7초
   * (backend quiz.TIME_LIMITS_MS). 유형 이름만 보고는 알 수 없다.
   *
   * **없을 수도 있다.** 한 판만 이 값을 쓰고 일일학습·복습은 시간을 안
   * 재는데, 세 화면이 이 타입을 같이 쓴다.
   */
  time_limit_ms?: number;
};

/** 답 하나의 채점 결과. */
export type RoundResult = {
  correct: boolean;
  skipped: boolean;
  /** 제한 시간 안에 답했나. 서버가 잰다 - 클라이언트 시계는 못 믿는다. */
  in_time: boolean;
  score: number;
  elapsed_ms: number;
  answer_type: string;
  answer_text: string;
  answer_extra: string;
};

export type RoundStarted = {
  token: string;
  question: RoundQuestion;
  round_seconds: number;
  max_skips: number;
  /**
   * 채점 연출 한 번에 화면이 멈추는 시간(ms).
   *
   * 서버가 답 하나마다 이만큼 마감을 미룬다. 화면도 같은 값으로 멈춰야
   * 한다 - 여기에 숫자를 따로 적어두면 한쪽만 바뀌었을 때 차이가 문제마다
   * 쌓인다.
   */
  reaction_pause_ms: number;
};

export type RoundAnswered = {
  token: string;
  result: RoundResult;
  question: RoundQuestion | null;
  finished: boolean;
};

export type RoundSummary = {
  score: number;
  answered: number;
  correct: number;
  skipped: number;
  /** 기록됐나. 로그인 안 했으면 false. */
  recorded: boolean;
  guest: boolean;
};

const BASE = "/api/learning/rounds/";

/**
 * 판을 연다.
 *
 * token 을 넘기면 그 계정의 판이 된다. 로그인 안 해도 풀 수 있으므로
 * 없어도 된다 - 그때는 끝내도 기록되지 않는다.
 */
export function startRound(token?: string): Promise<RoundStarted> {
  return request<RoundStarted>(BASE, { method: "POST", token });
}

export function answerRound(
  roundToken: string,
  choiceId: number | null,
  skip = false,
  token?: string,
): Promise<RoundAnswered> {
  return request<RoundAnswered>(`${BASE}answer/`, {
    method: "POST",
    body: skip
      ? { token: roundToken, skip: true }
      : { token: roundToken, choice_id: choiceId },
    token,
  });
}

export function finishRound(
  roundToken: string,
  token?: string,
): Promise<RoundSummary> {
  return request<RoundSummary>(`${BASE}finish/`, {
    method: "POST",
    body: { token: roundToken },
    token,
  });
}
