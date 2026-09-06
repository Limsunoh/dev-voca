import { buildQuery, request } from "./client";

/** 문제풀기 API 클라이언트. 공통 규칙은 client.ts 에 있다. */

/**
 * 어느 콘텐츠로 문제를 내는가.
 *
 * 백엔드가 콘텐츠마다 quiz/grade 를 따로 갖고 있다. 경로만 다르고
 * 주고받는 모양은 같아서 이 한 값으로 가른다 - 에러 메시지·아티클이
 * 붙어도 여기에 한 줄만 늘어난다.
 */
export type QuizContent = "words" | "sentences";

const BASE: Record<QuizContent, string> = {
  words: "/api/vocab/words/",
  sentences: "/api/vocab/sentences/",
};

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
  /** 단어: meaning / term / description. 문장: blank / situation */
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
  /**
   * 정답이 무엇의 id 인가. 문장 문제에만 온다.
   *
   * 빈칸 채우기는 문장을 보여주지만 답은 단어다. 그래서 지문의 종류와
   * 정답의 종류가 다르고, 방금 낸 것을 다시 안 내려면 문장 id 를 따로
   * 봐야 한다(source_sentence_id).
   */
  answer_type?: "word" | "sentence";
  /** 빈칸 문제를 낸 문장. 다음 문제의 exclude 에 쓴다. */
  source_sentence_id?: number | null;
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
export function getQuestion(
  params: QuizParams = {},
  content: QuizContent = "words",
): Promise<Question> {
  return request(`${BASE[content]}quiz/${buildQuery(params)}`);
}

/**
 * 채점 결과. 맞든 틀리든 정답 단어와 해설을 함께 받는다.
 *
 * 단어 상세보다 좁다. 채점은 로그인 없이 되는 경로라 백엔드가
 * 검수 상태나 출처 같은 내부 정보를 빼고 보낸다.
 */
/** 채점 뒤 보여줄 정답 문장. 상황 고르기가 이걸 받는다. */
export type GradedSentence = {
  id: number;
  text: string;
  reading: string;
  translation: string;
  /** 이 말이 나오는 상황. 상황 고르기의 정답 보기가 이 값이다. */
  context: string;
  description: string;
  kind: string;
  kind_label: string;
  category: string;
};

export type GradeResult = {
  correct: boolean;
  answer_id: number;
  /**
   * 정답이 무엇인가. 없으면 단어다(옛 응답 호환).
   *
   * 빈칸 채우기는 문장 문제인데 정답은 단어라, 화면이 이 값을 보고
   * 어느 쪽 해설을 그릴지 고른다.
   */
  answer_type?: "word" | "sentence";
  /** 정답이 문장일 때만 온다. */
  sentence?: GradedSentence;
  /** 정답이 단어일 때 온다. */
  word?: {
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
  content: QuizContent = "words",
): Promise<GradeResult> {
  return request(`${BASE[content]}grade/`, {
    method: "POST",
    body: { token, picked: pickedId },
  });
}
