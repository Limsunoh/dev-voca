import { FilterChip } from "@/components/FilterChip";
import type { CategoryOption } from "@/lib/api/vocab";

type Props = {
  options: CategoryOption[];
  /** 링크를 만들 기준 경로. 단어장·문장 등 쓰는 화면마다 다르다. */
  basePath: string;
  /** 지금 선택된 분류. 없으면 "전체". */
  selected?: string;
  /** 분류를 바꿔도 유지할 검색어. */
  search?: string;
  /** 분류를 바꿔도 유지할 난이도. */
  difficulty?: string;
  /** 분류를 바꿔도 유지할 그 밖의 조건(문장의 kind 등). */
  extra?: Record<string, string | undefined>;
  /**
   * 고른 칩을 다시 눌러 끌 수 있는지. 기본은 켬.
   *
   * 끄는 화면이 있는 이유: 문제풀기는 목록이 아니라 진행 중인 판이다.
   * 분류가 바뀌면 판을 새로 만들도록 돼 있어서, 켜진 칩을 잘못 한 번
   * 누르면 점수와 방금 푼 목록이 사라진다. 되돌릴 방법도 없다.
   * 거기서는 "전체" 를 눌러 의도적으로 초기화하게 둔다.
   */
  toggle?: boolean;
};

/**
 * 분류 필터 버튼 줄.
 *
 * 링크로 만든 이유: 서버 컴포넌트라 자바스크립트 없이 동작하고, 필터 상태가
 * URL 에 남아 뒤로가기와 공유가 그대로 된다.
 *
 * page 는 일부러 빼고 만든다. 3페이지를 보다 분류를 바꾸면 결과가 3페이지도
 * 안 되는 경우가 많아 빈 화면이 뜬다.
 */
export function CategoryFilter({
  options,
  basePath,
  selected,
  search,
  difficulty,
  extra,
  toggle = true,
}: Props) {
  if (options.length === 0) return null;

  // 분류 외의 조건은 그대로 들고 간다. 여기서 빠뜨리면 분류를 바꾸는 순간
  // 다른 필터가 조용히 풀린다(Pagination 은 유지하므로 규칙도 어긋난다).
  //
  // 이미 고른 것을 다시 누르면 그 조건을 뺀다. 끄는 방법이 "전체" 뿐이면
  // 방금 누른 자리에서 손을 떼고 줄 맨 앞까지 되돌아가야 한다.
  const href = (category?: string) => {
    const query = new URLSearchParams();
    if (search) query.set("search", search);
    if (difficulty) query.set("difficulty", difficulty);
    for (const [key, value] of Object.entries(extra ?? {})) {
      if (value) query.set(key, value);
    }
    // extra 에 category 가 섞여 오면 끄기 링크가 지금 주소와 같아져 눌러도
    // 아무 일이 없다. extra 는 자유형이라 다음 화면에서 밟기 쉽다.
    query.delete("category");
    if (category && !(toggle && category === selected)) {
      query.set("category", category);
    }
    const qs = query.toString();
    return qs ? `${basePath}?${qs}` : basePath;
  };

  return (
    <nav aria-label="분류 필터" className="mt-4 flex flex-wrap gap-2">
      {/* "전체" 는 화면에 필터 줄이 여러 개일 때 이름이 겹친다. 스크린리더의
          링크 목록에서는 nav 이름이 안 읽히므로 여기서 한정해 준다. */}
      <FilterChip href={href()} active={!selected} ariaLabel="분류 전체">
        전체
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
              active && toggle
                ? `분류 ${option.label} 선택 해제`
                : `분류 ${option.label} 적용`
            }
          >
            {option.label}
          </FilterChip>
        );
      })}
    </nav>
  );
}
