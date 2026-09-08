/**
 * 채점 뒤 사람이 걸어와 반응하고 가는 연출.
 *
 * 맞히면 따봉을 날리고, 틀리면 뒤통수를 한 대 치고 간다. 폭죽(Burst)과
 * 흔들림만 있을 때는 "맞았다/틀렸다" 가 색과 글자로만 오는데, 사람이
 * 오면 한 판을 오래 풀어도 매번 다른 것이 일어나는 느낌이 남는다.
 *
 * **여기가 Lottie 로 갈아끼울 자리다.** 지금은 SVG 를 CSS 키프레임으로
 * 움직인다 - 런타임 의존성이 셋뿐인 상태를 유지하려고 그렇게 했다
 * (skills/devvoca-design/SKILL.md 의 "의존성은 셋에서 늘리지 않는 걸
 * 기본으로"). 나중에 애니메이션 .json 을 구하면 아래 <Figure /> 를 Lottie
 * 플레이어로 바꾼다. 바깥(QuizBoard)이 보는 것은 fire 와 correct 두 값뿐이라
 * **호출부는 안 건드려도 된다.**
 *
 * 다만 이 파일만으로 안 끝난다. globals.css 의 .rx-leg-*·.rx-arm-* 과
 * step-a/step-b/raise-thumb/swing-hand 키프레임이 Figure 가 그리는 SVG
 * 노드에 직접 붙어 있어서, Lottie 로 바꾸면 그것들이 통째로 죽은 코드가
 * 된다. 다른 파일이라 안 지우고 남기 쉬우니 그때 같이 걷어낸다.
 *
 * 그때 dynamic import 로 문제풀기 화면에서만 받게 한다. 통째로 번들에
 * 넣으면 홈·단어장에서도 250KB 를 받는데, 거기서는 쓰지 않는다.
 *
 * fire 를 세는 이유는 Burst 와 같다. boolean 이면 연속 정답에서 두
 * 번째부터 안 뛴다 - 이미 true 라 값이 안 바뀐다.
 *
 * 'use client' 가 없다. 상태도 이벤트도 없이 받은 값으로 클래스만 붙인다.
 *
 * **끝난 뒤에도 DOM 에 남는다.** animation-fill-mode: both 라 마지막 프레임
 * (opacity 0)에 멈춰 있고, 다음 채점에서 key 가 바뀌며 교체된다. 타이머로
 * 지우면 상태와 정리가 늘어나는데, 안 보이는 SVG 하나가 남는 비용보다
 * 그쪽이 크다 - Burst 도 같은 판단이다.
 */

type Props = {
  /** 재생 횟수. 채점할 때마다 1 씩 올린다. 0 이면 아무것도 안 그린다. */
  fire: number;
  /** 맞혔는가. 따봉과 뒤통수를 가른다. */
  correct: boolean;
};

