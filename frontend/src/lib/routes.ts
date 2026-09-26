/**
 * 화면 경로.
 *
 * 경로는 /{모드}/{콘텐츠} 두 축으로 짠다.
 *
 *   모드   learn(익히기) · test(문제풀기) · talk(일상영어) · game(놀이)
 *   콘텐츠 words · sentences · errors · articles
 *
 * 같은 콘텐츠를 모드마다 다른 이름으로 부르면(/learn/vocab 인데 /test/words)
 * 경로만 보고 무엇을 다루는지 알 수 없게 된다. 그래서 콘텐츠 이름은
 * 백엔드 API(/api/vocab/words/)와 맞춰 words 로 통일한다.
 *
 * 문자열을 화면마다 박아두면 경로를 옮길 때 한 곳을 빠뜨리고, 그 링크는
 * 눌러보기 전까지 깨진 걸 모른다. 실제로 /vocab 에서 옮길 때 8곳을 고쳐야 했다.
 */

/** 콘텐츠 목록 경로. 모드가 늘어나면 mode 를 바꿔 부른다. */
export function contentPath(mode: string, content: string): string {
  return `/${mode}/${content}`;
}

/**
 * 순위표 종류. lib/api/leaderboards 의 BOARD_KINDS 와 같은 값이다.
 *
 * 거기서 import 하지 않는 이유: routes 는 아무것도 안 가져오는 순수
 * 모듈이라, API 계층을 끌어오면 의존 방향이 뒤집힌다. 값이 셋뿐이고
 * 백엔드 URL 과 묶여 있어 자주 바뀌지도 않는다.
 *
 * string 으로 두면 routes.board("weekli") 같은 오타가 타입 검사를
 * 통과해 /board/weekli 로 나간다 - 눌러보기 전까지 모른다.
 */
export type BoardKind = "weekly" | "all_time" | "streak";

/**
 * 소리내어 읽기의 갈래.
 *
 * daily 는 일상 표현("How was your weekend"), dev 는 개발 용어(cache).
 * 둘은 성격도 난이도도 달라서 한 판에 섞지 않는다 - deploy 다음에
 * 일상 인사가 나오면 머리를 다시 맞춰야 한다.
 *
 * string 으로 두지 않는 이유는 BoardKind 와 같다. 오타가 타입 검사를
 * 통과해 엉뚱한 쿼리로 나간다.
 */
export type TalkKind = "daily" | "dev";

/**
 * 고른 난이도. 0 은 "전체" 다.
 *
 * 0 을 쓰는 이유: 서버의 Difficulty 가 1·2·3 이라 그 바깥 값이 필요한데,
 * null 로 두면 주소 파싱·비교·기본값이 전부 두 갈래가 된다. 0 은 거짓이라
 * `if (level)` 한 줄로 "안 골랐다" 가 표현된다.
 */
export type TalkLevel = 0 | 1 | 2 | 3;

/**
 * 일상 표현의 상황. 서버 PhraseScene 의 값과 같다.
 *
 * 목록을 여기 둔다. 서버가 상황 목록 API 를 따로 만들지 않았다 - 다섯 개로
 * 고정이라 난이도처럼 화면이 들고 있으면 된다(679a205). 주소를 읽는
 * 페이지와 중계(api/talk)가 같은 목록으로 거른다.
 */
export const talkScenes = [
  "greeting",
  "shopping",
  "asking",
  "trouble",
  "smalltalk",
] as const;

/** 고른 상황. 빈 문자열은 "전체" 다(TalkLevel 의 0 과 같은 자리). */
export type TalkScene = (typeof talkScenes)[number] | "";

/** 아는 상황 값이면 그대로, 아니면 "" (전체). 주소와 중계가 같이 쓴다. */
export function toTalkScene(value: unknown): TalkScene {
  return talkScenes.find((scene) => scene === value) ?? "";
}

