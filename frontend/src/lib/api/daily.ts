import { request } from "./client";
import type { RoundChoice, RoundQuestion, RoundResult } from "./rounds";

/**
 * 일일공부. 공통 규칙은 client.ts 에 있다.
 *
 *   GET  /daily/          오늘 상태. 길이 선택지와 오늘 판(있으면)
 *   POST /daily/          판을 연다. {"length": "5m"|"10m"|"30m"}
 *   POST /daily/answer/   답 하나. 다음 문제가 같이 온다
 *
 * **로그인이 필요하다.** 진행이 서버에 남아야 이어서 풀 수 있는 기능이라
 * 계정이 없으면 이어 볼 자리가 없다. 자유 문제풀이가 게스트를 받는 것과
 * 다르다.
 *
 * 끝내기 요청이 없다. 마지막 문제를 풀면 서버가 판을 닫는다 - 끝내기를
 * 화면에 맡기면 중간에 나간 사람이 푼 만큼을 잃는다.
 *
 * **이 모듈은 서버에서만 부른다.** 백엔드 주소는 서버 전용 환경변수다.
 * 화면은 같은 출처 중계(/api/daily)를 부르고 그 중계가 이 함수들을 쓴다.
 */

const BASE = "/api/learning/daily/";

/** 고를 수 있는 길이 하나. */
export type StudyLength = {
  /** "5m" | "10m" | "30m". 시작할 때 그대로 보낸다. */
  value: string;
  label: string;
  questions: number;
  /** 다 풀면 붙는 점수. 길수록 크다. */
  bonus: number;
};

/** 오늘 판의 진행 상태. */
export type StudyProgress = {
  length: string;
  total: number;
  answered: number;
  correct: number;
  score: number;
  bonus: number;
  done: boolean;
};

export type DailyStatus = {
  lengths: StudyLength[];
  /** 오늘 시작한 판. 아직 안 골랐으면 null. */
  today: StudyProgress | null;
  /**
   * 하다 만 판을 이어 풀 토큰과 문제. 없으면 null.
   *
   * 시작은 하루 한 번 제약에 막히므로, 중간에 나간 사람에게는 이것이
   * 오늘 판을 끝낼 유일한 길이다.
   */
  token: string | null;
  question: RoundQuestion | null;
};

export type DailyStarted = {
  token: string;
  question: RoundQuestion;
  study: StudyProgress;
};

export type DailyAnswered = {
  /** 일일공부는 감점이 없어 skipped·in_time 을 안 쓴다. */
  result: RoundResult;
  token: string | null;
  question: RoundQuestion | null;
  finished: boolean;
  study: StudyProgress;
};

export type { RoundChoice, RoundQuestion };

export function fetchDailyStatus(token: string): Promise<DailyStatus> {
  return request<DailyStatus>(BASE, { token });
}

export function startDaily(
  length: string,
  token: string,
): Promise<DailyStarted> {
  return request<DailyStarted>(BASE, {
    method: "POST",
    body: { length },
    token,
  });
}

export function answerDaily(
  studyToken: string,
  choiceId: number,
  token: string,
): Promise<DailyAnswered> {
  return request<DailyAnswered>(`${BASE}answer/`, {
    method: "POST",
    body: { token: studyToken, choice_id: choiceId },
    token,
  });
}
