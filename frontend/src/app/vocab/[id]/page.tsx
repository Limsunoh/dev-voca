import Link from "next/link";
import { notFound } from "next/navigation";

import { getWord } from "@/lib/api/vocab";

// Next 16 에서 params 는 Promise 다.
type PageProps = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  const word = await getWord(id);
  if (!word) return { title: "단어를 찾을 수 없습니다 | devvoca" };

  return {
    title: `${word.term} | devvoca`,
    description: word.meaning,
  };
}

export default async function WordDetailPage({ params }: PageProps) {
  const { id } = await params;
  const word = await getWord(id);

  // 검수 안 된 단어도 백엔드가 404 를 주므로 여기로 온다.
  if (!word) notFound();

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <Link
        href="/vocab"
        className="text-sm text-slate-500 hover:underline dark:text-slate-400"
      >
        &larr; 단어장으로
      </Link>

      <header className="mt-4 flex flex-wrap items-baseline gap-3">
        <h1 className="font-mono text-3xl font-bold text-slate-900 dark:text-slate-100">
          {word.term}
        </h1>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {word.difficulty_label}
        </span>
        {word.category && (
          <span className="text-sm text-slate-500 dark:text-slate-400">
            {word.category}
          </span>
        )}
      </header>

      <p className="mt-2 text-xl text-slate-800 dark:text-slate-200">
        {word.meaning}
      </p>

      {word.description && (
        <Section title="설명">
          <p className="whitespace-pre-line">{word.description}</p>
        </Section>
      )}

      {word.example && (
        <Section title="예문">
          <p className="font-mono text-slate-800 dark:text-slate-200">
            {word.example}
          </p>
          {word.example_translation && (
            <p className="mt-2 text-slate-600 dark:text-slate-400">
              {word.example_translation}
            </p>
          )}
        </Section>
      )}

      {word.source && (
        <p className="mt-8 text-xs text-slate-400 dark:text-slate-500">
          출처: {word.source}
        </p>
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
