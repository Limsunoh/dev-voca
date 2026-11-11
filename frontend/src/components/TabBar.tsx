"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  activeTabSegment,
  immersiveRoutes,
  routes,
  tabHref,
  tabs,
} from "@/lib/routes";

/**
 * 화면 아래 탭바.
 *
 * 앱처럼 보이게 하는 핵심이 이것이다. 웹 사이트는 위에 로고와 로그인
 * 버튼을 두지만 앱은 아래에서 이동한다. 그래서 사이트 머리말을 없애고
 * 이걸로 대체했다.
 *
 * 클라이언트 컴포넌트인 이유: 지금 어느 탭인지 알려면 경로가 필요하고,
 * 그 표시는 이동할 때마다 즉시 바뀌어야 한다. 서버에서 그리면 이동할
 * 때마다 왕복이 생긴다.
 */
export function TabBar() {
  const pathname = usePathname();

  // 로그인·가입은 한 가지 일만 하는 화면이다. 여기에 탭바를 두면 작업을
  // 끝내지 않고 빠져나가게 되고, 폼이 짧은 화면에서 자리만 차지한다.
  // (대신 AuthForm 에 "로그인 없이 둘러보기" 버튼이 있다. 두 항목을 물은 뒤
  // 게스트 표시를 남기고 홈으로 보낸다. 없으면 막다른 화면이다.)
  //
  // startsWith 가 아니라 정확 일치인 이유: /loginxyz 같은 없는 경로에서도
  // 탭바가 사라져 404 화면이 막다른 곳이 된다.
  //
  // /start 도 같다. 앱을 처음 열었을 때 "누구로 시작할지" 를 묻는
  // 화면이라, 고르기 전에 이동 수단이 보이면 그냥 빠져나갈 수 있다.
  // 그다음에 하루 공부량을 묻는 /start/daily 도 같은 이유다.
  //
  // /privacy, /terms 는 가입 화면에서 새 탭으로 열리는 읽을거리다. 긴 글의
  // 마지막 줄을 탭바가 가리지 않게 하고, 나가는 길은 문서 맨 위 링크로 둔다.
  // /delete-account 도 같은 틀의 읽을거리다. 스토어의 링크로 바로 들어온다.
  if (
    pathname === "/login" ||
    pathname === "/signup" ||
    pathname === "/start" ||
    pathname === routes.startDaily ||
    pathname === "/privacy" ||
    pathname === "/terms" ||
    pathname === "/delete-account"
  ) {
    return null;
  }

  // 판이 걸린 화면에서는 나가는 길을 하나로 좁힌다. 어느 화면이 그런지는
  // routes 가 안다 - 목록과 근거는 immersiveRoutes 주석 참고.
  //
  // 위 로그인 검사와 같은 정확 일치다. 경로 앞부분으로 거르면 /test/ 아래의
  // 안내 화면과 에러 화면까지 탭바를 잃는다.
  if (immersiveRoutes.includes(pathname)) {
    return null;
  }

  // 순위표·오답 노트처럼 탭이 없는 화면은 routes 가 정한 탭을 켠다.
  const current = activeTabSegment(pathname);

  return (
    <>
      {/* 탭바가 차지하는 높이를 문서 뿌리에 알린다. globals.css 의
          scroll-padding-bottom 이 이 값을 읽어서, Tab 으로 이동할 때
          포커스가 탭바 뒤로 들어가지 않게 스크롤을 멈춘다.

          여기서 켜는 이유: html 은 지금 어느 화면인지 모른다. CSS 에
          리터럴로 박으면 탭바가 없는 문제풀이 화면에서도 없는 탭바만큼
          더 스크롤한다. 탭바가 그려질 때만 값이 생기면 그 판단이 필요 없다.

          style 로 두는 이유: Tailwind 클래스로는 임의 이름의 커스텀
          프로퍼티를 문서 뿌리에 올릴 수 없다. */}
      <style>{`:root{--tabbar-space:calc(5rem + env(safe-area-inset-bottom));--tabbar-height:calc(57px + env(safe-area-inset-bottom))}`}</style>

      {/* 자리막이. 아래 nav 가 fixed 라 흐름에서 빠져 있어서, 이게 없으면
          목록 마지막 항목과 페이지네이션이 탭바 뒤로 들어가 눌리지 않는다.

          5rem 은 탭바 높이(테두리 1px + min-h-14 의 56px = 57px)에 여유를
          더한 값이고,
          safe-area 를 더하는 이유는 탭바 자신도 그만큼 두꺼워지기 때문이다.
          이 둘이 어긋나면 아이폰에서만 마지막 항목이 가려진다.

          body 가 아니라 여기 두는 이유: 탭바가 숨는 화면에서는 이것도 같이
          사라져야 빈 띠가 안 남는다. 위의 return null 들이 이걸 공짜로
          해준다. */}
      {/* 높이를 변수가 아니라 값으로 직접 쓴다. var() 로 두면 위 style 이
          적용되기 전 한 프레임 동안 --tabbar-space 가 없어서 height 선언이
          무효가 되고, 자리막이가 0 이었다가 80px 로 뛴다. 목록 하단이
          올라갔다 내려온다.

          변수는 html 의 scroll-padding 이 읽으려고 있는 것이다. 같은
          컴포넌트 안의 자리막이가 그걸 거칠 이유가 없다. */}
      <div
        aria-hidden
        className="h-[calc(5rem+env(safe-area-inset-bottom))] shrink-0"
      />
      <nav
        aria-label="주요 화면"
        // 높이를 재려는 쪽(QuizBoard)이 이걸로 찾는다. aria-label 로 찾으면
        // 문구를 다듬는 순간 에러 없이 못 찾게 되고, 스크롤이 탭바 높이만큼
        // 어긋나는데 아무것도 깨지지 않아 알아채지 못한다.
        data-tabbar
        // 아래에 고정한다. 목록이 길어도 이동 수단이 늘 손 닿는 곳에 있다.
        // 폰의 홈 인디케이터에 가리지 않도록 safe-area 만큼 더 띄운다.
        //
        // 반투명 + backdrop-blur 는 쓰지 않는다. 다크에서는 뒤의 그라디언트가
        // 비쳐야 탭바가 화면에 붙어 보였지만, 크림에는 영역별 배경이 없어
        // 비칠 것이 없다. 흐림만 남으면 스크롤할 때마다 폰이 화면 폭 전체를
        // 다시 합성한다.
        //
        // 여기만 테두리(1px)를 남긴다. 크림의 두께는 전부 아래로 떨어지는데
        // 탭바는 화면 맨 아래에 붙어 있어 그림자를 놓을 자리가 없다.
        // 위로 그림자를 쏘면 이 시스템에서 유일하게 방향이 반대인 요소가
        // 되므로, 머리카락 굵기 선 하나로 바닥과 갈라놓는다
        // (번들 navigation/TabBar.jsx 도 이 자리만 테두리를 쓴다).
        className="fixed inset-x-0 bottom-0 z-20 border-t pb-[env(safe-area-inset-bottom)]"
        style={{
          background: "var(--paper)",
          borderColor: "var(--border-hairline)",
        }}
      >
        {/* flex 로 두는 이유: 모드가 하나 열리면 tabs 가 저절로 늘어난다.
          grid-cols-N 을 박아두면 그때 여기도 같이 고쳐야 한다.

          칸은 같은 너비(flex-1)가 아니라 글자 길이 + 남는 폭의 같은 몫
          (flex-auto)이다. 같은 너비면 글자 가운데끼리는 같은 간격이지만,
          라벨이 "홈"(1자)부터 "문제풀기"(4자)까지라 글자 사이 빈 칸이
          달라진다. 390px 에서 홈-익히기 56px, 익히기-문제풀기 39px 이라
          "익히기" 가 오른쪽으로 치우쳐 보였다(2026-11-11 사용자 지적).
          flex-auto 면 남는 폭이 칸마다 똑같이 붙어 글자 사이가 모두 같아진다.
          누르는 칸은 여전히 탭 줄 전체를 빈틈없이 덮는다.

          가장 짧은 라벨의 칸이 가장 좁다. 기본 글자 크기, 5탭, 360px 에서
          "홈" 칸이 50px 이다. 폰 글자 크기를 130% 로 키우면 43px 로 44px
          아래가 되어(둘 다 2026-11-11 에 브라우저로 잼), 칸마다 min-w-[44px]
          를 건다. --hit-floor(2.75rem)를 쓰지 않는 이유: rem 이라 브라우저의
          기본 글자 크기를 키우면 같이 커진다.

          다만 44px 은 탭 줄 폭의 1/5(20%)을 넘지 않는다. 폰 글자 크기를
          200% 로 키우면 Chrome 이 페이지를 확대해 360폭 폰이 180px 폭처럼
          그려지는데, 다섯 칸 x 44px = 220px 이라 "내정보" 가 화면 밖으로
          잘렸다. 확대된 화면이라 36px 칸도 손가락에 닿는 실제 크기는 72px 와
          같다. 보통 크기 360폭에서는 20% 가 72px 이라 그대로 44px 이다.
          칸이 좁아 라벨이 꺾일 때는 반씩 나눈다("문제/풀기", "일상/영어").
          앱 전체가 낱말 안에서 줄을 안 바꾸는데(globals.css 의 keep-all)
          4글자 라벨은 한 낱말이라 꺾을 자리가 없고, 넘칠 때의 비상 꺾기
          (overflow-wrap: anywhere)가 끝 글자에서 잘라 "문제풀/기" 가 됐다.
          그래서 탭 라벨은 모두 음절 사이에서 꺾게 하고([word-break:normal])
          줄 길이를 고르게 한다(text-balance). 비상 꺾기에는 text-balance 가
          안 먹어서 둘이 같이 있어야 한다. Tailwind 의 break-normal 은
          overflow-wrap 까지 normal 로 바꿔 안전망을 끄므로 쓰지 않는다.
          탭이 6개가 되면 20% 를 1/6 로 바꾸고 기본 글자 크기에서도 다시 잰다. */}
        <ul className="mx-auto flex max-w-md">
          {tabs.map((tab) => {
            const active = tab.segment === current;

            // 아이콘 라이브러리를 넣지 않으려고 막대 하나로 지금 위치를
            // 표시한다. 색만으로 구분하면 색각 이상이 있을 때 구분이 안 되므로
            // 진하기도 같이 바꾼다.
            // 크림에서는 이 막대가 켜졌을 때만 보이는 갈색 막대다(34x6).
            // 다크처럼 꺼진 탭도 40% 투명도로 남기면, 크림 바탕에서는 옅은
            // 회색 막대 다섯 개가 탭바 위에 눈금처럼 늘어서서 무엇이 켜진
            // 것인지 더 안 보인다. 꺼지면 자리만 남기고 색을 없앤다.
            //
            // 색만으로 구분하지 않는다는 규칙은 그대로다 - 켜진 탭은 글자도
            // 갈색이고 aria-current 가 소리로 말한다. 막대는 훑을 때를 돕는
            // 보조 수단이다.
            const marker = (
              <span
                aria-hidden
                // w-full + max-w 로 둔다. w-[34px] 로 박으면 막대가 칸의
                // 내용 너비가 되어, 글자가 34px 보다 짧은 "홈" 칸이 글자가
                // 아니라 막대 너비로 잡힌다. 그러면 flex-auto 가 글자 사이를
                // 고르게 벌리지 못한다. 퍼센트 너비는 칸 크기를 정할 때 안 셈한다.
                className="block h-1.5 w-full max-w-[34px] rounded-full"
                style={{ background: active ? "var(--brand)" : "transparent" }}
              />
            );

            // 터치 대상 44px 이상. 앱으로 옮겨도 그대로 쓰는 치수다.
            //
            // 다른 누를 수 있는 것들과 달리 여기에는 누름 축소(active:scale)를
            // 일부러 넣지 않는다. 탭바는 이 앱의 핵심 이동 수단이라 하루에
            // 수십~수백 번 눌린다. 그 빈도에서는 반응이 붙을수록 느리게
            // 느껴진다 - 색과 표시줄이 즉시 바뀌는 지금이 가장 빠르다.
            // (globals.css 의 "누름 피드백" 주석 참고)
            // min-h 를 14(56px)로 둔다. 12(48px)면 "준비 중 / 말하기" 처럼
            // 두 줄인 항목이 안 들어가 글자가 탭바 밖으로 잘린다. 준비 중인
            // 탭이 하나뿐이라 다른 항목만 보고는 못 알아챈다.
            // 칸 폭 규칙(위 ul 주석). 링크 칸과 준비 중 칸이 같이 쓴다.
            const cell = "min-w-[min(44px,20%)] flex-auto";

            const shape =
              "flex min-h-14 flex-col items-center justify-center gap-1 py-1.5 text-center text-xs [word-break:normal] text-balance transition";

            if (!tab.ready) {
              return (
                <li key={tab.key} className={cell}>
                  {/* 링크가 아니라 span 이다. 갈 곳이 없는데 눌리면 아무 일도
                    안 일어나는 것을 매번 겪는다. 대신 자리를 남겨 이 서비스가
                    단어장 하나로 끝나지 않는다는 걸 알린다.

                    title 은 달지 않는다. 터치에는 hover 가 없고 span 은 포커스도
                    못 받아 뜰 기회가 없다. 보이는 글자로 이미 말하고 있다.

                    "준비 중" 을 라벨 옆이 아니라 표시줄 자리에 둔다. 옆에 붙이면
                    한 줄에 두 덩이가 되어 탭이 5개인 좁은 폰(360px)에서 칸을
                    넘고, 마지막 탭이 화면 밖으로 밀린다. 위아래로 두면
                    다른 탭과 같은 두 줄이라 높이도 어긋나지 않는다. */}
                  <span
                    className={`${shape} cursor-default`}
                    style={{ color: "var(--text-muted)" }}
                  >
                    <span aria-hidden className="text-[0.625rem] leading-none">
                      준비 중
                    </span>
                    {tab.label}
                    <span className="sr-only">준비 중</span>
                  </span>
                </li>
              );
            }

            return (
              <li key={tab.key} className={cell}>
                <Link
                  href={tabHref(tab, pathname)}
                  aria-current={active ? "page" : undefined}
                  className={`${shape} focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus`}
                  style={{
                    // 글자와 위 막대 모두 --brand 다. 흰 종이 위 9.46:1 이라
                    // 글자 기준(4.5:1)과 막대 기준(3:1)을 함께 넘는다.
                    color: active ? "var(--brand)" : "var(--text-muted)",
                    fontWeight: "var(--weight-bold)",
                  }}
                >
                  {marker}
                  {tab.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}
