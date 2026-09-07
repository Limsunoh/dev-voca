import { FilterChip } from "@/components/FilterChip";

type Props = {
  /** 링크를 만들 기준 경로. */
  basePath: string;
  /** 지금 정처기 범위만 보고 있는지. */
  active: boolean;
  /** 이걸 켜고 꺼도 유지할 다른 조건들. */
  keep?: Record<string, string | undefined>;
};

/**
 * "정처기 범위만" 을 켜고 끄는 줄.
 *
 * 다른 필터와 성격이 다르다. 난이도·분류는 여러 값 중 하나를 고르는
 * 것이라 ChoiceFilter 로 줄을 만들지만, 이건 켜거나 끄거나 둘뿐이다.
 * 값이 하나인 목록을 만들면 "전체 / 정처기" 두 칩이 되어 무엇이 기본
 * 상태인지 흐려진다.
 *
 * 링크인 것은 다른 필터와 같다 - 서버 컴포넌트라 자바스크립트 없이
 * 동작하고, 상태가 URL 에 남아 뒤로가기와 공유가 그대로 된다.
 *
 * **끌 때 과목도 같이 뗀다.** 정처기를 끈 채로 과목만 남으면 백엔드가
 * 그 과목으로 계속 거르는데 화면에는 켜진 것이 안 보인다. 결과가 왜
 * 적은지 알 수 없는 상태가 된다.
 */
export function ExamScopeFilter({ basePath, active, keep }: Props) {
  const href = () => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(keep ?? {})) {
      if (value) query.set(key, value);
    }
    // keep 에 섞여 와도 여기서 정한다. 자유형이라 호출부가 실수로
    // 넣으면 끄는 링크가 지금 주소와 같아져 눌러도 아무 일이 없다.
    query.delete("is_exam");
    query.delete("exam_subject");
    if (!active) query.set("is_exam", "true");
    const qs = query.toString();
    return qs ? `${basePath}?${qs}` : basePath;
  };

  return (
    <nav aria-label="정처기 범위 필터" className="mt-4 flex flex-wrap gap-2">
      <FilterChip
        href={href()}
        active={active}
        // 켜고 끄는 것이라 무엇이 되는지 말해준다. 보이는 글자만으로는
        // 지금 켜진 것인지 누르면 켜지는 것인지 소리로 구분되지 않는다.
        ariaLabel={
          active ? "정처기 범위만 보기 해제" : "정처기 범위만 보기"
        }
      >
        정처기 범위만
      </FilterChip>
    </nav>
  );
}
