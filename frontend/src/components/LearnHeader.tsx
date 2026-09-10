import { ContentTabs } from "@/components/ContentTabs";

/**
 * 학습 화면 공통 머리말.
 *
 * 콘텐츠 탭(단어/문장)만 둔다. 모드(익히기/문제풀기)는 아래 탭바가 맡는다 -
 * 여기에도 두면 같은 이동 수단이 한 화면에 두 번 나온다.
 *
 * 프로토타입(ui_kits/devvoca-web/WordListScreen.jsx)은 탭을 ScreenHeader 의
 * aside 슬롯에 넣어 제목 오른쪽에 붙였다. 우리는 제목 위에 그대로 둔다 -
 * 제목이 24px 900 인데 그 옆에 세그먼트 알약이 서면 폰 폭(390)에서 제목이
 * 밀려 두 줄이 된다. 프로토타입 제목은 "단어장" 세 글자 고정이라 안 밀렸다.
 */
export function LearnHeader({
  mode,
  content,
  title,
  description,
}: {
  /** 지금 모드의 slug. 예: learn */
  mode: string;
  /** 지금 콘텐츠의 slug. 예: words */
  content: string;
  title: string;
  description: string;
}) {
  return (
    <header>
      <ContentTabs mode={mode} current={content} />

      {/* 크림에서 제목 굵기가 900 으로 올라갔다. 카드가 3px 두께를 갖고
          서 있어서 700 짜리 제목은 그 옆에서 가벼워 보인다. */}
      <h1
        className="mt-5"
        style={{
          fontSize: "var(--text-2xl)",
          fontWeight: "var(--weight-black)",
          letterSpacing: "var(--tracking-tight)",
          color: "var(--foreground)",
        }}
      >
        {title}
      </h1>
      <p
        className="mt-1"
        style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)" }}
      >
        {description}
      </p>
    </header>
  );
}
