# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json
import random
import time

from django.shortcuts import render

# Create your views here.
from rest_framework import status

from assessment.models import AssessSurveyRelation
from question.models import Question, QuestionFacet, QuestionOption
from question.serializers import QuestionSerializer, QuestionDetailSerializer, QuestionOptionSerializer
from research.models import ResearchDimension, ResearchSubstandard
from research.research_utils import ResearchModelUtils
from survey.models import Survey, SurveyModelFacetRelation, SurveyQuestionRelation, SurveyQuestionResult
from survey.serializers import SurveyBasicSerializer, SurveyForceQuestionResultSerializer
from survey.survey_utils import SurveyUtils
from survey.tasks import statistics_question_count, survey_used_count
from utils.logger import info_logger
from utils.response import ErrorCode, general_json_response
from utils.views import WdListCreateAPIView, WdDestroyAPIView, WdRetrieveUpdateAPIView, WdCreateAPIView, WdListAPIView


class OrgSurveyListCreateView(WdListCreateAPIView):
    u"""组织问卷 创建与列表接口
    order by: id, use_count, title
    """

    model = Survey
    serializer_class = SurveyBasicSerializer
    POST_CHECK_REQUEST_PARAMETER = ("title", )
    SEARCH_FIELDS = ('title', 'en_title')
    POST_DATA_ID_RESPONSE = True
    FILTER_FIELDS = ('survey_status', )

    def custom_filter(self, qs):
        qs = qs.filter(survey_type=Survey.SURVEY_ORG)
        return qs

    def qs_filter(self, qs):
        # 统计问卷的使用次数，获取组织问卷时触发
        survey_used_count.delay()
        qs = super(OrgSurveyListCreateView, self).qs_filter(qs)
        return self.custom_filter(qs)

    def qs_business_role(self, qs):
        from wduser.models import AuthUser, RoleUser, RoleBusinessPermission, BusinessPermission, RoleUserBusiness
        user = self.request.user
        if user.role_type == AuthUser.ROLE_SUPER_ADMIN:
            return qs
        role_ids = RoleUser.objects.filter_active(
            user_id=self.request.user.id).values_list("role_id", flat=True)
        pm_ids = RoleBusinessPermission.objects.filter_active(
            role_id__in=role_ids).values_list("permission_id", flat=True)
        if BusinessPermission.PERMISSION_ALL in pm_ids or BusinessPermission.PERMISSION_SURVEY_ORG_ALL in pm_ids \
            or BusinessPermission.PERMISSION_ENTERPRISE_PART in pm_ids:
            return qs
        role_user_qs = RoleUserBusiness.objects.filter_active(
            user_id=self.request.user.id, model_type=RoleUserBusiness.MODEL_TYPE_SURVEY)
        model_ids = role_user_qs.values_list("model_id", flat=True)
        return qs.filter(id__in=model_ids)


class PersonalSurveyListCreateView(OrgSurveyListCreateView):
    u"""个人问卷"""

    def post_check_parameter(self, kwargs):
        self.request.data["survey_type"] = Survey.SURVEY_PERSONAL
        return super(PersonalSurveyListCreateView, self).post_check_parameter(kwargs)

    def custom_filter(self, qs):
        qs = qs.filter(survey_type=Survey.SURVEY_PERSONAL)
        return qs


class Survey360ListCreateView(OrgSurveyListCreateView):
    u"""360问卷"""

    def post_check_parameter(self, kwargs):
        self.request.data["survey_type"] = Survey.SURVEY_360
        self.request.data["form_type"] = Survey.FORM_TYPE_FORCE
        return super(Survey360ListCreateView, self).post_check_parameter(kwargs)

    def custom_filter(self, qs):
        qs = qs.filter(survey_type=Survey.SURVEY_360)
        return qs


