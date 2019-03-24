# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json
import operator

from django.db.models import Q
from django.shortcuts import render

# Create your views here.
from rest_framework import status

from WeiDuAdmin import settings
from question.models import QuestionBank, Question, QuestionFolder, QuestionFacet, QuestionOption, QuestionPassage, \
    QuestionPassageRelation
from question.question_utils import QuestionUtils
from question.serializers import QuestionBankSerializer, QuestionFolderSerializer, QuestionFacetSerializer, \
    QuestionSerializer, QuestionOptionSerializer, QuestionDetailSerializer, QuestionListDetailSerializer, \
    QuestionPassageSerializer, QuestionListSerializer
from utils.response import ErrorCode, general_json_response
from utils.views import WdListCreateAPIView, WdRetrieveUpdateAPIView, WdDestroyAPIView, WdListAPIView
from utils.logger import get_logger

logger = get_logger("question")


class QuestionBankListCreateView(WdListCreateAPIView, WdDestroyAPIView):
    u"""题库的创建和列表"""

    model = QuestionBank
    serializer_class = QuestionBankSerializer
    POST_CHECK_REQUEST_PARAMETER = ('name', )
    DELETE_CHECK_REQUEST_PARAMETER = ("bank_ids", )
    POST_DATA_ID_RESPONSE = True
    SEARCH_FIELDS = ("name", "desc", "code")

    def post_check_parameter(self, kwargs):
        err_code = super(QuestionBankListCreateView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        if QuestionBank.objects.filter_active(name=self.name).exists():
            return ErrorCode.QUESTION_OBJECT_NAME_REPEAT
        return ErrorCode.SUCCESS

    def perform_create(self, serializer):
        super(QuestionBankListCreateView, self).perform_create(serializer)
        obj = self.model.objects.get(id=serializer.data["id"])
        obj.code = '%03d' % obj.id
        obj.save()

    def delete(self, request, *args, **kwargs):
        if "," in self.bank_ids:
            self.bank_ids = [int(bank_id) for bank_id in self.bank_ids.split(",")]
        else:
            self.bank_ids = [int(self.bank_ids)]

        if Question.objects.filter_active(question_bank_id__in=self.bank_ids, use_count__gt=0).exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.QUESTION_USED_DELETE_FORBID)
        # question_qs = Question.objects.filter_active(question_bank_id__in=self.bank_ids, use_count__gt=0)
        # reserved_ids = question_qs.values_list("question_bank_id", flat=True)
        # delete_ids = list(set(self.bank_ids) - set(reserved_ids))
        delete_ids = self.bank_ids
        QuestionBank.objects.filter_active(id__in=delete_ids).update(is_active=False)
        QuestionFolder.objects.filter_active(question_bank_id__in=delete_ids).update(is_active=False)
        QuestionFacet.objects.filter_active(question_bank_id__in=delete_ids).update(is_active=False)
        Question.objects.filter_active(question_bank_id__in=delete_ids).update(is_active=False)
        logger.info('user_id %s want delete question_bank %s' % (self.request.user.id, delete_ids))
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class QuestionBankDetailView(WdRetrieveUpdateAPIView, WdDestroyAPIView):
    u"""题库的编辑修改和删除"""

    model = QuestionBank
    serializer_class = QuestionBankSerializer

    def delete_check_parameter(self, kwargs):
        id = self.get_id()
        if Question.objects.filter_active(question_bank_id=id, use_count__gt=0).exists():
            return ErrorCode.QUESTION_USED_DELETE_FORBID
        logger.info('user_id %s want delete question_bank %s' % (self.request.user.id, id))
        return super(QuestionBankDetailView, self).delete_check_parameter(kwargs)