export const routes = {
  home: "/",
  words: "/learn/words",
  wordDetail: (id: number | string) => `/learn/words/${id}`,
  sentences: "/learn/sentences",
  sentenceDetail: (id: number | string) => `/learn/sentences/${id}`,
  login: "/login",
  signup: "/signup",
  profile: "/profile",
  /**
   * 문제풀기 허브. 탭바 "문제풀기" 가 여기로 온다.
   *
   * 일일공부·다시 보기·한 판은 탭 안에 입구가 없었다. 탭이 단어 문제로
   * 곧장 가서, 그 셋은 홈 카드나 단어 문제 화면 구석 링크로만 닿았다.
   */
  test: "/test",
  /*
   * 아래 다섯 중 words·sentences 만 콘텐츠 축을 따른다.
   *
   * round·daily·review 는 콘텐츠가 아니라 **판의 종류**다. 한 판에
   * 단어와 문장이 섞여 나오므로 /test/words 옆에 나란히 두면 같은 축인
   * 것처럼 보이지만 아니다. 다음에 /test/errors 를 만들 때 두 종류가
   * 섞여 있다는 것을 알고 놓으라고 적어둔다.
   */
  testWords: "/test/words",
  /** 문장 낱개 문제풀기. 빈칸 채우기와 상황 고르기가 나온다. */
  testSentences: "/test/sentences",
  /** 90초 한 판. 점수가 순위표에 오른다. */
  testRound: "/test/round",
  /** 하루 한 번 일일공부. 로그인이 필요하다. */
  testDaily: "/test/daily",
  /** 틀린 것 다시 풀기. 점수가 없고 로그인이 필요하다. */
  testReview: "/test/review",
  /**
   * 오답 노트. 마지막에 틀린 것을 모아 보는 자리다.
   *
   * 모드/콘텐츠 두 축을 안 따르는 이유는 순위표와 같다 - 단어와 문장이
   * 한 목록에 섞여 나오므로 /learn/... 도 /test/... 도 맞지 않는다.
   * 그리고 여기서는 풀지 않는다(푸는 자리는 testReview).
   */
  mistakes: "/mistakes",
  /**
   * 소리내어 읽기. 갈래(일상 표현/개발 용어)는 쿼리로 가른다.
   *
   * 콘텐츠 축(/talk/words)을 안 쓰는 이유: contents 는 모드와 무관한
   * 전역 목록이라 거기에 갈래를 더하면 익히기·문제풀기에도 같은 탭이
   * 생긴다. 그쪽에는 그 콘텐츠가 없어서 눌리는 순간 빈 화면이다.
   * 이 모드 안에서만 도는 축이라 여기서 푼다.
   *
   * 기본값(쿼리 없음)이 일상 표현이다. 탭 이름이 그것이라 처음 들어온
   * 사람이 보는 것과 이름이 맞아야 한다.
   */
  talk: (kind?: TalkKind, level?: TalkLevel, scene?: TalkScene) => {
    // 기본값은 아예 안 싣는다. 주소가 짧아야 공유했을 때 읽힌다.
    const query = new URLSearchParams();
    if (kind === "dev") query.set("kind", "dev");
    if (level) query.set("level", String(level));
    // 상황은 일상 표현에만 있다. 개발 용어로 갈 때 들고 가면 주소에만
    // 남고(서버도 무시한다) 다시 일상 표현으로 돌아올 때 모르는 새에
    // 되살아난다.
    if (scene && kind !== "dev") query.set("scene", scene);
    const rest = query.toString();
    return rest ? `/talk?${rest}` : "/talk";
  },
  /**
   * 순위표. 종류를 안 주면 이번 주.
   *
   * 모드/콘텐츠 두 축을 안 따르는 이유: 순위표는 콘텐츠(단어·문장)에
   * 걸리지 않는다. 단어로 얻은 점수와 문장으로 얻은 점수가 한 표에 같이
   * 오르므로 /learn/board 도 /test/board 도 맞지 않는다.
   */
  board: (kind?: BoardKind) =>
    kind && kind !== "weekly" ? `/board/${kind}` : "/board",
} as const;

