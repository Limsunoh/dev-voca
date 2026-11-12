"use client";

import { useState } from "react";

/**
 * 가입 동의 체크박스. 가입 화면과 필수 항목 시트가 같이 쓴다. 공개·해외 항목은
 * 가입할 때 받는 동의라 계정이 없는 게스트에게는 묻지 않고 둘만 묻는다.
 *
 * 처음에는 꺼져 있다. 미리 켜 두면 사용자가 하지 않은 동의가 된다.
 *
 * 회원 가입은 서버가 실제로 막고 화면은 안내만 한다(SignUpSerializer,
 * GoogleLoginView). 게스트는 저장할 곳이 없어 화면에서만 묻는다.
 *
 * 문서 링크를 새 탭으로 여는 이유: 같은 탭으로 가면 돌아왔을 때 입력한
 * 값이 사라진다. 새 탭이라 미리 불러올 일이 없어서 next/link 를 쓰지 않는다.
 */

/** 체크 상태. 물어본 항목을 다 켜야 ready 다. */
export function useConsent(needsDisclosure = true, idPrefix = "consent") {
  const [terms, setTerms] = useState(false);
  const [disclosure, setDisclosure] = useState(false);
  const [age, setAge] = useState(false);
  const [nudged, setNudged] = useState(false);

  // 잠긴 버튼을 눌렀을 때. 왜 잠겼는지 알리고 아직 안 켠 칸으로 데려간다.
  // 그냥 무시하면 다 입력하고 Enter 를 눌러도 아무 일이 안 일어난다.
  function guide() {
    setNudged(true);
    const first = !terms
      ? "terms"
      : needsDisclosure && !disclosure
        ? "disclosure"
        : "age";
    document.getElementById(`${idPrefix}-${first}`)?.focus();
  }

  // "전체 동의" 칸. 물어본 항목만 한꺼번에 켜고 끈다. 게스트에게 묻지 않는
  // 공개·해외 항목(needsDisclosure=false)은 건드리지 않는다.
  function setAll(value: boolean) {
    setTerms(value);
    setAge(value);
    if (needsDisclosure) setDisclosure(value);
  }

  return {
    terms,
    disclosure,
    age,
    setTerms,
    setDisclosure,
    setAge,
    setAll,
    idPrefix,
    needsDisclosure,
    ready: terms && age && (disclosure || !needsDisclosure),
    nudged,
    guide,
  };
}

/** 구글 시작 주소. 세 항목을 켠 뒤에만 이 주소로 보낸다. */
export function googleConsentHref(next?: string): string {
  const query = new URLSearchParams({ consent: "1" });
  if (next) query.set("next", next);
  return `/api/auth/google?${query.toString()}`;
}

type Props = ReturnType<typeof useConsent>;

export function ConsentChecks({
  terms,
  disclosure,
  age,
  setTerms,
  setDisclosure,
  setAge,
  setAll,
  idPrefix,
  needsDisclosure,
  ready,
  nudged,
}: Props) {
  return (
    <div className="grid gap-1">
      {/* 한 번에 켜는 칸. 따로 상태를 두지 않고 "물어본 항목이 다 켜졌나" 를
          그대로 보여 준다. 그래야 하나씩 다 켜면 이 칸도 켜지고, 하나라도
          끄면 같이 꺼져 두 표시가 어긋나지 않는다. 아래 항목은 그대로 보여
          무엇에 동의하는지 하나씩 읽고 켤 수도 있다. */}
      <Check id={`${idPrefix}-all`} checked={ready} onChange={setAll}>
        <span style={{ fontWeight: "var(--weight-bold)" }}>전체 동의</span>
        {/* 화면 낭독기는 이 칸에서 "전체 동의" 만 읽어, 무엇을 한꺼번에
            켜는지 칸을 지나간 뒤에야 안다. 보는 사람은 아래 목록이 같이
            보인다. */}
        <span className="sr-only">
          {` (아래 필수 ${needsDisclosure ? "세" : "두"} 항목에 모두 동의)`}
        </span>
      </Check>
      {/* 색은 같은 화면의 "또는" 구분선(AuthForm)과 맞춘다. */}
      <hr
        aria-hidden="true"
        className="my-1"
        style={{ border: 0, height: 1, background: "var(--sand-deep)" }}
      />
      <Check id={`${idPrefix}-terms`} checked={terms} onChange={setTerms}>
        <span style={{ fontWeight: "var(--weight-bold)" }}>[필수]</span>{" "}
        <DocLink href="/terms">이용약관</DocLink>과{" "}
        <DocLink href="/privacy">개인정보 처리방침</DocLink>에 동의합니다
      </Check>
      {needsDisclosure && (
        <Check
          id={`${idPrefix}-disclosure`}
          checked={disclosure}
          onChange={setDisclosure}
        >
          <span style={{ fontWeight: "var(--weight-bold)" }}>[필수]</span>{" "}
          순위표에 이름과 사진이 공개되고, 정보가 해외 업체(미국·싱가포르 등)에
          보관되는 것에 동의합니다
        </Check>
      )}
      <Check id={`${idPrefix}-age`} checked={age} onChange={setAge}>
        <span style={{ fontWeight: "var(--weight-bold)" }}>[필수]</span> 만
        14세 이상입니다
      </Check>
      {/* 알림 자리는 항상 그린다. 내용과 함께 새로 생기면 화면 낭독기가
          그 등장을 대부분 안 읽는다. */}
      <div aria-live="polite">
        {nudged && !ready && (
          <p className="text-sm" style={{ color: "var(--coral-deep)" }}>
            {needsDisclosure ? "세" : "두"} 항목을 모두 켜 주세요.
          </p>
        )}
      </div>
    </div>
  );
}

/**
 * 구글 버튼 근처의 안내 한 줄.
 *
 * 구글 이름과 사진을 순위표에 그대로 쓰므로, 가입 전에 알려야 한다.
 */
export function GoogleNameNote() {
  return (
    <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
      순위표에 오르면 구글 이름과 사진이 보입니다. 내정보에서 이름이나 아바타를
      바꿀 수 있습니다.
    </p>
  );
}

function Check({
  id,
  checked,
  onChange,
  children,
}: {
  id: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    // 줄 전체가 label 이라 빈 곳을 눌러도 켜진다. 높이는 44px. 안쪽 문서
    // 링크는 눌러도 체크가 바뀌지 않는다.
    <label
      className="flex cursor-pointer items-center gap-2.5 text-sm"
      style={{ minHeight: "var(--hit-floor)", color: "var(--text-body)" }}
    >
      <input
        id={id}
        type="checkbox"
        // 뒤로 가기로 돌아올 때 브라우저가 체크 표시만 되살리지 않게 한다.
        // 되살리면 칸은 켜져 있는데 상태는 꺼져 있어 버튼이 잠긴 채로 남는다.
        autoComplete="off"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-5 w-5 flex-none cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        style={{ accentColor: "var(--brand)" }}
      />
      <span>{children}</span>
    </label>
  );
}

function DocLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      style={{
        color: "var(--brand)",
        fontWeight: "var(--weight-bold)",
      }}
    >
      {children}
      <span className="sr-only"> (새 탭에서 열림)</span>
    </a>
  );
}