class OrgSurveyDetailView(WdDestroyAPIView, WdRetrieveUpdateAPIView):
    u"""问卷的删除 修改 获取详情接口"""
    model = Survey
    serializer_class = SurveyBasicSerializer
    # TODO: 问卷模型关联关系修改的话，记得去掉关联的题目关系

    def post_check_parameter(self, kwargs):
        # 燕计划，临时取消限制，方便调整信息
        obj = self.get_object()
        self.old_model_id = obj.model_id
        self.new_model_id = int(self.request.data.get("model_id", obj.model_id))
        form_type = int(self.request.data.get("form_type", obj.form_type))
        if obj.use_count > 0 and (self.new_model_id != self.old_model_id or form_type != obj.form_type):
        # if self.new_model_id != self.old_model_id or form_type != obj.form_type:
            # 研究院金老师方便调整 工作价值观
            return ErrorCode.SURVEY_USED_DELETE_MODIFY_FORBID
        return super(OrgSurveyDetailView, self).post_check_parameter(kwargs)

    def delete_check_parameter(self, kwargs):
        obj = self.get_object()
        if obj.use_count > 0:
            return ErrorCode.SURVEY_USED_DELETE_MODIFY_FORBID
        info_logger.info('user_id %s want delete survey_id %s' % (self.request.user.id, obj.id))
        return super(OrgSurveyDetailView, self).delete_check_parameter(kwargs)

    def perform_update(self, serializer):
        super(OrgSurveyDetailView, self).perform_update(serializer)
        obj = self.get_object()
        if self.new_model_id != 0 and self.new_model_id != self.old_model_id:
            SurveyModelFacetRelation.objects.filter_active(survey_id=obj.id).update(is_active=False)
            SurveyQuestionRelation.objects.filter_active(survey_id=obj.id).update(is_active=False)
        # 修改自定义配置
        custom_config = self.request.data.get("custom_config", None)
        if custom_config:
            obj.set_custom_config(custom_config)


class PersonalSurveyDetailView(OrgSurveyDetailView):
    u"""个人问卷  """
    pass


class Survey360DetailView(OrgSurveyDetailView):
    u"""360问卷"""
    pass


class OrgSurveyOpsView(WdCreateAPIView):
    u"""
    问卷操作接口
    ops_type : release 发布
    """
    model = Survey
    serializer_class = SurveyBasicSerializer
    POST_CHECK_REQUEST_PARAMETER = ('ops_type', 'survey_id')
    OPS_TYPE_RELEASE = 'release'

    def check_survey_model_question(self, survey):
        if SurveyQuestionRelation.objects.filter_active(survey_id=survey.id).exists() and \
                SurveyQuestionResult.objects.filter_active(survey_id=survey.id).exists():
            # 关联了题目，选项 ，且预览确认了
            return True
        return False

    def release_ops(self):
        survey = Survey.objects.get(id=self.survey_id)
        if survey.model_id == 0:
            # 未关联模型，不能发布
            return ErrorCode.SURVEY_RELEASE_FORBID_WITHOUT_MODEL
        # TODO: 检查问卷模型是否关联了题目
        if not self.check_survey_model_question(survey):
            return ErrorCode.SURVEY_RELEASE_FORBID_MODEL_QUESTION_RELATED_ERROR
        survey.survey_status = Survey.SURVEY_STATUS_RELEASE
        survey.save()
        ResearchModelUtils.add_used_count(survey.model_id)
        statistics_question_count.delay(survey.id)
        return ErrorCode.SUCCESS

    def post(self, request, *args, **kwargs):
        rst_code = ErrorCode.SUCCESS
        if self.ops_type == self.OPS_TYPE_RELEASE:
            rst_code = self.release_ops()
        return general_json_response(status.HTTP_200_OK, rst_code)