class QuestionFolderListCreateView(WdListCreateAPIView, WdDestroyAPIView):
    u"""文件夹的创建和列表"""

    model = QuestionFolder
    serializer_class = QuestionFolderSerializer
    POST_DATA_ID_RESPONSE = True
    GET_CHECK_REQUEST_PARAMETER = ("question_bank_id", )
    POST_CHECK_REQUEST_PARAMETER = ("question_bank_id", 'name')
    DELETE_CHECK_REQUEST_PARAMETER = ("folder_ids", )
    SEARCH_FIELDS = ("name", "desc", "code")

    def post_check_parameter(self, kwargs):
        err_code = super(QuestionFolderListCreateView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        parent_id = self.request.data.get("parent_id", 0)
        if QuestionFolder.objects.filter_active(
                question_bank_id=self.question_bank_id, name=self.name, parent_id=parent_id).exists():
            return ErrorCode.QUESTION_OBJECT_NAME_REPEAT
        return ErrorCode.SUCCESS

    def perform_create(self, serializer):
        super(QuestionFolderListCreateView, self).perform_create(serializer)
        obj = self.model.objects.get(id=serializer.data["id"])
        # obj.code = '%03d%03d' % (obj.question_bank_id, obj.id)
        count = QuestionFolder.objects.filter(
            question_bank_id=obj.question_bank_id, parent_id=obj.parent_id).count()
        obj.code = '%03d' % count
        obj.save()

    def qs_filter(self, qs):
        qs = qs.filter(question_bank_id=self.question_bank_id)
        parent_id = self.request.GET.get("parent_id", 0)
        qs = qs.filter(parent_id=parent_id)
        return qs

    def delete(self, request, *args, **kwargs):
        if "," in self.folder_ids:
            self.folder_ids = [int(obj_id) for obj_id in self.folder_ids.split(",")]
        else:
            self.folder_ids = [int(self.folder_ids)]
        if Question.objects.filter_active(question_folder_id__in=self.folder_ids, use_count__gt=0).exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.QUESTION_USED_DELETE_FORBID)
        # question_qs = Question.objects.filter_active(question_folder_id__in=self.folder_ids, use_count=0)
        # delete_ids = question_qs.values_list("question_folder_id", flat=True)
        delete_ids = self.folder_ids
        folder_ids = QuestionFolder.objects.filter_active(id__in=delete_ids)
        folder_id_list = list(folder_ids.values_list("id", flat=True))
        folder_ids.update(is_active=False)
        folder_ids = QuestionFolder.objects.filter_active(parent_id__in=delete_ids)
        folder_id_list += list(folder_ids.values_list("id", flat=True))
        folder_ids.update(is_active=False)
        QuestionFacet.objects.filter_active(question_folder_id__in=folder_id_list).update(is_active=False)
        Question.objects.filter_active(question_folder_id__in=folder_id_list).update(is_active=False)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class QuestionFolderDetailView(WdRetrieveUpdateAPIView, WdDestroyAPIView):
    u"""文件夹的编辑修改和删除"""

    model = QuestionFolder
    serializer_class = QuestionFolderSerializer

    def delete_check_parameter(self, kwargs):
        id = self.get_id()
        if Question.objects.filter_active(question_folder_id=id, use_count__gt=0).exists():
            return ErrorCode.QUESTION_USED_DELETE_FORBID
        logger.info('user_id %s want delete question_folder_id %s' % (self.request.user.id, id))
        return super(QuestionFolderDetailView, self).delete_check_parameter(kwargs)


