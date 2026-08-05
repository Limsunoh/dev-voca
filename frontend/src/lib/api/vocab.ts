import { cache } from "react";

import {
  buildQuery,
  fetchChoices,
  fetchDetail,
  request,
  type ChoiceOption,
  type Paginated,
} from "./client";

/** 단어 API 클라이언트. 공통 규칙은 client.ts 에 있다. */

const BASE = "/api/vocab/words/";

/** 목록 카드에 필요한 만큼. 백엔드 WordListSerializer 와 짝. */
export type WordListItem = {
  id: number;
  term: string;
  /** IPA 발음기호. 확실하지 않은 단어는 빈 문자열이다. */
  pronunciation: string;
  meaning: string;
  difficulty: number;
  difficulty_label: string;
  /** 영어 코드(devops 등). 필터 링크를 만들 때만 쓴다. */
  category: string;
  /** 화면에 보여줄 한글 라벨. 분류가 비어 있으면 빈 문자열이다. */
  category_label: string;
};

/**
 * 상세. 백엔드 WordDetailSerializer 와 짝.
 *
 * is_reviewed 는 일부러 뺐다. 검수 게이트는 백엔드가 전담하고(미검수는 404),
 * 프론트는 그 판단을 다시 하지 않는다. 타입에 있으면 언젠가
 * `{word.is_reviewed && ...}` 같은 프론트측 분기가 생긴다.
 *
 * source 도 같은 이유로 뺐다. API 는 여전히 내려주지만 학습자에게는
 * "직접 작성" 같은 값이 아무 정보도 주지 않는다. 타입에 없어야 화면에
 * 다시 새어나가지 않는다. 출처가 필요한 곳은 Admin 이다.
 */
export type WordDetail = WordListItem & {
  description: string;
  example: string;
  example_translation: string;
  created_at: string;
  updated_at: string;
};

// 백엔드는 ordering 도 받지만 화면에 정렬 UI 가 없어 넣지 않았다.
// 정렬 기능을 만들 때 추가한다.
export type WordListParams = {
  search?: string;
  category?: string;
  difficulty?: string;
  page?: string;
};

export function getWords(
  params: WordListParams = {},
): Promise<Paginated<WordListItem>> {
  return request(`${BASE}${buildQuery(params)}`);
}

/** 분류 목록. 실패해도 빈 배열이라 목록 화면은 계속 뜬다. */
export const getCategories = cache(() => fetchChoices(`${BASE}categories/`));

/**
 * 없으면 null.
 *
 * cache() 로 감싼 이유: 상세 페이지는 generateMetadata 와 본문에서 같은 단어를
 * 각각 불러 백엔드를 요청당 두 번 친다. no-store 라 fetch 자동 메모이제이션도
 * 기대할 수 없으므로 여기서 한 번만 나가게 묶는다.
 */
export const getWord = cache((id: string) => fetchDetail<WordDetail>(BASE, id));

// 이 모듈만 임포트하던 화면들이 계속 쓸 수 있게 다시 내보낸다.
export { ApiError, type Paginated } from "./client";
export type CategoryOption = ChoiceOption;
