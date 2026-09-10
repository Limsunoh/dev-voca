/**
 * 형광펜 밑줄.
 *
 * 글자 아래 38% 만 칠한다. 배경 전체를 칠하면 뜻이 배지처럼 보이고, 그러면
 * 옆의 난이도·분류 칩과 같은 종류로 읽힌다. 밑줄이면 "칠해둔 문장" 이다.
 *
 * **글자색을 바꾸지 않는다.** 색만으로 강조하면 색각 이상이 있는 사람에게
 * 아무 일도 안 일어나는데, 형광펜은 위치와 면적으로도 보인다.
 *
 * 그라디언트로 만드는 이유: border-bottom 은 글자 아래 바깥에 그어져
 * 줄바꿈된 문장에서 마지막 줄에만 붙는다. 배경은 줄마다 따라간다.
 *
 * 색은 초록 하나다. 코랄 변종을 두는 API 를 만들어봤지만 아무도 안 썼고,
 * 구현체가 하나인 선택지는 다음 사람이 "언제 코랄을 쓰나" 를 고민하게만
 * 한다. 필요해지면 그때 넣는다.
 */
export function Highlight({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        // color-mix 로 토큰과 잇는다. rgb 삼원색을 손으로 옮겨 적으면
        // --green 을 바꿔도 형광펜만 옛 색으로 남는다.
        backgroundImage:
          "linear-gradient(transparent 62%, color-mix(in srgb, var(--green) 30%, transparent) 62%)",
      }}
    >
      {children}
    </span>
  );
}