class QuestionFacetListCreateView(WdListCreateAPIView, WdDestroyAPIView):
    u"""构面的创建和列表"""

    model = QuestionFacet
    serializer_class = QuestionFacetSerializer
    POST_DATA_ID_RESPONSE = True
    GET_CHECK_REQUEST_PARAMETER = ('question_folder_id', )
    POST_CHECK_REQUEST_PARAMETER = ('question_bank_id', 'question_folder_id', 'name')
    DELETE_CHECK_REQUEST_PARAMETER = ("facet_ids", )
    SEARCH_FIELDS = ("name", "desc", "code")

    def post_check_parameter(self, kwargs):
        err_code = super(QuestionFacetListCreateView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        if QuestionFacet.objects.filter_active(
                question_bank_id=self.question_bank_id, name=self.name, question_folder_id=self.question_folder_id).exists():
            return ErrorCode.QUESTION_OBJECT_NAME_REPEAT
        return ErrorCode.SUCCESS

    def perform_create(self, serializer):
        super(QuestionFacetListCreateView, self).perform_create(serializer)
        obj = self.model.objects.get(id=serializer.data["id"])
        count = QuestionFacet.objects.filter(question_folder_id=obj.question_folder_id).count()
        # obj.code = '%03d%03d%03d' % (obj.question_bank_id, obj.question_folder_id, obj.id)
        obj.code = '%03d' % count
        obj.save()

    def qs_filter(self, qs):
        if self.question_folder_id == "all":
            # 关联构面的时候，搜索仅通过名称和编号搜索
            self.SEARCH_FIELDS = ("name", "code")
            return qs
        else:
            return qs.filter(question_folder_id=self.question_folder_id)

    def delete(self, request, *args, **kwargs):
        if "," in self.facet_ids:
            self.facet_ids = [int(obj_id) for obj_id in self.facet_ids.split(",")]
        else:
            self.facet_ids = [int(self.facet_ids)]
        if Question.objects.filter_active(question_facet_id__in=self.facet_ids, use_count__gt=0).exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.QUESTION_USED_DELETE_FORBID)
        # question_qs = Question.objects.filter_active(question_facet_id__in=self.facet_ids, use_count=0)
        # delete_ids = question_qs.values_list("question_facet_id", flat=True)
        delete_ids = self.facet_ids
        QuestionFacet.objects.filter_active(id__in=delete_ids).update(is_active=False)
        Question.objects.filter_active(question_facet_id__in=delete_ids).update(is_active=False)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class QuestionFacetDetailView(WdRetrieveUpdateAPIView, WdDestroyAPIView):
    u"""构面的编辑修改和删除"""

    model = QuestionFacet
    serializer_class = QuestionFacetSerializer

    def delete_check_parameter(self, kwargs):
        id = self.get_id()
        if Question.objects.filter_active(question_facet_id=id, use_count__gt=0).exists():
            return ErrorCode.QUESTION_USED_DELETE_FORBID
        logger.info('user_id %s want delete question_facet_id %s' % (self.request.user.id, id))
        return super(QuestionFacetDetailView, self).delete_check_parameter(kwargs)

    def perform_update(self, serializer):
        super(QuestionFacetDetailView, self).perform_update(serializer)
        custom_config = self.request.data.get("custom_config", None)
        if custom_config is not None:
            config_info = json.dumps(custom_config)
            obj = self.get_object()
            obj.config_info = config_info
            obj.save()


class QuestionListCreateView(WdListCreateAPIView, WdDestroyAPIView):
    u"""题目的新建和列表
    @version: 20180625 @summary: 需要可以跨构面显示题目
    """

    model = Question
    p_serializer_class = QuestionSerializer
    g_serializer_class = QuestionListSerializer
    POST_DATA_ID_RESPONSE = True
    POST_CHECK_REQUEST_PARAMETER = ('question_type', 'question_bank_id', 'question_folder_id', 'question_facet_id')
    GET_CHECK_REQUEST_PARAMETER = ('question_facet_id', )
    DELETE_CHECK_REQUEST_PARAMETER = ("question_ids", )
    SEARCH_FIELDS = ("title", )
    LIST_TYPE_NORMAL = 'normal'
    LIST_TYPE_SURVEY_QUESTION = 'related_question'

    def perform_create(self, serializer):
        super(QuestionListCreateView, self).perform_create(serializer)
        obj = self.model.objects.get(id=serializer.data["id"])
        bank = QuestionBank.objects.get(id=obj.question_bank_id)
        sub_folder = QuestionFolder.objects.get(id=obj.question_folder_id)
        folder = QuestionFolder.objects.get(id=sub_folder.parent_id)
        facet = QuestionFacet.objects.get(id=obj.question_facet_id)
        count = Question.objects.filter(question_facet_id=obj.question_facet_id).count()
        obj.code = '%s%s%s%s%03d' % (bank.code, folder.code, sub_folder.code, facet.code, count)
        obj.save()
        if obj.question_type == facet.default_question_type:
            if obj.question_type in [Question.QUESTION_TYPE_SINGLE, Question.QUESTION_TYPE_SINGLE_FILLIN]:
                if facet.default_options:
                    QuestionUtils(obj).create_option(**{'options': facet.default_options})
            else:
                if facet.default_options:
                    QuestionUtils(obj).create_option(**facet.default_options)

    def qs_order_by(self, qs):
        if self.list_type == self.LIST_TYPE_SURVEY_QUESTION:
            try:
                ordering = 'FIELD(`question_facet_id`, %s)' % ','.join(str(id) for id in self.question_facet_ids)
                qs = qs.extra(select={'ordering': ordering}, order_by=('-ordering', 'code'))
                return qs
            except Exception, e:
                print e
                return qs.order_by('code')  # super(QuestionListCreateView, self).qs_order_by(qs)
        else:
            return qs.order_by('code')  # super(QuestionListCreateView, self).qs_order_by(qs)

    def qs_filter(self, qs):
        u"""关联题目，支持跨构面显示题目"""
        question_category = self.request.GET.get("question_category", None)
        question_passage_id = self.request.GET.get("question_passage_id", None)
        question_type = self.request.GET.get("question_type", None)
        self.list_type = self.request.GET.get("list_type", self.LIST_TYPE_NORMAL)
        if question_category:
            # TODO: 前端代码请求增加参数需要
            self.list_type = self.LIST_TYPE_SURVEY_QUESTION
        self.question_facet_ids = []
        if "," in self.question_facet_id:
            self.question_facet_id = self.question_facet_id.split(",")
            # qs = qs.filter(question_facet_id__in=self.question_facet_id)
            self.question_facet_ids = self.question_facet_id
        else:
            # qs = qs.filter(question_facet_id=self.question_facet_id)
            self.question_facet_ids = [self.question_facet_id]

        if self.list_type == self.LIST_TYPE_NORMAL:
            qs = qs.filter(question_facet_id__in=self.question_facet_ids)
        if question_passage_id:
            qs = qs.filter(question_passage_id=question_passage_id)
        if question_category and int(question_category) in [Question.CATEGORY_UNIFORMITY, Question.CATEGORY_PRAISE]:
            qs = qs.filter(question_category=question_category)
        if question_type:
            qs = qs.filter(question_type=question_type)
        return qs

    def delete(self, request, *args, **kwargs):
        if "," in self.question_ids:
            self.question_ids = [int(obj_id) for obj_id in self.question_ids.split(",")]
        else:
            self.question_ids = [int(self.question_ids)]
        if Question.objects.filter_active(id__in=self.question_ids, use_count__gt=0).exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.QUESTION_USED_DELETE_FORBID)
        # question_qs = Question.objects.filter_active(id__in=self.question_ids, use_count=0)
        # delete_ids = question_qs.values_list("id", flat=True)
        delete_ids = self.question_ids
        Question.objects.filter_active(id__in=delete_ids).update(is_active=False)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class QuestionCategoryListView(WdListAPIView):
    u"""题目分类列表"""

    model = Question
    serializer_class = QuestionListDetailSerializer
    GET_CHECK_REQUEST_PARAMETER = ('category',)
    SEARCH_FIELDS = ('title', )

    def qs_filter(self, qs):
        src_uniformity_id = self.request.GET.get("src_uniformity_id", None)
        qs = qs.filter(question_category=self.category)
        if src_uniformity_id:
            # 一致性题目排除本题目
            qs = qs.exclude(id=src_uniformity_id)
        return qs


