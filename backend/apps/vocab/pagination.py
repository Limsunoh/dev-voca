"""익히기 목록(단어·문장)의 쪽 나누기.

DRF 기본(PageNumberPagination)은 그 쪽만큼 앞의 행을 건너뛰어(OFFSET) 읽는다.
콘텐츠가 33만 개일 때 마지막 쪽은 앞의 33만 행을 건너뛰느라 0.6초, 섞기
(shuffle) 순서면 1초가 걸렸다(2026-11-13 로컬 측정).

그래서 뒤쪽 절반의 쪽은 정렬을 뒤집어 앞에서부터 읽고 결과를 다시 뒤집는다.
건너뛰는 행이 많아야 전체의 절반이다. 어느 쪽에 무엇이 오는지는 그대로다.
가운데 쪽은 여전히 절반을 건너뛴다(33만 개에서 400ms 남짓). 거기까지 넘기는
일은 드물어 그대로 둔다.

짧은 검색어("쿼리", "a")가 느린 것은 이것으로 못 고친다. 검색 인덱스(pg_trgm)
는 세 글자 미만에 못 쓰고, 개수 세기와 목록 가져오기가 각각 표 전체를 훑는다.
개수를 목록 쿼리 안에서 함께 세는(COUNT(*) OVER ()) 방법을 재 봤는데, 걸리는
행이 많으면("a" 는 28만 행) 그 행을 전부 모아 정렬하게 돼 400ms 가 1초가 됐다.
걸리는 행이 적을 때만 이득이라 넣지 않았다.
"""

from __future__ import annotations

from django.core.paginator import Page, Paginator
from django.db.models import QuerySet
from rest_framework.pagination import PageNumberPagination


class TailReversingPaginator(Paginator):
    """뒤쪽 절반의 쪽은 정렬을 뒤집어 읽는다.

    정렬이 전순서(같은 값이 없는 순서)여야 뒤집어 읽어도 같은 행이 같은 쪽에
    온다. 익히기 목록은 LearningItemViewSet.filter_queryset 이 정렬 끝에 pk 를
    붙여 이를 보장한다. 다른 곳에 쓰려면 그쪽 정렬도 유일한 칸으로 끝나야 한다.
    """

    def page(self, number) -> Page:
        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        rows = self.object_list
        if not (isinstance(rows, QuerySet) and rows.ordered and bottom > self.count // 2):
            return super().page(number)

        top = bottom + self.per_page
        if top + self.orphans >= self.count:
            top = self.count
        # 끝에서 센 구간을 뒤집힌 순서로 읽고 원래 순서로 돌린다.
        tail = list(rows.reverse()[self.count - top : self.count - bottom])
        tail.reverse()
        return self._get_page(tail, number, self)


class ContentPagination(PageNumberPagination):
    """익히기 목록용. 뒤쪽 쪽을 뒤집어 읽는다(TailReversingPaginator)."""

    django_paginator_class = TailReversingPaginator