/**
 * 아래 탭바 항목.
 *
 * 앱은 화면 위에 사이트 머리말을 두지 않는다. 이동은 아래 탭이 맡고,
 * 계정은 "나" 안으로 들어간다. (`/profile` 은 로그인 안 했으면 로그인
 * 화면으로 보내므로 두 상태를 한 탭으로 덮는다.)
 *
 * 모드(익히기·문제풀기)가 탭이 된 이유: 화면 안에도 같은 줄이 있으면
 * 같은 이동 수단이 두 번 나온다. 콘텐츠(단어·문장)를 고르는 줄만 화면에
 * 남긴다.
 */
export type Tab = {
  key: string;
  label: string;
  /** 이 탭이 맡는 첫 경로 segment. 활성 판정에 쓴다. */
  segment: string;
  /** false 면 누를 수 없고 "준비 중" 으로 보인다. */
  ready: boolean;
};

/**
 * 탭을 눌렀을 때 갈 곳.
 *
 * 익히기는 보고 있던 콘텐츠를 유지한다. 문장을 보다 "익히기" 를 눌렀는데
 * 단어 목록이 나오면 사용자가 흐름을 잃는다.
 *
 * 문제풀기는 허브로 간다. 예전에는 익히기처럼 콘텐츠를 따라 단어·문장
 * 문제로 곧장 갔는데, 그러면 일일공부·다시 보기·한 판으로 가는 길이
 * 탭 안에 없었다. 단어·문장 문제는 허브에서 한 번 더 누른다.
 */
export function tabHref(tab: Tab, pathname: string): string {
  if (tab.segment === "learn") {
    return contentPath(tab.segment, contentFromPath(pathname));
  }
  return tab.segment ? `/${tab.segment}` : routes.home;
}

/**
 * 자기 탭이 없는 화면을 어느 탭 아래로 볼지.
 *
 * 순위표와 오답 노트는 탭이 없어서, 그대로 두면 탭바에 아무것도 안 켜져
 * 지금 어디 있는지 알 수 없다. 둘 다 문제풀기 쪽에서 들어오는 화면이라
 * 문제풀기를 켠다 - 오답 노트는 허브에서만, 순위표는 허브·한 판·일일공부
 * 결과에서 들어온다. 순위표는 내정보의 "순위표 전체" 로도 들어오지만 나머지
 * 입구가 전부 문제풀기 쪽이다.
 *
 * Map 인 이유: 객체로 두면 `/constructor` 같은 주소가 Object 의 속성을
 * 꺼내 온다.
 */
const tabOwners = new Map<string, string>([
  ["board", "test"],
  ["mistakes", "test"],
]);

/** 지금 경로에서 켜질 탭의 segment. TabBar 가 tab.segment 와 비교한다. */
export function activeTabSegment(pathname: string): string {
  const first = pathname.split("/")[1] ?? "";
  return tabOwners.get(first) ?? first;
}

/** 지금 보고 있는 콘텐츠. 알 수 없으면 words. */
export function contentFromPath(pathname: string): string {
  const second = pathname.split("/")[2] ?? "";
  return contents.some((c) => c.slug === second) ? second : "words";
}

/** 콘텐츠 탭에 쓰는 목록. 모드와 무관하게 이름만 갖는다. */
export const contents = [
  { slug: "words", label: "단어" },
  { slug: "sentences", label: "문장" },
] as const;

/** 학습 모드 하나. 아래 탭바의 가운데 칸들을 이걸로 만든다. */
export type LearningMode = {
  /** URL 의 첫 segment. */
  slug: string;
  label: string;
  /** 만들어졌는지. false 면 눌리지 않고 "준비 중" 으로 보인다. */
  ready: boolean;
};

