import { cache } from "react";

/**
 * devvoca 백엔드(DRF) 클라이언트.
 *
 * 서버 컴포넌트에서만 호출한다. 브라우저에서 직접 부르면 CORS 설정에 묶이고
 * 백엔드 주소가 번들에 노출되므로, 데이터는 서버에서 받아 내려보낸다.
 */

/**
 * 백엔드 주소를 요청 시점에 읽는다.
 *
 * 모듈 최상위에서 읽으면 빌드 시점 값이 그대로 굳어, 배포 플랫폼이 런타임에
 * 넣어주는 값을 못 받는다. 그러면 프로덕션에서 조용히 127.0.0.1 을 치고
 * "서버에 연결할 수 없습니다"만 뜬다.
 */
function apiBase(): string {
  const url = process.env.API_URL;
  if (url) return url;

  if (process.env.NODE_ENV === "production") {
    throw new Error("API_URL 환경변수가 필요합니다.");
  }
  return "http://127.0.0.1:8000";
}

/** 목록 카드에 필요한 만큼. 백엔드 WordListSerializer 와 짝. */
export type WordListItem = {
  id: number;
  term: string;
  meaning: string;
  difficulty: number;
  difficulty_label: string;
  category: string;
};

/**
 * 상세. 백엔드 WordDetailSerializer 와 짝.
 *
 * is_reviewed 는 일부러 뺐다. 검수 게이트는 백엔드가 전담하고(미검수는 404),
 * 프론트는 그 판단을 다시 하지 않는다. 타입에 있으면 언젠가
 * `{word.is_reviewed && ...}` 같은 프론트측 분기가 생긴다.
 */
export type WordDetail = WordListItem & {
  description: string;
  example: string;
  example_translation: string;
  source: string;
  created_at: string;
  updated_at: string;
};

/** DRF PageNumberPagination 응답 형태. */
export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

// 백엔드는 ordering 도 받지만 화면에 정렬 UI 가 없어 넣지 않았다.
// 정렬 기능을 만들 때 추가한다.
export type WordListParams = {
  search?: string;
  category?: string;
  difficulty?: string;
  page?: string;
};

/** 백엔드가 살아있지 않거나 4xx/5xx 를 줄 때. 페이지에서 잡아 사용자 문구로 바꾼다. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function buildQuery(params: WordListParams): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    // 빈 문자열은 필터를 걸지 않겠다는 뜻이므로 보내지 않는다.
    if (value) query.set(key, value);
  }
  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

async function request<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${apiBase()}${path}`, {
      headers: { Accept: "application/json" },
      // 캐시하지 않는다. 검수 상태(is_reviewed)는 언제든 바뀌는 값이라,
      // 응답이 굳으면 검수가 취소된 단어를 옛 스냅샷으로 계속 보여준다.
      // 목록은 searchParams 덕에 어차피 매 요청 렌더되지만, 상세는
      // request-time API 를 쓰지 않아 이 옵션이 없으면 빌드/첫요청 시점에 고정된다.
      cache: "no-store",
    });
  } catch {
    // 백엔드가 안 떠 있는 경우. 스택 대신 사람이 읽을 문구를 남긴다.
    throw new ApiError("서버에 연결할 수 없습니다.", 0);
  }

  if (!res.ok) {
    throw new ApiError(`요청이 실패했습니다. (${res.status})`, res.status);
  }
  return res.json() as Promise<T>;
}

export function getWords(
  params: WordListParams = {},
): Promise<Paginated<WordListItem>> {
  return request(`/api/vocab/words/${buildQuery(params)}`);
}

/**
 * 없으면 null. 404 는 실패가 아니라 "그런 단어 없음"이므로 호출부가 notFound() 로 처리한다.
 *
 * cache() 로 감싼 이유: 상세 페이지는 generateMetadata 와 본문에서 같은 단어를
 * 각각 불러 백엔드를 요청당 두 번 친다. no-store 라 fetch 자동 메모이제이션도
 * 기대할 수 없으므로 여기서 한 번만 나가게 묶는다.
 */
export const getWord = cache(
  async (id: string): Promise<WordDetail | null> => {
    // id 는 URL 세그먼트라 무엇이든 들어올 수 있다. 그대로 경로에 끼우면
    // 인코딩된 ../ 같은 값이 요청 경로를 /api/vocab/words/ 밖으로 끌어낸다.
    if (!/^\d+$/.test(id)) return null;

    try {
      return await request<WordDetail>(`/api/vocab/words/${id}/`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },
);
