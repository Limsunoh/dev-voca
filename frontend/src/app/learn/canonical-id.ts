/**
 * 상세 주소의 숫자 id 를 정규 표기로 고친 값. 고칠 것이 없으면 null.
 *
 * `/learn/words/007` 은 백엔드가 7 로 읽어 `/learn/words/7` 과 같은 내용을
 * 준다. 같은 화면이 주소 둘로 갈리지 않게 호출부가 redirect 한다.
 */
export function canonicalId(id: string): string | null {
  if (!/^\d+$/.test(id)) return null;

  const value = Number(id);
  if (!Number.isSafeInteger(value) || String(value) === id) return null;
  return String(value);
}
