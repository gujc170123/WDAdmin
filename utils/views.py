# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json
import traceback
from abc import abstractmethod

import operator
from django.db.models import Q
from django.db.models.query import RawQuerySet
from django.http import FileResponse
from django.http import HttpResponseRedirect
from rest_framework import status, exceptions,viewsets
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView, CreateAPIView, UpdateAPIView, RetrieveAPIView, GenericAPIView, \
    DestroyAPIView
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.utils.urls import replace_query_param
from rest_framework.views import APIView
from rest_framework_xml.parsers import XMLParser
from rest_framework.response import Response

from WeiDuAdmin import settings
from utils.logger import debug_logger, err_logger
from utils.response import general_json_response, ErrorCode

from research.models import *


class TextXMLParser(XMLParser):
    media_type = 'text/xml'


class AuthenticationExceptView(APIView):
    """pass authentication"""
    def perform_authentication(self, request): pass


class PermExceptView(APIView):
    """pass permission check"""
    def check_permissions(self, request): pass


class WdAPIView(GenericAPIView):
    CREATOR_AUTO_CREATE = True
    UPDATER_AUTO_REFRESH = True
    OWN_PERMISSION_CHECK = True
    POST_CHECK_REQUEST_PARAMETER = ()
    POST_CHECK_NONEMPTYREQUEST_PARAMETER = ()
    GET_CHECK_REQUEST_PARAMETER = ()
    DELETE_CHECK_REQUEST_PARAMETER = ()
    GET_AUTH_PASS = False
    CUSTOM_TEMPLATE_VIEW = False
    custom_page_size = None

    def get_queryset(self):
        return self.model.objects.all()

    def get_id(self):
        u"""get id from url: (?P<pk>\d+)"""
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        return self.kwargs[lookup_url_kwarg]

    def get_object(self):
        # if self.custom_view_cache.has_key("get_obj_cache"):
        #     return self.custom_view_cache["get_obj_cache"]
        obj = super(WdAPIView, self).get_object()
        if not obj.is_active:
            raise NotFound
        if self.OWN_PERMISSION_CHECK:
            pass
            # if hasattr(obj, "user_id") and obj.user_id != self.request.user.id:
            #     raise exceptions.PermissionDenied
        # self.custom_view_cache["get_obj_cache"] = obj
        return obj

    def perform_authentication(self, request):
        if request.method == "GET" and self.GET_AUTH_PASS:
            return True
        if not request.user.is_authenticated:
            raise exceptions.AuthenticationFailed()

    def post_check_parameter(self, kwargs):
        if self.POST_CHECK_REQUEST_PARAMETER:
            for parameter in self.POST_CHECK_REQUEST_PARAMETER:
                setattr(self, parameter, kwargs.get(parameter, None))
                if getattr(self, parameter) is None:
                    return ErrorCode.INVALID_INPUT
        return ErrorCode.SUCCESS

    def post_check_nonempty_parameter(self, kwargs):
        if self.POST_CHECK_NONEMPTYREQUEST_PARAMETER:
            for parameter in self.POST_CHECK_NONEMPTYREQUEST_PARAMETER:
                if not getattr(self, parameter):
                    return ErrorCode.NONEMPTY_INPUT
        return ErrorCode.SUCCESS

    def get_check_parameter(self, kwargs):
        if self.GET_CHECK_REQUEST_PARAMETER:
            for parameter in self.GET_CHECK_REQUEST_PARAMETER:
                setattr(self, parameter, kwargs.get(parameter, None))
                if getattr(self, parameter) is None:
                    return ErrorCode.INVALID_INPUT
        return ErrorCode.SUCCESS

    def delete_check_parameter(self, kwargs):
        if self.DELETE_CHECK_REQUEST_PARAMETER:
            for parameter in self.DELETE_CHECK_REQUEST_PARAMETER:
                setattr(self, parameter, kwargs.get(parameter, None))
                if getattr(self, parameter) is None:
                    return ErrorCode.INVALID_INPUT
        return ErrorCode.SUCCESS

    def check_parameter(self, kwargs):
        err_code = ErrorCode.SUCCESS
        if self.request.method == "POST":
            try:
                if self.CREATOR_AUTO_CREATE and hasattr(self, "model") and hasattr(self.model, "creator_id") and self.request.user:

                    if 'creator_id' not in self.get_serializer_class().Meta.fields:
                        self.get_serializer_class().Meta.fields += ('creator_id', )
                    self.request.data["creator_id"] = self.request.user.id
                    if self.request.data["creator_id"] == 0:
                        return ErrorCode.INVALID_INPUT
            except Exception, e:
                debug_logger.debug("user auto create failed, msg(%s)" %e)

        if self.request.method == "PUT":
            try:
                if self.UPDATER_AUTO_REFRESH and hasattr(self, "model") and hasattr(self.model, "last_modify_user_id") and self.request.user:
                    if 'last_modify_user_id' not in self.get_serializer_class().Meta.fields:
                        self.get_serializer_class().Meta.fields += ('last_modify_user_id',)
                    self.request.data["last_modify_user_id"] = self.request.user.id
                    if self.request.data["last_modify_user_id"] == 0:
                        return ErrorCode.INVALID_INPUT
            except Exception, e:
                err_logger.error("user auto create error, msg(%s)" %e)

        if self.request.method == "POST" or self.request.method == "PUT":
            err_code = self.post_check_parameter(kwargs)
            if not err_code:
               err_code = self.post_check_nonempty_parameter(kwargs)
        if self.request.method == "GET":
            err_code = self.get_check_parameter(kwargs)
        if self.request.method == "DELETE":
            err_code = self.delete_check_parameter(kwargs)
        return err_code

    @property
    def paginator(self):
        """
        The paginator instance associated with the view, or `None`.
        @version: 2017/05/11 @summary: custom with custom_page_size
        """
        if not hasattr(self, '_paginator'):
            if self.pagination_class is None:
                self._paginator = None
            else:
                self._paginator = self.pagination_class(self.custom_page_size)
        return self._paginator

    def custom_pagination(self, request, datalist, count=None):
        if count is None:
            if isinstance(datalist, list):
                count = len(datalist)
            elif isinstance(datalist, RawQuerySet):
                count = len(list(datalist))
            else:
                raise Exception("xd_pagination parse error")
        page = int(request.GET.get("page", 1))
        page_count = int(request.GET.get(settings.REST_FRAMEWORK["PAGINATE_SIZE_PARAM"],
                                         settings.REST_FRAMEWORK["PAGE_SIZE"]))
        next_page = None
        if page * page_count < count:
            next_page = page + 1
        prev_page = None
        if page > 1:
            prev_page = page - 1
        return datalist[(page-1)*page_count:page*page_count], count, prev_page, next_page

    def get_serializer_context(self):
        """
        Extra context provided to the serializer class.
        """
        return {
            'request': self.request,
            'format': self.format_kwarg,
            'view': self,
            'custom_view_cache': self.custom_view_cache
        }

    def get_serializer_data(self, instance, serializer_class=None, many=True):
        serializer_class = serializer_class if serializer_class else self.serializer_class
        serializer_data = serializer_class(instance=instance, many=many,
                                           context=self.get_serializer_context()).data
        if serializer_data is None:
            serializer_data = []
        return serializer_data

    def custom_serializer_pagination(self, request, datalist, count=None):
        page_data, count, prev_page, next_page = self.custom_pagination(request, datalist, count)
        serializer_data = self.get_serializer_data(page_data)
        next_url = None
        prev_url = None
        url = request.build_absolute_uri()
        if next_page is not None:
            next_url = replace_query_param(url, settings.REST_FRAMEWORK["PAGEPARAM_NAME"], next_page)
        if prev_page is not None:
            prev_url = replace_query_param(url, settings.REST_FRAMEWORK["PAGEPARAM_NAME"], prev_page)
        return {"count": count,"next": next_url, "previous": prev_url, "results": serializer_data}

    def unpack_response_data(self, response):
        return json.loads(response.content)

    def pack_response_data(self, response, data):
        response.content = json.dumps(data)
        return response

    def custom_response_data(self, response):
        data = self.unpack_response_data(response)
        data["detail"] = self.custom_data_results(data["detail"])
        custom_response = self.pack_response_data(response, data)
        return custom_response

    def custom_data_results(self, detail):
        return detail

    def dispatch(self, request, *args, **kwargs):
        """
            `.dispatch()` is pretty much the same as Django's regular dispatch,
            but with extra hooks for startup, finalize, and exception handling.
        """
        # self.err_code = ErrorCode.SUCCESS
        self.args = args
        self.kwargs = kwargs
        request = self.initialize_request(request, *args, **kwargs)
        self.request = request
        self.headers = self.default_response_headers  # deprecate?
        self.custom_view_cache = {}
        try:
            if not request.has_permission:
                return general_json_response(status.HTTP_200_OK, ErrorCode.PERMISSION_FAIL)
            self.initial(request, *args, **kwargs)
            req_kwargs = self.request.data if self.request.method not in ["GET", "DELETE"] else self.request.GET
            # if self.request.method != "DELETE":
            err_code = self.check_parameter(req_kwargs)
            if err_code != ErrorCode.SUCCESS:
                return general_json_response(status.HTTP_200_OK, err_code)
            # Get the appropriate handler method
            if request.method.lower() in self.http_method_names:
                handler = getattr(self, request.method.lower(),
                                  self.http_method_not_allowed)
            else:
                handler = self.http_method_not_allowed
            response = handler(request, *args, **kwargs)
        except Exception as exc:
            traceback.print_exc()
            err_logger.warning("dispatch error, msg: %s" % exc)
            if self.CUSTOM_TEMPLATE_VIEW:
                self.template_name = self.default_template_name
                return HttpResponseRedirect(self.template_name)
            try:
                response = self.handle_exception(exc)
            except Exception as e:
                traceback.print_exc()
                err_logger.error("dispatch handler exception error, msg: %s" %e.message)
                return general_json_response(status.HTTP_200_OK, ErrorCode.INTERNAL_ERROR)
        self.response = self.finalize_response(request, response, *args, **kwargs)
        if self.response.status_code in {status.HTTP_200_OK, status.HTTP_302_FOUND}:
            return self.response
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE + self.response.status_code)


