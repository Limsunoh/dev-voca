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
  words: "/learn/words",
  wordDetail: (id: number | string) => `/learn/words/${id}`,
  sentences: "/learn/sentences",
  sentenceDetail: (id: number | string) => `/learn/sentences/${id}`,
} as const;

/** 콘텐츠 탭에 쓰는 목록. 모드와 무관하게 이름만 갖는다. */
export const contents = [
  { slug: "words", label: "단어" },
  { slug: "sentences", label: "문장" },
] as const;

/** 학습 모드 하나. 화면 위쪽 탭을 이걸로 만든다. */
export type LearningMode = {
  /** URL 의 첫 segment. */
  slug: string;
  label: string;
  /** 만들어졌는지. false 면 링크 대신 "준비 중" 으로 보인다. */
  ready: boolean;
  description: string;
};

/**
 * 모드 목록.
 *
 * 아직 learn 만 동작한다. 나머지를 "준비 중"으로 함께 보여주는 이유는
 * 이 서비스가 단어장 하나로 끝나지 않는다는 걸 알리기 위해서다.
 * 각 모드를 만들면 ready 를 true 로 바꾸면 그대로 링크가 된다.
 *
 * 경로를 여기 박아두지 않는 이유: 모드를 바꿀 때 보고 있던 콘텐츠를
 * 유지해야 한다. 문장을 보다 "문제풀기" 를 눌렀는데 단어 문제가 나오면
 * 사용자가 흐름을 잃는다. 링크는 ModeTabs 가 현재 콘텐츠로 만든다.
 */
export const learningModes: LearningMode[] = [
  {
    slug: "learn",
    label: "익히기",
    ready: true,
    description: "뜻과 쓰임을 읽으며 익힙니다.",
  },
  {
    slug: "test",
    label: "문제풀기",
    ready: true,
    description: "외운 것을 문제로 확인합니다.",
  },
  {
    slug: "talk",
    label: "말하기",
    ready: false,
    description: "소리 내어 읽고 따라 합니다.",
  },
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
