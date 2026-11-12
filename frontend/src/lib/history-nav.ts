/**
 * 앱(TWA)의 뒤로 가기를 일반 앱처럼 만드는 이동 도우미.
 *
 * 앱은 폰의 Chrome 이 이 웹을 띄운 것이라, 폰의 뒤로 가기가 곧 브라우저의
 * 뒤로 가기다. 맨 처음 기록에서 한 번 더 누르면 Android 가 앱을 닫는다. 그래서
 * 화면을 옮길 때마다 기록(push)을 쌓으면, 탭을 다섯 번 오간 사람은 뒤로 가기를
 * 다섯 번 눌러야 앱이 닫힌다(11-12 사용자가 앱으로 써 보고 "앱이 안 닫힌다").
 *
 * 웹은 이미 쌓인 기록을 지울 수 없다. 할 수 있는 것은 둘이다.
 * - 뒤쪽 기록에 가려는 주소가 있으면 거기로 돌아간다(Navigation API 의
 *   traverseTo). 그 앞쪽 기록은 다음에 화면을 옮길 때 브라우저가 버린다.
 * - 없으면 지금 칸을 바꿔치기한다(replace). 기록이 늘지 않는다.
 *
 * 돌아간 화면을 새로 받는 일은 여기서 하지 않는다. 탭바가 뒤로·앞으로 가기마다
 * 맡는다(TabBar 가 onTraverseToOtherScreen 으로). 돌아가는 것도 뒤로 가기와 같은
 * 이동이라 그쪽에서 같이 처리된다.
 *
 * Navigation API 는 Chrome 102 부터 있다. 앱은 Chrome 이라 늘 있고, 없는
 * 브라우저(Safari·Firefox 일부)에서는 바꿔치기만 한다.
 */

/** Navigation API 중 여기서 쓰는 것만. TypeScript 5.9 의 dom 정의에 아직 없다. */
type HistoryEntry = { key: string; url: string | null; index: number; sameDocument: boolean };
type NavigationHistory = {
  entries(): HistoryEntry[];
  currentEntry: HistoryEntry | null;
  traverseTo(key: string): { committed: Promise<unknown>; finished: Promise<unknown> };
  addEventListener(type: "currententrychange", listener: (event: Event) => void): void;
  removeEventListener(type: "currententrychange", listener: (event: Event) => void): void;
};
/** currententrychange 이벤트 중 여기서 쓰는 것. */
type EntryChange = Event & { navigationType?: string; from?: { url: string | null } };

function navigationApi(): NavigationHistory | undefined {
  if (typeof window === "undefined") return undefined;
  return (window as { navigation?: NavigationHistory }).navigation;
}

/**
 * 지금보다 뒤쪽(뒤로 가기 쪽) 기록 중 경로가 path 인 가장 가까운 칸의 key.
 *
 * 쿼리는 보지 않는다. 탭은 경로로 가리키는데, 단어 목록처럼 들어가면 쿼리
 * (?shuffle=)가 붙는 화면이 있어서다. 돌아가면 보던 필터와 순서도 그대로다.
 *
 * sameDocument 면 이 문서 안의 칸만 본다. 다른 문서의 칸(주소를 쳐서 열었거나
 * 구글 로그인에서 돌아오며 페이지를 통째로 받은 칸)으로 돌아가는 것은 페이지를
 * 다시 받는 이동이라, 한 판 도중이면 브라우저의 "나가시겠습니까" 경고
 * (beforeunload)가 우리 확인 창 뒤에 한 번 더 뜬다. 새로고침은 해당하지 않는다.
 * Chrome 은 새로고침한 뒤에도 앞 칸들을 같은 문서로 친다(11-12 확인).
 *
 * Navigation API 는 같은 사이트의 이어진 기록만 보여 준다. 구글 로그인처럼
 * 다른 사이트를 거쳤으면 그보다 앞의 기록은 보이지 않아 찾지 못한다.
 */
export function earlierEntryKey(path: string, sameDocument = false): string | null {
  const nav = navigationApi();
  const here = nav?.currentEntry;
  if (!nav || !here) return null;
  const entries = nav.entries();
  for (let i = here.index - 1; i >= 0; i--) {
    const entry = entries[i];
    if (!entry?.url || (sameDocument && !entry.sameDocument)) continue;
    const at = new URL(entry.url);
    if (at.origin === window.location.origin && at.pathname === path) {
      return entry.key;
    }
  }
  return null;
}

/** traverseTo 의 거절을 받아 둔다. 안 받으면 "Uncaught (in promise)" 가 콘솔에 남는다. */
function traverse(nav: NavigationHistory, key: string) {
  const moving = nav.traverseTo(key);
  // 막히거나(ExitGuard 의 확인 창) 다른 이동에 밀려 끝나지 못하면 둘 다 거절된다.
  moving.committed.catch(() => {});
  moving.finished.catch(() => {});
  return moving;
}