class WdListAPIView(ListAPIView, WdAPIView):

    DEFAULT_ORDER_BY = "-id"
    QUERY_WITH_ACTIVE = True
    CUSTOM_RESPONSE = False
    CUSTOM_PAGINATION_SERIALIZER = False
    SEARCH_KEY = 'key_words'
    SEARCH_FIELDS = ()
    FILTER_FIELDS = ()
    FOREIGN_SEARCH_FIELD_MAP = {}  # {'model_id': 'ResearchModel__name'}

    def process_foreign_search(self):
        key_words = self.request.GET.get(self.SEARCH_KEY, None)
        search_sql = []
        for key_name in self.FOREIGN_SEARCH_FIELD_MAP:
            search_info = self.FOREIGN_SEARCH_FIELD_MAP[key_name].split("__")
            foreign_cls = eval(search_info[0])
            foreign_field = eval(search_info[1])
            ids = eval(foreign_cls).objects.filter_active(**{"%s__icontains" % foreign_field: key_words})
            search_sql.append(Q(**{"%s__in" % key_name: ids}))
        return search_sql

    def process_tag_search(self, qs, key_words):
        from research.models import *
        if not hasattr(self, 'model'):
            return []
        model_name = self.model.__name__
        if not Tag.TAG_MODEL_MAP.has_key(model_name):
            return []
        tag_map_info = Tag.TAG_MODEL_MAP[model_name]
        tag_rel_model = tag_map_info["relation"]
        qs_ids = qs.values_list("id", flat=True)
        object_ids = list(eval(tag_rel_model).objects.filter_active(
            tag_value__icontains=key_words, object_id__in=qs_ids).values_list("object_id", flat=True))
        return [Q(**{"id__in": object_ids})]

    def qs_search(self, qs):
        u"""REF: restframe work SearchFilter"""

        key_words = self.request.GET.get(self.SEARCH_KEY, None)
        if key_words is None or not key_words:
            return qs
        search_sql = []
        for search_field in self.SEARCH_FIELDS:
            search_sql.append(Q(**{"%s__icontains" % search_field: key_words}))

        # search_sql += self.process_foreign_search()
        search_sql += self.process_tag_search(qs, key_words)

        if len(search_sql) == 0:
            return qs
        else:
            query = reduce(operator.or_, search_sql)
            qs = qs.filter(query)
        return qs

    def get_order_by_name(self):
        return self.request.GET.get(settings.REST_FRAMEWORK['ORDER_BY_NAME'], self.DEFAULT_ORDER_BY)

    def qs_order_by(self, qs):
        order_by = self.get_order_by_name()
        qs = qs.order_by(order_by)
        return qs

    def qs_business_role(self, qs):
        return qs

    def qs_filter(self, qs):
        if not self.FILTER_FIELDS:
            return qs
        for filter_field in self.FILTER_FIELDS:
            field_value = self.request.GET.get(filter_field, None)
            if field_value:
                qs = qs.filter(**{"%s" % filter_field: field_value})
        return qs

    def get_queryset(self):
        qs = self.model.objects.all()
        if self.QUERY_WITH_ACTIVE:
            qs = qs.filter(is_active=True)
        qs = self.qs_filter(qs)
        qs = self.qs_search(qs)
        qs = self.qs_order_by(qs)
        qs = self.qs_business_role(qs)
        return qs

    def get(self, request, *args, **kwargs):
        try:
            response = super(WdListAPIView, self).get(request, *args, **kwargs)
        except NotFound, e: # paginate_queryset raise NotFound
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, [])
        response = general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, response.data)
        if self.CUSTOM_RESPONSE:
            response = self.custom_response_data(response)
        return response


