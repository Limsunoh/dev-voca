import { apiBase } from "@/lib/api/client";

/**
 * 올린 프로필 사진 중계.
 *
 * 브라우저의 <img src> 가 이 주소를 직접 부른다. 백엔드 주소는 서버 전용
 * 환경변수라 브라우저가 알 수 없고, 안다 해도 다른 오리진이라 CORS 에
 * 묶인다. 그래서 같은 오리진의 이 자리를 거친다.
 *
 * 다른 중계(/api/daily 등)와 달리 **토큰을 붙이지 않는다.** 순위표가 남의
 * 아바타를 그리는 화면이고, 백엔드도 이 경로만은 로그인 없이 연다.
 * 여기서 내 토큰을 붙이면 남의 사진을 볼 때 쓸데없이 내 인증이 나간다.
 *
 * 응답 본문을 그대로 흘려보낸다. 바이트를 읽어 다시 만들면 Node 메모리에
 * 한 장씩 올라가는데, 순위표 한 화면이 스무 장을 동시에 부른다.
 *
 * 캐시 깨는 꼬리표(?v=)가 없다. 사진을 바꾸면 백엔드가 UUID 를 새로
 * 만들어 주소 자체가 달라지기 때문이다.
 */

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  // 경로에 무엇이든 들어올 수 있다. 그대로 끼우면 인코딩된 ../ 같은 값이
  // 요청을 API 밖으로 끌어낸다(client.ts 의 fetchDetail 과 같은 이유).
  //
  // 주소는 사용자 번호가 아니라 UUID 다. 번호면 1번부터 눌러보는 것만으로
  // 사진 올린 계정을 전부 훑을 수 있다(backend 의 avatar_photo_key 주석).
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
    return new Response(null, { status: 404 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBase()}/api/accounts/photo/${id}/`, {
      headers: {
        // 브라우저가 "이 판은 이미 있다" 고 하면 그대로 백엔드에 묻는다.
        // 안 넘기면 304 가 날 자리에서 매번 그림이 통째로 온다.
        ...(request.headers.get("if-none-match")
          ? { "If-None-Match": request.headers.get("if-none-match")! }
          : {}),
      },
      cache: "no-store",
    });
  } catch {
    // 백엔드가 안 떠 있는 경우. 화면은 이 그림이 안 뜨면 아바타로
    // 떨어지므로(Avatar.tsx 의 onError) 여기서는 상태만 알린다.
    return new Response(null, { status: 502 });
  }

  if (upstream.status === 304) {
    return new Response(null, {
      status: 304,
      headers: { ETag: upstream.headers.get("ETag") ?? "" },
    });
  }

  if (!upstream.ok) {
    return new Response(null, { status: upstream.status });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "image/webp",
      "Cache-Control":
        upstream.headers.get("Cache-Control") ?? "public, max-age=604800",
      ...(upstream.headers.get("ETag")
        ? { ETag: upstream.headers.get("ETag")! }
        : {}),
    },
  });
}
