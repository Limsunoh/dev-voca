"use client";

import { useRouter } from "next/navigation";
import { type ReactNode, startTransition, useEffect, useState } from "react";

/** 이미 그린 서버 응답의 번호. 탭을 새로 열면 비므로 쌓일 일이 없다. */
const seen = new Set<string>();

/**
 * 뒤로·앞으로 가기로 돌아왔을 때 서버 응답을 새로 받은 뒤에 화면을 그린다.
 *
 * 뒤로 가기는 서버에 묻지 않고 처음 받아 둔 응답으로 화면을 다시 만든다
 * (Next 의 staleTimes 로도 못 끈다). 서버 상태가 그사이 바뀌는 화면이면 이미 푼
 * 문제가 다시 뜬다.
 *
 * 서버가 그릴 때마다 새 renderId 를 주므로, 이미 본 번호가 또 오면 옛 응답이다.
 * popstate 를 듣지 않는 이유: 이 파일은 화면에 처음 들어올 때 불러와져 Next 의
 * 리스너보다 뒤에 붙는데, Next 는 자기 리스너 안에서 화면까지 다 그린다. 들었을
 * 때는 이미 늦다.
 *
 * children 을 새 응답이 올 때까지 그리지 않는다. 먼저 그리면 useState 의 초깃값이
 * 옛 응답으로 굳고, 잠깐이라도 옛 문제를 눌러 볼 수 있다.
 */
export function RefreshOnBack({
  renderId,
  children,
}: {
  renderId: string;
  children: ReactNode;
}) {
  const router = useRouter();
  const [stale, setStale] = useState(() => seen.has(renderId));

  // 새로 받은 응답도 적어 둔다. 안 적으면 두 번째 뒤로 가기를 놓친다.
  useEffect(() => {
    seen.add(renderId);
  }, [renderId]);

  useEffect(() => {
    if (!stale) return;
    // 같은 transition 이라 새 응답이 도착해야 stale 도 함께 풀린다.
    startTransition(() => {
      router.refresh();
      setStale(false);
    });
  }, [stale, router]);

  if (stale) {
    return (
      <p
        role="status"
        className="py-10 text-center text-sm"
        style={{ color: "var(--text-muted)" }}
      >
        불러오는 중입니다.
      </p>
    );
  }
  return children;
}
