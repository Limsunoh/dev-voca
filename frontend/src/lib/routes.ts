/**
 * 화면 경로.
 *
 * 경로는 /{모드}/{콘텐츠} 두 축으로 짠다.
 *
 *   모드   learn(익히기) · test(문제풀기) · talk(말하기) · game(놀이)
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

export const routes = {
  home: "/",
  words: "/learn/words",
  wordDetail: (id: number | string) => `/learn/words/${id}`,
  sentences: "/learn/sentences",
  sentenceDetail: (id: number | string) => `/learn/sentences/${id}`,
  login: "/login",
  signup: "/signup",
  profile: "/profile",
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
 * 익히기·문제풀기는 보고 있던 콘텐츠를 유지한다. 문장을 보다 "문제풀기"
 * 를 눌렀는데 단어 문제가 나오면 사용자가 흐름을 잃는다.
 */
export function tabHref(tab: Tab, pathname: string): string {
  if (tab.segment === "learn" || tab.segment === "test") {
    const content = contentFromPath(pathname);
    return contentPath(tab.segment, content);
  }
  return tab.segment ? `/${tab.segment}` : routes.home;
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
 * 아직 안 만든 모드(talk)도 목록에 있다. 만들고 나서 ready 를 true 로
 * 바꾸면 그대로 눌리는 탭이 된다.
 *
 * 경로를 여기 박아두지 않는 이유: 모드를 바꿀 때 보고 있던 콘텐츠를
 * 유지해야 한다. 문장을 보다 "문제풀기" 를 눌렀는데 단어 문제가 나오면
 * 사용자가 흐름을 잃는다. 링크는 tabHref 가 현재 콘텐츠로 만든다.
 */
export const learningModes: LearningMode[] = [
  { slug: "learn", label: "익히기", ready: true },
  { slug: "test", label: "문제풀기", ready: true },
  { slug: "talk", label: "말하기", ready: false },
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
  { key: "profile", label: "나", segment: "profile", ready: true },
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
