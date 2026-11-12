/**
 * devvoca 백엔드(DRF) 공용 클라이언트.
 *
 * 서버 컴포넌트에서만 호출한다. 브라우저에서 직접 부르면 CORS 설정에 묶이고
 * 백엔드 주소가 번들에 노출되므로, 데이터는 서버에서 받아 내려보낸다.
 *
 * 단어·문장이 같은 규칙을 쓴다. 도메인마다 복사해두면 캐시 설정이나 에러
 * 처리가 한쪽만 바뀌어 서로 어긋난다.
 */

/**
 * 백엔드 주소를 요청 시점에 읽는다.
 *
 * 모듈 최상위에서 읽으면 빌드 시점 값이 그대로 굳어, 배포 플랫폼이 런타임에
 * 넣어주는 값을 못 받는다. 그러면 프로덕션에서 에러 없이 127.0.0.1 로
 * 요청하고 "서버에 연결할 수 없습니다"만 뜬다.
 *
 * export 인 이유: 파일 업로드(lib/api/accounts.ts)는 multipart 경계를
 * fetch 가 지어야 해서 아래 request() 를 못 쓴다. 그쪽에서 주소만
 * 다시 읽으면 위의 규칙(요청 시점에 읽기, 프로덕션에서는 없으면
 * 던지기)이 두 곳으로 갈라진다.
 */
