/**
 * 맞혔을 때 터지는 조각들.
 *
 * 오답에 흔들림이 있듯 정답에도 반응을 둔다. 틀린 것만 몸으로 오고 맞힌
 * 것은 글자로만 오면 계속 풀 이유가 약해진다.
 *
 * fire 를 세면 그때마다 다시 터진다. boolean 으로 두면 연속 정답에서 두
 * 번째부터 안 터진다 - 이미 true 라 값이 안 바뀌기 때문이다. 오답 흔들림이
 * shake 카운터를 쓰는 것과 같은 이유다.
 *
 * 조각의 방향은 미리 계산해 고정한다. 매번 난수를 뽑으면 서버가 그린 것과
 * 클라이언트가 그린 것이 달라져 hydration 이 어긋난다.
 *
 * 'use client' 가 없다. 상태도 이벤트도 없이 받은 숫자로 클래스만 붙이므로
 * 클라이언트 번들에 넣을 이유가 없다. 지금은 클라이언트 컴포넌트에서만
 * 불리지만 그건 호출부 사정이다.
 */

/** 조각 하나의 날아갈 방향·거리·회전. */
type Piece = {
  x: string;
  y: string;
  rot: string;
  delay: string;
  color: string;
  size: string;
};

// 열여섯 조각. 이보다 적으면 "터졌다" 가 아니라 "몇 개 튀었다" 로 보이고,
// 많으면 문제 글자를 가린다.
//
// 원 둘레에 고르게 놓지 않고 각도를 살짝 흩뜨린다. 정확히 30도씩 벌리면
// 눈이 그 규칙을 읽어내서 폭죽이 아니라 도형으로 보인다.
const PIECES: Piece[] = Array.from({ length: 16 }, (_, i) => {
  // 황금각(137.5도)으로 돌린다. 어떤 개수에서도 뭉치지 않고 고르게 퍼지는
  // 각도다 - 해바라기 씨가 이 규칙으로 배열된다.
  const angle = (i * 137.5 * Math.PI) / 180;
  // 거리를 두 겹으로 둔다. 다 같은 거리로 날아가면 원형 테두리가 그려져
  // 폭죽이 아니라 고리로 보인다.
  const dist = i % 2 === 0 ? 132 : 84;

  return {
    x: `${Math.round(Math.cos(angle) * dist)}px`,
    y: `${Math.round(Math.sin(angle) * dist)}px`,
    rot: `${(i % 2 === 0 ? 1 : -1) * (120 + i * 17)}deg`,
    // 아주 짧은 시차. 전부 동시에 나가면 한 덩이가 부풀었다 꺼지는 것처럼
    // 보인다. 40ms 를 넘기면 이제 터지는 게 아니라 하나씩 튀어나온다.
    delay: `${(i % 4) * 12}ms`,
    // 세 색을 돌려 쓴다. 한 색이면 그림자로 보이고, 색이 너무 많으면 파티
    // 장식이 된다. 토큰으로 받는 이유는 크림 바탕에서 색을 다시 고를 때
    // 이 파일이 아니라 globals.css 한 곳만 고치면 되게 하려는 것이다.
    color: `var(--confetti-${(i % 3) + 1})`,
    // 10px/7px 이면 390px 폭 화면에서 "터졌다" 가 아니라 "먼지가
    // 뿌려졌다" 로 보인다. 조각 하나가 글자 한 자만 해야 눈에 걸린다.
    size: i % 2 === 0 ? "18px" : "13px",
  };
});

