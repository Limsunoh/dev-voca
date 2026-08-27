import "server-only";

import {
  type StudyCard,
  interleave,
  widestPlan,
} from "@/lib/study-plan";

import { newShuffleSeed } from "./client";
import { getSentences } from "./sentences";
import { getWords } from "./vocab";

/**
 * 일일공부 앞에 붙는 공부 단계의 카드를 가져온다.
 *
 * **아직 전용 API 가 없다.** 백엔드의 일일공부는 길이를 받아 문제만 내주고,
 * 그 문제(RoundQuestion)에는 뜻도 예문도 없다 - 보기 넷과 정답뿐이라
 * 훑어볼 거리가 못 된다. 그래서 이미 있는 목록 API 둘을 섞어서 만든다.
 *
 * 전용 엔드포인트(GET /daily/deck/)가 생기면 바뀌는 것은 아래 함수 본문
 * 하나다. 타입(StudyCard)과 구성 규칙(planFor)을 lib/study-plan.ts 에
 * 따로 둔 이유가 그것이다 - 화면은 그쪽만 보므로 여기가 바뀌어도 안 바뀐다.
 *
 * **이 모듈은 서버에서만 부른다.** 맨 위의 "server-only" 가 그 방어선이다.
 * 주석만으로는 못 막는다 - 클라이언트 컴포넌트가 여기서 값 하나만 꺼내
 * 가도 백엔드 주소를 아는 api/client.ts 까지 브라우저 번들로 끌려온다.
 * (lib/session.ts 가 같은 방어선을 쓴다.)
 */
export async function fetchStudyDeck(): Promise<StudyCard[]> {
  // 가장 긴 구성만큼 받아둔다. 길이를 고르기 전에 미리 받아야 판이 열린
  // 직후에 빈 화면으로 기다리지 않는다. 짧은 길이는 planFor 가 자른다.
  const most = widestPlan();

  // 시드를 주지 않으면 목록이 가나다순으로 와서 늘 같은 앞부분만 본다.
  const seed = newShuffleSeed();

  const [words, sentences] = await Promise.all([
    getWords({ shuffle: seed }).catch(() => null),
    getSentences({ shuffle: seed }).catch(() => null),
  ]);

  const wordCards: StudyCard[] = (words?.results ?? [])
    .slice(0, most.words)
    .map((word) => ({
      id: `w-${word.id}`,
      kind: "word" as const,
      term: word.term,
      reading: word.pronunciation,
      meaning: word.meaning,
      // 목록 API 는 예문을 안 준다(상세에만 있다). 카드마다 상세를
      // 한 번씩 더 부르면 5분짜리에 여섯 번이 붙어서, 뒷면 둘째 줄을
      // 비운다. 전용 API 가 생기면 예문이 같이 온다.
      note: "",
      label: word.category_label,
      href: `/learn/words/${word.id}`,
    }));

  const sentenceCards: StudyCard[] = (sentences?.results ?? [])
    .slice(0, most.sentences)
    .map((sentence) => ({
      id: `s-${sentence.id}`,
      kind: "sentence" as const,
      term: sentence.text,
      reading: "",
      meaning: sentence.translation,
      note: sentence.context,
      label: sentence.kind_label,
      href: `/learn/sentences/${sentence.id}`,
    }));

  return interleave(wordCards, sentenceCards);
}
