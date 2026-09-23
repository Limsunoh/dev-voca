/**
 * 문제 유형마다 지문과 보기가 용어(영어 낱말)인지, 영어인지.
 *
 * 용어는 고정폭, 한글(뜻·설명·상황)은 본문체로 그린다. 고정폭 글꼴
 * (JetBrains Mono)에는 한글 글자가 없어서, 한글을 고정폭으로 주면 OS 기본
 * 글꼴로 떨어져 굵고 뭉툭하게 나온다.
 *
 * 문제풀기(QuizBoard)와 한 판·일일공부·복습(QuestionCard)이 둘 다 여기를
 * 본다. 따로 정하던 때 두 화면이 달랐다 - 한쪽은 한글 지문(뜻·설명)을
 * 고정폭으로, 다른 쪽은 한글 보기(상황)를 고정폭으로 그렸고, 영어 보기는
 * 한쪽만 고정폭이었다.
 *
 *   유형          지문            보기
 *   meaning       용어            뜻(한글)
 *   term          뜻(한글)        용어
 *   description   설명(한글)      용어
 *   blank         문장(영어)      용어
 *   situation     문장(영어)      상황(한글)
 *
 * 문장 지문(blank·situation)의 글꼴은 화면마다 다르다. 영어지만 낱말이
 * 아니라 문장이라서다. 문제풀기(QuizBoard)는 promptIsTerm 을 안 보고 따로
 * 고정폭으로 그린다 - 아래 해설이 같은 문장을 고정폭으로 보여 줘서다(Prompt
 * 주석). 한 판·일일공부·복습(QuestionCard)은 promptIsTerm 이 false 라
 * 본문체다. 어느 쪽이든 영어이긴 하므로 lang 은 promptIsEnglish 로 붙인다.
 *
 * 모르는 유형은 용어가 아닌 것으로 본다. 본문체는 영어도 멀쩡히 그리지만,
 * 고정폭은 한글을 망가뜨린다.
 */
export function promptIsTerm(kind: string): boolean {
  return kind === "meaning";
}

const ENGLISH_PROMPT = new Set(["meaning", "blank", "situation"]);

/**
 * 지문이 영어인지. lang="en" 을 붙일 자리다 - 없으면 화면 낭독기가 영어
 * 문장을 한국어 음성으로 읽는다.
 */
export function promptIsEnglish(kind: string): boolean {
  return ENGLISH_PROMPT.has(kind);
}

const TERM_CHOICES = new Set(["term", "description", "blank"]);

export function choicesAreTerms(kind: string): boolean {
  return TERM_CHOICES.has(kind);
}