class WdCreateAPIView(CreateAPIView, WdAPIView):
    POST_DATA_RESPONSE = False
    POST_DATA_ID_RESPONSE = False
    POST_DATA_STRID_RESPONSE = False
    CREATE_TAG = True

    def post(self, request, *args, **kwargs):
        rsp = super(WdCreateAPIView, self).post(request, *args, **kwargs)
        if self.POST_DATA_RESPONSE:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, rsp.data)
        elif self.POST_DATA_ID_RESPONSE:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"id": rsp.data["id"]})
        elif self.POST_DATA_STRID_RESPONSE:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"id": str(rsp.data["id"])})
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def perform_create(self, serializer):
        # super(XdCreateAPIView, self).perform_create(serializer)
        self.create_obj = serializer.save()
        if serializer.data and serializer.data.has_key("id"):
            self.custom_view_cache["perform_id"] = serializer.data["id"]
        else:
            self.custom_view_cache["perform_id"] = None
        if self.CREATE_TAG:
            self.perform_tag(self.custom_view_cache["perform_id"])

    def perform_tag(self, obj_id):
        from research.models import *
        if not hasattr(self, 'model'):
            return
        model_name = self.model.__name__
        tag_datas = self.request.data.get("tag_datas")
        if not Tag.TAG_MODEL_MAP.has_key(model_name) or not tag_datas:
            return
        tag_map_info = Tag.TAG_MODEL_MAP[model_name]
        tag_rel_model = tag_map_info["relation"]
        tag_creates = []
        tag_ids = []
        for tag_data in tag_datas:
            tag_creates.append(eval(tag_rel_model)(
                tag_id=tag_data["tag_id"],
                object_id=obj_id,
                tag_value=tag_data["tag_value"]
            ))
            tag_ids.append(tag_data["tag_id"])
        eval(tag_rel_model).objects.bulk_create(tag_creates)
        Tag.objects.filter_active(id__in=tag_ids, is_used=False).update(is_used=True)


