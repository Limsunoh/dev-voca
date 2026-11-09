import Link from "next/link";
import type { ReactNode } from "react";

export type LegalSection = { id: string; title: string; body: ReactNode };

// 가입할 때 저장하는 backend/apps/accounts/models.py 의 TERMS_VERSION 과 같아야
// 누가 어느 문서에 동의했는지 가릴 수 있다. 어긋나면 테스트가 실패한다.
export const DOC_VERSION = "v2";

// 시행일은 화면을 올리는 날이다.
export const EFFECTIVE_DATE = "2026년 11월 9일";

const CONTACT = "vhtmxjooo@gmail.com";

export function ContactEmail() {
  return <a href={`mailto:${CONTACT}`}>{CONTACT}</a>;
}

/**
 * 처리방침과 약관이 같이 쓰는 틀.
 *
 * 글이 길어서 문단마다 클래스를 달지 않고 바깥 한 곳에서 p·ul·ol 의 모양을
 * 정한다. 로그인 없이 열려야 하므로 서버에서 아무것도 읽지 않는다.
 */
export function LegalDoc({
  title,
  intro,
  sections,
  other,
}: {
  title: string;
  intro?: ReactNode;
  sections: LegalSection[];
  other: { href: string; label: string };
}) {
  return (
    <main
      className="mx-auto w-full max-w-2xl flex-1 px-4 py-8 text-base leading-7 [overflow-wrap:anywhere] [&_a]:underline [&_a]:underline-offset-4 [&_code]:font-mono [&_code]:text-sm [&_h3]:mt-5 [&_h3]:font-bold [&_h3]:text-balance [&_p]:mt-3 [&_section_ol]:mt-3 [&_section_ol]:list-decimal [&_section_ol]:space-y-2 [&_section_ol]:pl-5 [&_section_ul]:mt-3 [&_section_ul]:list-disc [&_section_ul]:space-y-2 [&_section_ul]:pl-5"
      style={{ color: "var(--text-body)" }}
    >
      <Link
        href="/"
        className="inline-flex items-center text-sm"
        style={{ minHeight: "var(--hit-floor)", color: "var(--text-muted)" }}
      >
        devvoca 홈으로
      </Link>

      <h1
        className="mt-2 text-2xl"
        style={{
          color: "var(--text-strong)",
          fontWeight: "var(--weight-black)",
        }}
      >
        {title}
      </h1>
      <p className="text-sm" style={{ color: "var(--text-muted)" }}>
        버전 {DOC_VERSION} · 시행일 {EFFECTIVE_DATE}
      </p>
      {intro}

      <nav aria-label="목차" className="mt-6">
        <ol className="text-sm">
          {sections.map((section) => (
            <li key={section.id}>
              <a
                href={`#${section.id}`}
                className="inline-flex items-center"
                style={{ minHeight: "var(--hit-floor)" }}
              >
                {section.title}
              </a>
            </li>
          ))}
        </ol>
      </nav>

      {sections.map((section) => (
        <section
          key={section.id}
          id={section.id}
          aria-labelledby={`${section.id}-title`}
          className="mt-10"
        >
          <h2
            id={`${section.id}-title`}
            className="text-lg text-balance"
            style={{
              color: "var(--text-strong)",
              fontWeight: "var(--weight-bold)",
            }}
          >
            {section.title}
          </h2>
          {section.body}
        </section>
      ))}

      <footer className="mt-12 text-sm" style={{ color: "var(--text-muted)" }}>
        <p>
          <Link
            href={other.href}
            className="inline-flex items-center"
            style={{ minHeight: "var(--hit-floor)" }}
          >
            {other.label} 보기
          </Link>
        </p>
        <p>
          글꼴: Noto Sans KR, JetBrains Mono - SIL Open Font License 1.1 (
          <a href="https://openfontlicense.org">openfontlicense.org</a>)
        </p>
      </footer>
    </main>
  );
}
