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
  /** 이 판에서 학습하는 단어 수. 나머지 문제는 전체에서 나온다. */
  words: number;
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
  /** 한 묶음에서 학습하는 단어 수. 0 이면 학습 없이 문제만 푸는 판이다. */
  chunk_size: number;
  /** 학습 묶음 개수. 이 뒤의 문제는 전체에서 나온다. */
  chunk_count: number;
  /** 지금 몇 번째 묶음인가(0부터). 화면이 "2/4" 를 그린다. */
  chunk_index: number;
};

/**
 * 학습 카드 한 장.
 *
 * 단어 상세(WordDetail)와 따로 두는 이유: 저기는 목록·상세 화면이 쓰는
 * 타입이라 created_at 같은 칸이 붙어 있고, 이쪽은 백엔드가 카드용으로
 * 추린 것이다. 한 타입으로 합치면 어느 화면이 무엇을 쓰는지 흐려진다.
 */
export type StudyCard = {
  id: number;
  term: string;
  pronunciation: string;
  /** 한글 발음. 검수 전이면 빈 문자열. */
  reading: string;
  meaning: string;
  description: string;
  example: string;
  example_translation: string;
  category_label: string;
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
  /**
   * 이번 묶음에서 학습할 단어들. 학습할 차례가 아니면 빈 배열.
   *
   * **문제와 함께 온다.** 카드를 다 넘기면 그 자리에서 문제로 넘어가므로
   * 서버에 "봤다" 를 알릴 필요가 없다 - 그건 점수와 무관한 요청이라
   * 되돌리기를 막을 이유가 없고, 막지 않으면 왕복만 늘어난다.
   */
  learning: StudyCard[];
};

export type DailyStarted = {
  token: string;
  question: RoundQuestion;
  study: StudyProgress;
  learning: StudyCard[];
};

export type DailyAnswered = {
  /** 일일공부는 감점이 없어 skipped·in_time 을 안 쓴다. */
  result: RoundResult;
  token: string | null;
  question: RoundQuestion | null;
  finished: boolean;
  study: StudyProgress;
  /** 묶음이 넘어가는 답에만 채워진다. 묶음 안에서는 빈 배열. */
  learning: StudyCard[];
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
