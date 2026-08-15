import Link from "next/link";
import { notFound } from "next/navigation";

import { CategoryChip, DifficultyBadge } from "@/components/MetaBadge";
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
        <CategoryChip label={sentence.kind_label} />
        <DifficultyBadge
          level={sentence.difficulty}
          label={sentence.difficulty_label}
        />
        {sentence.category_label && (
          <CategoryChip
            label={sentence.category_label}
            href={`${routes.sentences}?category=${encodeURIComponent(sentence.category)}`}
          />
        )}
      </div>

      {/* 크기를 삼항 안에서 통째로 고른다. 기본 크기를 밖에 두고 안에서
          덮으려 하면 안 먹는다 - Tailwind 는 같은 속성 유틸을 이름순으로
          출력하므로 class 문자열의 순서가 우선순위를 정하지 않는다.
          (text-3xl 이 text-2xl 보다 뒤에 나와서 늘 이긴다.) */}
      <h1
        className={`mt-4 leading-snug font-bold tracking-tight text-slate-900 dark:text-slate-50 ${
          isError ? "font-mono text-2xl" : "text-3xl"
        }`}
      >
        {sentence.text}
      </h1>

      <p className="mt-4 text-xl leading-snug text-slate-800 dark:text-slate-100">
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
