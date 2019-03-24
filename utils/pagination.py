# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from rest_framework.pagination import PageNumberPagination

from WeiDuAdmin import settings


class WdPageNumberPagination(PageNumberPagination):
    page_size_query_param = settings.REST_FRAMEWORK["PAGINATE_SIZE_PARAM"]
    page_query_param = settings.REST_FRAMEWORK["PAGEPARAM_NAME"]

    def __init__(self, page_size=None):
        self.__page_size = page_size

    def get_page_size(self, request):
        if self.__page_size is not None:
            return self.__page_size
        else:
            return super(WdPageNumberPagination, self).get_page_size(request)