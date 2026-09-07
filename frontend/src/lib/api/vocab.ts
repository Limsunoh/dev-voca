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
  /**
   * 한글만 읽어도 통하게 적은 발음. 규칙은 apps/ai_pipeline/prompts/korean-reading.md.
   *
   * **검수되지 않았으면 빈 문자열로 온다.** 백엔드가 그 판단을 전담하므로
   * 화면은 "있으면 그린다" 만 하면 된다. 발음기호와 같은 처리다.
   *
   * 강세가 `**...**` 로 감싸여 있다. 그대로 그리면 별표가 보이므로
   * Reading 컴포넌트가 굵게 바꿔 그린다.
   */
  reading: string;
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
  /** 그 발음을 왜 그렇게 읽는지. 특별히 설명할 것이 없으면 빈 문자열. */
  reading_note: string;
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
  /**
   * 목록을 섞을 시드. 없으면 기본 정렬(가나다순)로 온다.
   *
   * 같은 시드면 같은 순서라 페이지를 넘겨도 겹치거나 빠지지 않는다.
   * 새로 섞고 싶으면 새 시드를 만들어 보낸다.
   */
  shuffle?: string;
};

/**
 * 단어 목록.
 *
 * **토큰을 넘기지 않는다.** 백엔드(views.py 의 get_queryset)는 검수 권한이
 * 있는 사람에게 미검수까지 준다. 여기서 토큰을 실으면 검수자 화면에만
 * 미검수 단어가 조용히 섞이고, 백엔드도 프론트도 정상 동작이라 아무도
 * 모른다. 개인화(정렬·최근 본 것)를 붙일 일이 생기면 그때 미검수를 어떻게
 * 할지부터 정한다.
 */
export function getWords(
  params: WordListParams = {},
): Promise<Paginated<WordListItem>> {
  return request(`${BASE}${buildQuery(params)}`);
}

/**
 * 홈이 받는 단어 수. 첫 장 하나 + 아래에 깔 여섯.
 *
 * **화면 높이에 맞추려고 정한 수가 아니다.** 그렇게 맞추면 폰마다 어긋난다 -
 * 390x844 에 맞춘 값이 430x932 에서는 아래가 85px 남는다. 여백은 목록이 남은
 * 공간을 먹어서(UpNext 의 flex-1) 해결하고, 이 수는 "가장 큰 폰에서도 한
 * 화면에 다 안 들어올 만큼" 이면 된다. 440x956 기준으로 잡았다.
 *
 * 함수 옆에 두는 이유: 이 값이 몇이냐에 따라 묶음이 걸치는 페이지 수가
 * 달라진다. 화면 쪽에 두면 테스트가 실제 값을 모른 채 다른 수로만 돌게 된다.
 */
export const HOME_WORDS = 7;

/**
 * 오늘 보여줄 단어들. 첫 번째가 "오늘의 단어" 고 나머지가 이어서 볼 것이다.
 *
 * 홈이 첫 장 아래에 몇 개를 더 깔아둔다. 한 개만 두면 화면 아래가 비어서
 * 스크롤할 것이 있다는 신호가 없다.
 *
 * **"오늘" 은 KST 로 센다.** UTC 로 두면 밤 9시에 연 한국 사용자에게 다음 날
 * 단어가 나온다.
 *
 * **무작위로 뽑지 않는다.** 화면을 새로 그릴 때마다 바뀌면 "오늘의 단어" 가
 * 아니다. 날짜에서 시작점을 만들어 목록 순서대로 가져오면 서버가 여러 대여도
 * 같은 묶음이 나온다. 끝에 닿으면 앞으로 돌아간다(`% count`) - 안 그러면
 * 목록 끝에 걸린 날에만 짧아진다.
 *
 * 다만 하루 안에 안 바뀐다는 보장은 아니다. 인덱스가 목록 순서(term 오름차순)
 * 기준이라, 검수가 하나 통과되면 count 가 늘고 새 단어가 알파벳 중간에
 * 끼어들어 그 뒤가 한 칸씩 밀린다. 정말 고정하려면 백엔드에 daily 엔드포인트가
 * 필요한데, 지금은 그만한 값어치가 없다.
 *
 * 목록 API 만 쓰는 이유: 전용 엔드포인트를 만들 만큼 무겁지 않고,
 * 검수 게이트(is_reviewed)를 백엔드가 이미 걸어둔 경로를 그대로 탄다.
 *
 * **요청은 하루 최대 세 번이다.** count 를 알려면 1페이지를 먼저 받아야
 * 하는데, 묶음이 그 페이지를 안 지나가면 그것은 버려지고 필요한 페이지를
 * 새로 받는다. 566개·20개씩·7개 묶음 기준으로 한 장 392일, 두 장 174일이고
 * 뒤엣것이 실제로는 세 번의 요청이다.
 *
 * 한 번으로 줄이려면 백엔드에 daily 엔드포인트가 필요하다. 하루 한 번 여는
 * 화면이라 아직 그만한 값어치가 아니다.
 */
