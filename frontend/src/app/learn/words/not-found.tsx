import Link from "next/link";

import { routes } from "@/lib/routes";

// notFound() 가 호출되면 이 화면이 나온다. 없으면 Next 기본 영문 404 가 뜬다.
export default function VocabNotFound() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <h1
        style={{
          fontSize: "var(--text-2xl)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
          color: "var(--foreground)",
        }}
      >
        찾을 수 없습니다
      </h1>
      <p className="mt-2" style={{ color: "var(--text-muted)" }}>
        주소가 잘못되었거나, 아직 공개되지 않은 단어입니다.
      </p>

      {/* 이 화면의 유일한 동작이라 코랄을 준다. */}
      <Link
        href={routes.words}
        className="dv-btn mt-6 inline-flex items-center rounded-full px-5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        style={
          {
            background: "var(--coral)",
            color: "var(--text-on-color)",
            minHeight: "var(--hit-min)",
            fontWeight: "var(--weight-black)",
            letterSpacing: "var(--tracking-tight)",
            // 쉬는 두께는 --lift 로. 인라인 box-shadow 는 :active 를 이긴다.
            "--lift": "var(--lift-button)",
          } as React.CSSProperties
        }
      >
        단어장으로 돌아가기
      </Link>
    </main>
  );
}