/**
 * 모드 목록. 아래 탭바가 이걸로 만들어진다.
 *
 * ready 가 false 인 모드는 눌리지 않고 "준비 중" 으로 보인다. 지금은
 * 셋 다 열려 있고, 다음 모드(놀이 등)를 만들 때 다시 쓴다.
 *
 * 경로를 여기 박아두지 않는 이유: 익히기는 모드를 바꿀 때 보고 있던
 * 콘텐츠를 유지해야 한다. 링크는 tabHref 가 만든다.
 */
export const learningModes: LearningMode[] = [
  { slug: "learn", label: "익히기", ready: true },
  { slug: "test", label: "문제풀기", ready: true },
  { slug: "talk", label: "일상영어", ready: true },
];

/**
 * 탭바를 숨기고 나가기 버튼으로만 나가는 화면들.
 *
 * 판이 걸린 화면이다. 탭바를 두면 푸는 중에 홈이나 익히기를 눌러 그냥
 * 빠져나가지고, 그때 점수가 사라진다. 게임이 그러지 않는 이유와 같다 -
 * 나가는 길은 하나여야 실수로 안 나간다.
 *
 * **여기 넣는 화면에는 ExitGuard 를 반드시 둔다.** 안 그러면 나갈 방법이
 * 없는 막다른 화면이 된다.
 *
 * 경로 앞부분으로 거르지 않고 하나씩 적는 이유: "/test/" 로 시작하는 것을
 * 전부 숨겼더니 판이 없는 화면까지 걸렸다. /test/words 의 error.tsx 는
 * 문제를 못 불러왔을 때 뜨는데, 지킬 점수가 없으면서 탭바만 사라져서
 * 그 안에 링크가 있느냐에 따라 막다른 곳이 됐다.
 *
 * 새 문제 화면을 만들면 여기 한 줄을 더한다. 빠뜨리면 탭바가 남아
 * 연출이 어긋날 뿐이지만, 반대(자동으로 숨김)는 빠뜨렸을 때 갇힌다.
 */
export const immersiveRoutes: readonly string[] = [
  routes.testWords,
  routes.testSentences,
  routes.testRound,
];

/**
 * 아래 탭바 항목.
 *
 * 가운데는 learningModes 에서 만든다. 두 벌로 두면 모드를 하나 열 때
 * 탭바만 낡는다.
 *
 * 아직 안 만든 모드도 자리를 준다. 이 서비스가 단어장 하나로 끝나지
 * 않는다는 걸 로그인 전에도 알리기 위해서다. 대신 누를 수는 없게 두고
 * "준비 중" 을 함께 보여준다 - 눌리는데 아무 일도 안 일어나는 것이
 * 눌리지 않는 것보다 나쁘다.
 */
export const tabs: Tab[] = [
  { key: "home", label: "홈", segment: "", ready: true },
  ...learningModes.map((mode) => ({
    key: mode.slug,
    label: mode.label,
    segment: mode.slug,
    ready: mode.ready,
  })),
  // "나" 가 아니라 "내정보" 인 이유: 나머지 탭이 전부 명사(홈·단어·문장)라
  // 대명사 하나만 결이 어긋난다. 그리고 이 화면에 이메일·비밀번호 변경이
  // 들어오면서 학습 기록만 있는 자리가 아니게 됐다. "내 기록" 으로 좁히면
  // 계정 설정이 들어간 뒤 이름을 다시 바꿔야 한다.
  { key: "profile", label: "내정보", segment: "profile", ready: true },
];

/**
 * 로그인 후 돌아갈 곳. 내부 경로만 통과시킨다.
 *
 * 검사 전에 브라우저가 읽는 모양으로 맞춘다. 주소를 해석할 때 탭과
 * 줄바꿈은 지워지고 역슬래시는 슬래시로 취급되기 때문에, 원문 그대로
 * 보면 "/\남의사이트" 가 내부 경로처럼 보이고 실제로는 밖으로 나간다.
 *
 * 그러면 사용자는 진짜 주소에서 제대로 로그인한 직후 남의 사이트로
 * 넘어간다. 방금 로그인에 성공했으니 거기서 다시 로그인을 요구해도
 * 의심하기 어렵다.
 *
 * 이메일 로그인과 구글 로그인이 같은 함수를 쓴다. 두 벌로 두면 한쪽만
 * 고쳐지고 다른 쪽은 조용히 낡는다.
 */