export function Reaction({ fire, correct }: Props) {
  if (fire === 0) return null;

  return (
    // key 로 횟수를 넘겨 매번 새로 마운트시킨다. 클래스만 토글하면
    // 연속으로 맞혔을 때 두 번째부터 애니메이션이 안 뛴다.
    //
    // fixed 이유: 문제 위치와 무관하게 화면 아래에서 걸어와야 한다.
    // 지문 길이에 따라 자리가 밀리면 어디서 나타날지 예측이 안 된다.
    //
    // pointer-events-none 은 필수다. 이 층이 보기 버튼 위를 지나가는데,
    // 없으면 걸어오는 0.6초 동안 답을 못 고른다.
    <div
      key={fire}
      aria-hidden
      // bottom-0 인 이유: bottom-24 는 해설 카드 한가운데라 예문 글자를
      // 가렸다. 화면 맨 아래에 세우면 "다음 문제" 버튼 옆을 지나가는
      // 모양이 되어 읽는 것을 안 막는다.
      // 가운데를 비운다. "다음 문제" 버튼 글자가 거기 있어서, 가운데에
      // 세우면 몸통이 글자를 가린다. 온 방향 쪽에 서게 두면 버튼도 안
      // 가리고 걸어온 궤적도 자연스럽다.
      // z-40 은 본문 위·나가기 장막(z-50) 아래다. **탭바(z-20)와 같은
      // bottom-0 앵커라 그 위를 덮는다** - 지금 문제풀이 화면에는 탭바가
      // 없어서(immersiveRoutes) 안 드러나지만, 탭바 있는 화면에서 쓰면
      // 사람이 탭바를 밟고 지나간다.
      //
      // overflow-hidden 은 화면 밖에서 출발하는 것(±160px)이 가로 스크롤을
      // 만들지 않게 자른다. 아래쪽 그림자는 SVG 자체의 viewBox 하단 여백이
      // 받아준다 - 다리 끝이 y=88 이고 뷰박스가 96 이라 10px 남는다.
      // pb-2 는 그 위에 얹는 여유지 그림자를 지키는 값이 아니다.
      className={`pointer-events-none fixed inset-x-0 bottom-0 z-40 flex overflow-hidden pb-2 ${
        correct ? "justify-start pl-6" : "justify-end pr-6"
      }`}
    >
      <div className={correct ? "rx-praise" : "rx-smack"}>
        <Figure correct={correct} />
      </div>
    </div>
  );
}

/**
 * 사람 하나. 이 함수만 Lottie 로 바꾸면 된다.
 *
 * 스틱피겨인 것은 의존성을 안 늘리려는 타협이다. 얼굴을 그리지 않는
 * 이유는 둘이다 - 작게 그리면 뭉개져서 표정이 안 보이고, 특정 인물처럼
 * 보이면 그 사람을 아는 사용자에게 다른 뜻이 된다.
 *
 * 색은 판정에 맞춘다. 맞히면 emerald, 틀리면 rose - 보기 버튼의 정답·오답
 * 테두리와 같은 색이라 무엇 때문에 온 사람인지가 색으로 먼저 온다.
 */
function Figure({ correct }: { correct: boolean }) {
  const stroke = correct ? "#6ee7b7" : "#fda4af";

  return (
    <svg
      width="96"
      height="128"
      viewBox="0 0 72 96"
      fill="none"
      stroke={stroke}
      strokeWidth="4"
      strokeLinecap="round"
      strokeLinejoin="round"
      // 어두운 배경에서 가는 선이 묻힌다. 검은 그림자를 깔아 띄운다 -
      // 배경이 어떤 카드 위든 실루엣이 읽힌다.
      style={{ filter: "drop-shadow(0 2px 6px rgb(0 0 0 / 0.6))" }}
    >
      {/* 머리 */}
      <circle cx="36" cy="16" r="11" />
      {/* 몸통 */}
      <line x1="36" y1="27" x2="36" y2="60" />
      {/* 다리. 걷는 동안 CSS 가 번갈아 흔든다. */}
      <g className="rx-leg-a">
        <line x1="36" y1="60" x2="26" y2="88" />
      </g>
      <g className="rx-leg-b">
        <line x1="36" y1="60" x2="46" y2="88" />
      </g>
      {/* 왼팔은 그냥 흔들리고 오른팔이 동작을 한다. */}
      <line x1="36" y1="36" x2="22" y2="52" className="rx-arm-idle" />
      <g className="rx-arm-act">
        {correct ? (
          // 따봉. 팔을 들고 주먹에서 엄지가 위로 선다.
          <>
            <line x1="36" y1="36" x2="52" y2="26" />
            <circle cx="55" cy="24" r="5" fill={stroke} stroke="none" />
            <line x1="55" y1="19" x2="55" y2="11" strokeWidth="4" />
          </>
        ) : (
          // 손바닥. 화면 쪽(보는 사람 뒤통수)을 향해 아래로 내려친다 -
          // 옆으로 뻗으면 허공을 치는 것으로 보인다.
          <>
            <line x1="36" y1="36" x2="56" y2="48" />
            <circle cx="59" cy="50" r="6" fill={stroke} stroke="none" />
          </>
        )}
      </g>
    </svg>
  );
}
