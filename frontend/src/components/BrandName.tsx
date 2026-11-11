/**
 * 서비스 이름 "DeVoca". 문단 안에서는 글자로 쓰지 말고 이걸 쓴다.
 *
 * 문단 안의 이름을 여기로 모은다. 탭 제목, 설명, alt, 메일은 문자열이라 이름을
 * 바꿀 때 따로 고친다(2026-11-11 dev-voca -> DeVoca 때 30곳 남짓).
 *
 * 옛 이름 dev-voca 는 하이픈 뒤에서 줄이 갈려("dev-" / "voca") 줄바꿈을 막았다.
 * 지금 이름에는 하이픈이 없지만 막아 둬도 손해가 없어 그대로 둔다.
 */
export function BrandName() {
  return <span className="whitespace-nowrap">DeVoca</span>;
}