class WdListCreateAPIView(WdListAPIView, WdCreateAPIView):
    p_serializer_class = None
    g_serializer_class = None

    def check_parameter(self, kwargs):
        return super(WdListCreateAPIView, self).check_parameter(kwargs)

    def post(self, request, *args, **kwargs):
        if self.p_serializer_class is not None:
            self.serializer_class = self.p_serializer_class
        return super(WdListCreateAPIView, self).post(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if self.g_serializer_class is not None:
            self.serializer_class = self.g_serializer_class
        return super(WdListCreateAPIView, self).get(request, *args, **kwargs)


class WdUpdateAPIView(UpdateAPIView, WdAPIView):
    partial = True
    POST_DATA_RESPONSE = False
    p_serializer_class = None
    UPDATE_TAG = True

    def put(self, request, *args, **kwargs):
        if self.p_serializer_class is not None:
            self.serializer_class = self.p_serializer_class
        if self.partial:
            rsp = self.partial_update(request, *args, **kwargs)
        else:
            rsp = self.update(request, *args, **kwargs)
        if self.UPDATE_TAG:
            self.perform_tag()
        if self.POST_DATA_RESPONSE:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, rsp.data)
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def perform_tag(self):
        u"""tag model relation change value"""
        from research.models import *
        obj_id = self.get_id()
        model_name = self.model.__name__
        tag_datas = self.request.data.get("tag_datas")
        if not Tag.TAG_MODEL_MAP.has_key(model_name) or not tag_datas:
            return
        tag_map_info = Tag.TAG_MODEL_MAP[model_name]
        tag_rel_model = tag_map_info["relation"]
        bulk_list = []
        for tag_data in tag_datas:
            qs = eval(tag_rel_model).objects.filter_active(
                tag_id=tag_data["tag_id"],
                object_id=obj_id
            )
            if qs.exists():
                qs.update(tag_value=tag_data["tag_value"])
            else:
                bulk_list.append(eval(tag_rel_model)(
                    tag_id=tag_data["tag_id"],
                    object_id=obj_id,
                    tag_value=tag_data["tag_value"]
                ))
        eval(tag_rel_model).objects.bulk_create(bulk_list)


