import Link from "next/link";
import type { ReactNode } from "react";

import { BrandName } from "@/components/BrandName";
import { HomeLink } from "@/components/HomeLink";

export type LegalSection = { id: string; title: string; body: ReactNode };

// 가입할 때 저장하는 backend/apps/accounts/models.py 의 TERMS_VERSION 과 같아야
// 누가 어느 문서에 동의했는지 가릴 수 있다. 어긋나면 테스트가 실패한다.
// 약관과 처리방침이 버전 하나를 같이 쓴다. v3 은 처리방침만 바뀌었다.
export const DOC_VERSION = "v3";

// 약관 시행일. 시행일은 화면을 올리는 날이다.
export const EFFECTIVE_DATE = "2026년 11월 9일";

/**
 * 처리방침을 마지막으로 바꾼 공고일과 시행일(한국 시간, YYYY-MM-DD).
 *
 * 처리방침 14절이 "바꾸면 시행 7일 전부터 서비스 화면에 알린다" 고 약속한다.
 * 그래서 머지하는 날을 공고일로, 그 7일 뒤를 시행일로 두고, 시행일 전까지 홈에
 * 알림을 띄운다(PolicyNotice). 다음에 처리방침을 바꿀 때도 이 두 날짜만 고치면
 * 알림이 다시 뜬다.
 *
 * v3 의 시행일은 서버가 운영 로그에 오류 메시지를 싣기 시작하는 날
 * (backend/apps/accounts/error_mail.py 의 MESSAGE_FROM)과 같아야 한다. 어긋나면
 * 테스트가 실패한다.
 */
export const PRIVACY_CHANGE = {
  announced: "2026-11-12",
  effective: "2026-11-19",
};

/** "2026-11-19" 를 "2026년 11월 19일" 로. 문서의 다른 날짜와 같은 꼴이다. */
export function koreanDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return `${year}년 ${month}월 ${day}일`;
}

const CONTACT = "vhtmxjooo@gmail.com";

export function ContactEmail() {
  return <a href={`mailto:${CONTACT}`}>{CONTACT}</a>;
}

/**
 * 처리방침, 약관, 계정 삭제 안내가 같이 쓰는 틀.
 *
 * 글이 길어서 문단마다 클래스를 달지 않고 바깥 한 곳에서 p·ul·ol 의 모양을
 * 정한다. 링크(목차, 메일 주소, 홈·다른 문서로 가기)의 밑줄과 키보드 포커스
 * 테두리도 같은 곳에서 준다. 본문에 링크가 새로 들어와도 빠지지 않는다.
 * 로그인 없이 열려야 하므로 서버에서 아무것도 읽지 않는다.
 */
export function LegalDoc({
  title,
  intro,
  sections,
  other,
  showVersion = true,
  effectiveDate = EFFECTIVE_DATE,
}: {
  title: string;
  intro?: ReactNode;
  sections: LegalSection[];
  other: { href: string; label: string };
  /** 동의를 받는 문서(처리방침·약관)만 버전을 보인다. 안내 글에는 없다. */
  showVersion?: boolean;
  /** 버전 줄의 시행일. 처리방침은 약관과 따로 바뀌어 자기 날짜를 넘긴다. */
  effectiveDate?: string;
}) {
  return (
    <main
      className="mx-auto w-full max-w-2xl flex-1 px-4 py-8 text-base leading-7 [overflow-wrap:anywhere] [&_a]:underline [&_a]:underline-offset-4 [&_a:focus-visible]:outline [&_a:focus-visible]:outline-2 [&_a:focus-visible]:outline-offset-2 [&_a:focus-visible]:outline-focus [&_code]:font-mono [&_code]:text-sm [&_h3]:mt-5 [&_h3]:font-bold [&_h3]:text-balance [&_p]:mt-3 [&_section_ol]:mt-3 [&_section_ol]:list-decimal [&_section_ol]:space-y-2 [&_section_ol]:pl-5 [&_section_ul]:mt-3 [&_section_ul]:list-disc [&_section_ul]:space-y-2 [&_section_ul]:pl-5"
      style={{ color: "var(--text-body)" }}
    >
      <HomeLink
        className="inline-flex items-center text-sm"
        style={{ minHeight: "var(--hit-floor)", color: "var(--text-muted)" }}
      >
        {/* 링크가 flex 라 이름과 " 홈으로" 를 그대로 두면 서로 다른 칸이 되고,
            칸 맨 앞 공백이 지워져 "DeVoca홈으로" 로 붙는다. 한 칸으로 묶는다. */}
        <span>
          <BrandName /> 홈으로
        </span>
      </HomeLink>

      <h1
        className="mt-2 text-2xl"
        style={{
          color: "var(--text-strong)",
          fontWeight: "var(--weight-black)",
        }}
      >
        {title}
      </h1>
      {showVersion && (
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          버전 {DOC_VERSION} · 시행일 {effectiveDate}
        </p>
      )}
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
