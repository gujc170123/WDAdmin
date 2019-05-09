# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json

from django.shortcuts import render

# Create your views here.
from rest_framework import status

from survey.models import Survey
from assessment.models import AssessSurveyRelation,AssessProject
from assessment.serializers import AssessmentSurveyRelationGetSerializer, AssessSurveyReportListSerializer
from research.models import ResearchModel, ResearchDimension, ResearchSubstandard, Tag, GeneralTagRelation, Report
from research.research_utils import ResearchModelUtils, ResearchDimensionUtils, ResearchSubstandardUtils
from research.serializers import ResearchModelBasicSerializer, ResearchDimensionBasicSerializer, \
    ResearchSubstandardBasicSerializer, ResearchModelDetailSerializer, ResearchDimensionDetailSerializer, \
    ResearchSubstandardDetailSerializer, TagBasicSerializer, TagRelationSerializer, ReportBasicSerializer,\
    ReportSurveyAssessmentProjectRelation, ReportSurveyAssessmentProjectSerializer
from utils.regular import Convert
from utils.response import general_json_response, ErrorCode
from utils.views import WdListCreateAPIView, WdDestroyAPIView, WdRetrieveUpdateAPIView, WdCreateAPIView
from utils.logger import info_logger


class ResearchModelListCreateView(WdListCreateAPIView):
    u"""模型新建与列表接口
    只有标准模型可以新建，派生模型只能派生
    @version:20180621
    @summary: 个人模型，新增参数model_category = 20
    """

    model = ResearchModel
    serializer_class = ResearchModelBasicSerializer
    POST_DATA_ID_RESPONSE = True
    SEARCH_FIELDS = ('name', 'en_name')
    GET_CHECK_REQUEST_PARAMETER = ('model_type', )
    POST_CHECK_REQUEST_PARAMETER = ('name', 'en_name', 'algorithm_id')

    def post_check_parameter(self, kwargs):
        err_code = super(ResearchModelListCreateView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        if ResearchModel.objects.filter_active(name=self.name).exists():
            return ErrorCode.RESEARCH_MODEL_NAME_REPEAT
        self.request.data["model_type"] = ResearchModel.TYPE_STANDARD
        return ErrorCode.SUCCESS

    def qs_filter(self, queryset):
        u"""标准模型 派生模型 筛选
        @summary: 个人模型，新增参数model_category = 20, 默认是组织模型
        """
        category = self.request.GET.get("model_category", ResearchModel.CATEGORY_ORG)
        status = self.request.GET.get('status', None)
        queryset = queryset.filter(model_category=category)
        queryset = queryset.filter(model_type=self.model_type)
        if status is not None and len(str(status)) > 0:
            status = int(status)
            if status == ResearchModel.STATUS_RELEASE or status == ResearchModel.STATUS_DRAFT:
                queryset = queryset.filter(status=status)
        return queryset

    def qs_order_by(self, qs):
        order_name = self.get_order_by_name()
        if order_name == "name":
            return qs.order_by(Convert('name', 'gbk').desc())
        elif order_name == "-name":
            return qs.order_by(Convert('name', 'gbk').asc())
        elif order_name == "use_count":
            return qs.order_by("used_count")
        elif order_name == "-use_count":
            return qs.order_by("-used_count")
        return super(ResearchModelListCreateView, self).qs_order_by(qs)


class ResearchModelDetailAPIView(WdDestroyAPIView, WdRetrieveUpdateAPIView):
    u"""模型的详情获取，修改，删除"""

    # TODO: 已经使用的模型不能删除，仅能修改基本信息
    model = ResearchModel
    serializer_class = ResearchModelBasicSerializer
    g_serializer_class = ResearchModelDetailSerializer

    def post_check_parameter(self, kwargs):
        err_code = super(ResearchModelDetailAPIView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        name = self.request.data.get("name", None)
        algorithm_id = self.request.data.get("algorithm_id", None)
        obj = self.get_object()
        # 9.20 增加模型的维度排序
        is_dimension_by_order = self.request.data.get("is_dimension_by_order", None)
        if is_dimension_by_order == True :
            orders = self.request.data.get("orders", [])
            if not orders:
                return ErrorCode.INVALID_INPUT
        if name is not None:
            if name != obj.name and ResearchModel.objects.filter_active(name=name).exists():
                return ErrorCode.RESEARCH_MODEL_NAME_REPEAT
        if obj.used_count > 0 and algorithm_id is not None and obj.algorithm_id != algorithm_id:
            return ErrorCode.RESEARCH_MODEL_USED_MODIFY_ALGO_ERROR
        return ErrorCode.SUCCESS

    def delete(self, request, *args, **kwargs):
        self.obj = self.get_object()
        if self.obj.used_count > 0:
            return general_json_response(status.HTTP_200_OK, ErrorCode.RESEARCH_MODEL_USED_DEL_ERROR)
        info_logger.info('user_id %s want delete researchmodel %s' % (self.request.user.id, self.obj.id))
        return super(ResearchModelDetailAPIView, self).delete(request, *args, **kwargs)

    def perform_destroy(self, instance):
        super(ResearchModelDetailAPIView, self).perform_destroy(instance)
        ResearchDimension.objects.filter_active(model_id=self.obj.id).update(is_active=False)
        ResearchSubstandard.objects.filter_active(model_id=self.obj.id).update(is_active=False)

    def perform_update(self, serializer):
        super(ResearchModelDetailAPIView, self).perform_update(serializer)
        is_dimension_by_order = self.request.data.get("is_dimension_by_order", None)
        if is_dimension_by_order == True:
            orders = self.request.data.get("orders", [])
            for index, order_id in enumerate(orders):
                ResearchDimension.objects.filter_active(id=order_id).update(order_number=index + 1)
        elif is_dimension_by_order == False:
            orders = self.request.data.get("orders", [])
            ResearchDimension.objects.filter_active(id__in=orders).update(order_number=0)


class ResearchModelOpsAPIView(WdCreateAPIView):
    u"""模型的发布与派生"""

    model = ResearchModel
    # serializer_class =
    POST_CHECK_REQUEST_PARAMETER = ('ops_type', 'model_id')
    OPS_TYPE_RELEASE = 'release'
    OPS_TYPE_INHERIT = 'inherit'

    def post_check_parameter(self, kwargs):
        err_code = super(ResearchModelOpsAPIView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        if self.ops_type == self.OPS_TYPE_RELEASE:
            if not ResearchSubstandard.objects.filter_active(model_id=self.model_id).exists():
                return ErrorCode.RESEARCH_MODEL_RELEASE_DATA_INVALID
        elif self.ops_type == self.OPS_TYPE_INHERIT:
            src_model = ResearchModel.objects.get(id=self.model_id)
            if src_model.status != ResearchModel.STATUS_RELEASE:
                return ErrorCode.RESEARCH_MODEL_INHERIT_DATA_INVALID
        return ErrorCode.SUCCESS

    def release_model(self):
        ResearchModel.objects.filter(id=self.model_id).update(status=ResearchModel.STATUS_RELEASE)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def inherit_model(self):
        new_model_name = self.request.data.get('new_model_name', None)
        new_model_en_name = self.request.data.get('new_model_en_name', None)
        if new_model_name is None or new_model_en_name is None:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)
        inherit_obj = ResearchModelUtils.deep_copy(int(self.model_id), new_model_name, new_model_en_name)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"id": inherit_obj.id})

    def post(self, request, *args, **kwargs):
        if self.ops_type == self.OPS_TYPE_RELEASE:
            return self.release_model()
        elif self.ops_type == self.OPS_TYPE_INHERIT:
            return self.inherit_model()
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)


