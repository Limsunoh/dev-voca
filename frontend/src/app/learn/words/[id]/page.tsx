import { notFound } from "next/navigation";

import {
  DetailBack,
  DetailCard,
  DetailHero,
  DetailMeaning,
  DetailShell,
} from "@/components/DetailLayout";
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
    <DetailShell>
      <DetailBack href={routes.words} label="단어장으로" />

      <DetailHero
        title={word.term}
        aside={word.pronunciation || undefined}
        reading={word.reading || undefined}
        meta={
          <>
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
          </>
        }
      />

      <DetailMeaning>{word.meaning}</DetailMeaning>

      {/* 발음 설명은 접어둔다. 목록에서 훑을 때는 필요 없고, 상세에서도
          "왜 그렇게 읽는지" 가 궁금한 사람만 연다. 펼친 채로 두면 뜻보다
          먼저 눈에 들어와 읽는 순서가 뒤집힌다.

          details/summary 를 쓰는 이유: 여는 상태를 브라우저가 들고 있어
          클라이언트 컴포넌트로 만들 필요가 없고, 키보드와 스크린리더가
          그냥 동작한다. */}
      {word.reading_note && (
        <details className="rise mt-4 [animation-delay:240ms]">
          <summary className="inline-flex min-h-11 cursor-pointer items-center text-sm text-slate-400 transition-colors hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">
            발음 자세히
          </summary>
          <p className="mt-2 text-pretty text-slate-300">{word.reading_note}</p>
        </details>
      )}

      {word.description && (
        <DetailCard label="설명" delay="[animation-delay:280ms]">
          <p className="whitespace-pre-line text-pretty">{word.description}</p>
        </DetailCard>
      )}

      {word.example && (
        <DetailCard label="예문" delay="[animation-delay:360ms]" raised>
          {/* 예문은 코드에 가까워 고정폭으로 둔다. 번역은 사람이 쓴
              문장이라 가변폭이 읽기 좋다. */}
          <p className="font-mono text-[1rem] leading-relaxed text-slate-100">
            {word.example}
          </p>
          {word.example_translation && (
            <p className="mt-3 border-t border-white/10 pt-3 text-slate-400">
              {word.example_translation}
            </p>
          )}
        </DetailCard>
      )}
    </DetailShell>
  );
}
