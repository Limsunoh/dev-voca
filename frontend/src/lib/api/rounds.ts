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
