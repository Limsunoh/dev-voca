"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { leaveDetail, solvedNow } from "@/lib/quiz-progress";

import { LeaveConfirm } from "./LeaveConfirm";

/**
 * 문제풀이에서 나가는 문.
 *
 * 이 화면에는 탭바가 없다(TabBar 의 return null 참고). 게임이 그렇듯
 * 나가는 길을 하나로 좁혀서, 푸는 중에 홈을 눌러 점수를 날리는 일이
 * 없게 한다. 그 하나가 이 버튼이다.
 *
 * 그래서 이건 장식이 아니라 **유일한 출구**다. 빠지면 막다른 화면이 된다.
 *
 * 나가기 전에 묻는 방식이 둘이다. confirm 은 늘 묻고, 점수가 남는 판(한
 * 판 모드)에서 켠다. confirmWhenSolved 는 푼 것이 있을 때만 묻고,
 * 문제풀기가 이쪽이다 - 거기도 판을 떠나면 푼 것이 사라지지만, 한 문제도
 * 안 푼 사람에게 매번 물으면 성가시다.
 *
 * 묻는 창은 LeaveConfirm 이다. 같은 화면의 다른 출구(분류·탭·"한 판
 * 풀기")와 같은 창을 쓴다 - 따로 두던 때 이쪽만 문구가 어긋났다.
 * 제목만 다르게 둔다. 다른 출구는 새 판으로 옮기는 것이라 "판을
 * 끝낼까요?" 이고, 여기는 문제풀기를 떠나는 것이라 "나가시겠습니까?" 다.
 */
export function ExitGuard({
  to,
  label = "나가기",
  ariaLabel,
  confirm = false,
  confirmWhenSolved = false,
  score,
  countdown = false,
}: {
  /** 나갈 곳. */
  to: string;
  /** 버튼에 쓸 글자. */
  label?: string;
  /**
   * 화면낭독기가 읽을 이름. 없으면 보이는 글자(label)를 읽는다.
   *
   * 보이는 글자가 목적지 이름뿐일 때 준다. 화살표(←)는 aria-hidden 이라
   * "문제풀기, 버튼" 으로만 읽히는데, 문제풀기 화면 안에서는 나가는 버튼인지
   * 풀기를 시작하는 버튼인지 구분이 안 된다.
   */
  ariaLabel?: string;
  /** 나가기 전에 늘 물어볼지. 점수가 남는 판에서만 켠다. */
  confirm?: boolean;
  /** 푼 것이 있을 때만 물어볼지. 문제풀기가 이쪽이다. */
  confirmWhenSolved?: boolean;
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
  // LeaveConfirm 이 채워 주는 여는 함수.
  const openRef = useRef<(() => void) | null>(null);
  // 창을 열 때 푼 문제 수. 그릴 때 읽으면 창이 처음 그려진 때의 0 이 남는다.
  const [asked, setAsked] = useState(0);
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
  const open = () => {
    setAsked(solvedNow());
    openRef.current?.();
  };

  const leave = () => {
    // 이미 나가는 중이면 무시한다. state 가 아니라 ref 로 보는 이유는
    // leavingRef 선언부 참고 - 같은 틱에 들어온 클릭은 state 로 못 막는다.
    // 장막이 pointer-events-none 이라 220ms 동안 버튼은 계속 눌린다.
    if (leavingRef.current) return;
    leavingRef.current = true;

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
        aria-label={ariaLabel}
        onClick={() => {
          if (confirm || (confirmWhenSolved && solvedNow() > 0)) open();
          else leave();
        }}
        // 흰 알약에 두께를 준다. 위계가 필요한 자리라서다 - 옆의 "순위표"
        // 링크와 같은 무게로 두면 화면의 유일한 출구가 그냥 링크 중 하나로
        // 보인다. 크게 만들 필요는 없고 눌리는 것처럼 보이면 된다.
        //
        // 코랄은 안 쓴다. 나가기는 물러나는 동작이고, 이 화면의 코랄
        // 하나는 "시작"·"이어서 익히기" 같은 주된 동작이 갖는다.
        //
        // 상세의 되돌아가기(DetailBack)와 같은 모양이다 - 화살표를 옅은
        // 띠에 앉힌 흰 알약. 둘 다 "여기서 빠져나가는 길" 이라 같아야 한다.
        className="dv-card dv-card-press inline-flex min-h-11 items-center gap-2 rounded-full py-1 pr-4 pl-1.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        style={
          {
            background: "var(--paper)",
            color: "var(--foreground)",
            fontSize: "var(--text-sm)",
            fontWeight: "var(--weight-black)",
            // 쉬는 두께는 --lift 로. 인라인 box-shadow 는 :active 를 이겨서
            // 눌러도 두께가 안 사라진다.
            "--lift": "var(--lift-card)",
          } as React.CSSProperties
        }
      >
        {/* 화살표만 옅은 띠에 앉힌다. 알약 전체가 이미 흰 종이라 여기에
            또 종이를 깔면 층이 둘이 된다. */}
        <span
          aria-hidden
          className="grid h-7 w-7 place-items-center"
          style={{
            background: "var(--background-deep)",
            borderRadius: "var(--radius-md)",
            fontSize: "var(--text-sm)",
          }}
        >
          ←
        </span>
        {label}
      </button>

      {(confirm || confirmWhenSolved) && (
        <LeaveConfirm
          openRef={openRef}
          title="지금 나가시겠습니까?"
          detail={
            // 양수일 때만 점수를 말한다. 틀려서 음수인 사람에게 "딴 -2점이
            // 사라진다" 고 하면 거짓말이고, 0 이면 잃을 게 없다.
            score !== undefined && score > 0
              ? `지금까지 딴 ${score}점이 사라지고 순위표에 오르지 않습니다.`
              : confirmWhenSolved && asked > 0
                ? leaveDetail(asked)
                : "지금 나가면 점수가 적용되지 않습니다."
          }
          note={
            // 판의 마감은 서버가 정한 시각이라 이 창을 띄웠다고 멈출 수
            // 없다. 멈출 수 없으면 최소한 숨기지는 않는다.
            //
            // --amber 를 글자색으로 쓰지 않는다. 크림 위에서 2.2:1 이라 안
            // 읽힌다. --amber-deep 이 그 자리를 위해 있는 토큰이다.
            countdown && (
              <p
                className="mt-3 px-3 py-2 text-sm"
                style={{
                  background: "var(--amber-soft)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--amber-deep)",
                  fontWeight: "var(--weight-bold)",
                }}
              >
                창이 떠 있는 동안에도 시간은 흐릅니다.
              </p>
            )
          }
          confirmLabel="나가기"
          onConfirm={leave}
        />
      )}
    </>
  );
}
