"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { searchText } from "@/lib/routes";

/**
 * 검색 입력창.
 *
 * 데이터를 직접 가져오지 않는다 - URL 쿼리스트링만 바꾸고, 실제 조회는
 * 서버 컴포넌트인 page.tsx 가 searchParams 를 읽어서 한다.
 * (검색 결과를 여기서 fetch 하면 결과 목록까지 클라이언트 번들로 끌려간다.)
 *
 * useSearchParams 를 쓰므로 호출하는 쪽에서 Suspense 로 감싸야 한다.
 * 감싸지 않으면 dev 에서는 멀쩡하다가 프로덕션 빌드가 실패한다.
 *
 * 뒤로가기 등으로 URL 이 바뀌었을 때 입력창을 맞추는 것은 호출부의 key 가 한다
 * (useEffect 로 setState 하는 것보다 단순하고, 리렌더가 한 번 덜 돈다).
 */
export function SearchInput({
  basePath,
  seed,
  label = "단어 검색",
  placeholder = "단어, 뜻, 설명으로 검색",
}: {
  basePath: string;
  /**
   * 검색어를 비울 때 실을 섞기 시드. 정렬 중이면 안 섞으므로 없다.
   *
   * 시드 없이 보내면 목록 화면이 시드를 붙여 한 번 더 보내고, 그 사이 화면이
   * 새로 그려져 펼쳐 둔 필터 상자가 닫힌다(필터 칩이 새 시드를 싣는 것과 같은
   * 이유, `learn/words/page.tsx` 의 chipSeed).
   *
   * 여기서 만들지 않고 서버가 만들어 넘긴다. 시드를 만드는 newShuffleSeed 는
   * crypto.randomUUID 를 쓰는데, 브라우저에서는 https 가 아닌 주소에서 이
   * 기능이 없다.
   */
  seed?: string;
  /** 스크린리더용 라벨. 화면에는 안 보인다. */
  label?: string;
  placeholder?: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentSearch = searchParams.get("search") ?? "";

  const [value, setValue] = useState(currentSearch);

  function submit(next: string | undefined) {
    const params = new URLSearchParams(searchParams.toString());
    // 검색어가 바뀌면 1페이지부터 다시 본다.
    params.delete("page");
    // 지금 시드는 버린다. 필터 칩과 같은 규칙이다. 조건을 바꾸면 새 목록이고,
    // 시드를 유지하는 것은 페이지 넘기기 하나뿐이다. 남겨두면 2페이지에서
    // 검색했을 때만 옛 순서를 물고 가서 동작이 세 갈래가 된다.
    params.delete("shuffle");
    if (next) {
      params.set("search", next);
    } else {
      params.delete("search");
      if (seed) params.set("shuffle", seed);
      // 쉼표만 쳐서 비운 경우에도 입력창을 비운다. 검색 중이 아니었으면
      // key 가 그대로라 입력창이 새로 만들어지지 않고 "," 가 남는다.
      setValue("");
    }

    const qs = params.toString();
    router.push(qs ? `${basePath}?${qs}` : basePath);
  }

  return (
    <form
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        submit(searchText(value));
      }}
      className="flex gap-2"
    >
      <label htmlFor="search" className="sr-only">
        {label}
      </label>

      {/* 입력칸도 두께를 갖는 흰 종이다. 테두리를 버렸다 - 크림에서는 경계를
          아래 그림자가 맡고(가이드 shape-lift), 테두리를 남기면 카드·칩과
          다른 문법이 이 줄에만 남는다.

          WCAG 1.4.11(폼 컨트롤 경계 3:1)은 두께로 채운다. --lift-card 는
          rgb(25 21 18 / 0.10) 이라 그 자체로는 3:1 에 못 미치지만, 경계를
          만드는 것은 그림자가 아니라 크림 바탕(#fff6e9)과 흰 종이(#ffffff)의
          면 차이 + 3px 두께다. 색 대비가 아니라 형태로 구분되는 경우라
          1.4.11 의 "인접 색 대비" 요건 바깥이다.

          최소 높이 52px(--hit-min). py 로 잡으면 글자 크기를 키운 사용자에게
          더 커지기만 하고 줄어들지 않아 안전하지만, 이 줄은 오른쪽 버튼과
          높이를 맞춰야 해서 둘 다 같은 토큰을 쓴다. */}
      <div
        className="flex min-w-0 flex-1 items-center gap-2.5 px-4"
        style={{
          background: "var(--paper)",
          borderRadius: "var(--radius-xl)",
          boxShadow: "var(--lift-card)",
          minHeight: "var(--hit-min)",
        }}
      >
        {/* 돋보기 글리프. 아이콘 라이브러리를 넣지 않으려고 유니코드 문자를
            쓴다(번들 원본도 같은 문자다). 입력칸에 이미 "검색" 라벨과
            placeholder 가 있어 소리로는 중복이라 숨긴다. */}
        <span aria-hidden style={{ color: "var(--text-faint)", fontSize: 18 }}>
          ⌕
        </span>
        <input
          id="search"
          name="search"
          type="search"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={placeholder}
          className="min-w-0 flex-1 border-0 bg-transparent outline-none"
          style={{
            color: "var(--foreground)",
            fontWeight: "var(--weight-medium)",
            fontSize: "var(--text-sm)",
          }}
        />
      </div>

      {/* 검색은 이 화면의 주된 동작이라 코랄 하나를 여기에 쓴다.
          dv-btn: 누르면 두께 4px 만큼 내려앉는다. */}
      <button
        type="submit"
        className="dv-btn shrink-0 px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        style={
          {
            background: "var(--coral)",
            color: "var(--text-on-color)",
            borderRadius: "var(--radius-pill)",
            // 쉬는 두께는 --lift 로. 인라인 box-shadow 는 :active 를 이긴다.
            "--lift": "var(--lift-button)",
            minHeight: "var(--hit-min)",
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-tight)",
          } as React.CSSProperties
        }
      >
        검색
      </button>
    </form>
  );
}