class SurveyModelFacetQuestionRelationOpsView(WdListCreateAPIView, WdDestroyAPIView):
    u"""问卷模型维度指标关联构面题目"""

    OPS_TYPE_REPLACE = 'new-replace'
    OPS_TYPE_ADD = 'add'
    OPS_TYPE_VIEW_ALL = 'view_all'
    OPS_TYPE_VIEW_UNIFORMITY = 'view_uniformity'
    OPS_TYPE_VIEW_PRAISE = 'view_praise'

    POST_CHECK_REQUEST_PARAMETER = (
        "ops_type", "survey_id", "model_id", "facet_infos", "related_type",
        "related_obj_id", "related_obj_type")
    DELETE_CHECK_REQUEST_PARAMETER = ("survey_id", "question_ids")
    GET_CHECK_REQUEST_PARAMETER = ("survey_id", "ops_type", "related_obj_type", "related_obj_id")

    def remove_old_relations(self):
        qs = SurveyModelFacetRelation.objects.filter_active(
            survey_id=self.survey_id, model_id=self.model_id,
            related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id
        )
        ids = list(qs.values_list("id", flat=True))
        qs.update(is_active=False)
        SurveyQuestionRelation.objects.filter_active(model_facet_relation_id__in=ids).update(is_active=False)

    def ops_manual(self):
        u"""手动选题"""
        questions = self.request.data.get("questions", None)
        is_question_passage = self.request.data.get("is_question_passage", False)
        if questions is None:
            return ErrorCode.INVALID_INPUT
        if self.ops_type == self.OPS_TYPE_REPLACE:
            self.remove_old_relations()

        related_obj = SurveyModelFacetRelation.objects.create(
            survey_id=self.survey_id, model_id=self.model_id,
            related_type=SurveyModelFacetRelation.RELATED_TYPE_MANUAL,
            related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id,
            facet_ids=json.dumps(self.facet_infos)
        )
        relation_qs = []
        # 关联所有题目
        if questions == 'all':
            # TODO:讲self.facet_infos按一个进行了处理，支持多选的话需要调整
            key_words = self.request.data.get("key_words", None)
            question_category = self.request.data.get("question_category", None)
            facet_id = self.facet_infos[0]["id"]
            question_qs = Question.objects.filter_active(question_facet_id=facet_id)
            if key_words:
                question_qs = question_qs.filter(title__icontains=key_words)
            if question_category and int(question_category) in [Question.CATEGORY_UNIFORMITY, Question.CATEGORY_PRAISE]:
                question_qs = question_qs.filter(question_category=question_category)
            questions = question_qs.values_list("id", flat=True)
        # 如果是材料题
        else:
            if is_question_passage:
                questions = Question.objects.filter_active(
                    question_passage_id__in=questions).values_list("id", flat=True)
        # 关联传入的或得到的题目
        for question_id in questions:
            relation_qs.append(SurveyQuestionRelation(
                survey_id=self.survey_id, model_facet_relation_id=related_obj.id, question_id=question_id
            ))
        SurveyQuestionRelation.objects.bulk_create(relation_qs)
        return ErrorCode.SUCCESS

    def ops_auto(self):
        u"""自动选题"""
        question_count = self.request.data.get("question_count", None)
        question_category = self.request.data.get("question_category", None)
        if question_count is None:
            return ErrorCode.INVALID_INPUT
        if self.ops_type == self.OPS_TYPE_REPLACE:
            self.remove_old_relations()

        related_obj = SurveyModelFacetRelation.objects.create(
            survey_id=self.survey_id, model_id=self.model_id,
            related_type=SurveyModelFacetRelation.RELATED_TYPE_AUTO,
            related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id,
            facet_ids=json.dumps(self.facet_infos), question_count=question_count
        )
        question_ids = SurveyQuestionRelation.objects.filter_active(
            survey_id=self.survey_id).values_list("question_id", flat=True)
        facet_ids = [int(facet_info["id"]) for facet_info in self.facet_infos]
        query_set = Question.objects.filter_active(
            question_facet_id__in=facet_ids).exclude(id__in=question_ids).values_list(
            "id", flat=True)
        # 会排除已经关联过的题目
        if question_category == Question.CATEGORY_PRAISE or question_category == Question.CATEGORY_UNIFORMITY:
            query_set = query_set.filter(question_category=question_category)
        questions = query_set[:question_count]
        if len(questions) == 0:
            return ErrorCode.SURVEY_QUESTION_AUTO_EMPTY
        relation_qs = []
        for question_id in questions:
            relation_qs.append(SurveyQuestionRelation(
                survey_id=self.survey_id, model_facet_relation_id=related_obj.id, question_id=question_id
            ))
        SurveyQuestionRelation.objects.bulk_create(relation_qs)
        return ErrorCode.SUCCESS

    def ops_view_all(self):
        smfrqs = SurveyModelFacetRelation.objects.filter_active(
            survey_id=self.survey_id, related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id)
        if not smfrqs.exists():
            return ErrorCode.SURVEY_MODEL_SUBSTANDARD_NOT_RELATED_QUESTION, None
        facet_infos = []
        related_facet_ids = []
        for smfr in smfrqs:
            facet_ids, facet_weights = smfr.get_facet_infos()
            for index, facet_id in enumerate(facet_ids):
                if facet_id not in related_facet_ids:
                    facet_infos.append({
                        "id": facet_id,
                        "weight": facet_weights[index],
                        "name": QuestionFacet.objects.get(id=facet_id).name
                    })
                    related_facet_ids.append(facet_id)
        question_ids_qs = SurveyQuestionRelation.objects.filter_active(
            survey_id=self.survey_id, model_facet_relation_id__in=smfrqs.values_list("id", flat=True)
        )
        question_ids = question_ids_qs.filter(related_facet_type=SurveyQuestionRelation.RELATED_FACET_TYPE_QUESTION).values_list("question_id", flat=True)
        questions = Question.objects.filter_active(id__in=question_ids)
        question_data = QuestionSerializer(instance=questions, many=True).data
        # 这个是子标关联那边，这里需要返回选项级别的关联
        options_ids = question_ids_qs.filter(related_facet_type=SurveyQuestionRelation.RELATED_FACET_TYPE_OPTION).values_list("question_option_id", flat=True)
        options = QuestionOption.objects.filter_active(id__in=options_ids)
        option_data = QuestionOptionSerializer(instance=options, many=True).data
        return ErrorCode.SUCCESS, {"facet_infos": facet_infos, "question_data": question_data, "option_data": option_data}

    def ops_view_uniformity(self):
        smfrqs = SurveyModelFacetRelation.objects.filter_active(
            survey_id=self.survey_id, related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id)
        if not smfrqs.exists():
            return ErrorCode.SURVEY_MODEL_SUBSTANDARD_NOT_RELATED_QUESTION, None
        question_ids = SurveyQuestionRelation.objects.filter_active(
            survey_id=self.survey_id, model_facet_relation_id__in=smfrqs.values_list("id", flat=True)).values_list(
            "question_id", flat=True)
        questions = Question.objects.filter_active(id__in=question_ids, question_category=Question.CATEGORY_UNIFORMITY)
        question_data = QuestionSerializer(instance=questions, many=True).data
        return ErrorCode.SUCCESS, {"question_data": question_data}

    def ops_view_praise(self):
        smfrqs = SurveyModelFacetRelation.objects.filter_active(
            survey_id=self.survey_id, related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id)
        if not smfrqs.exists():
            return ErrorCode.SURVEY_MODEL_SUBSTANDARD_NOT_RELATED_QUESTION, None
        question_ids = SurveyQuestionRelation.objects.filter_active(
            survey_id=self.survey_id, model_facet_relation_id__in=smfrqs.values_list("id", flat=True)).values_list(
            "question_id", flat=True)
        questions = Question.objects.filter_active(id__in=question_ids, question_category=Question.CATEGORY_PRAISE)
        question_data = QuestionSerializer(instance=questions, many=True).data
        return ErrorCode.SUCCESS, {"question_data": question_data}

    def post(self, request, *args, **kwargs):
        u"""模型维度指标与构面的关联，以及选择题目
        支持新增题目，或者全部替换
        """
        relation_option_qs = SurveyModelFacetRelation.objects.filter_active(
            survey_id=self.survey_id,
            model_id=self.model_id,
            related_facet_type=SurveyModelFacetRelation.RELATED_FACET_TYPE_OPTION
        )
        if relation_option_qs.exists():
            # 问卷关联了选项就不能关联题目
            return general_json_response(status.HTTP_200_OK, ErrorCode.SURVEY_QUESTION_OPTION_DOUBLE_ERROR, [])
        rst_code = ErrorCode.SUCCESS
        if self.related_type == SurveyModelFacetRelation.RELATED_TYPE_MANUAL:
            # 手动组卷
            rst_code = self.ops_manual()
        elif self.related_type == SurveyModelFacetRelation.RELATED_TYPE_AUTO:
            # 自动组卷
            rst_code = self.ops_auto()
        if rst_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, rst_code)
        question_category = self.request.data.get("question_category", None)
        if not question_category or int(question_category) == Question.CATEGORY_NORMAL:
            rst_code, rst_data = self.ops_view_all()
        elif int(question_category) == Question.CATEGORY_UNIFORMITY:
            rst_code, rst_data = self.ops_view_uniformity()
        elif int(question_category) == Question.CATEGORY_PRAISE:
            rst_code, rst_data = self.ops_view_praise()
        else:
            rst_code, rst_data = self.ops_view_all()
        return general_json_response(status.HTTP_200_OK, rst_code, rst_data)

    def delete(self, request, *args, **kwargs):
        u"""维度指标关联题目删除调整"""
        if "," in self.question_ids:
            self.question_ids = [int(obj_id) for obj_id in self.question_ids.split(",")]
        else:
            self.question_ids = [int(self.question_ids)]
        SurveyQuestionRelation.objects.filter_active(
            survey_id=self.survey_id,
            question_id__in=self.question_ids
        ).update(is_active=False)
        SurveyQuestionResult.objects.filter_active(
            survey_id=self.survey_id,
            question_id__in=self.question_ids
        ).update(is_active=False)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def get(self, request, *args, **kwargs):
        u"""查看当前所有题目 测谎题 社会称许题
        迫选组卷，仅能查看指标/维度下选的全部题目，最终迫选结果在预览里面
        """
        rst_code = ErrorCode.SUCCESS
        data = {}

        if self.ops_type == self.OPS_TYPE_VIEW_ALL:
            # 查看全部题目
            rst_code, data = self.ops_view_all()
        elif self.ops_type == self.OPS_TYPE_VIEW_PRAISE:
            # 查看社会称许题
            rst_code, data = self.ops_view_praise()
        elif self.ops_type == self.OPS_TYPE_VIEW_UNIFORMITY:
            # 查看测谎题（一致性题目）
            rst_code, data = self.ops_view_uniformity()
        if rst_code == ErrorCode.SURVEY_MODEL_SUBSTANDARD_NOT_RELATED_QUESTION:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {})
        elif rst_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, rst_code)
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)


