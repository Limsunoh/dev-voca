import { notFound } from "next/navigation";

import {
  DetailAction,
  DetailBack,
  DetailCard,
  DetailHero,
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
      <DetailBack href={routes.words} label="단어장" />

      <DetailHero
        title={word.term}
        aside={word.pronunciation || undefined}
        reading={word.reading || undefined}
        meaning={word.meaning}
        meta={
          <>
            {word.category_label && (
              <CategoryChip
                label={word.category_label}
                href={`${routes.words}?category=${encodeURIComponent(word.category)}`}
              />
            )}
            {/* 상세는 목록 카드와 달리 과목 이름을 통째로 보여준다. 카드에서는
                자리가 없어 ExamBadge 가 "N과목" 만 잘라 쓰는데, 여기는 그
                과목이 무엇인지 읽을 공간이 있다. 정처기 준비생은 과목 단위로
                공부하므로 그 과목만 모아 볼 수 있게 링크로 둔다. */}
            {word.is_exam && (
              <CategoryChip
                label={word.exam_subject_label || "정처기 범위"}
                href={
                  word.exam_subject
                    ? `${routes.words}?is_exam=true&exam_subject=${encodeURIComponent(word.exam_subject)}`
                    : `${routes.words}?is_exam=true`
                }
              />
            )}
            <DifficultyBadge
              level={word.difficulty}
              label={word.difficulty_label}
            />
          </>
        }
      />

      {/* 발음 설명은 접어둔다. 목록에서 훑을 때는 필요 없고, 상세에서도
          "왜 그렇게 읽는지" 가 궁금한 사람만 연다. 펼친 채로 두면 뜻보다
          먼저 눈에 들어와 읽는 순서가 뒤집힌다.

          프로토타입에는 이 줄이 없다. 발음 설명 데이터 자체가 시안에
          없어서인데, 우리는 백엔드가 reading_note 를 채우고 있다.

          details/summary 를 쓰는 이유: 여는 상태를 브라우저가 들고 있어
          클라이언트 컴포넌트로 만들 필요가 없고, 키보드와 스크린리더가
          그냥 동작한다. */}
      {word.reading_note && (
        // group 이 있어야 아래 삼각형의 group-open:rotate-180 이 걸린다.
        <details className="rise group mt-3.5 [animation-delay:240ms]">
          <summary
            // 흰 알약 + 두께. 아래 정보 카드들과 같은 종이 위에 서야 이
            // 줄도 화면의 일부로 읽힌다. 맨몸 회색 글씨로 두면 크림 바탕에
            // 떠 있는 문장이 되어 눌리는 줄 모른다.
            className="dv-card dv-card-press flex min-h-11 w-fit cursor-pointer list-none items-center gap-2 rounded-full px-3.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus [&::-webkit-details-marker]:hidden"
            style={
              {
                background: "var(--paper)",
                color: "var(--foreground)",
                fontSize: "var(--text-sm)",
                fontWeight: "var(--weight-bold)",
                "--lift": "var(--lift-card)",
              } as React.CSSProperties
            }
          >
            발음 자세히
            {/* 삼각형은 CSS 로 돌린다. FilterPanel 의 summary 와 같은 문법.
                aria-hidden 인 이유: summary 자체가 이미 "확장/축소" 로 읽힌다. */}
            <span
              aria-hidden
              className="text-[0.625rem] transition-transform duration-150 group-open:rotate-180"
              style={{ color: "var(--text-faint)" }}
            >
              ▼
            </span>
          </summary>
          <p
            className="mt-2.5 px-1 text-pretty"
            style={{
              color: "var(--text-body)",
              lineHeight: "var(--leading-relaxed)",
            }}
          >
            {word.reading_note}
          </p>
        </details>
      )}

      {word.description && (
        <DetailCard label="설명" delay="[animation-delay:280ms]">
          <p className="whitespace-pre-line text-pretty">{word.description}</p>
        </DetailCard>
      )}

      {word.example && (
        // 반전 카드. 이 화면의 시각적 강조점이다.
        <DetailCard label="예문" delay="[animation-delay:360ms]" tone="dark">
          {/* 예문은 코드에 가까워 고정폭으로 둔다. 번역은 사람이 쓴
              문장이라 가변폭이 읽기 좋다. */}
          <p
            lang="en"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-sm)",
              fontWeight: "var(--weight-medium)",
              lineHeight: "var(--leading-normal)",
            }}
          >
            {word.example}
          </p>
          {word.example_translation && (
            <p
              className="mt-2.5"
              style={{
                fontSize: "var(--text-sm)",
                color: "var(--text-on-dark)",
              }}
            >
              {word.example_translation}
            </p>
          )}
        </DetailCard>
      )}

      {/* 읽고 나서 할 일. 없으면 이 화면에서 나가는 길이 "뒤로" 하나뿐이다. */}
      <DetailAction href={routes.testWords}>이 단어로 문제 풀기</DetailAction>
    </DetailShell>
  );
}
