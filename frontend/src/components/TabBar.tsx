"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { tabHref, tabs } from "@/lib/routes";

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

  const current = pathname.split("/")[1] ?? "";

  return (
    <nav
      aria-label="주요 화면"
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
                  active ? "text-focus" : "text-slate-300 hover:text-slate-100"
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
  );
}
