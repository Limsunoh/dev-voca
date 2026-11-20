"""익히기 목록(단어·문장)의 쪽 나누기.

DRF 기본(PageNumberPagination)은 그 쪽만큼 앞의 행을 건너뛰어(OFFSET) 읽는다.
콘텐츠가 33만 개일 때 마지막 쪽은 앞의 33만 행을 건너뛰느라 0.6초, 섞기
(shuffle) 순서면 1초가 걸렸다(2026-11-13 로컬 측정). 그래서 세 가지를 한다.

1. 뒤쪽 절반의 쪽은 정렬을 뒤집어 앞에서부터 읽고 결과를 다시 뒤집는다.
   건너뛰는 행이 많아야 전체의 절반이다. 어느 쪽에 무엇이 오는지는 그대로다.

2. 정렬은 번호(pk)만 들고 한다. 그 쪽의 번호 20개를 고른 뒤 그 20행만
   통째로 가져온다. 행 전체(설명·예문까지)를 들고 정렬하던 것보다 가볍다.
   쪽마다 쿼리가 하나 는다(개수, 번호, 행).

3. 전체 개수를 5분 동안 서버 메모리(settings 의 CACHES["counts"])에 기억한다.
   단어 100만 개면 셀 때마다 55ms, 두 글자 검색은 500ms 다. 섞기는 사람마다
   순서가 달라도 개수는 같아 함께 쓴다.

   기억한 개수는 낡을 수 있다(그새 단어가 공개·삭제된다). 그래서
   - 뒤쪽 절반의 쪽은 늘 다시 센다. 끝에서 세어 읽어서 개수가 하나라도
     틀리면 그만큼 밀려, 앞쪽 쪽과 만나는 경계에서 항목이 빠지거나 겹친다.
   - 앞쪽 쪽은 다음 쪽의 첫 번호까지 하나 더 읽어, 읽힌 수가 기억한 개수와
     맞는지 본다. 안 맞으면(그 근처에서 늘거나 줄었다) 다시 센다. 그래서
     목록과 "다음" 링크는 맞다.
   - 없는 쪽이 나오거나 "last" 를 받으면 다시 센다.
   그래도 앞쪽 쪽의 "count" 는 5분까지 몇 개 틀릴 수 있다. 화면의 "끝" 쪽
   번호는 이 count 로 계산하므로, 그새 단어가 지워졌으면 없는 쪽을 가리켜
   404 가 날 수 있다(목록 화면은 1쪽으로 돌린다). 그 요청이 다시 센 개수를
   기억하므로 같은 작업자에서는 한 번으로 끝난다.

짧은 검색어("쿼리", "a")의 목록 가져오기가 느린 것은 이것으로 못 고친다. 검색
인덱스(pg_trgm)는 세 글자 미만에 못 쓴다. 개수를 목록 쿼리 안에서 함께 세는
(COUNT(*) OVER ()) 방법도 재 봤는데, 걸리는 행이 많으면("a" 는 28만 행) 그
행을 전부 모아 정렬하게 돼 400ms 가 1초가 됐다.

단어 100만 개 측정(2026-11-20, 로컬): ABC순 1쪽 259 -> 167ms(개수를 기억한
뒤 115ms), 가운데 쪽 820 -> 304ms(249ms), 섞기 1쪽 424 -> 285ms(229ms), 두
글자 검색 1쪽 1,101 -> 1,071ms(537ms).
"""

from __future__ import annotations

import hashlib

from django.core.cache import caches
from django.core.exceptions import EmptyResultSet
from django.core.paginator import EmptyPage, Page, Paginator
from django.db.models import QuerySet
from django.utils.functional import cached_property
from rest_framework.pagination import PageNumberPagination


