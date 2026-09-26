import { FilterChip } from "@/components/FilterChip";
import type { ChoiceOption } from "@/lib/api/client";

type Props = {
  /** 필터 줄 앞에 붙는 이름. 스크린리더용 라벨로도 쓴다. */
  label: string;
  /** URL 쿼리 키. 예: kind */
  paramName: string;
  options: readonly ChoiceOption[];
  /** 링크를 만들 기준 경로. */
  basePath: string;
  /** 지금 선택된 값. 없으면 맨 앞 칩(allLabel)이 켜진다. */
  selected?: string;
  /**
   * 아무것도 안 골랐을 때의 칩 이름. 거르는 줄은 "전체" 가 맞지만 정렬
   * 줄에서 고르지 않은 상태는 "섞어서"(검색 중에는 "기본순") 다 - 전체를
   * 보여주는 것은 같고 순서만 다르다.
   */
  allLabel?: string;
  /** 이 필터를 바꿔도 유지할 다른 조건들. */
  keep?: Record<string, string | undefined>;
  /**
   * 이 줄을 끄는 링크(맨 앞 칩, 켜진 칩 다시 누르기)에만 더 싣는 값.
   *
   * 정렬 줄이 쓴다. 정렬을 끄면 목록이 섞이는데, 섞기 시드가 주소에 없으면
   * 서버가 시드를 붙여 다시 보내고 그 사이 필터 상자가 닫힌다. 켜는 링크에는
   * 시드가 필요 없어서(정렬이 있으면 섞지 않는다) 끄는 링크에만 싣는다.
   */
  keepWhenOff?: Record<string, string | undefined>;
};

/**
 * 선택지 하나를 고르는 필터 칩 줄.
 *
 * 링크로 만든 이유: 서버 컴포넌트라 자바스크립트 없이 동작하고, 필터 상태가
 * URL 에 남아 뒤로가기와 공유가 그대로 된다.
 *
 * page 는 일부러 빼고 만든다. 3페이지를 보다 조건을 바꾸면 결과가 3페이지도
 * 안 되는 경우가 많아 빈 화면이 뜬다.
 */
export function ChoiceFilter({
  label,
  paramName,
  options,
  basePath,
  selected,
  allLabel = "전체",
  keep,
  keepWhenOff,
}: Props) {
  if (options.length === 0) return null;

  // 이미 고른 것을 다시 누르면 그 조건을 뺀다. 끄는 방법이 "전체" 뿐이면
  // 방금 누른 자리에서 손을 떼고 줄 맨 앞까지 되돌아가야 한다.
  const href = (value?: string) => {
    const turnsOff = !value || value === selected;
    const query = new URLSearchParams();
    for (const [key, kept] of Object.entries({
      ...keep,
      ...(turnsOff ? keepWhenOff : {}),
    })) {
      if (kept) query.set(key, kept);
    }
    // keep 에 이 필터와 같은 키가 섞여 오면 끄기 링크가 지금 주소와 같아져
    // 눌러도 아무 일이 없다. keep 은 자유형이라 다음 필터를 추가할 때
    // 밟기 쉬우므로 여기서 한 번 지운다.
    query.delete(paramName);
    if (!turnsOff) query.set(paramName, value);
    const qs = query.toString();
    return qs ? `${basePath}?${qs}` : basePath;
  };

  return (
    <nav
      aria-label={`${label} 필터`}
      className="mt-4 flex flex-wrap items-center gap-2"
    >
      {/* 라벨은 dim + 700 굵기. 크기가 작아도 굵기로 읽힌다
          (디자인 가이드 color-text). */}
      <span
        className="text-sm"
        style={{ color: "var(--text-muted)", fontWeight: "var(--weight-bold)" }}
      >
        {label}
      </span>
      {/* 맨 앞 칩("전체" 등)은 화면에 여러 줄이 나란히 설 때 이름이
          겹친다(문장 화면은 종류·난이도·분류 셋). 스크린리더의 링크
          목록에서는 nav 이름이 안 읽히므로 여기서 한정해 준다. */}
      <FilterChip
        href={href()}
        active={!selected}
        ariaLabel={`${label} ${allLabel}`}
      >
        {allLabel}
      </FilterChip>
      {options.map((option) => {
        const active = selected === option.value;
        return (
          <FilterChip
            key={option.value}
            href={href(option.value)}
            active={active}
            // 눌렀을 때 무엇이 되는지 말해준다. 켜진 칩과 꺼진 칩이 같은
            // 링크처럼 읽히면 다시 누르면 취소된다는 걸 알 수 없다.
            // 조사를 붙이지 않는다. "네트워크 로" 처럼 띄면 어색하고,
            // 붙이면 받침에 따라 로/으로 가 갈려 "깃로" 같은 것이 나온다.
            ariaLabel={
              active
                ? `${label} ${option.label} 선택 해제`
                : `${label} ${option.label} 적용`
            }
          >
            {option.label}
          </FilterChip>
        );
      })}
    </nav>
  );
}
