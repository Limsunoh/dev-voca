/**
 * 한글 발음. 강세를 굵게 그린다.
 *
 * 데이터에 `**...**` 로 강세가 표시돼 있다(백엔드 prompts/korean-reading.md).
 * 그대로 두면 별표가 화면에 보이고, 굵게 안 그리면 어디에 힘을 주는지 알 수 없다 -
 * 강세는 이 표기에서 가장 중요한 정보다.
 *
 * **마크다운 파서를 넣지 않는다.** 규칙이 `**` 하나뿐이라 split 으로 끝나고,
 * 런타임 의존성을 셋으로 유지하는 것이 이 프로젝트의 자산이다.
 *
 * dangerouslySetInnerHTML 도 쓰지 않는다. 발음은 Admin 에서 사람이 넣는
 * 값이라 지금은 안전하지만, 그 경로가 열려 있으면 언젠가 AI 생성 결과가
 * 그대로 들어온다. split 이 같은 일을 하면서 그 문을 안 연다.
 */
// 강세에 색을 주지 않는다. 부르는 쪽이 자기 자리에 맞는 색을 정하는데
// 여기서 박으면 그것을 덮어, 흐린 글씨 안에서 강세만 튀어 대비가 과해진다.
// 굵기만으로 충분히 보인다.
export function Reading({
  text,
  className = "",
}: {
  text: string;
  className?: string;
}) {
  if (!text) return null;

  // `**` 로 잘라 홀수 번째만 굵게.
  //
  // 짝이 안 맞으면 마지막 조각이 굵어지거나 빈 <strong> 이 생긴다. 둘 다
  // 화면에서는 티가 안 나고, 별표가 그대로 보이는 것보다 낫다. 값은 Admin
  // 검수를 거치므로 짝이 맞는 것이 정상이다.
  const parts = text.split("**");

  return (
    <span className={className}>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <strong key={i} className="font-semibold">
            {part}
          </strong>
        ) : (
          part
        ),
      )}
    </span>
  );
}
