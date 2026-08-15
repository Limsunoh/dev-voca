import Link from "next/link";
import { notFound } from "next/navigation";

import { CategoryChip, DifficultyBadge } from "@/components/MetaBadge";
import { getWord } from "@/lib/api/vocab";
import { routes } from "@/lib/routes";

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
        href={routes.words}
        className="text-sm text-slate-500 hover:underline dark:text-slate-400"
      >
        &larr; 단어장으로
      </Link>

      {/* 단어와 발음기호가 한 줄, 부가 정보는 아랫줄로 내린다. 넷을 한 줄에
          쓸어 담으면 난이도와 분류가 제목 옆에 붙은 잔글씨로 보여서
          눈에 들어오지 않는다. */}
      <header className="mt-4">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="font-mono text-4xl font-bold text-slate-900 dark:text-slate-50">
            {word.term}
          </h1>
          {word.pronunciation && (
            // 발음기호는 고정폭으로 두지 않는다. IPA 기호가 고정폭 글꼴에서
            // 깨지거나 폭이 어긋나는 경우가 있다.
            <span
              lang="en-US"
              className="text-lg text-slate-500 dark:text-slate-300"
            >
              {word.pronunciation}
            </span>
          )}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <DifficultyBadge
            level={word.difficulty}
            label={word.difficulty_label}
          />
          {word.category_label && (
            <CategoryChip
              label={word.category_label}
              href={`${routes.words}?category=${encodeURIComponent(word.category)}`}
            />
          )}
        </div>
      </header>

      <p className="mt-5 text-2xl leading-snug font-semibold tracking-tight text-slate-800 dark:text-slate-100">
        {word.meaning}
      </p>

      {word.description && (
        <Section title="설명">
          <p className="whitespace-pre-line">{word.description}</p>
        </Section>
      )}

      {word.example && (
        <Section title="예문">
          <p className="font-mono text-slate-800 dark:text-slate-100">
            {word.example}
          </p>
          {word.example_translation && (
            <p className="mt-2.5 text-slate-600 dark:text-slate-300">
              {word.example_translation}
            </p>
          )}
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
    // 제목이 본문보다 작고 흐리면 어디서 무엇이 시작되는지 안 보인다.
    // 본문과 같은 크기로 올리고 굵기와 색으로 구분한다.
    <section className="mt-9">
      <h2 className="text-base font-semibold text-slate-500 dark:text-slate-200">
        {title}
      </h2>
      <div className="mt-2.5 text-lg leading-relaxed text-slate-700 dark:text-slate-200">
        {children}
      </div>
    </section>
  );
}
