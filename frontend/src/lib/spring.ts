/**
 * 제스처가 붙는 움직임에 쓰는 물리 함수들.
 *
 * **CSS transition 이나 @keyframes 로는 안 되는 자리에만 쓴다.** 저쪽은
 * 시작할 때 목적지가 정해지고 중간에 못 바꾼다. 날아가는 카드를 손가락으로
 * 다시 잡으려면 지금 화면에 그려진 값에서 새 움직임이 출발해야 하는데,
 * CSS 는 그 값을 안 알려준다.
 *
 * 그래서 여기 있는 것은 전부 "현재값에서 출발한다" 를 전제로 한다.
 */

/** 움직임을 끊는 함수. 부르면 다음 프레임부터 onFrame 이 안 온다. */
export type Stop = () => void;

/**
 * 스프링. 현재값에서 목표값으로 감쇠 진동하며 간다.
 *
 * 시간(duration)이 아니라 두 값으로 성질을 정한다. 이게 사람이 다루기 쉽다 -
 * "0.3 초 동안" 보다 "얼마나 튕기고 얼마나 빠른가" 가 화면에서 보이는 것이다.
 *
 *   damping   1 이면 안 튕기고 목표에 붙는다. 낮을수록 넘겼다 돌아온다
 *   response  목표에 닿는 데 걸리는 대략의 시간(초). 낮을수록 빠르다
 *
 * 값은 Apple 의 Designing Fluid Interfaces 가 공개한 것을 쓴다.
 *
 *   되돌아옴  damping 1.0  / response 0.34   손가락이 만든 속도를 이어받되 안 튕긴다
 *   날아감    damping 0.9  / response 0.4    던진 것이라 살짝 넘겨도 자연스럽다
 *
 * initialVelocity 는 px/s 다. 손가락이 놓인 순간의 속도를 그대로 넘기면
 * 드래그와 애니메이션 사이에 이음매가 안 보인다.
 *
 * **반환값을 반드시 들고 있다가 부른다.** 컴포넌트가 사라져도 루프는 계속
 * 돌기 때문에, cleanup 에서 이걸 안 부르면 없는 DOM 에 transform 을 쓴다.
 */
export function spring(
  from: number,
  to: number,
  initialVelocity: number,
  damping: number,
  response: number,
  onFrame: (value: number) => void,
  onDone?: () => void,
): Stop {
  const omega = (2 * Math.PI) / response;
  let x = from - to;
  let v = initialVelocity;
  let alive = true;
  let raf = 0;
  let last = performance.now();

  const step = (now: number) => {
    if (!alive) return;

    // 한 프레임의 상한을 둔다. 탭을 바꿨다 돌아오면 now 가 몇 초 뛰는데,
    // 그 값을 그대로 적분하면 x 가 화면 밖으로 튀어나간다.
    const dt = Math.min((now - last) / 1000, 1 / 30);
    last = now;

    v += (-omega * omega * x - 2 * damping * omega * v) * dt;
    x += v * dt;
    onFrame(to + x);

    // 눈에 안 보이는 거리(0.4px)와 속도(12px/s)가 되면 끊는다. 수학적으로는
    // 영원히 0 에 안 닿아서, 이 기준이 없으면 루프가 안 끝난다.
    if (Math.abs(x) < 0.4 && Math.abs(v) < 12) {
      onFrame(to);
      alive = false;
      onDone?.();
      return;
    }
    raf = requestAnimationFrame(step);
  };

  raf = requestAnimationFrame(step);
  return () => {
    alive = false;
    cancelAnimationFrame(raf);
  };
}

/**
 * 손을 뗀 뒤 관성으로 얼마나 더 갈지. px 단위 거리를 돌려준다.
 *
 * 놓은 자리가 아니라 **가려던 자리**로 판정하려고 쓴다. 이게 없으면 짧고
 * 빠르게 튕긴 동작이 "조금밖에 안 움직였다" 로 읽혀서, 손가락은 던졌는데
 * 카드가 제자리로 돌아온다.
 *
 * 교과서의 v²/(2a) 가 아니라 지수 감쇠식이다. 스크롤 관성이 실제로 이
 * 모양이라 눈에 익다.
 *
 * decelerationRate 0.998 이 보통 스크롤 느낌이고, 낮추면 덜 미끄러진다.
 */
export function project(velocity: number, decelerationRate = 0.998): number {
  return ((velocity / 1000) * decelerationRate) / (1 - decelerationRate);
}

/**
 * 경계 밖으로 끌 때 붙는 저항. 넘어간 거리를 줄여서 돌려준다.
 *
 * 딱 멈추면 화면이 굳은 것으로 보이고, 그대로 따라가면 경계가 없는 것으로
 * 보인다. 갈수록 안 따라오면 "더 없다" 가 손으로 전달된다.
 *
 *   overshoot   경계를 넘어간 거리(px). 부호를 그대로 유지한다
 *   dimension   기준 크기(보통 컨테이너 폭). 상한이자 눈금이다
 *   constant    얼마나 빨리 뻑뻑해지는지. 상한에는 영향이 없다
 *
 * 결과는 항상 overshoot 보다 작고, **아무리 끌어도 dimension 을 못 넘는다**
 * - 식을 극한으로 보내면 (o·d·c)/(c·o) = d 라 constant 가 약분돼 사라진다.
 * 그래서 손가락을 화면 밖까지 끌어도 카드가 딱 한 폭만큼만 밀리고 멈춘다.
 *
 * 이 상한을 레이아웃 여백의 근거로 쓸 거면 dimension 을 그대로 보면 된다.
 * constant 를 곱하지 않는다 - 0.1 로 낮춰도 상한은 그대로 dimension 이다.
 */
export function rubber(
  overshoot: number,
  dimension: number,
  constant = 0.55,
): number {
  return (
    (overshoot * dimension * constant) /
    (dimension + constant * Math.abs(overshoot))
  );
}
