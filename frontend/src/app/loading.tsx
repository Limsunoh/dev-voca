/**
 * 화면을 그리는 동안 보여 주는 대기 화면.
 *
 * 이 파일이 없으면 탭을 눌러도 서버가 다음 화면을 다 그릴 때까지 이전 화면이
 * 그대로 멈춰 있다. 브라우저에서는 주소창의 로딩 표시라도 돌지만, 앱(TWA)은
 * 주소창이 없어서 아무 신호도 없다. 사용자는 "앱이 멈췄다" 로 읽는다.
 *
 * 루트의 이 파일은 첫 경로가 바뀌는 이동(탭 사이, `/` 에서 `/learn` 으로)에만
 * 뜬다. 대기 화면은 바로 아래 경로 조각이 바뀔 때만 다시 보이고, 같은 조각
 * 안의 이동(`/learn/words` 에서 `/learn/words/12` 로)은 React 가 옛 화면을
 * 붙든다(Next 의 layout-router 가 경로 조각을 key 로 쓴다). 그래서 그런
 * 이동이 있는 폴더(`learn`, `learn/words`, `learn/sentences`, `test/(hub)`,
 * `test/daily`, `test/review`, `board`)에 이 파일을 다시 내보내는 한 줄짜리 loading.tsx 를
 * 둔다. 폴더를 새로 만들어 그 안에서 옮겨 다니게 되면 거기에도 둔다. 쿼리만
 * 바뀌는 이동(페이지 넘김, 필터)은 key 가 그대로라 어디에 두어도 안 뜬다.
 *
 * `test` 폴더와 몰입 화면 폴더(`test/round`, `test/words`, `test/sentences`,
 * lib/routes.ts 의 immersiveRoutes)에는 두지 않는다. 거기 두면 허브에서 문제
 * 화면으로 갈 때 대기 화면이 먼저 확정되고, test layout 의 진입 장막
 * (EnterVeil)이 문제 화면이 아니라 아직 투명한 대기 화면 위에서 끝나 버린다.
 * 몰입 화면이라 그동안 탭바도 나가기 버튼도 없다. 그래서 탭바가 있고 장막이 안
 * 도는 일일공부·복습에만 따로 둔다(허브에서 들어올 때 뜬다).
 *
 * 허브(/test)는 `test/(hub)` 묶음에 넣고 거기에 둔다. 괄호 폴더는 주소에 안
 * 나타나서 /test 는 그대로다. 문제 화면에서 나가 허브로 돌아올 때 대기 화면이
 * 뜨게 하려는 것이다. 이게 없으면 나가기 버튼이 덮은 막(ExitGuard)이 허브가 다
 * 그려질 때까지 남아 빈 화면처럼 보인다. 묶음 안에 두었으므로 반대 방향(허브에서
 * 문제 화면으로)에는 걸리지 않아 위 진입 장막이 그대로 돈다.
 *
 * 루트 layout 이 쿠키를 읽지 않아서 위 경계들이 막히지 않는다(Next 문서
 * loading.js: layout 이 런타임 데이터를 읽으면 그 아래로는 대기 화면이 안
 * 뜬다). 탭바는 layout 에 있으므로 기다리는 동안에도 남아 다른 탭으로 옮겨 갈
 * 수 있다. 예외가 하나 있다. 단어 상세의 "문제로 풀기" 나 순위표처럼 탭 밖에서
 * 문제 화면으로 바로 가면 이 루트 대기 화면이 뜨는데, 주소가 몰입 화면으로 바뀌는
 * 순간 탭바가 숨어 나가는 버튼이 없다. 읽기 10초 한도(lib/api/client.ts)에
 * 걸리면 홈 버튼이 있는 test/error.tsx 로 바뀌고 폰의 뒤로 가기도 되므로 그대로
 * 둔다.
 *
 * 300ms 뒤에 나타난다. 빠른 이동에서 대기 화면이 번쩍 떴다 사라지면 오히려
 * 느려 보인다. rise 는 animation-fill-mode: both 라 기다리는 동안 투명하게
 * 남는다. 움직임을 줄인 사용자는 globals.css 가 delay 를 0 으로 만들어 바로
 * 보인다.
 *
 * 점의 깜빡임은 움직임을 줄인 사용자에게 끈다(motion-reduce:animate-none).
 * globals.css 는 반복 애니메이션의 길이만 0.01ms 로 줄이고 반복은 그대로 두어,
 * 그대로 두면 프레임마다 불투명도가 튄다(같은 파일 prefers-reduced-motion 블록
 * 주석). 그래서 상태는 점이 아니라 "불러오는 중" 글자가 알린다.
 *
 * role="status" 는 main 이 아니라 글자에 둔다. main 에 두면 본문 랜드마크를
 * 덮어쓴다.
 */
export default function Loading() {
  return (
    <main className="rise mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center px-4 py-10 text-center [animation-delay:300ms]">
      <div className="flex gap-2" aria-hidden="true">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            className="block size-2.5 animate-pulse rounded-full motion-reduce:animate-none"
            style={{ background: "var(--brand)", animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
      <p
        className="mt-4"
        role="status"
        aria-live="polite"
        style={{
          color: "var(--text-muted)",
          fontWeight: "var(--weight-bold)",
        }}
      >
        불러오는 중입니다
      </p>
    </main>
  );
}
