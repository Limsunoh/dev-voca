"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

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
  label = "단어 검색",
  placeholder = "단어, 뜻, 설명으로 검색",
}: {
  basePath: string;
  /** 스크린리더용 라벨. 화면에는 안 보인다. */
  label?: string;
  placeholder?: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentSearch = searchParams.get("search") ?? "";

  const [value, setValue] = useState(currentSearch);

  function submit(next: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (next) {
      params.set("search", next);
    } else {
      params.delete("search");
    }
    // 검색어가 바뀌면 1페이지부터 다시 본다.
    params.delete("page");

    const qs = params.toString();
    router.push(qs ? `${basePath}?${qs}` : basePath);
  }

  return (
    <form
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        submit(value.trim());
      }}
      className="flex gap-2"
    >
      <label htmlFor="search" className="sr-only">
        {label}
      </label>
      <input
        id="search"
        name="search"
        type="search"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
      <button
        type="submit"
        className="shrink-0 rounded-md bg-slate-900 px-4 py-2 font-medium text-white transition hover:bg-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
      >
        검색
      </button>
    </form>
  );
}
