"use client";

import { useEffect, useRef } from "react";

/**
 * 새 문제가 뜨면 초점을 문제로 옮긴다. 돌려준 ref 를 QuestionCard 의 cardRef
 * 로 넘긴다. 카드 없이 그리는 문제풀기(QuizBoard)는 안내문과 지문을 감싼 곳에
 * 붙인다. 어느 쪽이든 바로 다음 요소가 보기 목록이어야 한다.
 *
 * 방금 누른 보기는 잠기거나 문제와 함께 사라져서, 그대로 두면 초점이 문서
 * 전체(body)로 떨어지고 키보드로 풀던 사람은 문제마다 맨 위에서 다시 Tab 을
 * 눌러야 한다. 채점이 실패해 문제가 그대로일 때도 보기가 잠겼다 풀리며 초점을
 * 잃으므로 error 가 바뀔 때도 돈다.
 *
 * 첫 보기가 아니라 카드로 옮긴다. 보기로 옮기면 Enter 를 길게 눌렀을 때 다음
 * 문제의 첫 보기가 답으로 나가고, 화면 낭독기도 문제를 건너뛰고 보기부터
 * 읽는다. 대신 답하려면 Tab 을 한 번 눌러야 한다.
 *
 * 화면 낭독기에서 이 이동이 위 결과 줄(polite)의 안내나 채점 실패 문구
 * (role="alert")를 끊을 수 있다. DailyStudyBoard 의 autoFocus 와 같은 위험인데,
 * 결과와 다음 문제가 같이 뜨는 일일공부·복습에서는 문제마다 일어난다(한 판은
 * 연출을 기다리는 동안 결과가 먼저 나간다). 실제 낭독기로는 확인하지 않았다.
 */
export function useFocusNewQuestion(question: unknown, error: string | null) {
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 새로고침이나 주소로 바로 열어 아직 아무것도 안 눌렀으면 옮기지 않는다.
    // 일일공부는 풀던 문제부터 열릴 수 있어 초점을 가로채게 된다. 앱 안 링크로
    // 들어온 경우는 누른 링크가 사라져 초점을 잃었으므로 옮기는 것이 맞다.
    // 이 값이 없는 옛 브라우저는 안 옮기는 쪽으로 떨어져 지금까지와 같다.
    if (!navigator.userActivation?.hasBeenActive) return;

    const card = cardRef.current;
    const focused = document.activeElement;
    // 초점이 보기 밖(나가기 버튼 등)에 서 있으면 뺏지 않는다. 카드 바로
    // 다음 요소가 보기 목록이다. 보기 번호가 다음 문제에도 나오면 React 가
    // 그 버튼을 다시 쓰므로 초점이 목록 안에 남아 있을 수 있다. 잠긴 버튼에
    // 초점을 남겨 두는 브라우저도 있어 잠긴 것은 초점이 없는 것으로 본다.
    if (
      focused &&
      focused !== document.body &&
      !focused.matches(":disabled") &&
      !card?.nextElementSibling?.contains(focused)
    ) {
      return;
    }
    // preventScroll: 보기를 누르려고 내려온 화면을 위로 끌어올리지 않는다.
    // 마우스로 푸는 사람에게 포커스 링이 뜨지는 않는다(focus-visible 만 쓴다).
    card?.focus({ preventScroll: true });
  }, [question, error]);

  return cardRef;
}
