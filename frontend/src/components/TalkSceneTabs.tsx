import {
  routes,
  type TalkLevel,
  type TalkScene,
  talkScenes,
} from "@/lib/routes";

import { TalkTabRow } from "./TalkKindTabs";

/**
 * 일상 표현의 상황(인사·쇼핑·길찾기 ...)을 고르는 탭.
 *
 * 개발 용어에는 상황이 없어서 페이지가 일상 표현일 때만 그린다. 난이도
 * 탭과 달리 갈래를 받지 않는 이유가 그것이다 - 이 줄의 링크는 늘 일상
 * 표현으로 간다.
 *
 * "전체" 를 맨 앞에 둔다. Admin 에서 상황을 비운 채 검수를 통과한 표현은
 * 어느 상황 탭에서도 안 나오고 전체에서만 나온다(679a205).
 *
 * 여섯 개라 폰 폭(390)에서 한 줄에 안 들어가 줄을 바꾼다(TalkTabRow 의
 * wrap). 가로로 밀어 보게 두면 뒤쪽 셋이 화면 밖에 숨어, 그런 상황이 있는
 * 줄 모른다.
 */
export function TalkSceneTabs({
  level,
  current,
}: {
  /** 지금 고른 난이도. 상황을 바꿔도 들고 간다(갈래 탭과 같은 이유). */
  level: TalkLevel;
  current: TalkScene;
}) {
  return (
    <TalkTabRow
      label="상황"
      wrap
      items={SCENES.map((scene) => ({
        key: scene.value || "all",
        href: routes.talk("daily", level, scene.value),
        label: scene.label,
        active: scene.value === current,
      }))}
    />
  );
}

/**
 * 상황 이름. 서버 PhraseScene 의 이름과 같게 둔다 - 카드 위 배지는 서버가
 * 보낸 이름(scene_label)을 그리므로, 여기서 다른 말을 쓰면 "쇼핑" 을
 * 골랐는데 카드에는 "쇼핑·주문" 이 뜬다(TalkLevelTabs 의 LEVELS 와 같은 규칙).
 *
 * Record 로 두는 이유: talkScenes 에 값이 늘면 여기 이름이 없다는 것을
 * 타입 검사가 알려준다.
 */
const SCENE_LABELS: Record<(typeof talkScenes)[number], string> = {
  greeting: "인사·소개",
  shopping: "쇼핑·주문",
  asking: "묻기·길찾기",
  trouble: "곤란할 때",
  smalltalk: "가벼운 대화",
};

const SCENES: { value: TalkScene; label: string }[] = [
  { value: "", label: "전체" },
  ...talkScenes.map((value) => ({ value, label: SCENE_LABELS[value] })),
];
