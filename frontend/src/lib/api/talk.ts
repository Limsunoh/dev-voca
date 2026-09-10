import { buildQuery, request } from "./client";

export type { TalkKind } from "@/lib/routes";
import type { TalkKind } from "@/lib/routes";

/**
 * 소리내어 읽기. 공통 규칙은 client.ts 에 있다.
 *
 *   GET  /api/vocab/talk/question/   읽을 것 하나
 *   POST /api/vocab/talk/grade/      인식된 글자를 보내 채점한다
 *
 * 경로가 vocab 아래인 이유: config/urls.py 가 vocab 앱을 통째로 그 밑에
 * 걸어서 ViewSet 이 따라 들어간다. 화면 경로(/talk)와 다르지만 맞출 이유가
 * 없다 - API 는 무엇을 다루는 데이터인지로 묶이고 화면은 사용자가 무엇을
 * 하는지로 묶인다.
 *
 * **음성 파일은 서버에 오지 않는다.** 브라우저가 음성을 글자로 바꾸고
 * (Web Speech API), 우리는 그 글자만 보낸다. 그래서 저장할 음성이 없고,
 * 목소리를 다루는 데 따르는 보관 기간·삭제 절차 문제가 생기지 않는다.
 * 배포마다 디스크가 초기화되는 이 프로젝트에서 음성 파일을 두면 사라진다는
 * 문제도 함께 없어진다.
 *
 * 다만 **브라우저가 그 글자를 만들려고 음성을 구글 서버로 보낸다.**
 * 우리 서버에 안 온다는 것과 별개 사실이라, 마이크를 켜기 전에 화면이
 * 그것을 알린다(MicGate).
 *
 * **로그인이 필요 없다.** 점수가 안 남는 연습이라 계정에 쌓일 것이 없고,
 * 이 기능은 처음 온 사람의 두려움을 줄이려는 것이라 로그인 뒤에 숨기면
 * 정작 필요한 사람이 못 만난다. 토큰이 있으면 실어 보내고 없으면 없는
 * 대로 부른다(문제풀기가 AllowAny 인 것과 같은 결).
 *
 * **이 모듈은 서버에서만 부른다.** 백엔드 주소는 서버 전용 환경변수다.
 * 화면은 같은 출처 중계(/api/talk)를 부르고 그 중계가 이 함수들을 쓴다.
 */

const BASE = "/api/vocab/talk/";

/**
 * 서버가 부르는 갈래 이름.
 *
 * 화면 쪽(TalkKind)은 daily·dev 이고 서버는 phrase·word 다. **화면 이름을
 * 서버에 맞추지 않는다** - 주소에 나오는 말은 사용자가 읽는 것이라
 * (`?kind=dev`) "일상/개발" 쪽이 알아보기 쉽고, 서버 이름은 데이터 모델
 * (Word·DailyPhrase)을 따른 것이라 그쪽대로가 맞다. 옮기는 자리를 여기
 * 한 곳으로 모은다.
 */
export type ServerKind = "word" | "phrase";

/** 읽을 것 하나. */
export type TalkPrompt = {
  /** 채점할 때 그대로 돌려보낸다. 정답은 이 안에 서명되어 있다. */
  token: string;
  /**
   * 방금 낸 것의 번호. 다음에 부를 때 exclude 로 돌려준다.
   *
   * 없으면 같은 것이 계속 나온다 - 표현이 60개뿐이라 열 번 누르면
   * 절반쯤은 겹친다.
   */
  id: number;
  /** 서버가 부르는 이름. 화면은 배지에만 쓴다. */
  kind: ServerKind;
  /** 읽어야 할 글자. 낱말 하나일 수도, 여섯 낱말까지의 표현일 수도 있다. */
  term: string;
  /**
   * 발음기호. 바깥을 슬래시로 한 번 감싼 모양이다(`/wɛr ɪz ðə/`).
   *
   * 그리는 자리에서는 **받은 값을 그대로 쓴다.** 이 저장소의 다섯 화면이
   * 이미 그렇게 그리고 있어서(learn/words, app/page, QuizBoard,
   * StudyCards) 여기서만 벗기면 그 화면들과 어긋난다. 슬래시를 떼는 곳은
   * 낱말로 쪼개는 함수 안 한 곳뿐이다(talk-parts 의 stripSlashes).
   *
   * 낱말 수가 term 과 안 맞을 수 있다. 낱말이 하나인데 음절 단위로 띄어
   * 쓴 항목이 있고(npm 이 `/ˌen pi ˈem/`), 하이픈이 든 항목은 공백만으로
   * 세면 어긋난다(client-side routing). 그때는 강조를 포기하고 통째로
   * 그린다(talk-parts 의 alignParts).
   */
  pronunciation: string;
  /**
   * 한글 발음. 강세가 `**` 로 표시돼 있어 Reading 이 굵게 그린다.
   *
   * **빌 수 있다.** 개발 용어의 발음은 별도 명령(load_readings)으로 붓는
   * 것이라 픽스처를 안 부은 환경에서는 빈 문자열로 온다. 없으면 그 줄을
   * 안 그린다 - 본보기가 발음기호 하나로 줄어들 뿐 화면이 깨지지 않는다.
   */
  reading: string;
  /**
   * 한글 뜻.
   *
   * 무엇을 읽는지 모른 채 소리만 흉내내면 남는 것이 없다. 읽을 것 아래에
   * 작게 둔다.
   */
  meaning: string;
};

