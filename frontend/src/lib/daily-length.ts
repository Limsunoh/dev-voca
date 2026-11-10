/**
 * 하루 공부량. 일일공부의 길이(5분·10분·30분) 중 하나를 골라 두면, 일일공부가
 * 고르는 화면 없이 그 길이로 바로 시작한다.
 *
 * 로그인한 사람은 계정(daily_length)에, 게스트는 이 기기의 쿠키에 둔다.
 * 게스트가 나중에 로그인하면 쿠키 값을 계정으로 옮긴다(session.carryGuestDailyLength).
 *
 * 값과 이름은 백엔드 StudyLength(apps/learning/models.py)와 같아야 한다.
 * daily-length.test.mts 가 두 쪽을 맞대 본다.
 */
export const DAILY_LENGTHS = [
  { value: "5m", label: "5분" },
  { value: "10m", label: "10분" },
  { value: "30m", label: "30분" },
] as const;

export type DailyLength = (typeof DAILY_LENGTHS)[number]["value"];

export function isDailyLength(value: unknown): value is DailyLength {
  return DAILY_LENGTHS.some((one) => one.value === value);
}

export function dailyLengthLabel(value: string): string | null {
  return DAILY_LENGTHS.find((one) => one.value === value)?.label ?? null;
}
