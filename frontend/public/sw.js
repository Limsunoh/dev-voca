/*
 * 인터넷이 끊겼을 때 안내 화면을 띄우는 service worker.
 *
 * Google Play 의 Android 앱(TWA)은 화면을 열 때 응답을 못 받으면 Chrome 이 그것을
 * 앱 오류로 셀 수 있다. 그래서 화면 이동 요청이 실패하면 미리 받아 둔
 * offline.html 을 대신 돌려준다.
 *
 * 그 밖의 요청(API, 그림, 스크립트)은 건드리지 않는다. 캐시에서 옛 화면을
 * 내주기 시작하면 배포한 내용이 앱에 바로 안 나간다.
 *
 * offline.html 을 고치면 아래 CACHE 의 숫자를 하나 올린다(v2 -> v3). 2026-11-11 에
 * 버튼 색을 갈색으로 바꾸며 v1 -> v2 로 올렸다. 브라우저는 이
 * 파일(sw.js)이 바뀔 때만 다시 설치하고, 안내 화면도 그때만 새로 받는다.
 *
 * 웹 푸시를 붙이게 되면 이 파일에 push 처리를 더한다. 같은 주소(/)에는
 * service worker 를 하나만 둘 수 있다. 걷어낼 때는 이 파일을 지우지 말고
 * self.registration.unregister() 만 하는 내용으로 바꿔 배포한다. 지우면 이미
 * 설치된 폰에는 옛 service worker 가 그대로 남는다.
 *
 * navigation preload 를 켠 상태는 이 파일이 아니라 폰의 등록 정보에 남는다.
 * fetch 처리를 preloadResponse 를 안 쓰게 바꾸면 activate 에서
 * navigationPreload.disable() 도 부른다. 안 부르면 화면 요청이 두 번 나간다.
 */
const CACHE = "offline-v2";
const OFFLINE_URL = "/offline.html";

self.addEventListener("install", (event) => {
  // 브라우저의 HTTP 캐시를 거치지 않고 새로 받는다. 거치면 CACHE 를 올려도
  // 옛 안내 화면이 담길 수 있다.
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.add(new Request(OFFLINE_URL, { cache: "reload" }))),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    Promise.all([
      // service worker 가 깨어나는 동안 화면 요청을 미리 보내 둔다. 없으면 화면을
      // 옮길 때마다 깨어나길 기다린 뒤에야 요청이 나가 첫 화면이 늦게 뜬다.
      self.registration.navigationPreload?.enable(),
      // 이 파일이 만든 옛 안내 화면 캐시만 지운다. 다른 기능이 캐시를 따로 두어도
      // 건드리지 않는다.
      caches
        .keys()
        .then((names) =>
          Promise.all(
            names
              .filter((n) => n.startsWith("offline-") && n !== CACHE)
              .map((n) => caches.delete(n)),
          ),
        ),
    ]).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(
    (async () => {
      try {
        return (await event.preloadResponse) ?? (await fetch(event.request));
      } catch {
        return (await caches.match(OFFLINE_URL)) ?? Response.error();
      }
    })(),
  );
});
