import Link from "next/link";

import { PRIVACY_CHANGE } from "@/components/LegalDoc";

/** 오늘 날짜(한국 시간, YYYY-MM-DD). sv-SE 는 날짜를 그 꼴로 쓰는 로캘이다. */
export function seoulToday(): string {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });
}

/**
 * 처리방침이 바뀐다는 알림. 시행일 전까지 홈에 뜬다.
 *
 * 처리방침 14절이 "바꾸면 시행 7일 전부터 서비스 화면에 알린다" 고 약속해서
 * 둔다. 홈에 두는 이유: 앱을 열면 처음 뜨는 화면이다(manifest 의 start_url).
 * 시행일이 지나면 그리지 않으므로 지울 필요가 없다. 다음에 처리방침을 바꿀 때
 * PRIVACY_CHANGE 의 날짜만 고치면 다시 뜬다.
 *
 * 홈은 쿠키를 읽어 요청마다 서버에서 그린다. 그래서 날짜를 서버에서 비교해도
 * 빌드한 날에 굳지 않는다.
 */
export function PolicyNotice({ today = seoulToday() }: { today?: string }) {
  if (today >= PRIVACY_CHANGE.effective) return null;
  // 해는 뺀다. 7일 뒤 날짜라 헷갈릴 일이 없고, 넣으면 360폭 폰에서 두 줄이 된다.
  const [, month, day] = PRIVACY_CHANGE.effective.split("-").map(Number);
  return (
    <Link
      href="/privacy#changes"
      className="mt-3 inline-flex min-h-11 items-center self-start text-sm underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      style={{ color: "var(--text-muted)" }}
    >
      개인정보 처리방침이 {month}월 {day}일부터 바뀝니다
    </Link>
  );
}