class QuestionDetailView(WdRetrieveUpdateAPIView, WdDestroyAPIView):
    u"""题目的修改 删除"""

    model = Question
    serializer_class = QuestionDetailSerializer
    p_serializer_class = QuestionSerializer

    def delete_check_parameter(self, kwargs):
        obj = self.get_object()
        if obj.use_count > 0:
            return ErrorCode.QUESTION_USED_DELETE_FORBID
        logger.info('user_id %s want delete question %s' % (self.request.user.id, obj.id))
        return super(QuestionDetailView, self).delete_check_parameter(kwargs)

    def post_check_parameter(self, kwargs):
        options_titles = self.request.data.get("options_titles", None)
        en_options_titles = self.request.data.get("en_options_titles", Question.EN_DEFAULT_MUTEX_ORDER_TITLE)
        scores = self.request.data.get("scores", None)
        if options_titles and scores:
            if len(options_titles) != 5 or len(scores) != 5 or len(en_options_titles) != 5:
                return ErrorCode.INVALID_INPUT
        # obj = self.get_object()
        # if obj.use_count > 0:
        #     return ErrorCode.QUESTION_USED_MODIFIED_FORBID
        return super(QuestionDetailView, self).post_check_parameter(kwargs)

    def partial_update(self, request, *args, **kwargs):
        obj = self.get_object()
        # 迫选排序题修改结果项相关
        if obj.question_type == Question.QUESTION_TYPE_FORCE_ORDER_QUESTION:
            options_titles = self.request.data.get("options_titles", None)
            en_options_titles = self.request.data.get("en_options_titles", Question.EN_DEFAULT_MUTEX_ORDER_TITLE)
            scores = self.request.data.get("scores", Question.DEFAULT_SCORES)
            if options_titles and scores:
                if len(scores) == 5 and len(options_titles) == 5:
                    if obj.config_info:
                        config = json.loads(obj.config_info)
                    else:
                        config = {}
                    config["option_titles"] = options_titles
                    config["en_option_titles"] = en_options_titles
                    config["scores"] = scores
                    obj.config_info = json.dumps(config)
                    obj.save()
        super(QuestionDetailView, self).partial_update(request, *args, **kwargs)


