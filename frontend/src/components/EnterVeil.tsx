/**
 * 화면에 들어올 때 아래로 빠지는 장막.
 *
 * 문제풀이는 탭바가 없는 별도 화면이다(TabBar 의 return null 참고). 앱에서
 * 전체 화면이 열릴 때 아래에서 올라오는 그 동작을 흉내내서, 돌아가려면
 * 나가기를 눌러야 한다는 것을 설명 없이 전달한다.
 *
 * **layout.tsx 에 둔다. ExitGuard 안에도, page.tsx 에도 두지 않는다.**
 *
 * 나가기 버튼과 한 몸으로 묶었더니 한 판에서 화면이 네 번 가려졌다.
 * RoundBoard 는 단계마다(시작 전 / 푸는 중 / 결과) ExitGuard 를 다른 JSX
 * 자리에 그리는데, React 는 그것을 같은 요소로 보지 않아 단계가 바뀔 때마다
 * 언마운트하고 새로 마운트한다. 그때마다 장막이 처음부터 다시 떨어졌다 -
 * "시작" 을 누른 직후 첫 문제가 260ms 동안 안 보였고, 90초는 이미 흐르고
 * 있었다. 시간제한이 걸린 화면에서 그건 미관이 아니라 점수 손실이다.
 *
 * page.tsx 도 아닌 이유: page 는 같은 세그먼트 안에서 이동할 때 교체된다.
 * 유지되는 것은 layout 쪽이다. page 에 두면 문제풀이 안에서 모드를 바꿀
 * 때마다 장막이 다시 돈다.
 *
 * 서버 컴포넌트다. 상태도 이벤트도 없이 클래스 하나만 붙이므로 클라이언트로
 * 내려보낼 이유가 없다.
 */
export function EnterVeil() {
  return (
    // fill-mode 가 both 라 끝난 뒤에는 화면 아래(translateY 100%)에 붙어
    // 있는다. pointer-events-none 이 없으면 그 상태로 아래쪽 터치를 먹는다.
    //
    // z-50 은 대화상자보다 낮아도 된다. dialog 는 showModal() 로 열면
    // top layer 에 올라가 z-index 와 무관하게 항상 위다.
    <div
      aria-hidden
      className="enter-veil pointer-events-none fixed inset-0 z-50 bg-background"
    />
  );
}
