"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { immersiveRoutes, tabHref, tabs } from "@/lib/routes";

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
  // (대신 AuthForm 이 홈으로 나가는 링크를 갖는다. 없으면 막다른 화면이다.)
  //
  // startsWith 가 아니라 정확 일치인 이유: /loginxyz 같은 없는 경로에서도
  // 탭바가 사라져 404 화면이 막다른 곳이 된다.
  if (pathname === "/login" || pathname === "/signup") {
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

  const current = pathname.split("/")[1] ?? "";

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
      <style>{`:root{--tabbar-space:calc(5rem + env(safe-area-inset-bottom))}`}</style>

      {/* 자리막이. 아래 nav 가 fixed 라 흐름에서 빠져 있어서, 이게 없으면
          목록 마지막 항목과 페이지네이션이 탭바 뒤로 들어가 눌리지 않는다.

          5rem 은 탭바 높이(테두리 1px + 48px)에 여유를 더한 값이고,
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
          컴포넌트 안의 형제가 그걸 거칠 이유가 없다. */}
      <div
        aria-hidden
        className="h-[calc(5rem+env(safe-area-inset-bottom))] shrink-0"
      />
      <nav
        aria-label="주요 화면"
        // 높이를 재려는 쪽(QuizBoard)이 이걸로 찾는다. aria-label 로 찾으면
        // 문구를 다듬는 순간 조용히 못 찾게 되고, 스크롤이 탭바 높이만큼
        // 어긋나는데 아무것도 깨지지 않아 알아채지 못한다.
        data-tabbar
        // 아래에 고정한다. 목록이 길어도 이동 수단이 늘 손 닿는 곳에 있다.
        // 폰의 홈 인디케이터에 가리지 않도록 safe-area 만큼 더 띄운다.
        // 배경은 토큰으로 둔다. 리터럴로 박으면 문제풀이·내정보가 각자
        // 배경을 받을 때 탭바만 단어·문장 색으로 남고, 그 줄을 찾아야 한다.
        className="fixed inset-x-0 bottom-0 z-20 border-t border-white/10 bg-background/85 pb-[env(safe-area-inset-bottom)] backdrop-blur-md"
      >
        {/* flex 로 두는 이유: 모드가 하나 열리면 tabs 가 저절로 늘어난다.
          grid-cols-N 을 박아두면 그때 여기도 같이 고쳐야 한다. */}
        <ul className="mx-auto flex max-w-md">
          {tabs.map((tab) => {
            const active = tab.segment === current;

            // 아이콘 라이브러리를 넣지 않으려고 막대 하나로 지금 위치를
            // 표시한다. 색만으로 구분하면 색각 이상이 있을 때 구분이 안 되므로
            // 진하기도 같이 바꾼다.
            const marker = (
              <span
                aria-hidden
                className={`block h-0.5 w-5 rounded-full bg-current transition ${
                  active ? "opacity-100" : "opacity-40"
                }`}
              />
            );

            // 터치 대상 44px 이상. 앱으로 옮겨도 그대로 쓰는 치수다.
            //
            // 다른 누를 수 있는 것들과 달리 여기에는 누름 축소(active:scale)를
            // 일부러 넣지 않는다. 탭바는 이 앱의 핵심 이동 수단이라 하루에
            // 수십~수백 번 눌린다. 그 빈도에서는 반응이 붙을수록 느리게
            // 느껴진다 - 색과 표시줄이 즉시 바뀌는 지금이 가장 빠르다.
            // (globals.css 의 "누름 피드백" 주석 참고)
            const shape =
              "flex min-h-12 flex-col items-center justify-center gap-1.5 py-2 text-xs transition";

            if (!tab.ready) {
              return (
                <li key={tab.key} className="flex-1">
                  {/* 링크가 아니라 span 이다. 갈 곳이 없는데 눌리면 아무 일도
                    안 일어나는 것을 매번 겪는다. 대신 자리를 남겨 이 서비스가
                    단어장 하나로 끝나지 않는다는 걸 알린다.

                    title 은 달지 않는다. 터치에는 hover 가 없고 span 은 포커스도
                    못 받아 뜰 기회가 없다. 보이는 글자로 이미 말하고 있다.

                    "준비 중" 을 라벨 옆이 아니라 표시줄 자리에 둔다. 옆에 붙이면
                    한 줄에 두 덩이가 되어 탭이 5개인 좁은 폰(360px)에서 칸을
                    넘고, 마지막 탭이 화면 밖으로 조용히 밀린다. 위아래로 두면
                    다른 탭과 같은 두 줄이라 높이도 어긋나지 않는다. */}
                  <span className={`${shape} cursor-default text-slate-400`}>
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
              <li key={tab.key} className="flex-1">
                <Link
                  href={tabHref(tab, pathname)}
                  aria-current={active ? "page" : undefined}
                  className={`${shape} focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus ${
                    active
                      ? "text-focus"
                      : "text-slate-300 hover:text-slate-100"
                  }`}
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