/** 채점 결과가 무엇 때문인가. */
export type TalkReason =
  /** 정답에 가깝게 읽었다. */
  | "pass"
  /** 글자는 들렸는데 정답과 다르다. */
  | "mismatch"
  /** 인식된 글자가 없다. */
  | "not_heard";

export type TalkResult = {
  /**
   * 통과인가.
   *
   * **이것을 먼저 본다.** wrong_at 만 보고 판단하면 안 된다 - 통과인데
   * wrong_at 이 null 로 오는 경우가 있다(인식기가 낱말을 쪼갠 것을
   * 살릴 때. `rest room` 이 그렇다).
   */
  ok: boolean;
  reason: TalkReason;
  /** 서버가 정규화한 인식 결과. 화면은 안 쓴다 - 아래 주석 참고. */
  heard: string[];
  /** 정답. 채점이 끝났으므로 알려준다. */
  answer: string;
  /**
   * 1등이 아닌 후보 중에 정답이 있었으면 그 값(DB 의 표기).
   *
   * "bathroom 으로 들렸어요, 혹시 restroom 을 말하셨나요" 에 쓴다. 통과
   * 판정에는 쓰지 않는다 - 후보 안에 정답이 있다는 것만으로 통과시키면
   * deploy 를 employ 로 잘못 읽은 사람도 통과한다(2등에 deploy 가 뜬다).
   * 살리려는 경우와 막아야 하는 경우가 후보 목록에서는 같은 모양이다.
   */
  near: string | null;
  /**
   * 어긋난 낱말의 자리(0부터).
   *
   * `[]` 는 어긋난 자리가 없다는 뜻이고 `null` 은 자리를 못 짚는다는
   * 뜻이다. **둘을 뭉치면 안 된다** - 통과일 때도 어긋난 자리가 없어서
   * 빈 배열이라, 하나로 합치면 "통과" 와 "실패인데 어딘지 모름" 이
   * 같아진다.
   *
   * 낱말 수가 다르면 null 이다. **통과이면서 null 인 경우도 있다** -
   * `rest room` 처럼 낱말 경계만 어긋난 것을 살릴 때가 그렇다. 그래서
   * ok 를 먼저 보고 wrong_at 은 강조에만 쓴다.
   */
  wrong_at: number[] | null;
};

/** 화면 갈래를 서버 갈래로 옮긴다. 배지에 쓴다. */
export function isDevKind(kind: ServerKind): boolean {
  return kind === "word";
}

/**
 * 읽을 것 하나를 받는다.
 *
 * exclude 로 최근에 낸 것을 뺀다. 안 빼면 같은 것이 연달아 나온다. 남는
 * 것이 없으면 서버가 404 를 주고, 화면은 "다 봤다" 로 그린다.
 */
export function fetchTalkQuestion(
  kind: TalkKind,
  options: { exclude?: number[]; token?: string } = {},
): Promise<TalkPrompt> {
  const query = buildQuery({
    // 일상 표현이 기본이라 그때는 아예 안 보낸다.
    kind: kind === "dev" ? "dev" : undefined,
    exclude: options.exclude?.length ? options.exclude.join(",") : undefined,
  });
  return request(`${BASE}question/${query}`, { token: options.token });
}

/**
 * 인식된 글자를 보내 채점한다.
 *
 * heard 가 배열인 이유: 인식기가 후보를 여러 개 준다(maxAlternatives).
 * 1등만 보내면 "제대로 읽었는데 1등이 엉뚱한 것" 을 살릴 방법이 없다 -
 * 통과 판정은 1등만 보되, 2등 이하에 정답이 있으면 안내에 쓴다.
 *
 * 빈 배열도 정상이다. 아무 말도 안 했거나 인식기가 포기한 경우이고,
 * 서버는 not_heard 로 답한다.
 */
export function gradeTalk(
  body: { token: string; heard: string[] },
  token?: string,
): Promise<TalkResult> {
  return request(`${BASE}grade/`, { method: "POST", body, token });
}