class TailReversingPaginator(Paginator):
    """번호만 정렬하고, 뒤쪽 절반은 거꾸로 읽고, 개수는 기억한다.

    정렬이 전순서(같은 값이 없는 순서)여야 뒤집어 읽어도 같은 행이 같은 쪽에
    온다. 익히기 목록은 LearningItemViewSet.filter_queryset 이 정렬 끝에 pk 를
    붙여 이를 보장한다. 다른 곳에 쓰려면 그쪽 정렬도 유일한 칸으로 끝나야 한다.
    """

    # count 가 메모리에서 꺼낸 값인가. 그렇다면 낡았을 수 있다.
    remembered = False

    @cached_property
    def count(self) -> int:
        rows = self.object_list
        if not (isinstance(rows, QuerySet) and rows.ordered):
            return super().count
        try:
            found = caches["counts"].get(self._count_key)
        except EmptyResultSet:
            # .none() 처럼 결과가 없는 게 정해진 조건은 SQL 이 만들어지지 않는다.
            # 지금 익히기 목록에서는 안 나오고, 다른 목록에 갖다 쓸 때를 막는다.
            return 0
        if found is None:
            return self._count_now()
        self.remembered = True
        return found

    @cached_property
    def _count_key(self) -> str:
        """조건이 같으면 같은 키. 정렬과 섞기 시드는 개수와 상관없어 뺀다.

        SQL 과 인자를 따로 둔 채로 해시한다. 인자를 SQL 에 끼워 넣은 글
        (str(query))로 하면 검색어를 잘 지어 다른 조건과 같은 글을 만들 수 있다.
        """
        sql, params = self.object_list.order_by().values("pk").query.sql_with_params()
        return "list-count:" + hashlib.sha256(repr((sql, params)).encode()).hexdigest()

    def _count_now(self) -> int:
        found = self.object_list.count()
        caches["counts"].set(self._count_key, found)
        self.remembered = False
        return found

    def recount(self) -> bool:
        """기억한 개수를 쓰고 있었으면 새로 세어 바꾸고 True."""
        _ = self.count  # 아직 안 꺼냈으면 꺼내 봐야 기억한 값인지 안다
        if not self.remembered:
            return False
        self.count = self._count_now()
        self.__dict__.pop("num_pages", None)  # count 로 계산해 둔 값
        return True

    def page(self, number) -> Page:
        if not (isinstance(self.object_list, QuerySet) and self.object_list.ordered):
            return super().page(number)

        try:
            number = self.validate_number(number)
        except EmptyPage:
            # 기억한 개수가 낡아 실제로 있는 쪽을 없다고 봤을 수 있다.
            if int(number) < 1 or not self.recount():
                raise
            number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        if bottom > self.count // 2 and self.recount():
            number = self.validate_number(number)

        ids = self._pick_ids(bottom)
        if len(ids) != self._expected(bottom) and self.recount():
            number = self.validate_number(number)
            ids = self._pick_ids(bottom)

        ids = ids[: self._top(bottom) - bottom]  # 확인용으로 더 읽은 번호를 뗀다
        # 같은 조건으로 다시 걸러 가져온다. 번호를 고른 뒤 그새 검수가 취소된
        # 항목이 있으면 빠진다(그 쪽이 한 칸 짧아질 뿐 미검수가 나가지 않는다).
        found = self.object_list.in_bulk(ids)
        return self._get_page([found[pk] for pk in ids if pk in found], number, self)

    def _top(self, bottom: int) -> int:
        top = bottom + self.per_page
        return self.count if top + self.orphans >= self.count else top

    def _pick_ids(self, bottom: int) -> list[int]:
        """그 쪽에 올 번호(pk)를 정렬 순서대로 고른다.

        앞에서 읽는 쪽은 다음 쪽의 첫 번호까지 하나 더 읽는다(orphans 가 있으면
        그만큼 더). 읽힌 수가 _expected 와 다르면 개수가 낡은 것이다.
        """
        rows, top = self.object_list, self._top(bottom)
        if bottom <= self.count // 2:
            return list(rows.values_list("pk", flat=True)[bottom : top + self.orphans + 1])
        # 끝에서 센 구간을 뒤집힌 순서로 읽고 원래 순서로 돌린다.
        ids = list(rows.reverse().values_list("pk", flat=True)[self.count - top : self.count - bottom])
        ids.reverse()
        return ids

    def _expected(self, bottom: int) -> int:
        """개수가 맞다면 _pick_ids 가 돌려줄 번호 수."""
        top = self._top(bottom)
        if bottom > self.count // 2:
            return top - bottom
        return min(top + self.orphans + 1, self.count) - bottom


class ContentPagination(PageNumberPagination):
    """익히기 목록용(TailReversingPaginator)."""

    django_paginator_class = TailReversingPaginator

    def get_page_number(self, request, paginator):
        # "last" 는 개수로 쪽 번호를 정하므로 정확한 개수로 정한다.
        if request.query_params.get(self.page_query_param) in self.last_page_strings:
            paginator.recount()
        return super().get_page_number(request, paginator)