export function Burst({
  fire,
  atReveal = false,
}: {
  fire: number;
  /**
   * 판정이 드러나는 순간(채점 연출의 66%)에 연출 층 위에서 터진다.
   *
   * 화면을 어둡게 까는 채점 연출(Reaction 의 dim)과 같이 쓰는 화면이 켠다.
   * 끄면 조각이 연출 층(z-40) 아래에서 바로 터져, 화면 가운데의 불투명한
   * 원형 무대(지름 300px)에 전부 가려진다. 조각은 가운데서 132px 까지만
   * 날아가기 때문이다. 그렇다고 바로 위로 올리면 "66% 전에는 결과를
   * 모른다" 는 연출의 요점을 축포가 먼저 깨뜨린다.
   *
   * 연출 길이가 0 이면(한 판에서 서버가 멈추지 않을 때) 축포도 안 보인다.
   * 연출이 안 도는 판에서는 축포도 같이 쉰다.
   */
  atReveal?: boolean;
}) {
  // 아직 한 번도 안 맞혔으면 아무것도 안 그린다.
  //
  // 다 터진 뒤 DOM 에서 빼는 장치는 두지 않는다. 상태와 타이머로 700ms
  // 뒤에 지워도 막아 주는 것이 없다. 조각은 pointer-events-none 이라 아래
  // 버튼을 가리지 않고, aria-hidden 이라 낭독에도 안 걸린다. 다음 정답이
  // 오면 key 가 바뀌어 전부 새로 그려지므로 열여섯 개를 넘겨 쌓이지도
  // 않는다. 상태 하나와 타이머 하나를 판마다 수십 번 돌리는 비용이 더 크다.
  if (fire === 0) return null;

  return (
    // 화면 가운데에 고정한다. 문제 영역 안에 두면 문제 길이에 따라 터지는
    // 자리가 위아래로 움직여서, 어디를 볼지 매번 달라진다.
    //
    // aria-hidden: 화면 낭독기에는 이미 채점 결과가 글자로 전달된다. 여기서
    // 또 알리면 같은 말이 두 번 나온다.
    <div
      aria-hidden
      key={fire}
      // z-10 은 본문 위, 탭바(z-20) 아래다.
      // 탭바보다 위에 두면 조각이 탭바를 가로지른다. 일일공부·복습처럼
      // 탭바 있는 화면이 이 값을 쓴다. 조각이 본문 위를 지나가는 데는 z-10
      // 이면 충분하다. atReveal 은 연출 층(z-40) 위, 나가기 장막(z-50)
      // 아래다. 그 화면들(문제풀기·한 판)에는 탭바가 없다.
      className={`pointer-events-none fixed inset-0 flex items-center justify-center ${
        atReveal ? "z-[45]" : "z-10"
      }`}
      // 기다리는 시간과 터지는 길이를 연출 길이에서 구한다. 한 판은 서버
      // 값으로 --duration-verdict 를 덮어써서(RoundBoard) 숫자로 들고 있으면
      // 갈린다. 0.66 은 무대가 판정색으로 넘어가는 정지점(globals.css 의
      // vx-spot)과 같은 값이다.
      //
      // 길이는 연출이 끝나기 전에 조각이 다 사라지도록 잡는다. 연출 1000ms
      // 기준으로 660 + 300 에 조각별 시차(최대 36ms)를 더해도 1000ms 안이라,
      // 한 판에서 다음 문제가 뜰 때는 이미 없다. 더 길게 잡으면 조각이 새 문제 글자 위에
      // 불투명하게 남는다.
      style={
        atReveal
          ? ({
              "--burst-wait": "calc(var(--duration-verdict) * 0.66)",
              "--burst-duration": "calc(var(--duration-verdict) * 0.3)",
            } as React.CSSProperties)
          : undefined
      }
    >
      <div className="relative">
        {PIECES.map((p, i) => (
          <span
            key={i}
            className="burst-piece absolute rounded-[2px]"
            style={
              {
                "--burst-x": p.x,
                "--burst-y": p.y,
                "--burst-rot": p.rot,
                animationDelay: `calc(var(--burst-wait, 0ms) + ${p.delay})`,
                background: p.color,
                width: p.size,
                height: p.size,
                // absolute 의 기준점이 왼쪽 위라 조각 크기의 절반만큼
                // 어긋난다. 안 빼면 전부 오른쪽 아래로 쏠려 나간다.
                marginLeft: `calc(${p.size} / -2)`,
                marginTop: `calc(${p.size} / -2)`,
              } as React.CSSProperties
            }
          />
        ))}
      </div>
    </div>
  );
}
