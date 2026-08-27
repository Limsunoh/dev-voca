import { cache } from "react";

import {
  buildQuery,
  fetchChoices,
  fetchDetail,
  request,
  type Paginated,
} from "./client";

/** 문장 API 클라이언트. 공통 규칙은 client.ts 에 있다. */

const BASE = "/api/vocab/sentences/";

/** 목록용. 백엔드 SentenceListSerializer 와 짝. */
export type SentenceListItem = {
  id: number;
  /** 문장은 본문이 곧 제목이라 목록에서도 통째로 보여준다. */
  text: string;
  /**
   * 한글만 읽어도 통하게 적은 발음. 검수 안 됐으면 빈 문자열이다.
   *
   * 문장에는 단어와 달리 설명(reading_note)이 없다. 길어서 화면이
   * 감당하지 못하고, 문장에서 알아야 할 것은 단어 경계가 뭉개지는 것
   * ("Could you" -> "쿠쥬") 하나라 그건 표기 자체에 담긴다.
   */
  reading: string;
  translation: string;
  /** 영어 코드(phrase/error). 필터 링크에 쓴다. */
  kind: string;
  /** 화면에 보여줄 한글 라벨. */
  kind_label: string;
  context: string;
  difficulty: number;
  difficulty_label: string;
  category: string;
  category_label: string;
};

/**
 * 상세. 백엔드 SentenceDetailSerializer 와 짝.
 *
 * is_reviewed 와 source 는 단어와 같은 이유로 뺐다(vocab.ts 주석 참고).
 */
export type SentenceDetail = SentenceListItem & {
  description: string;
  created_at: string;
  updated_at: string;
};

export type SentenceListParams = {
  search?: string;
  category?: string;
  kind?: string;
  difficulty?: string;
  page?: string;
  /** 목록을 섞을 시드. 자세한 설명은 vocab 의 WordListParams 참고. */
  shuffle?: string;
};

export function getSentences(
  params: SentenceListParams = {},
): Promise<Paginated<SentenceListItem>> {
  return request(`${BASE}${buildQuery(params)}`);
}

/** 분류 목록. 단어와 같은 값이지만 각 화면이 자기 API 를 부른다. */
export const getSentenceCategories = cache(() =>
  fetchChoices(`${BASE}categories/`),
);

/** 종류 목록(실무 표현/에러 메시지). */
export const getSentenceKinds = cache(() => fetchChoices(`${BASE}kinds/`));

/** 난이도 목록. 단어와 같은 척도를 쓴다. */
export const getSentenceDifficulties = cache(() =>
  fetchChoices(`${BASE}difficulties/`),
);

export const getSentence = cache((id: string) =>
  fetchDetail<SentenceDetail>(BASE, id),
);
