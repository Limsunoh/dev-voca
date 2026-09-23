/**
 * 지금 문제 판에서 푼 문제 수.
 *
 * 문제풀기 화면에는 판을 끝내는 출구가 넷이다 - 홈 버튼, "한 판 풀기"
 * 링크, 분류 고르개, 단어·문장 탭. 넷 다 누르면 문제 판(QuizBoard)이
 * 사라져 푼 점수가 없어지는데, 점수는 서버에 안 남아 되돌릴 수 없다.
 * 그래서 푼 것이 있을 때만 확인을 묻는다. 한 문제도 안 푼 사람에게 매번
 * 물으면 성가시다.
 *
 * **판이 적고 출구가 읽는 값 하나를 모듈에 둔다.** 출구들은 서버가 그리는
 * 페이지 안에 흩어져 있고 판은 그 아래 있다. Context 로 묶을 수도 있지만
 * 그러려면 페이지마다 Provider 를 두르고 출구마다 구독해야 한다. 읽는 쪽이
 * 전부 클릭한 순간에만 값을 보면 되므로(다시 그릴 일이 없다) 변수 하나로
 * 충분하다. 넷 다 같은 클라이언트 번들에 있어서 같은 값을 본다.
 */
let solved = 0;

/** 판이 부른다. 푼 수가 바뀔 때마다 적는다. */
export function markSolved(count: number): void {
  solved = count;
}

/** 판이 사라질 때 부른다. 안 지우면 판이 없는 화면에서도 확인이 뜬다. */
export function clearSolved(): void {
  solved = 0;
}

/** 지금 판에서 푼 문제 수. */
export function solvedNow(): number {
  return solved;
}

/** 클릭에서 필요한 것만. 테스트가 가짜로 만들 수 있게 좁혀 둔다. */
type ClickLike = {
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
  button: number;
};

/**
 * 이 클릭에 확인을 물어야 하면 푼 문제 수, 아니면 0.
 *
 * **새 탭으로 여는 클릭은 묻지 않는다.** Ctrl·Cmd·Shift 를 누르거나 가운데
 * 버튼으로 누르면 브라우저가 새 탭·새 창에 연다. 지금 판은 그대로 남는데,
 * 여기서 막고 확인을 받아 지금 탭을 옮기면 판을 지키려고 새 탭을 연 사람이
 * 정반대 결과를 얻는다.
 */
export function solvedToConfirm(event: ClickLike): number {
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return 0;
  if (event.button !== 0) return 0;
  return solved > 0 ? solved : 0;
}

/** 확인 창 제목. 판을 끝내고 다른 문제로 옮기는 출구가 쓴다. */
export const LEAVE_TITLE = "지금 판을 끝낼까요?";

/** 잃는 것. 네 출구가 같은 말을 쓴다 - 어디로 가든 사라지는 것은 같다. */
export function leaveDetail(count: number): string {
  return `지금까지 푼 ${count}문제가 사라집니다.`;
}