/**
 * 뒤쪽 기록에 path 가 있으면 거기로 돌아간다. 돌아가기 시작했으면 true,
 * 없으면 false(아무것도 안 했다). 탭과 "홈으로" 링크(Link 의 onNavigate), 저장
 * 안 한 내정보의 확인 창에서 탭으로 나갈 때(useUnsavedGuard)가 쓴다.
 */
export function traverseBackTo(path: string): boolean {
  const nav = navigationApi();
  const key = earlierEntryKey(path);
  if (!nav || !key) return false;
  traverse(nav, key);
  return true;
}

/**
 * path 로 간다. 이 문서 안의 뒤쪽 기록에 같은 경로가 있으면 거기로 돌아가고,
 * 없으면 지금 칸을 바꿔치기한다. 어느 쪽이든 기록이 늘지 않는다. 한 판의
 * 나가기(ExitGuard)가 쓴다.
 *
 * 돌아가기가 막히면(ExitGuard 가 확인 창을 띄우려고 취소하면) 아무것도 하지
 * 않는다. 바꿔치기로 대신 가면 그 확인 창을 건너뛰게 된다.
 */
export function goBackOrReplace(router: { replace(href: string): void }, path: string): void {
  const nav = navigationApi();
  const key = earlierEntryKey(path, true);
  if (nav && key) traverse(nav, key);
  else router.replace(path);
}

/**
 * 바로 앞 칸이 지금과 같은 주소면 그 칸으로 돌아가, 같은 화면이 두 칸 쌓이지
 * 않게 한다. 돌아갔으면 true.
 *
 * 로그인하면 로그인 화면의 칸이 돌아갈 주소로 바꿔치기된다. 홈에서 로그인을
 * 눌렀으면 그 앞 칸도 홈이라 [홈, 홈] 이 되고, 홈에서 뒤로 가기가 옛 홈으로
 * 간다. 순위표에서 로그인했을 때, 게스트가 내정보 탭의 로그인 화면에서 "로그인
 * 없이 둘러보기" 를 골랐을 때도 같다.
 *
 * Next 는 지금과 같은 주소로 가는 이동을 쌓지 않는다. 그래서 같은 주소 두 칸은
 * 이런 바꿔치기에서만 생긴다. 앞 칸이 다른 문서면 돌아가는 것이 페이지를
 * 통째로 다시 받는 것이라 두고 넘어간다.
 */
export function stepOffRepeat(): boolean {
  const nav = navigationApi();
  const here = nav?.currentEntry;
  if (!nav || !here || here.index < 1) return false;
  const before = nav.entries()[here.index - 1];
  if (!before || !before.sameDocument || before.url !== here.url) return false;
  traverse(nav, before.key);
  return true;
}

/**
 * 뒤로·앞으로 가기로 다른 화면(경로나 쿼리가 다른 칸)으로 옮겨지는 순간 run 을
 * 부른다. 뗄 때 부를 함수를 돌려준다.
 *
 * 부르는 때는 주소가 바뀐 직후, Next 가 popstate 에서 그 칸을 되살리기 전이다
 * (11-12 Chrome 에서 잰 순서: currententrychange, popstate). 확인 창이 이동을
 * 막으면(ExitGuard) 오지 않는다.
 *
 * popstate 를 듣지 않는 이유: 같은 화면 안의 # 이동(약관의 목차)도 popstate 를
 * 일으킨다. 거기서 화면을 새로 받으면 Next 가 주소를 자기가 아는 주소로
 * 바꿔치기해 # 이 지워지고, 뒤로 가기가 엉뚱한 절로 튄다(11-12 확인).
 * currententrychange 는 이동 종류(traverse)와 떠나온 칸(from)을 알려 줘서 그런
 * 이동을 가를 수 있다. 바로 앞 칸과 주소가 같은 칸으로 돌아갈 때(stepOffRepeat)도
 * 부르지 않는다. 그때 Next 는 지금 그린 화면을 그대로 쓴다(Next 16.4 의
 * restore-reducer 기준. Next 를 올리면 로그인·로그아웃 뒤 화면을 다시 본다).
 *
 * Navigation API 가 없는 브라우저에서는 아무것도 안 한다. 그곳에서는 탭과
 * "홈으로" 가 돌아가지 않고 바꿔치기만 해서, 뒤로 가기로 옛 화면을 볼 일이
 * 이 변경 전과 같다.
 */
export function onTraverseToOtherScreen(run: () => void): () => void {
  const nav = navigationApi();
  if (!nav) return () => {};
  const listen = (event: Event) => {
    const { navigationType, from } = event as EntryChange;
    if (navigationType !== "traverse" || !from?.url) return;
    const left = new URL(from.url);
    const here = window.location;
    if (left.pathname === here.pathname && left.search === here.search) return;
    run();
  };
  nav.addEventListener("currententrychange", listen);
  return () => nav.removeEventListener("currententrychange", listen);
}