export function safeNext(value: unknown): string {
  const raw = typeof value === "string" ? value : "";
  const next = raw.replace(/[\t\r\n]/g, "").replace(/\\/g, "/");

  // 슬래시 하나로 시작하고 그다음이 슬래시가 아닌 경로만 받는다.
  return /^\/(?!\/)/.test(next) ? next : "/";
}

/**
 * 상세에서 돌아갈 목록 주소. **목록 경로가 아니면 버린다.**
 *
 * 상세 화면은 이 값을 URL 쿼리로 받으므로 주소창에 아무것도 넣을 수 있다.
 * `safeNext` 는 내부 경로인지까지만 보는데, 여기서는 그보다 좁아야 한다 -
 * 목록으로 돌아가는 버튼이 로그아웃이나 문제풀기 시작으로 튀면 안 된다.
 *
 * 그래서 경로 부분이 아는 목록과 정확히 같을 때만 통과시키고, 쿼리는
 * 그대로 둔다(페이지·검색어·필터·섞은 순서가 거기 들어 있다).
 */
export function safeListUrl(value: unknown, expected: string): string {
  const next = safeNext(value);
  const [path] = next.split("?");
  return path === expected ? next : expected;
}

/**
 * 상세 주소에 "돌아올 목록 주소" 를 붙인다.
 *
 * 목록에서 상세로 갈 때 지금 보던 주소를 같이 넘긴다. 그래야 상세의
 * 되돌아가기가 페이지·검색어·필터·섞은 순서를 그대로 들고 돌아온다 -
 * 이것이 없으면 2페이지에서 들어간 사람이 1페이지로 떨어진다.
 *
 * 브라우저 뒤로가기는 이 값과 무관하게 동작한다. 그쪽은 목록 주소가
 * 순서를 기억하는 것으로 해결된다 - 목록 화면이 시드 없이 들어온 요청을
 * 시드 붙인 주소로 보내는 자리를 보라(`learn/words/page.tsx`).
 */
export function detailWithBack(detailPath: string, backTo: string): string {
  return `${detailPath}?from=${encodeURIComponent(backTo)}`;
}

/**
 * 목록 주소를 만든다. 빈 값은 빼고, 1페이지는 page 를 안 적는다.
 *
 * 쓰는 자리가 셋이다 - 섞은 순서를 주소에 적으려 보낼 때(목록 진입),
 * 카드가 "되돌아올 주소" 로 실어 보낼 때, 페이지 넘기기 링크를 만들 때.
 * 한 곳에서 만들지 않으면 되돌아가기가 페이지 넘기기와 다른 주소를
 * 가리킨다.
 *
 * **빈 값을 빼는 이 판정은 목록 화면의 판정과 같은 기준이어야 한다** - 둘 다
 * 공백을 턴 뒤 값이 남는지 본다. `if (one !== undefined)` 로 바꾸면 빈
 * 문자열이 주소에 적히기 시작해서, 고르지도 않은 조건이 `?search=` 처럼
 * 링크마다 따라다닌다(`Pagination` 머리말이 경계하는 것과 같은 부류다).
 *
 * 같은 판정이 `lib/api/client.ts` 의 `buildQuery` 에도 있다 - 그쪽은 백엔드로
 * 보내는 쿼리를 만든다. 한쪽만 고치면 화면 주소와 API 요청이 어긋난다.
 */
export function listUrl(
  basePath: string,
  filters: Record<string, string | string[] | undefined>,
  page?: number | string,
): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    const one = Array.isArray(value) ? value[0] : value;
    if (one) query.set(key, one);
  }
  const n = Number(page);
  if (Number.isInteger(n) && n > 1) query.set("page", String(n));

  const qs = query.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}
