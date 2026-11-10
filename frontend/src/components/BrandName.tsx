/**
 * 서비스 이름 "dev-voca". 문단 안에서는 글자로 쓰지 말고 이걸 쓴다.
 *
 * 브라우저는 하이픈 뒤에서 줄을 바꿀 수 있어서, 글자 그대로 두면 폭에 따라
 * "dev-" 와 "voca" 가 다른 줄로 갈린다. 약관은 360px, 처리방침은 390px,
 * 마이크 안내는 412px 에서 실제로 갈렸다.
 */
export function BrandName() {
  return <span className="whitespace-nowrap">dev-voca</span>;
}
