"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

/**
 * 문제풀이에서 나가는 문.
 *
 * 이 화면에는 탭바가 없다(TabBar 의 return null 참고). 게임이 그렇듯
 * 나가는 길을 하나로 좁혀서, 푸는 중에 홈을 눌러 점수를 날리는 일이
 * 없게 한다. 그 하나가 이 버튼이다.
 *
 * 그래서 이건 장식이 아니라 **유일한 출구**다. 빠지면 막다른 화면이 된다.
 *
 * confirm 을 켜면 나가기 전에 물어본다. 점수가 남는 판(한 판 모드)에서만
 * 켠다. 낱개 연습은 점수가 안 남으니 물어볼 게 없고, 매번 물으면 성가시다.
 *
 * dialog 를 쓰는 이유: 포커스 가둠, Esc 닫기, 뒤 스크롤 막기, 그리고
 * 화면 낭독기에 "대화상자" 로 알리는 것까지 브라우저가 해준다. div 로
 * 만들면 그 넷을 직접 짜야 하고, 대개 포커스 가둠에서 샌다.
 */
export function ExitGuard({
  to,
  label = "나가기",
  confirm = false,
  score,
  countdown = false,
}: {
  /** 나갈 곳. */
  to: string;
  /** 버튼에 쓸 글자. */
  label?: string;
  /** 나가기 전에 물어볼지. 점수가 남는 판에서만 켠다. */
  confirm?: boolean;
  /**
   * 지금까지 딴 점수. 주면 경고 문구가 그 값을 말한다.
   *
   * "점수가 적용되지 않습니다" 만으로는 순위표에 안 오른다는 뜻으로만
   * 읽혀서, 90초 중 70초를 푼 사람이 이미 딴 점수는 남는 줄 안다.
   * 얼마를 버리는지 숫자로 보여줘야 정직하다.
   */
  score?: number;
  /**
   * 시간이 걸린 판인지. 켜면 "창이 떠 있는 동안에도 시간은 흐릅니다" 를
   * 같이 보여준다.
   *
   * 마감은 서버가 정한 시각이라 이 창을 띄웠다고 멈출 수 없다. 멈출 수
   * 없으면 최소한 숨기지 않는다.
   */
  countdown?: boolean;
}) {
  const router = useRouter();
  // 예약한 이동을 취소할지 판단하는 근거. 아래 effect 설명 참고.
  const pathname = usePathname();
  const dialogRef = useRef<HTMLDialogElement>(null);
  // 예약한 이동. 경로가 바뀌면 취소하려고 들고 있는다.
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [leaving, setLeaving] = useState(false);
  // 나가는 중인지. 위의 state 와 짝인데 이쪽이 실제 문지기다.
  //
  // state 로만 막으면 한 틱 안에 들어온 클릭들이 전부 leaving === false 를
  // 읽는다(실측: 3연타에 타이머 3개가 예약됐고 timerRef 에는 마지막 것만
  // 남아 하나만 취소됐다). 남은 타이머는 취소할 방법이 없어서, 아래
  // cleanup 이 막으려던 바로 그 버그 - 220ms 안에 뒤로가기를 누른 사람이
  // 도로 끌려오는 것 - 가 연타 경로로 되살아난다.
  //
  // 같은 함정을 RoundBoard 의 busyRef 가 이미 다루고 있다.
  const leavingRef = useRef(false);
  // 대화상자 제목과 잇는다. 고정 문자열로 두면 한 화면에 나가기가 둘 이상
  // 생길 때 id 가 겹쳐서 낭독기가 엉뚱한 제목을 읽는다.
  const titleId = useId();

  // showModal() 은 명령형이라 open 속성으로는 못 연다. 속성으로 열면
  // ::backdrop 도, 포커스 가둠도 안 붙는 그냥 보이는 상자가 된다.
  const open = () => dialogRef.current?.showModal();

  const leave = () => {
    // 이미 나가는 중이면 무시한다. state 가 아니라 ref 로 보는 이유는
    // leavingRef 선언부 참고 - 같은 틱에 들어온 클릭은 state 로 못 막는다.
    // 장막이 pointer-events-none 이라 220ms 동안 버튼은 계속 눌린다.
    if (leavingRef.current) return;
    leavingRef.current = true;
    dialogRef.current?.close();

    // 움직임을 줄인 사용자에게는 장막을 안 그리고 곧장 이동한다.
    //
    // 전역 reduced-motion 규칙이 animation-duration 을 0.01ms 로 만드는데,
    // exit-veil 은 fill-mode 가 both 라 즉시 화면을 덮은 상태로 고정된다.
    // 그 상태로 아래 220ms 를 기다리면, 움직임을 없애달라고 한 사람이
    // 아무 설명 없는 빈 배경색 화면을 0.22초 본다. 애니메이션을 보는 것보다
    // 나쁘다 - 멈춘 화면은 고장으로 읽힌다.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      router.push(to);
      return;
    }

    // 화면을 먼저 내리고 이동한다. 바로 push 하면 다음 화면이 그려지는
    // 것과 겹쳐서 나가는 동작이 안 보인다.
    setLeaving(true);

    // 타이머를 effect 가 아니라 여기서 건다.
    //
    // effect 로 두면 의존성에 to·router 가 들어가고, 그 참조가 바뀌면
    // cleanup 이 타이머를 지우고 처음부터 다시 센다. 한 판 화면은 남은
    // 시간을 매 초 다시 그려서 리렌더가 계속 일어나고, 그 사이 90초가
    // 만료되면 결과 화면으로 바뀌며 이 컴포넌트가 통째로 사라진다.
    // 그러면 cleanup 만 돌고 push 는 영영 안 온다 - 나가기를 눌렀는데
    // 장막만 덮인 채 화면이 그대로 남는다.
    //
    // 여기서 걸면 언마운트돼도 예약된 이동이 살아 있다. 이미 떠나기로
    // 정한 동작이라 컴포넌트가 사라졌다고 취소할 이유가 없다.
    //
    // 220ms 는 exit-veil 의 200ms 보다 조금 길다. 덮이기 전에 이동하면
    // 다음 화면이 번쩍인다. globals.css 의 exit-veil 을 고치면 여기도
    // 같이 고친다.
    timerRef.current = setTimeout(() => router.push(to), 220);
  };

  // 그 사이 다른 곳으로 이미 갔으면 예약을 취소한다.
  //
  // 취소하지 않으면 이 220ms 안에 브라우저 뒤로가기를 누른 사람이 도로
  // 끌려온다(실측 - 뒤로가기로 /learn/words 에 갔다가 곧바로 홈으로
  // 밀렸다). 명시적으로 요청한 이동이 조용히 덮이는 것이라 나쁘다.
  //
  // 언마운트가 아니라 경로 변화로 판단하는 게 핵심이다. 언마운트에 걸면
  // 원래 막으려던 버그가 돌아온다 - 한 판에서 나가기를 누른 직후 90초가
  // 만료되면 결과 화면으로 바뀌며 이 컴포넌트가 사라지는데, 그때는 경로가
  // 그대로라 예약이 살아 있어야 한다. 그 경우까지 취소하면 장막만 덮이고
  // 화면이 안 넘어간다.
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
      // 문지기도 푼다. 취소했는데 잠긴 채로 두면, 뒤로가기로 이 화면에
      // 돌아온 사람이 나가기를 눌러도 아무 일이 안 일어난다.
      leavingRef.current = false;
    };
  }, [pathname]);

  // 대화상자를 연 채로 이 컴포넌트가 사라지면 닫아준다.
  //
  // showModal() 은 dialog 를 top layer 에 올리고 나머지 문서를 inert 로
  // 만든다. close() 없이 노드만 제거되면 브라우저가 top layer 에서는 빼주지만
  // 포커스가 body 로 떨어져서, 키보드로 "계속 풀기" 에 서 있던 사람이 문서
  // 맨 앞으로 돌아간다. 스크린리더도 닫혔다는 통지를 못 받는다.
  //
  // 실제 경로: 한 판에서 나가기를 눌러 확인창을 연 채 두면 90초가 만료되고,
  // RoundBoard 가 결과 화면으로 바뀌면서 이 컴포넌트가 통째로 사라진다.
  useEffect(() => {
    const dialog = dialogRef.current;
    return () => dialog?.close();
  }, []);

  return (
    <>
      {leaving && (
        // 화면 전체를 덮고 아래로 밀어낸다. 실제 화면은 그대로 있고 이
        // 장막만 움직이지만, 덮은 채로 내려가니 화면이 내려가는 것으로
        // 보인다. 진짜 화면을 움직이면 fixed 로 붙은 것들이 따라오지 않아
        // 어긋난다.
        <div
          aria-hidden
          className="exit-veil pointer-events-none fixed inset-0 z-50 bg-background"
        />
      )}

      <button
        type="button"
        onClick={confirm ? open : leave}
        // 테두리와 배경을 준다. 대비는 원래도 충분했지만(12.83:1) 위계가
        // 없었다 - 옆의 "한 판 풀기" 링크와 같은 크기·같은 무게라, 화면의
        // 유일한 출구가 그냥 링크 중 하나로 보였다. 크게 만들 필요는 없고
        // 눌리는 것처럼 보이면 된다.
        className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-white/12 bg-white/5 px-3 text-[0.9375rem] font-medium text-slate-200 transition-[scale,color,background-color] duration-[120ms] ease-press hover:bg-white/10 hover:text-slate-50 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        <span aria-hidden className="text-base leading-none">
          ←
        </span>
        {label}
      </button>

      {confirm && (
        <dialog
          ref={dialogRef}
          // 제목을 잇는다. 없으면 낭독기가 "대화상자" 라고만 알리고 무엇을
          // 묻는지는 안 읽는 조합이 있다.
          aria-labelledby={titleId}
          // m-auto 를 반드시 준다. dialog 는 브라우저 기본값이 margin: auto
          // 라서 저절로 가운데 서는데, Tailwind 의 리셋이 모든 요소의 margin
          // 을 0 으로 만들어 그 기본값을 지운다. 그러면 inset: 0 만 남아
          // 화면 왼쪽 위에 붙는다(실측: top 0, left 0).
          className="pop m-auto max-w-[min(22rem,calc(100vw-2rem))] rounded-2xl border border-white/12 bg-slate-900 p-6 text-slate-100 shadow-[0_24px_64px_-12px_rgb(0_0_0/0.9)] backdrop:bg-black/70 backdrop:backdrop-blur-sm"
        >
          <h2 id={titleId} className="text-lg font-bold">
            지금 나가시겠습니까?
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-300">
            {/* 양수일 때만 숫자를 말한다. 틀려서 점수가 음수인 사람에게
                "딴 -2점이 사라진다" 고 하면 거짓말이고, 0 이면 잃을 게
                없다. 두 경우 모두 일반 문구가 맞다.
                score > 0 하나로 충분하지만 undefined 를 명시적으로 거른다 -
                생략하면 0 과 미지정이 같은 조건에 뭉개져, 나중에 둘을 다르게
                다뤄야 할 때 어디를 고칠지 안 보인다. */}
            {score !== undefined && score > 0
              ? `지금까지 딴 ${score}점이 사라지고 순위표에 오르지 않습니다.`
              : "지금 나가면 점수가 적용되지 않습니다."}
          </p>

          {/* 시간이 계속 간다는 것을 알린다.
              판의 마감은 서버가 정한 시각이라 이 창을 띄웠다고 멈출 수
              없다 - 화면 숫자만 늘리면 답이 서버에 거절돼 더 나쁘다.
              멈출 수 없으면 최소한 숨기지는 않는다. 실수로 연 사람이
              바로 손을 떼게 만드는 것이 지금 할 수 있는 최선이다.
              (Esc 로도 닫힌다) */}
          {countdown && (
            <p className="mt-2 text-sm font-medium text-amber-300">
              창이 떠 있는 동안에도 시간은 흐릅니다.
            </p>
          )}

          <div className="mt-6 flex gap-2">
            {/* 계속 풀기를 먼저 둔다. 실수로 연 사람이 대부분이라 손가락이
                먼저 닿는 자리에 되돌아가는 쪽이 있어야 한다. */}
            <button
              type="button"
              onClick={() => dialogRef.current?.close()}
              className="flex min-h-12 flex-1 items-center justify-center rounded-xl bg-white/10 px-4 text-sm font-semibold transition-[scale,background-color] duration-[120ms] ease-press hover:bg-white/15 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            >
              계속 풀기
            </button>
            <button
              type="button"
              onClick={leave}
              className="flex min-h-12 flex-1 items-center justify-center rounded-xl border border-rose-400/40 px-4 text-sm font-semibold text-rose-200 transition-[scale,background-color] duration-[120ms] ease-press hover:bg-rose-400/10 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            >
              나가기
            </button>
          </div>
        </dialog>
      )}
    </>
  );
}
