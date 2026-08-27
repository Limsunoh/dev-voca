import { buildQuery, request } from "./client";

/** 문제풀기 API 클라이언트. 공통 규칙은 client.ts 에 있다. */

const BASE = "/api/vocab/words/";

/** 보기 하나. */
export type QuizChoice = {
  id: number;
  text: string;
};

/**
 * 문제 하나. 백엔드 quiz 액션과 짝.
 *
 * 정답 id 가 없다는 점이 중요하다. 응답에 담으면 개발자도구로 미리 보인다.
 * 대신 서명된 token 을 받아 채점할 때 그대로 돌려준다.
 */
export type Question = {
  /** meaning / term / description */
  kind: string;
  kind_label: string;
  /** "이 단어의 뜻은?" 같은 물음. */
  question: string;
  /** 문제로 보여줄 것. 단어이거나 뜻이거나 설명이다. */
  prompt: string;
  category: string;
  category_label: string;
  choices: QuizChoice[];
  /** 정답을 서명한 값. 읽을 수 없고 채점할 때 그대로 보낸다. */
  token: string;
};

export type QuizParams = {
  category?: string;
  kind?: string;
  /** 방금 낸 문제를 다시 내지 않으려고 보낸다. "1,2,3" 형태. */
  exclude?: string;
};

/**
 * 문제 하나를 받는다.
 *
 * cache() 로 감싸지 않는다. 같은 조건이라도 매번 다른 문제가 나와야 한다.
 */
export function getQuestion(params: QuizParams = {}): Promise<Question> {
  return request(`${BASE}quiz/${buildQuery(params)}`);
}

/**
 * 채점 결과. 맞든 틀리든 정답 단어와 해설을 함께 받는다.
 *
 * 단어 상세보다 좁다. 채점은 로그인 없이 되는 경로라 백엔드가
 * 검수 상태나 출처 같은 내부 정보를 빼고 보낸다.
 */
export type GradeResult = {
  correct: boolean;
  answer_id: number;
  word: {
    id: number;
    term: string;
    pronunciation: string;
    /** 한글 발음. 검수 안 됐으면 빈 문자열이다(백엔드가 거른다). */
    reading: string;
    meaning: string;
    description: string;
    example: string;
    example_translation: string;
    category: string;
  };
};

/**
 * 고른 보기를 채점한다.
 *
 * POST 인 이유: 토큰을 URL 에 실으면 브라우저 기록과 서버 로그에 남는다.
 * 데이터를 바꾸지는 않지만 "제출" 이라는 의미상으로도 POST 가 맞다.
 */
export async function gradeAnswer(
  token: string,
  pickedId: number,
): Promise<GradeResult> {
  return request(`${BASE}grade/`, {
    method: "POST",
    body: { token, picked: pickedId },
  });
}
