/**
 * 읽을 것을 낱말 단위로 쪼개 짝짓는다.
 *
 * 서버가 "몇 번째 낱말이 어긋났다"(wrong_at)를 주므로, 화면은 글자·발음기호·
 * 한글발음 셋을 같은 낱말 수로 쪼개야 그 자리를 짚을 수 있다.
 *
 * 셋 중 하나라도 개수가 다르면 강조하지 않고 쪼개지 않은 채로 그린다. 엉뚱한
 * 자리를 강조하면 사용자가 멀쩡한 낱말을 고치려 들어서, 강조를 안 하는
 * 것보다 나쁘다.
 */

/**
 * 낱말로 쪼갠다. 하이픈도 구분자로 쓴다.
 *
 * 공백만으로 쪼개면 하이픈이 든 항목에서 발음기호와 개수가 어긋난다. 출제
 * 대상 361개 중 22개가 어긋나던 것이 하이픈까지 쪼개면 11개로 준다. 남는
 * 11개는 전부 낱말 하나짜리(npm 이 `/ˌen pi ˈem/`)라 강조할 자리가 없어서
 * 문제가 되지 않는다.
 *
 *   client-side routing   공백=2  하이픈까지=3  ipa=3
 *   end-to-end test       공백=2  하이픈까지=4  ipa=4
 *   three-way handshake   공백=2  하이픈까지=3  ipa=3
 */
export function splitWords(text: string): string[] {
  return text.split(/[\s-]+/).filter(Boolean);
}

/**
 * 발음기호 바깥의 슬래시를 뗀다.
 *
 * 검수가 끝난 개발 용어 566개는 `/ˈitæɡ/` 처럼 감싸진 채로 저장돼 있고,
 * 새로 쓰는 일상 표현은 슬래시 없이 들어온다. 화면이 여기서 떼고 그릴 때
 * 다시 두르면 두 갈래가 같게 보이고, 검수 끝난 데이터는 고치지 않아도 된다.
 *
 * 떼지 않으면 낱말로 쪼갤 때 첫 낱말에 `/` 가 붙고 마지막 낱말이 `/` 로
 * 끝나서, 강조한 조각이 잘린 것처럼 보인다.
 */
export function stripSlashes(ipa: string): string {
  return ipa.trim().replace(/^\/+/, "").replace(/\/+$/, "");
}

/**
 * 강세 표시를 걷어낸다.
 *
 * 한글 발음은 `**쏘r s**` 처럼 강세를 별표로 감싼다(Reading 이 굵게 그린다).
 * 낱말 수를 셀 때 이걸 안 걷으면 별표가 글자로 세어져 개수가 어긋난다.
 */
export function stripStress(reading: string): string {
  return reading.replace(/\*\*/g, "");
}

/** 낱말 하나와 그 발음. */
export type WordPart = {
  word: string;
  ipa: string;
  reading: string;
};

/**
 * 셋을 낱말 단위로 짝짓는다. 개수가 어긋나면 null.
 *
 * null 은 실패가 아니라 정상적인 갈래다. 부르는 쪽은 그때 쪼개지 않고
 * 그린다.
 */
export function alignParts(
  term: string,
  pronunciation: string,
  reading: string,
): WordPart[] | null {
  const words = splitWords(term);
  const ipas = splitWords(stripSlashes(pronunciation));
  // 강세를 걷어내고 세지만, 그릴 때는 별표가 든 원본을 쓴다(Reading 이
  // 별표로 굵기를 정한다). 그래서 원본도 따로 쪼개 두고 같은 자리의 조각을
  // 가져온다.
  const readingWords = splitWords(reading);
  const readingCount = splitWords(stripStress(reading)).length;

  // 낱말이 하나뿐이면 짝지을 것이 없으니 쪼개지 않고 그린다.
  if (words.length < 2) return null;

  // 발음이 비어 있는 항목이 있다(검수가 안 끝났거나 갈리는 발음). 그때는
  // 짝지을 수 없다.
  if (!ipas.length || !readingWords.length) return null;

  if (words.length !== ipas.length) return null;
  // 별표를 걷어낸 개수와 안 걷은 개수가 다르면(강세가 공백을 걸침) 자리를
  // 믿을 수 없다. 실제로 `**쏘r s** 맾` 이 그렇다.
  if (words.length !== readingCount || readingCount !== readingWords.length) {
    return null;
  }

  return words.map((word, i) => ({
    word,
    ipa: ipas[i],
    reading: readingWords[i],
  }));
}
