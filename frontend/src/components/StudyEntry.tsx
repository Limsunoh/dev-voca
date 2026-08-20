import Link from "next/link";

import { routes } from "@/lib/routes";

/**
 * 홈에서 오늘 공부를 시작하는 자리.
 *
 * 홈에 있던 링크는 "더 보기"(오늘의 단어 상세)와 "단어장"(목록) 둘뿐이라,
 * 둘 다 **읽으러 가는 길**이었다. 문제를 풀려면 아래 탭바에서 "문제풀기"
 * 를 찾아 눌러야 했는데, 처음 온 사람은 그게 있는 줄 모른다. 홈은 오늘
 * 무엇을 할지 정하는 화면인데 선택지 하나가 통째로 빠져 있던 셈이다.
 *
 * 두 갈래로 나눈 이유: 같은 "문제풀기" 라도 성격이 다르다.
 *
 *   한 판     90초, 점수가 순위표에 남는다. 승부다
 *   가볍게    시간 제한 없이 한 문제씩. 점수가 안 남는다
 *
 * 한 판을 크게 두는 이유는 그쪽이 오늘의 목표가 되기 때문이다. 매일 한 판
 * 이 이 앱의 리듬이고, 연습은 그 준비다.
 *
 * 로그인 여부를 받는 이유: 게스트도 한 판을 풀 수 있지만 점수가 안 남는다.
 * 그것을 90초 다 쓰고 결과 화면에서 처음 알면 속은 기분이 든다.
 */
export function StudyEntry({ isGuest }: { isGuest: boolean }) {
  return (
    // 위 여백을 오늘의 단어(mt-8)보다 좁게 둔다. 읽기와 풀기는 한 묶음이라
    // 그 사이가 순위표와의 사이보다 가까워야 한다.
    //
    // 320ms 는 위 오늘의 단어가 순서대로 올라온 다음이다(라벨 0 · 단어 80
    // · 뜻 160 · 버튼 240). delay 를 안 주면 맨 위 라벨과 동시에 떠서,
    // 위에서 아래로 흐르던 순서가 여기서 끊긴다.
    <section
      aria-labelledby="study-entry"
      className="rise mt-6 [animation-delay:320ms]"
    >
      <h2
        id="study-entry"
        className="text-xs font-semibold tracking-wide text-slate-400"
      >
        오늘 공부
      </h2>

      <div className="mt-3 flex flex-col gap-2.5">
        {/* 한 판이 주인공이다. 앰버는 한 판 화면의 타이머와 시작 버튼이
            쓰는 색이라, 눌러보기 전에 무엇이 나올지 짐작된다.
            (점수·순위는 보라다 - 순위표와 내 기록이 그 색을 쓴다.) */}
        <Link
          href={routes.testRound}
          className="group flex min-h-16 items-center justify-between gap-3 rounded-2xl border border-amber-300/30 bg-amber-300/10 px-5 transition-[scale,background-color] duration-[120ms] ease-press hover:bg-amber-300/15 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          <span className="flex flex-col gap-0.5">
            <span className="text-base font-bold text-amber-100">
              한 판 풀기
            </span>
            {/* 로그인 안 했으면 순위 얘기를 하지 않는다. 게스트도 풀 수는
                있지만 기록은 안 남는다 - 그것을 90초 다 쓰고 결과 화면에서
                처음 알면 속은 기분이 든다. 여기서 미리 말한다. */}
            <span className="text-sm text-amber-200/70">
              {isGuest
                ? "90초, 순위표는 로그인 후부터"
                : "90초, 점수가 순위표에 오릅니다"}
            </span>
          </span>
          {/* 화살표는 장식이라 낭독에서 뺀다. 링크 글자가 이미 어디로
              가는지 말하고 있다. */}
          <span
            aria-hidden
            className="text-lg leading-none text-amber-200/60 transition-transform duration-[120ms] ease-press group-hover:translate-x-0.5"
          >
            →
          </span>
        </Link>

        {/* 연습은 한 단 낮춘다. 둘을 같은 무게로 두면 무엇부터 할지
            고르는 데 시간이 걸리고, 홈은 고민하는 자리가 아니다. */}
        <Link
          href={routes.testWords}
          // 테두리만으로 두지 않는다. 배경(surface-learn)의 층이 겹쳐
          // 밝아지는 지점에서 white/12 는 배경에 묻혀, 위의 앰버 카드와
          // 나란히 있을 때 이쪽만 "눌리지 않는 글자" 로 보인다. WCAG
          // 1.4.11 이 컨트롤 경계에 3:1 을 요구하는데 white/15 도 1.5:1 이다
          // (page.tsx 의 "단어장" 버튼 주석 참고).
          //
          // 테두리를 white/40 으로 올리는 대신 옅은 채움을 준 이유: 위
          // 앰버 카드와의 위계를 지켜야 한다. 테두리를 그만큼 밝히면 둘이
          // 같은 무게가 되어 무엇부터 할지 고르는 데 시간이 걸린다.
          className="group flex min-h-14 items-center justify-between gap-3 rounded-xl border border-white/12 bg-white/5 px-5 transition-[scale,background-color] duration-[120ms] ease-press hover:bg-white/10 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          <span className="flex flex-col gap-0.5">
            <span className="text-sm font-semibold text-slate-100">
              가볍게 연습
            </span>
            <span className="text-sm text-slate-400">
              시간 제한 없이 한 문제씩
            </span>
          </span>
          <span
            aria-hidden
            className="text-base leading-none text-slate-500 transition-transform duration-[120ms] ease-press group-hover:translate-x-0.5"
          >
            →
          </span>
        </Link>
      </div>
    </section>
  );
}
