/**
 * 필터를 접어두는 상자.
 *
 * 접는 이유: 단어장은 난이도 4 + 분류 9 라 폰 폭(390)에서 필터가 다섯 줄을
 * 먹었다. 문장은 종류까지 있어 더 길다. 목록을 보러 들어온 화면인데 첫
 * 카드가 화면 끝에 걸쳐 있어서, 단어를 보려면 매번 스크롤부터 해야 했다.
 *
 * `<details>` 를 쓴 이유는 이 화면이 서버 컴포넌트이기 때문이다. useState 로
 * 접으면 이 파일에 "use client" 가 붙고, 그러면 필터 줄 전체가 클라이언트
 * 번들로 딸려 간다. `<details>` 는 브라우저가 여는 것이라 자바스크립트가
 * 꺼져 있어도 열리고, 필터가 링크라는 성질(URL 에 상태가 남아 뒤로가기·공유가
 * 되는 것)도 그대로 둔다.
 *
 * **`open` 은 React 에 넘기지 않는다.** 조건에 따라 켜고 끄면 안 된다.
 * 이유가 덫이라 적어둔다.
 *
 * 필터는 링크라 칩을 누르면 이 컴포넌트가 다시 렌더된다. 그때 `open` 을
 * `activeCount > 0` 처럼 계산하면 **값이 바뀌는 렌더에서 React 가 DOM 의
 * open 을 지운다** - controlled 요소가 아니라 평범한 boolean 속성이라
 * `removeAttribute("open")` 을 할 뿐, 사용자가 손으로 펴 뒀는지는 안 본다.
 * 조건을 하나씩 끄다가 마지막 하나를 끄는 순간이 그 자리다.
 *
 * `key` 로 다시 마운트시키는 우회는 안 통한다. 같은 화면 안에서는 key 가
 * 안 바뀌고, 바뀌게 만들면 이번엔 칩을 누를 때마다 접힌다.
 *
 * 그래서 아예 안 넘긴다. 여닫기는 통째로 브라우저와 사용자 몫이다.
 * 대가로 조건이 걸린 링크로 들어와도 접혀 있는데, 그건 배지가 알려준다.
 */
export function FilterPanel({
  /**
   * 지금 걸려 있는 조건들. 값이 있는 것만 세어 배지에 띄운다.
   *
   * 개수가 아니라 값을 그대로 받는 이유: 세는 자리가 호출부에 있으면
   * 필터를 하나 더 붙일 때 거기도 같이 고쳐야 하는데, 안 고쳐도 아무
   * 에러가 안 나고 배지 숫자만 조용히 틀린다. 검색어는 넘기지 않는다 -
   * 검색창이 패널 밖에 따로 있어서 무엇으로 찾는 중인지 이미 보인다.
   */
  active,
  children,
}: {
  active: (string | undefined)[];
  children: React.ReactNode;
}) {
  const activeCount = active.filter(Boolean).length;

  return (
    <details className="group mt-4">
      <summary
        // list-none 과 ::-webkit-details-marker 를 같이 지운다. 사파리는
        // 아직 후자만 본다. 안 지우면 알약 왼쪽에 기본 삼각형이 하나 더 붙는다.
        //
        // 높이는 min-h-11(44px)로 직접 잡는다. 상세 화면의 "발음 자세히"
        // (learn/words/[id]/page.tsx)가 쓰는 것과 같은 방식이다. 칩들이
        // 쓰는 after 히트영역은 옆에 이웃이 있어 알약을 못 키울 때 쓰는
        // 우회책인데, 이 summary 는 한 줄을 혼자 쓰므로 그냥 키우면 된다.
        //
        // 필터 칩과 같은 흰 알약 + 두께다. 이 summary 는 바로 아래에 그 칩들을
        // 여는 것이라, 다른 문법으로 두면 둘이 관계없는 것처럼 보인다.
        className="dv-card dv-card-press flex min-h-11 w-fit cursor-pointer list-none items-center gap-2 rounded-full px-3.5 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus [&::-webkit-details-marker]:hidden"
        style={
          {
            background: "var(--paper)",
            color: "var(--foreground)",
            // 쉬는 두께는 --lift 로. 인라인 box-shadow 는 :active 를 이긴다.
            "--lift": "var(--lift-card)",
            fontWeight: "var(--weight-bold)",
          } as React.CSSProperties
        }
      >
        필터
        {/* 접혀 있어도 조건이 걸렸다는 걸 알려주는 유일한 신호다. 0 일 때는
            아예 안 그린다 - "필터 0" 은 아무 조건도 없다는 뜻인데 배지가
            붙어 있으면 뭔가 걸린 것처럼 보인다. */}
        {activeCount > 0 && (
          <span
            className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full px-1.5 text-[length:var(--text-11)]"
            style={{
              background: "var(--coral)",
              color: "var(--text-on-color)",
              fontWeight: "var(--weight-black)",
            }}
          >
            {activeCount}
            {/* 숫자만 두면 음성으로는 "필터 2" 가 무엇의 2 인지 알 수 없다.
                페이지 번호로도 들린다. 화면에서는 알약 안의 강조색 배지라
                개수로 읽히지만 그 단서가 소리에는 없다. */}
            <span className="sr-only">개 적용됨</span>
          </span>
        )}
        {/* 삼각형은 CSS 로 돌린다. 열림 상태에 따라 아이콘을 갈아끼우면
            details 의 열림을 다시 읽어야 하는데, 그건 클라이언트 몫이다.
            aria-hidden 인 이유: summary 자체가 이미 "확장/축소" 로 읽힌다. */}
        <span
          aria-hidden
          className="text-[0.625rem] transition-transform duration-150 group-open:rotate-180"
          style={{ color: "var(--text-faint)" }}
        >
          ▼
        </span>
      </summary>

      {/* 칩 줄들이 여기 들어온다. 상자로 감싸 목록과 구분한다 - 안 감싸면
          펼쳤을 때 칩이 카드 위에 그냥 얹혀 어디까지가 필터인지 흐릿하다.

          첫 줄의 위 여백은 여기서 지운다. 필터 줄들은 자기 위에 mt-4 를
          갖고 있는데 첫 줄에서는 상자의 p-3 과 겹쳐 위만 두꺼워진다.
          호출부에서 "첫 자식만 끄기" 로 넘기지 않는 이유: 필터 줄은 자기
          선택지가 비면 null 을 반환하고(ChoiceFilter.tsx), 선택지는 API 가
          실패하면 조용히 빈 배열이 된다(lib/api/client.ts 의 fetchChoices).
          즉 백엔드 부분 장애에서 첫 자식이 사라져 표시가 엉뚱한 줄에 붙는다.
          :first-child 는 DOM 기준이라 그때도 살아남은 첫 줄을 맞춘다. */}
      {/* 펼친 칩들을 옅은 띠 위에 앉힌다. 흰 종이로 두면 그 위의 흰 칩이
          안 보이고, 두께를 주면 칩마다 있는 두께와 겹쳐 층이 둘이 된다.
          띠(--background-deep)는 그림자 없이 면으로만 구분하는 자리다
          (번들 core/Card.jsx 의 tone="sand" 와 같은 문법). */}
      <div
        className="mt-3 p-3 [&>*:first-child]:mt-0"
        style={{
          background: "var(--background-deep)",
          borderRadius: "var(--radius-2xl)",
        }}
      >
        {children}
      </div>
    </details>
  );
}