export function apiBase(): string {
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
    /**
     * 칸별 오류였다면 그 칸 이름(예: "current_password"). 아니면 없다.
     *
     * 폼이 어느 칸을 비울지 고를 때 쓴다. 문구로 가르면 백엔드가 문구만
     * 다듬어도 엉뚱한 칸을 비운다.
     */
    readonly field?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * 목록을 섞을 새 시드.
 *
 * 화면을 열 때마다 새로 만들면 들어올 때마다 다른 항목이 보인다. 대신
 * 페이지 넘기기 링크에는 이 값을 실어 보내야 1페이지와 2페이지가 같은
 * 순서를 공유한다.
 *
 * 콘텐츠 타입과 무관해서 도메인 모듈(vocab·sentences)이 아니라 여기 둔다.
 * vocab 에 두면 문장 화면이 단어 모듈을 거치게 되고, 에러·아티클이 늘면
 * 전부 그렇게 된다.
 *
 * 서버에서만 부른다. 브라우저의 비보안 컨텍스트에서는 crypto 가 없다.
 */
export function newShuffleSeed(): string {
  return crypto.randomUUID().slice(0, 8);
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

/**
 * 백엔드가 이 시간 안에 답하지 않으면 끊는다.
 *
 * 끊지 않으면 백엔드가 멈췄을 때 화면이 대기 화면(app/loading.tsx)에 계속
 * 머문다. 끊으면 오류가 나서 각 화면의 실패 안내나 error.tsx 가 "다시 시도"
 * 를 보여 준다.
 *
 * 읽기(GET)에만 건다. 쓰기는 우리가 끊어도 백엔드가 하던 일을 마칠 수 있어서,
 * 저장은 됐는데 화면은 실패로 보이는 일이 생긴다. 판 답이 저장된 뒤 끊기면
 * RoundBoard 가 옛 토큰으로 끝내기를 불러 판 기록이 통째로 빠지고, 비밀번호
 * 변경이 저장된 뒤 끊기면 새 토큰을 못 받아 로그아웃된다. 백엔드의 gunicorn 도
 * 막지 못한다 - 스레드 방식(Procfile --threads)이라 오래 걸리는 요청을 끊지
 * 않는다(DEPLOY.md). 쓰기는 누른 버튼이
 * 이미 "처리 중" 을 보여 줘서 멈춘 것처럼 보이지 않는다.
 */
const READ_TIMEOUT_MS = 10_000;

/**
 * 읽기 요청에 넘길 대기 시간 신호. 백엔드를 직접 부르는 읽기(이 파일의
 * request 의 GET, 사진 중계 라우트)가 같은 값을 쓰게 한다.
 *
 * fetch 에 signal 을 넘기면 Next 가 한 요청 안의 같은 GET 을 합치지 않는다
 * (next/dist/server/lib/dedupe-fetch.js). 한 화면에서 같은 것을 두 번 부르는
 * 곳(getWord, getSentence, getCurrentUser, 선택지 목록)은 React cache() 로
 * 감싸 두었으니, 새로 그런 함수를 만들면 같이 감싼다.
 */
export function readTimeout(): AbortSignal {
  return AbortSignal.timeout(READ_TIMEOUT_MS);
}

/**
 * 위 대기 시간을 넘겨서 끊긴 것인가.
 *
 * 연결 실패(ApiError 의 status 0)와 가른다. 연결 실패는 화면이 "서버에 연결할
 * 수 없습니다" 로 안내하는데, 느려서 끊긴 것에 그 문구를 쓰면 사실과 다르다.
 */
export function isBackendTimeout(error: unknown): boolean {
  return error instanceof DOMException && error.name === "TimeoutError";
}

/** 대기 시간을 넘겨 끊었을 때 던지는 오류. 중계 라우트는 504 로 내보낸다. */
export function slowBackendError(): ApiError {
  return new ApiError("서버 응답이 늦습니다. 잠시 뒤 다시 시도해주세요.", 504);
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  /** JSON 으로 직렬화해 본문에 싣는다. */
  body?: unknown;
  /**
   * 인증 토큰. 서버가 쿠키에서 꺼내 넘긴다.
   *
   * 브라우저는 이 값을 볼 수 없다 - 토큰은 httpOnly 쿠키에만 있고,
   * 그것을 읽어 헤더에 붙이는 일은 Next 서버에서만 일어난다.
   */
  token?: string;
};

/**
 * 백엔드가 준 안내 문구를 꺼낸다.
 *
 * 상태 코드만 남기면 "이미 가입된 이메일입니다" 같은 안내가 사용자에게
 * 닿지 않는다. 사용자는 왜 안 되는지 모른 채 같은 시도를 반복한다.
 *
 * DRF 는 형태가 여러 가지다.
 *   {"detail": "..."}                  권한·인증 오류
 *   {"non_field_errors": ["..."]}      폼 전체에 걸린 오류
 *   {"email": ["..."], "password": [...]}  칸별 오류
 *
 * 칸별 오류면 그 칸 이름도 같이 돌려준다(ApiError.field). 칸이 아닌 것(폼
 * 전체 오류 non_field_errors, 목록 모양 본문, detail)은 이름을 싣지 않는다.
 */
async function errorDetail(
  res: Response,
): Promise<{ message: string; field?: string }> {
  const fallback = { message: `요청이 실패했습니다. (${res.status})` };

  // 서버 오류의 본문은 그대로 보여주지 않는다. 거기엔 사용자가 할 수 있는
  // 일이 없고, 내부 사정이 적혀 나갈 수 있다. 400 대만 안내로 쓴다.
  if (res.status >= 500) return fallback;

  try {
    const data = await res.json();

    // 객체가 아니면 아래 순회가 이상하게 동작한다. 문자열이 오면
    // Object.values 가 글자 하나씩 쪼개서 첫 글자만 보여준다.
    if (!data || typeof data !== "object") return fallback;

    if (typeof data.detail === "string") return { message: data.detail };

    // 칸별 오류는 첫 줄만 보여준다. 여러 개를 이어 붙이면 읽기 어렵다.
    //
    // 칸 이름으로 싣지 않는 키: 폼 전체 오류(non_field_errors), 목록 모양
    // 오류(DRF 가 ["..."] 로 줄 때 키가 "0"), detail 이 목록으로 온 경우.
    const fieldless = Array.isArray(data);
    for (const [key, value] of Object.entries(data)) {
      const field =
        fieldless || key === "non_field_errors" || key === "detail"
          ? undefined
          : key;
      if (typeof value === "string") return { message: value, field };
      if (Array.isArray(value) && typeof value[0] === "string") {
        return { message: value[0], field };
      }
    }
  } catch (error) {
    // 본문을 읽다 대기 시간을 넘긴 것은 삼키지 않는다. request() 가 받아
    // "서버 응답이 늦습니다" 로 바꾼다. 여기서 삼키면 "요청이 실패했습니다.
    // (400)" 처럼 사실과 다른 문구가 나간다.
    if (isBackendTimeout(error)) throw error;
    // 본문이 JSON 이 아닌 경우. 아래 기본 문구를 쓴다.
  }

  return fallback;
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, token } = options;

  let res: Response;
  try {
    res = await fetch(`${apiBase()}${path}`, {
      method,
      headers: {
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Token ${token}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      // 캐시하지 않는다. 검수 상태(is_reviewed)는 언제든 바뀌는 값이라,
      // 응답이 굳으면 검수가 취소된 항목을 옛 스냅샷으로 계속 보여준다.
      // 목록은 searchParams 덕에 어차피 매 요청 렌더되지만, 상세는
      // request-time API 를 쓰지 않아 이 옵션이 없으면 빌드/첫요청 시점에 고정된다.
      cache: "no-store",
      signal: method === "GET" ? readTimeout() : undefined,
    });
  } catch (error) {
    if (isBackendTimeout(error)) throw slowBackendError();
    // 백엔드가 안 떠 있는 경우. 스택 대신 사람이 읽을 문구를 남긴다.
    throw new ApiError("서버에 연결할 수 없습니다.", 0);
  }

  // GET 이면 아래 본문 읽기도 같은 대기 시간 안에 든다. 머리만 오고 본문이
  // 늦게 오다 끊기면 여기서 TimeoutError 가 나므로 같은 오류로 바꾼다.
  try {
    if (!res.ok) {
      const { message, field } = await errorDetail(res);
      throw new ApiError(message, res.status, field);
    }
    // 204 는 본문이 없다. json() 을 부르면 파싱 에러가 난다.
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } catch (error) {
    if (isBackendTimeout(error)) throw slowBackendError();
    throw error;
  }
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
    // 로그 없이 삼키면 필터 칩이 사라진 이유를 알 방법이 없다. 화면은 그대로
    // 두되 서버 로그에는 남긴다.
    console.error(`선택지 목록을 불러오지 못했습니다: ${path}`, error);
    return [];
  }
}