class SurveyPreviewView(WdListCreateAPIView):
    u"""问卷预览"""

    model = Survey
    serializer_class = SurveyBasicSerializer

    GET_CHECK_REQUEST_PARAMETER = ("survey_id", )
    POST_CHECK_REQUEST_PARAMETER = ("survey_id", "question_data")

    def get(self, request, *args, **kwargs):
        rst_code, survey_data, question_data = SurveyUtils(
            self.survey_id, int(self.request.GET.get("force_option_num", 0)), int(self.request.GET.get("force_base_level", Survey.BASE_LEVEL_SUBSTANDARD)),
            is_test=False, context=self.get_serializer_context(),
        ).preview()
        if rst_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, rst_code)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {
            "survey_data": survey_data,
            "question_data": question_data
        })

    def post(self, request, *args, **kwargs):
        bulk_creates = []
        force_option_num = int(self.request.data.get("force_option_num", 0))
        force_base_level = int(self.request.data.get("force_base_level", Survey.BASE_LEVEL_SUBSTANDARD))
        survey = Survey.objects.get(id=self.survey_id)
        if force_option_num == 0 and survey.form_type == Survey.FORM_TYPE_FORCE:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)
        SurveyQuestionResult.objects.filter_active(survey_id=self.survey_id).update(is_active=False)
        for index, q_data in enumerate(self.question_data):
            bulk_creates.append(SurveyQuestionResult(
                survey_id=self.survey_id,
                order_num=index+1,
                question_id=q_data.get("id", 0),
                config_info=json.dumps(SurveyQuestionResult.parse_config_info(q_data, survey.form_type))
            ))
        SurveyQuestionResult.objects.bulk_create(bulk_creates)
        if survey.form_type == Survey.FORM_TYPE_FORCE:
            survey.set_force_option_num(force_option_num, False)
            survey.set_force_base_level(force_base_level, True)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class SurveyModelFacetOptionRelationOpsView(WdListCreateAPIView, WdDestroyAPIView):
    u"""问卷模型维度指标关联构面选项"""

    POST_CHECK_REQUEST_PARAMETER = ("survey_id", "model_id",
                                    "facet_infos", "related_type", "related_obj_id", "related_obj_type")
    DELETE_CHECK_REQUEST_PARAMETER = ("survey_id", "option_ids")
    GET_CHECK_REQUEST_PARAMETER = ("survey_id", "related_obj_type", "related_obj_id")

    def ops_manual(self):
        u"""手动选题"""
        options = self.request.data.get("options", None)
        ops_type = self.request.data.get('ops_type', None)
        #  数据预处理
        #  全部变更 则先处理当前子标旧的关联选项
        if ops_type == 'new-replace':
            qs = SurveyModelFacetRelation.objects.filter_active(
                survey_id=self.survey_id, model_id=self.model_id,
                related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id
            )
            ids = list(qs.values_list("id", flat=True))
            qs.update(is_active=False)
            SurveyQuestionRelation.objects.filter_active(model_facet_relation_id__in=ids).update(is_active=False)
        #  全选选项 则将options==all 变成一个将要的数组
        if options == 'all':
            facet_id = self.facet_infos[0]["id"]
            question_qs = Question.objects.filter_active(question_facet_id=facet_id)
            question_qs_ids = question_qs.values_list("id", flat=True)
            options_qs = QuestionOption.objects.filter_active(question_id__in=question_qs_ids, parent_id=0)
            options = list(options_qs.values_list("id", flat=True))

        #  数据合法处理 选项空
        if options is None or type(options) != list:
            return ErrorCode.INVALID_INPUT
        # 选项重复关联
        all_old_options = list(SurveyQuestionRelation.objects.filter_active(survey_id=self.survey_id).values_list("question_option_id", flat=True))
        if list((set(all_old_options).union(set(options))) ^ (set(all_old_options) ^ set(options))):
                return ErrorCode.SURVEY_REALTION_OPTION_REPEAT_ERROR
        # 一题选项关联不同维度
        def weidu_question(model_id, survey_id):
            s_m_f_r_qs = SurveyModelFacetRelation.objects.filter_active(survey_id=survey_id, model_id=model_id)
            weidu_question_map = {}
            for s_m_f_r in s_m_f_r_qs:
                all_questions = SurveyQuestionRelation.objects.filter_active(model_facet_relation_id=s_m_f_r.id).values_list('question_id', flat=True).distinct()
                if s_m_f_r.related_obj_type == SurveyModelFacetRelation.RELATED_SUBSTANDARD:
                    weidu_id = str(ResearchSubstandard.objects.get(id=s_m_f_r.related_obj_id).dimension_id)
                    if weidu_id in weidu_question_map:
                        weidu_question_map[weidu_id].append(list(all_questions))
                    else:
                        weidu_question_map[weidu_id] = list(all_questions)
            info_logger.info('%s' % weidu_question_map)
            return weidu_question_map
        now_s_m_f_r_qs = SurveyModelFacetRelation.objects.filter_active(survey_id=self.survey_id, model_id=self.model_id)
        old_other_question = []
        if now_s_m_f_r_qs.exists():
            if self.related_obj_type == SurveyModelFacetRelation.RELATED_SUBSTANDARD:
                weidu_question_map = weidu_question(self.model_id, self.survey_id)
                weidu_id = str(ResearchSubstandard.objects.get(id=self.related_obj_id).dimension_id)
                for x in weidu_question_map:
                    if x != weidu_id:
                        old_other_question.extend(weidu_question_map[x])
        if old_other_question:
            new_qsuestion_qs = QuestionOption.objects.filter_active(id__in=options).values_list('question_id', flat=True)
            for x in new_qsuestion_qs:
                if x in old_other_question:
                    return ErrorCode.SURVEY_OPTION_QUESTION_OF_DIMENSION_ERROR
        # 选项的题目不是迫选排序题
        question_ids = QuestionOption.objects.filter_active(id__in=options).values_list('question_id', flat=True)
        ques_type = list(Question.objects.filter_active(id__in=question_ids).values_list('question_type', flat=True).distinct())
        if (len(ques_type) != 1) or ques_type[0] != Question.QUESTION_TYPE_FORCE_ORDER_QUESTION:
            return ErrorCode.SURVEY_OPTION_QUESTION_TYPE_ERROR  # 选项的题目类型不是迫选排序题  44011

        # 数据处理完毕开始操作
        if ops_type == 'add':
            related_obj_qs = SurveyModelFacetRelation.objects.filter_active(
                survey_id=self.survey_id, model_id=self.model_id,
                related_type=SurveyModelFacetRelation.RELATED_TYPE_MANUAL,
                related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id,
                related_facet_type=SurveyModelFacetRelation.RELATED_FACET_TYPE_OPTION
            )
            if related_obj_qs.exists():
                related_obj = related_obj_qs[0]
            else:
                related_obj = SurveyModelFacetRelation.objects.create(
                    survey_id=self.survey_id, model_id=self.model_id,
                    related_type=SurveyModelFacetRelation.RELATED_TYPE_MANUAL,
                    related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id,
                    facet_ids=json.dumps(self.facet_infos),
                    related_facet_type=SurveyModelFacetRelation.RELATED_FACET_TYPE_OPTION
                )
        else:
            related_obj = SurveyModelFacetRelation.objects.create(
                survey_id=self.survey_id, model_id=self.model_id,
                related_type=SurveyModelFacetRelation.RELATED_TYPE_MANUAL,
                related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id,
                facet_ids=json.dumps(self.facet_infos),
                related_facet_type=SurveyModelFacetRelation.RELATED_FACET_TYPE_OPTION
            )
        relation_qs = []
        for option in options:
            qo_qs = QuestionOption.objects.filter_active(id=option)
            if qo_qs.exists():
                qo_obj = qo_qs[0]
            else:
                continue
            relation_qs.append(SurveyQuestionRelation(
                survey_id=self.survey_id, model_facet_relation_id=related_obj.id, question_option_id=option,
                question_id=qo_obj.question_id, related_facet_type=SurveyQuestionRelation.RELATED_FACET_TYPE_OPTION
            ))
        SurveyQuestionRelation.objects.bulk_create(relation_qs)
        return ErrorCode.SUCCESS

    def post(self, request, *args, **kwargs):
        # 选项只能手动关联
        rst_code = self.ops_manual()
        if rst_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, rst_code)
        rst_code, rst_data = self.ops_view_all()
        return general_json_response(status.HTTP_200_OK, rst_code, rst_data)

    def ops_view_all(self):
        smfrqs = SurveyModelFacetRelation.objects.filter_active(
            survey_id=self.survey_id, related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id,
            related_facet_type=SurveyModelFacetRelation.RELATED_FACET_TYPE_OPTION
        )
        if not smfrqs.exists():
            return ErrorCode.SURVEY_MODEL_SUBSTANDARD_NOT_RELATED_QUESTION, None
        facet_infos = []
        related_facet_ids = []
        for smfr in smfrqs:
            facet_ids, facet_weights = smfr.get_facet_infos()
            for index, facet_id in enumerate(facet_ids):
                if facet_id not in related_facet_ids:
                    facet_infos.append({
                        "id": facet_id,
                        "weight": facet_weights[index],
                        "name": QuestionFacet.objects.get(id=facet_id).name
                    })
                    related_facet_ids.append(facet_id)
        # 这边的返回question要不要返回
        question_ids_qs = SurveyQuestionRelation.objects.filter_active(
            survey_id=self.survey_id, model_facet_relation_id__in=smfrqs.values_list("id", flat=True)
        )
        question_ids = question_ids_qs.filter(related_facet_type=SurveyQuestionRelation.RELATED_FACET_TYPE_QUESTION).values_list("question_id", flat=True)
        questions = Question.objects.filter_active(id__in=question_ids)
        question_data = QuestionSerializer(instance=questions, many=True).data

        options_ids = question_ids_qs.filter(related_facet_type=SurveyQuestionRelation.RELATED_FACET_TYPE_OPTION).values_list("question_option_id", flat=True)
        options = QuestionOption.objects.filter_active(id__in=options_ids)
        option_data = QuestionOptionSerializer(instance=options, many=True).data
        return ErrorCode.SUCCESS, {"facet_infos": facet_infos, "question_data": question_data, "option_data": option_data}

    def get(self, request, *args, **kwargs):
        u"""迫选排序题，仅支持普通题
        """
        rst_code, data = self.ops_view_all()
        if rst_code == ErrorCode.SURVEY_MODEL_SUBSTANDARD_NOT_RELATED_QUESTION:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {})
        elif rst_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, rst_code)
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)

    def delete(self, request, *args, **kwargs):
        if "," in self.option_ids:
            self.option_ids = [int(obj_id) for obj_id in self.option_ids.split(",")]
        else:
            self.option_ids = [int(self.option_ids)]
        # 关联的选项
        SurveyQuestionRelation.objects.filter_active(
            survey_id=self.survey_id,
            question_option_id__in=self.option_ids
        ).update(is_active=False)
        # 选项的题目，这些选项对应的题目下的选项都没有关联时，这个题目删除
        question_ids = QuestionOption.objects.filter_active(id__in=self.option_ids).values_list("question_id", flat=True).distinct()
        # 找到这些选项的题目
        for q_id in question_ids:
            # 查看每个题目是不是有题目或选项级别的关联
            s_qs = SurveyQuestionRelation.objects.filter_active(
                survey_id=self.survey_id,
                question_id=q_id,
            )
            # 如果没有这个题目的题目和选项级别的关联，那么删除这个题目的结果关联
            if not s_qs.exists():
                SurveyQuestionResult.objects.filter_active(
                    survey_id=self.survey_id,
                    question_id=q_id
                ).update(is_active=False)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)