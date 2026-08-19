import Link from "next/link";

import { LearnHeader } from "@/components/LearnHeader";
import { contentPath } from "@/lib/routes";

export const metadata = {
  title: "문장 문제풀기 | devvoca",
  description: "문장 문제는 준비 중입니다.",
};

/**
 * 아직 만들지 않은 화면.
 *
 * 콘텐츠 탭에서 "문장" 을 누르면 여기로 온다. 페이지 자체가 없으면
 * 404 가 뜨는데, 탭이 보이는데 눌렀더니 404 인 것은 고장으로 읽힌다.
 * 준비 중이라고 알려주고 갈 곳을 준다.
 */
export default function TestSentencesPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <LearnHeader
        mode="test"
        content="sentences"
        title="문장 문제풀기"
        description="준비 중입니다."
      />

      <p className="mt-8 rounded-lg border border-white/12 bg-slate-950/45 p-6 text-center text-slate-300">
        문장 문제는 아직 만들지 않았습니다. 단어 문제부터 풀어보세요.
      </p>

      {/* flex-wrap 을 준다. 글자를 200% 로 키우면 버튼 둘이 한 줄에 못
          들어가는데, 안 주면 줄바꿈 대신 화면 밖으로 밀린다. */}
      <div className="mt-6 flex flex-wrap gap-2.5">
        <Link
          href={contentPath("test", "words")}
          className="flex min-h-12 flex-1 items-center justify-center rounded-full bg-focus px-5 font-semibold text-focus-on transition-[scale] duration-[120ms] ease-press active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          단어 문제풀기
        </Link>
        <Link
          href={contentPath("learn", "sentences")}
          // 테두리가 유일한 "여기가 버튼" 신호라 white/40 아래로 내리지
          // 않는다. WCAG 1.4.11 이 컨트롤 경계에 3:1 을 요구하는데
          // white/15 는 1.5:1 이라 떠 있는 글자로 읽힌다.
          className="flex min-h-12 flex-1 items-center justify-center rounded-full border border-white/40 px-5 font-semibold text-slate-100 transition-[scale,border-color] duration-[120ms] ease-press hover:border-white/60 active:scale-[0.96] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          문장 익히기
        </Link>
      </div>
    </main>
  );
}
