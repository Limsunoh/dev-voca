import Link from "next/link";
import { notFound } from "next/navigation";

import { getSentence } from "@/lib/api/sentences";
import { routes } from "@/lib/routes";

// Next 16 에서 params 는 Promise 다.
type PageProps = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  const sentence = await getSentence(id);
  if (!sentence) return { title: "문장을 찾을 수 없습니다 | devvoca" };

  // 문장은 길어서 제목에 통째로 넣으면 탭 이름이 잘린다.
  const head =
    sentence.text.length <= 40
      ? sentence.text
      : `${sentence.text.slice(0, 40)}...`;

  return {
    title: `${head} | devvoca`,
    description: sentence.translation,
  };
}

export default async function SentenceDetailPage({ params }: PageProps) {
  const { id } = await params;
  const sentence = await getSentence(id);

  // 검수 안 된 문장도 백엔드가 404 를 주므로 여기로 온다.
  if (!sentence) notFound();

  // 에러 메시지는 코드에 가까워 고정폭이 읽기 좋다.
  const isError = sentence.kind === "error";

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <Link
        href={routes.sentences}
        className="text-sm text-slate-500 hover:underline dark:text-slate-400"
      >
        &larr; 문장으로
      </Link>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {sentence.kind_label}
        </span>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {sentence.difficulty_label}
        </span>
        {sentence.category_label && (
          <Link
            href={`${routes.sentences}?category=${encodeURIComponent(sentence.category)}`}
            className="text-sm text-slate-500 underline-offset-4 hover:underline dark:text-slate-400"
          >
            {sentence.category_label}
          </Link>
        )}
      </div>

      <h1
        className={`mt-3 text-2xl font-bold text-slate-900 dark:text-slate-100 ${
          isError ? "font-mono text-xl" : ""
        }`}
      >
        {sentence.text}
      </h1>

      <p className="mt-3 text-lg text-slate-800 dark:text-slate-200">
        {sentence.translation}
      </p>

      {sentence.context && (
        <Section title="어디서 나오나">
          <p>{sentence.context}</p>
        </Section>
      )}

      {sentence.description && (
        <Section title="설명">
          <p className="whitespace-pre-line">{sentence.description}</p>
        </Section>
      )}
    </main>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold text-slate-500 dark:text-slate-400">
        {title}
      </h2>
      <div className="mt-2 text-slate-700 dark:text-slate-300">{children}</div>
    </section>
  );
}
