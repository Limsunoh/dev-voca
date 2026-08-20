/**
 * 맞혔을 때 터지는 조각들.
 *
 * 오답에는 흔들림이 있는데 정답에는 아무 반응이 없었다. 틀린 것만 몸으로
 * 오고 맞힌 것은 글자로만 오면 계속 풀 이유가 약해진다.
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
    // 정답 색(emerald)을 중심으로 두고 amber 를 섞는다. 한 색이면 그림자로
    // 보이고, 색이 너무 많으면 파티 장식이 된다.
    color: i % 3 === 0 ? "#fbbf24" : i % 3 === 1 ? "#34d399" : "#a7f3d0",
    // 처음에는 10px/7px 로 잡았는데 390px 폭 화면에서 "터졌다" 가 아니라
    // "먼지가 뿌려졌다" 로 보였다. 조각 하나가 글자 한 자만 해야 눈에 걸린다.
    size: i % 2 === 0 ? "18px" : "13px",
  };
});

export function Burst({ fire }: { fire: number }) {
  // 아직 한 번도 안 맞혔으면 아무것도 안 그린다.
  //
  // 다 터진 뒤 DOM 에서 빼는 장치는 두지 않는다. 한때 상태와 타이머로
  // 700ms 뒤에 지웠는데, 그것이 막아주는 것이 없었다. 조각은
  // pointer-events-none 이라 아래 버튼을 가리지 않고, aria-hidden 이라
  // 낭독에도 안 걸린다. 다음 정답이 오면 key 가 바뀌어 통째로 교체되므로
  // 열여섯 개를 넘겨 쌓이지도 않는다. 상태 하나와 타이머 하나를 판마다
  // 수십 번 돌리는 값이 더 컸다.
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
      // z-10 은 배경(SurfaceLayer 의 -z-10) 위, 탭바(z-20) 아래다.
      // 탭바보다 위에 두면 조각이 탭바를 가로지른다 - 지금 문제풀이에는
      // 탭바가 없어 안 드러나지만, 이 컴포넌트가 탭바 있는 화면에서 쓰이면
      // 그때 나타난다. 조각이 본문 위를 지나가는 데는 z-10 이면 충분하다.
      className="pointer-events-none fixed inset-0 z-10 flex items-center justify-center"
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
                animationDelay: p.delay,
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
