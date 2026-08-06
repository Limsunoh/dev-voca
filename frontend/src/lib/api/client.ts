/**
 * devvoca 백엔드(DRF) 공용 클라이언트.
 *
 * 서버 컴포넌트에서만 호출한다. 브라우저에서 직접 부르면 CORS 설정에 묶이고
 * 백엔드 주소가 번들에 노출되므로, 데이터는 서버에서 받아 내려보낸다.
 *
 * 단어·문장이 같은 규칙을 쓴다. 도메인마다 복사해두면 캐시 설정이나 에러
 * 처리가 한쪽만 바뀌어 조용히 어긋난다.
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

/** DRF PageNumberPagination 응답 형태. */
export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

/** 분류·종류 필터 버튼 하나. 백엔드의 TextChoices 와 짝. */
export type ChoiceOption = {
  /** 필터 URL 에 넣는 영어 코드. */
  value: string;
  /** 버튼에 보이는 한글 라벨. */
  label: string;
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

export function buildQuery(params: Record<string, string | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    // 빈 문자열은 필터를 걸지 않겠다는 뜻이므로 보내지 않는다.
    if (value) query.set(key, value);
  }
  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

type RequestOptions = {
  method?: "GET" | "POST";
  /** JSON 으로 직렬화해 본문에 싣는다. */
  body?: unknown;
};

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body } = options;

  let res: Response;
  try {
    res = await fetch(`${apiBase()}${path}`, {
      method,
      headers: {
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      // 캐시하지 않는다. 검수 상태(is_reviewed)는 언제든 바뀌는 값이라,
      // 응답이 굳으면 검수가 취소된 항목을 옛 스냅샷으로 계속 보여준다.
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

/**
 * 상세 조회 공용.
 *
 * 없으면 null. 404 는 실패가 아니라 "그런 항목 없음"이므로 호출부가
 * notFound() 로 처리한다.
 */
export async function fetchDetail<T>(
  basePath: string,
  id: string,
): Promise<T | null> {
  // id 는 URL 세그먼트라 무엇이든 들어올 수 있다. 그대로 경로에 끼우면
  // 인코딩된 ../ 같은 값이 요청 경로를 API 밖으로 끌어낸다.
  if (!/^\d+$/.test(id)) return null;

  try {
    return await request<T>(`${basePath}${id}/`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/**
 * 선택지 목록(분류·종류) 공용.
 *
 * 실패해도 빈 배열을 돌려준다. 필터 버튼은 편의 기능이라, 이것 때문에
 * 목록까지 못 보여주면 손해가 더 크다.
 */
export async function fetchChoices(path: string): Promise<ChoiceOption[]> {
  try {
    return await request<ChoiceOption[]>(path);
  } catch (error) {
    // 조용히 삼키면 필터 칩이 사라진 이유를 알 방법이 없다. 화면은 그대로
    // 두되 서버 로그에는 남긴다.
    console.error(`선택지 목록을 불러오지 못했습니다: ${path}`, error);
    return [];
  }
}