class ResearchDimensionListCreateAPIView(WdListCreateAPIView):
    u"""维度创建与列表接口"""
    # TODO: 未发布模型的维度可以进入列表么

    model = ResearchDimension
    serializer_class = ResearchDimensionDetailSerializer
    POST_CHECK_REQUEST_PARAMETER = ('model_id', 'name', 'en_name', 'weight', 'model_type')
    POST_DATA_RESPONSE = True
    SEARCH_FIELDS = ('name', 'en_name')
    FOREIGN_SEARCH_FIELD_MAP = {'model_id': 'ResearchModel__name'}
    DEFAULT_ORDER_BY = "model_type"
    # TODO: 按照模型名称搜索

    def qs_filter(self, qs):
        u"""
        @version: 20180621 @summary: 新增model_category区分组织模型个人模型
        :param qs:
        :return:
        """
        model_category = self.request.GET.get("model_category", ResearchModel.CATEGORY_ORG)
        qs = qs.filter(model_category=model_category)
        model_ids = ResearchModel.objects.filter_active(
            status=ResearchModel.STATUS_RELEASE).values_list("id", flat=True)
        return qs.filter(model_id__in=model_ids)

    def post_check_parameter(self, kwargs):
        err_code = super(ResearchDimensionListCreateAPIView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        model_obj = ResearchModel.objects.get(id=self.model_id)
        if model_obj.used_count > 0:
            return ErrorCode.RESEARCH_DIMENSION_MODIFY_FORBID
        self.request.data["model_category"] = model_obj.model_category
        return err_code

    def perform_create(self, serializer):
        super(ResearchDimensionListCreateAPIView, self).perform_create(serializer)
        is_batch_update = int(self.request.data.get("is_batch_update", 0))
        if is_batch_update:
            rd_qs = ResearchDimension.objects.filter_active(model_id=self.model_id)
            if rd_qs.count() > 1:
                rd_qs.update(weight=self.weight)


class ResearchDimensionDetailView(WdDestroyAPIView, WdRetrieveUpdateAPIView):
    u"""维度的删除 更新接口"""
    model = ResearchDimension
    serializer_class = ResearchDimensionDetailSerializer
    POST_DATA_RESPONSE = True

    def post_check_parameter(self, kwargs):
        err_code = super(ResearchDimensionDetailView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        self.dimension_obj = self.get_object()
        research_model = ResearchModel.objects.get(id=self.dimension_obj.model_id)
        if research_model.used_count > 0:
            return ErrorCode.RESEARCH_DIMENSION_MODIFY_FORBID
        return err_code

    def delete_check_parameter(self, kwargs):
        err_code = super(ResearchDimensionDetailView, self).delete_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        self.dimension_obj = self.get_object()
        research_model = ResearchModel.objects.get(id=self.dimension_obj.model_id)
        # if (research_model.used_count > 0) or research_model.status == ResearchModel.STATUS_RELEASE:
            # 模型使用次数为0，不能删除维度了   修继伟   2018/09/21
        if research_model.used_count > 0:
            return ErrorCode.RESEARCH_DIMENSION_DELETE_FORBID
        info_logger.info('user_id %s want delete model_id %s research_dimension %s' % (self.request.user.id, self.dimension_obj.model_id, self.dimension_obj.id))
        return err_code

    def perform_update(self, serializer):
        super(ResearchDimensionDetailView, self).perform_update(serializer)
        is_batch_update = int(self.request.data.get("is_batch_update", 0))
        if is_batch_update:
            rd_qs = ResearchDimension.objects.filter_active(model_id=self.dimension_obj.model_id)
            rd_qs.update(weight=serializer.data["weight"])


class ResearchDimensionCopyCreateAPIView(WdCreateAPIView):
    u"""维度拷贝接口"""
    # TODO: 未发布模型的维度可以拷贝么

    model = ResearchDimension
    serializer_class = ResearchDimensionDetailSerializer
    POST_CHECK_REQUEST_PARAMETER = ('dest_model_id', 'src_dimension_id')

    def post(self, request, *args, **kwargs):
        dimension_obj = ResearchDimensionUtils.deep_copy(int(self.src_dimension_id), int(self.dest_model_id))
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,
                                     ResearchDimensionDetailSerializer(instance=dimension_obj).data)


class ResearchSubstandardListCreateAPIView(WdListCreateAPIView):
    u"""指标创建与列表接口"""
    # TODO: 未发布模型的指标可以拷贝么

    model = ResearchSubstandard
    serializer_class = ResearchSubstandardDetailSerializer
    POST_CHECK_REQUEST_PARAMETER = ("model_id", "dimension_id", "parent_id", "name", "en_name", "weight", "model_type")
    POST_DATA_RESPONSE = True
    SEARCH_FIELDS = ('name', 'en_name')
    FOREIGN_SEARCH_FIELD_MAP = {'model_id': 'ResearchModel__name'}
    DEFAULT_ORDER_BY = "model_type"

    def qs_filter(self, qs):
        model_category = self.request.GET.get("model_category", ResearchModel.CATEGORY_ORG)
        qs = qs.filter(model_category=model_category)
        model_ids = ResearchModel.objects.filter_active(
            status=ResearchModel.STATUS_RELEASE).values_list("id", flat=True)
        return qs.filter(model_id__in=model_ids)

    def post_check_parameter(self, kwargs):
        err_code = super(ResearchSubstandardListCreateAPIView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        model_obj = ResearchModel.objects.get(id=self.model_id)
        if model_obj.used_count > 0:
            return ErrorCode.RESEARCH_DIMENSION_MODIFY_FORBID
        self.request.data["model_category"] = model_obj.model_category
        return err_code

    def perform_create(self, serializer):
        super(ResearchSubstandardListCreateAPIView, self).perform_create(serializer)
        is_batch_update = int(self.request.data.get("is_batch_update", 0))
        if is_batch_update:
            rs_qs = ResearchSubstandard.objects.filter_active(
                model_id=self.model_id, dimension_id=self.dimension_id, parent_id=serializer.data['parent_id'])
            rs_qs.update(weight=serializer.data["weight"])


class ResearchSubstandardDetailView(WdDestroyAPIView, WdRetrieveUpdateAPIView):
    u"""指标的删除 更新接口"""
    model = ResearchSubstandard
    serializer_class = ResearchSubstandardDetailSerializer
    POST_DATA_RESPONSE = True

    def post_check_parameter(self, kwargs):
        err_code = super(ResearchSubstandardDetailView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        self.substandard_obj = self.get_object()
        self.weight_before_update = self.substandard_obj.weight
        self.weight_after_update = self.request.data.get("weight", None)
        if self.weight_after_update:
            self.weight_after_update = int(self.weight_after_update)
        research_model = ResearchModel.objects.get(id=self.substandard_obj.model_id)
        if research_model.used_count > 0:
            return ErrorCode.RESEARCH_DIMENSION_MODIFY_FORBID
        return err_code

    def delete_check_parameter(self, kwargs):
        err_code = super(ResearchSubstandardDetailView, self).delete_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        self.substandard_obj = self.get_object()
        research_model = ResearchModel.objects.get(id=self.substandard_obj.model_id)
        if (research_model.used_count > 0) or research_model.status == ResearchModel.STATUS_RELEASE:
        # if research_model.used_count > 0:
            return ErrorCode.RESEARCH_DIMENSION_DELETE_FORBID
        info_logger.info('user_id %s want delete model_id %s research_subsandard %s' % (self.request.user.id, self.substandard_obj.model_id, self.substandard_obj.id))
        return err_code

    def perform_update(self, serializer):
        super(ResearchSubstandardDetailView, self).perform_update(serializer)
        is_batch_update = int(self.request.data.get("is_batch_update", 0))
        if is_batch_update:
            rs_qs = ResearchSubstandard.objects.filter_active(
                model_id=self.substandard_obj.model_id, dimension_id=self.substandard_obj.dimension_id,
                parent_id=self.substandard_obj.parent_id)
            rs_qs.update(weight=serializer.data["weight"])


class ResearchSubstandardCopyCreateAPIView(WdCreateAPIView):
    u"""指标拷贝接口"""
    # TODO: 未发布模型的指标可以进入列表么

    model = ResearchSubstandard
    serializer_class = ResearchSubstandardDetailSerializer
    POST_CHECK_REQUEST_PARAMETER = ('dest_model_id', 'dest_demension_id', 'src_substandard_id', 'dest_parent_id')

    def post(self, request, *args, **kwargs):
        if self.dest_parent_id == self.src_substandard_id:
            return general_json_response(status.HTTP_200_OK, ErrorCode.RESEARCH_COPY_SELF_FORBID)
        substandard = ResearchSubstandardUtils.deep_copy(
            int(self.src_substandard_id), int(self.dest_model_id),
            int(self.dest_demension_id), int(self.dest_parent_id))
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,
                                     ResearchSubstandardDetailSerializer(instance=substandard).data)


class TagListCreateAPIView(WdListCreateAPIView):
    u"""
    @POST: 新建标签
    @GET：获取谋业务模型的标签
    """

    model = Tag
    serializer_class = TagBasicSerializer
    POST_CHECK_REQUEST_PARAMETER = ("tag_type", "business_model", "tag_name")
    GET_CHECK_REQUEST_PARAMETER = ("business_model", )
    SEARCH_FIELDS = ('tag_name',)

    def post_check_parameter(self, kwargs):
        err_code = super(TagListCreateAPIView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        if self.tag_type == Tag.TYPE_OPTION:
            options = self.request.data.get("options", None)  # ['test1', 'test2']
            if options is None:
                return ErrorCode.INVALID_INPUT
            self.request.data["tag_config"] = json.dumps({"options": options})
        enterprise_id = self.request.data.get("enterprise_id", None)
        if enterprise_id and int(enterprise_id) > 0:
            self.request.data["is_system"] = False
        if Tag.objects.filter_active(tag_name=self.tag_name, business_model=self.business_model).exists():
            return ErrorCode.RESEARCH_TAG_NAME_FORBID
        return err_code

    def qs_filter(self, qs):
        return qs.filter(business_model=self.business_model)


class TagDetailAPIView(WdRetrieveUpdateAPIView, WdDestroyAPIView):
    u"""标签的修改，删除"""
    # TODO： 标签的修改和删除 对数据造成的影响
    model = Tag
    serializer_class = TagBasicSerializer
    POST_CHECK_REQUEST_PARAMETER = ("tag_type", )

    def post_check_parameter(self, kwargs):
        err_code = super(TagDetailAPIView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        if self.tag_type == Tag.TYPE_OPTION:
            options = kwargs.get("options", None)
            if options is None:
                return ErrorCode.INVALID_INPUT
            self.request.data["tag_config"] = json.dumps({"options": options})
        # tag_name = self.request.data.get("tag_name", None)
        # if tag_name and Tag.objects.filter_active(
        #         tag_name=tag_name).exclude(id=self.get_id()).exists():
        #     return ErrorCode.RESEARCH_TAG_NAME_FORBID
        obj = self.get_object()
        tag_name = self.request.data.get("tag_name", None)
        if tag_name and Tag.objects.filter_active(
                tag_name=tag_name, business_model=obj.business_model).exclude(id=self.get_id()).exists():
            return ErrorCode.RESEARCH_TAG_NAME_FORBID
        # if obj.is_used:
        #     return ErrorCode.RESEARCH_TAG_USED_MODIFY_DELETE_FORBID
        return err_code

    # def delete_check_parameter(self, kwargs):
    #     rst_code = super(TagDetailAPIView, self).delete_check_parameter(kwargs)
    #     if rst_code != ErrorCode.SUCCESS:
    #         return rst_code
    #     # obj = self.get_object()
    #     # if obj.is_used:
    #     #     return ErrorCode.RESEARCH_TAG_USED_MODIFY_DELETE_FORBID
    #     return ErrorCode.SUCCESS

    def perform_destroy(self, instance):
        u"""如果标签已经使用，则不能允许删除"""
        from research.models import *
        super(TagDetailAPIView, self).perform_destroy(instance)
        eval(instance.tag_rel_model).objects.filter_active(tag_id=instance.id).update(is_active=False)
        info_logger.info('user_id %s want delete tag %s' % (self.request.user.id, instance.id))

# class TagRelationAPIView(WdListCreateAPIView):
#     u"""标签 业务模型 关联接口 新建"""
#
#     model = GeneralTagRelation
#     serializer_class = TagRelationSerializer
#     POST_CHECK_REQUEST_PARAMETER = ("business_model", "tag_datas")
#
#     def post(self, request, *args, **kwargs):
#         self.model = eval(Tag.TAG_MODEL_MAP[self.business_model])
#         self.serializer_class.Meta.model = self.model
#         tag_create = []
#         for tag_data in self.tag_datas:
#             tag_create.append(self.model(
#                 tag_id=tag_data["tag_id"],
#                 object_id=tag_data["object_id"],
#                 tag_value=tag_data["tag_value"],
#             ))
#             self.model.objects.bulk_create(tag_create)
#         return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class ReportListCreateAPIView(WdListCreateAPIView):
    u"""报告模板创建与列表接口"""

    model = Report
    serializer_class = ReportBasicSerializer
    POST_CHECK_REQUEST_PARAMETER = ('report_name', 'report_url', 'report_type_id')
    POST_DATA_RESPONSE = True
    SEARCH_FIELDS = ('report_name', )

    def post_check_parameter(self, kwargs):
        err_code = super(ReportListCreateAPIView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        if Report.objects.filter_active(report_name=self.report_name).exists():
            return ErrorCode.RESEARCH_REPORT_NAME_FORBID
        return ErrorCode.SUCCESS


class ReportDetailView(WdDestroyAPIView, WdRetrieveUpdateAPIView):
    u"""报告模板的删除  更新接口"""
    model = Report
    serializer_class = ReportBasicSerializer
    POST_DATA_RESPONSE = True

    def post_check_parameter(self, kwargs):
        err_code = super(ReportDetailView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        report_name = self.request.data.get("report_name", None)
        if report_name and Report.objects.filter_active(
                report_name=report_name).exclude(id=self.get_id()).exists():
            return ErrorCode.RESEARCH_REPORT_NAME_FORBID
        return ErrorCode.SUCCESS

    def delete_check_parameter(self, kwargs):
        err_code = super(ReportDetailView, self).delete_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        # self.report_obj = self.get_object()
        survey_relations = ReportSurveyAssessmentProjectRelation.objects.filter_active(report_id=self.get_id())
        if survey_relations.exists():
            return ErrorCode.RESEARCH_REPORT_DELETE_FORBID
        info_logger.info('user_id %s want delete report_id %s' % (self.request.user.id, self.get_id()))
        return ErrorCode.SUCCESS


class ReportSurveyListCreateAPIView(WdListCreateAPIView):
    u"""报告问卷关联创建与列表接口 """

    model = ReportSurveyAssessmentProjectRelation
    serializer_class = ReportSurveyAssessmentProjectSerializer
    POST_CHECK_REQUEST_PARAMETER = ('report_id', 'survey_infos')
    GET_CHECK_REQUEST_PARAMETER = ('report_id', )
    POST_DATA_RESPONSE = True
    FILTER_FIELDS = ('report_id', )
    SEARCH_FIELDS = ('survey_name', )

    def post(self, request, *args, **kwargs):
        report_assess_survey = []
        for survey_info in self.survey_infos:
            survey_name = Survey.objects.get(id=survey_info["survey_id"]).title
            if not ReportSurveyAssessmentProjectRelation.objects.filter_active(
                    assessment_project_id=survey_info["project_id"],
                    survey_id=survey_info["survey_id"],
                    report_id=self.report_id
            ).exists():
                report_assess_survey.append(ReportSurveyAssessmentProjectRelation(
                    assessment_project_id=survey_info["project_id"],
                    survey_id=survey_info["survey_id"],
                    report_id=self.report_id,
                    survey_name=survey_name

                ))
        ReportSurveyAssessmentProjectRelation.objects.bulk_create(report_assess_survey)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class ReportSurveyDetailView(WdDestroyAPIView, WdRetrieveUpdateAPIView):
    u"""报告问卷关联的删除接口 """
    model = ReportSurveyAssessmentProjectRelation
    serializer_class = ReportSurveyAssessmentProjectSerializer
    POST_DATA_RESPONSE = True


class ReportSurveyAssessmentProjectListAPIView(WdListCreateAPIView):
    u"""企业问卷项目筛选接口 """
    model = AssessSurveyRelation
    serializer_class = AssessSurveyReportListSerializer

    def qs_filter(self, qs):
        enterprise_id = self.request.GET.get("enterprise_id", None)
        project_id = self.request.GET.get("project_id", None)
        if project_id:
            qs = qs.filter(assess_id=project_id)
            return qs
        if enterprise_id:
            assess_ids = AssessProject.objects.filter_active(enterprise_id=enterprise_id)
            qs = qs.filter(assess_id__in=assess_ids)
        return qs

    def qs_search(self, qs):
        # 企业名称  项目名称
        key_words = self.request.GET.get("key_words", None)
        if not key_words:
            return qs
        survey_ids = Survey.objects.filter_active(title__icontains=key_words).values_list("id", flat=True)
        qs = qs.filter(survey_id__in=survey_ids)
        return qs
        # enterprise_key_words = self.request.GET.get("enterprise_key_words", None)
        # assess_key_words = self.request.GET.get("assess_key_words", None)
        # if enterprise_key_words is None and assess_key_words is None:
        #     return qs
        # elif enterprise_key_words is None and assess_key_words is not None:
        #     # 模糊查询 得到项目,问卷
        #     assess_qs = AssessProject.objects.filter_active(name__icontains=assess_key_words)
        #     # 通过 survey_id__in  过滤
        #     qs = qs.filter(survey_id__in=survey_qs.values_list("id", flat=True))
        #     return qs
        # elif enterprise_key_words is not None and assess_key_words is None:
        #     pass
        # else:
        #     pass