class QuestionOptionListCreateView(WdListCreateAPIView):
    u"""选项的创建、修改和展示"""

    model = QuestionOption
    serializer_class = QuestionOptionSerializer
    POST_CHECK_REQUEST_PARAMETER = ('question_id', )
    GET_CHECK_REQUEST_PARAMETER = ('question_id', )

    def post(self, request, *args, **kwargs):
        rst_code = QuestionUtils(int(self.question_id)).create_option(**self.request.data)
        return general_json_response(status.HTTP_200_OK, rst_code)

    def get(self, request, *args, **kwargs):
        data = QuestionUtils(int(self.question_id)).get_options()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)


class QuestionPassageCreateView(WdListCreateAPIView, WdDestroyAPIView):
    u"""题目文章段落创建接口"""

    POST_DATA_RESPONSE = True
    model = QuestionPassage
    serializer_class = QuestionPassageSerializer
    POST_CHECK_REQUEST_PARAMETER = ("passage", "question_facet_id")
    GET_CHECK_REQUEST_PARAMETER = ("question_facet_id", )
    DELETE_CHECK_REQUEST_PARAMETER = ("passage_ids", "question_facet_id")
    FILTER_FIELDS = ("question_facet_id", )
    SEARCH_FIELDS = ("passage",)   # 10.9 增加材料搜索

    # 批量删除
    def delete(self, request, *args, **kwargs):
        if "," in self.passage_ids:
            self.passage_ids = [int(obj_id) for obj_id in self.passage_ids.split(",")]
        else:
            if self.passage_ids:
                self.passage_ids = [int(self.passage_ids)]
        for passage_id in self.passage_ids:
            if Question.objects.filter_active(question_passage_id=passage_id, use_count__gt=0).exists():
                return general_json_response(status.HTTP_200_OK, ErrorCode.QUESTION_USED_DELETE_FORBID)
        passage_qs = QuestionPassage.objects.filter_active(id__in=self.passage_ids,
                                                           question_facet_id=self.question_facet_id)
        # 批量删除材料禁止
        for passage_id in self.passage_ids:
            if Question.objects.filter_active(question_passage_id=passage_id, use_count__gt=0).exists():
                return general_json_response(status.HTTP_200_OK, ErrorCode.QUESTION_USED_DELETE_FORBID)
        passage_qs.update(is_active=False)
        logger.info("user_id %s want delete passage_ids %s" % (self.request.user.id, self.passage_ids))
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def qs_order_by(self, qs):
        return qs.order_by("id")

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


class QuestionPassageDetailView(WdRetrieveUpdateAPIView, WdDestroyAPIView):
    u"""题目文章段落修改接口"""

    model = QuestionPassage
    serializer_class = QuestionPassageSerializer

    def delete_check_parameter(self, kwargs):
        passage_id = self.get_id()
        if Question.objects.filter_active(question_passage_id=passage_id, use_count__gt=0).exists():
            return ErrorCode.QUESTION_USED_DELETE_FORBID
        logger.info('user_id %s want delete question_passage %s' % (self.request.user.id, passage_id))
        return super(QuestionPassageDetailView, self).delete_check_parameter(kwargs)


class QuestionOptionAllListView(WdListCreateAPIView):
    u"""获得构面下所有题目的选项
    """
    model = QuestionOption
    serializer_class = QuestionOptionSerializer
    GET_CHECK_REQUEST_PARAMETER = ('question_facet_id', )

    def qs_filter(self, qs):
        self.question_facet_ids = []
        if "," in self.question_facet_id:
            self.question_facet_id = self.question_facet_id.split(",")
            self.question_facet_ids = self.question_facet_id
        else:
            self.question_facet_ids = [self.question_facet_id]
        # 获得输入构面下的所有题目 # 10.14 获得所有迫排题的选项，选项的时候就不用判断是不是迫排选项
        question_ids = Question.objects.filter(question_facet_id__in=self.question_facet_ids,
                                               question_type=Question.QUESTION_TYPE_FORCE_ORDER_QUESTION)
        qs = qs.filter(question_id__in=question_ids, parent_id=0)
        return qs