export async function getDailyWords(size: number): Promise<WordListItem[]> {
  if (size < 1) return [];

  const KST_OFFSET_MS = 9 * 60 * 60 * 1000;
  const day = Math.floor((Date.now() + KST_OFFSET_MS) / 86_400_000);

  const first = await getWords();
  if (first.count === 0 || first.results.length === 0) return [];

  const pageSize = first.results.length;
  const start = day % first.count;
  const wanted = Math.min(size, first.count);

  // 묶음이 걸치는 페이지를 미리 계산해서 필요한 것만 받는다.
  //
  // **1페이지를 캐시에 미리 넣어두고 "받은 페이지 수" 로 제한하면 안 된다.**
  // 묶음이 1페이지를 안 지나가면 그 자리가 쓰이지도 않는 채 한도를 먹어서,
  // 정작 필요한 두 장 중 뒤엣것을 못 받는다. 566개·20개씩일 때 시작점이
  // 페이지 끝 네 칸(16~19)에 걸리는 날 - 1년에 108일 - 목록이 짧아지고
  // 그중 27일은 한 개만 남아 섹션이 통째로 사라진다.
  const needed = new Set<number>();
  for (let i = 0; i < wanted; i += 1) {
    const index = (start + i) % first.count;
    needed.add(Math.floor(index / pageSize) + 1);
  }

  const pages = new Map<number, Paginated<WordListItem>>();
  // 1페이지는 count 를 알려고 이미 받았다. 묶음이 거기 걸치면 그대로 쓴다.
  if (needed.has(1)) pages.set(1, first);

  await Promise.all(
    [...needed]
      .filter((page) => page !== 1)
      .map(async (page) => {
        pages.set(page, await getWords({ page: String(page) }));
      }),
  );

  const out: WordListItem[] = [];
  for (let i = 0; i < wanted; i += 1) {
    const index = (start + i) % first.count;
    const target = pages.get(Math.floor(index / pageSize) + 1);
    // 마지막 페이지는 pageSize 보다 짧을 수 있다.
    const item = target?.results[index % pageSize];
    if (item) out.push(item);
  }

  // 조용히 짧아지지 않게 남긴다. count 를 읽은 뒤 뒷페이지를 받기 전에
  // 항목이 줄면(검수 취소·삭제) 여기 걸리는데, 그건 정상 동작이라 받은
  // 만큼만 돌려준다. 자주 뜨면 그때는 다른 이유다.
  if (out.length < wanted) {
    console.warn(
      `오늘의 단어를 ${wanted}개 요청했으나 ${out.length}개만 받았습니다. ` +
        `요청 사이에 항목이 줄었거나, 페이지 크기가 예상과 다릅니다.`,
    );
  }
  return out;
}

/** 분류 목록. 실패해도 빈 배열이라 목록 화면은 계속 뜬다. */
export const getCategories = cache(() => fetchChoices(`${BASE}categories/`));

/**
 * 난이도 목록(쉬움·보통·어려움). 분류와 같은 이유로 백엔드에서 받는다 -
 * 화면에 적어두면 난이도가 늘 때 두 곳을 고쳐야 한다.
 */
export const getDifficulties = cache(() =>
  fetchChoices(`${BASE}difficulties/`),
);

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