class WdRetrieveAPIView(WdAPIView, RetrieveAPIView):

    def get(self, request, *args, **kwargs):
        rsp = super(WdRetrieveAPIView, self).get(request, *args, **kwargs)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, rsp.data)


class WdDestroyAPIView(WdAPIView, DestroyAPIView):
    OBJECT_WITH_ACTIVE = True
    DEL_OWN_PERMISSION_CHECK = True

    def delete(self, request, *args, **kwargs):
        self.OWN_PERMISSION_CHECK = self.DEL_OWN_PERMISSION_CHECK
        super(WdDestroyAPIView, self).delete(request, *args, **kwargs)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def perform_destroy(self, instance):
        if self.OBJECT_WITH_ACTIVE:
            instance.is_active = False
            if hasattr(instance, 'last_modify_user_id'):
                instance.last_modify_user_id = self.request.user.id
            instance.save()
        else:
            instance.delete()


class WdRetrieveUpdateAPIView(WdRetrieveAPIView, WdUpdateAPIView):
    serializer_class = None
    p_serializer_class = None
    g_serializer_class = None
    GET_OWN_PERMISSION_CHECK = True
    PUT_OWN_PERMISSION_CHECK = True

    def put(self, request, *args, **kwargs):
        self.OWN_PERMISSION_CHECK = self.PUT_OWN_PERMISSION_CHECK
        if self.p_serializer_class is not None:
            self.serializer_class = self.p_serializer_class
        return super(WdRetrieveUpdateAPIView, self).put(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        self.OWN_PERMISSION_CHECK = self.GET_OWN_PERMISSION_CHECK
        if self.g_serializer_class is not None:
            self.serializer_class = self.g_serializer_class
        return super(WdRetrieveUpdateAPIView, self).get(request, *args, **kwargs)


class WdTemplateHTMLRenderer(TemplateHTMLRenderer):
    pass


class WdTemplateView(WdAPIView):
    WD_TEMPLATE_VIEW = True
    default_template_name = settings.CLIENT_HOST
    renderer_classes = (WdTemplateHTMLRenderer, )

    def get_page_count(self, count):
        page_size = int(self.request.GET.get("page_size_count", settings.REST_FRAMEWORK['PAGE_SIZE']))
        if count % page_size == 0:
            return count / page_size
        else:
            return count / page_size + 1

    def get(self, request, *args, **kwargs):
        return Response()


class WdExeclExportView(WdAPIView):
    u"""数据导出Excel文件下载"""

    default_export_file_name = "wd-export.xlsx"

    def get_title(self):
        pass

    def get_data(self):
        pass

    @abstractmethod
    def get_file(self):
        pass

    def get(self, request, *args, **kwargs):
        file_full_path = self.get_file()
        if file_full_path is None:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)
        r = FileResponse(open(file_full_path, "rb"))
        r['Content-Disposition'] = 'attachment; filename=%s' % self.default_export_file_name
        return r

class CustomModelViewSet(viewsets.ModelViewSet):

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)            
        self.perform_create(serializer)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)           
        self.perform_update(serializer)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)            

        serializer = self.get_serializer(queryset, many=True)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)  