# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from console.tasks import auto_update_clean_status
from utils.views import WdListCreateAPIView, WdRetrieveUpdateAPIView, WdListAPIView, WdCreateAPIView, WdDestroyAPIView
from console.serializers import SurveyOverviewSerializer,  CleanTaskSerializer, AnalysisTaskSerializer,\
     EscapeTaskSerializer, CleanTaskListSerializer, EscapeTaskListSerializer, AnalysisTaskListSerializer, \
     OfficialCleanTaskSerializer
from .models import SurveyOverviewCleanTask, EscapeTask, SurveyOverviewAnalysisTask, SurveyOverviewEscapeTask, \
    SurveyOverview, CleanTask, AnalysisTask, ConsoleSurveyModelFacetRelation as SM, ConsoleSurveyQuestionRelation as SQ
from research.models import ResearchModel, ResearchDimension
from console.console_utils import DimensionUtils
from survey.models import Survey
from utils.logger import get_logger
from utils.response import ErrorCode, general_json_response
from rest_framework import status
from question.models import Question, QuestionFacet
from question.serializers import QuestionSerializer, QuestionFacetSerializer
import json
from console.etl import EtlTrialClean, EtlClean


logger = get_logger("console")


class SignalView(WdCreateAPIView):
    POST_CHECK_REQUEST_PARAMETER = ('task', 'task_id', 'status')

    def trial(self):
        for trial_id in self.task_id:
            if type(trial_id) in [str, unicode]:
                trial_id = eval(trial_id)
            obj = EtlTrialClean(trial_id)
            if self.status == u'start':
                obj.start()
            elif self.status == u'stop':
                obj.stop()
        return ErrorCode.SUCCESS

    def clean(self):
        for clean_id in self.task_id:
            if type(clean_id) in [str, unicode]:
                clean_id = eval(clean_id)
            obj = EtlClean(clean_id)
            if self.status == u'start':
                logger.debug(u"任务启动")
                obj.start()
                logger.debug(u"正式清洗任务清洗完毕")
            elif self.status == u'stop':
                logger.debug(u"任务终止")
                obj.stop()
                logger.debug(u"正式清洗任务已被终止")
        return ErrorCode.SUCCESS

    def post(self, request, *args, **kwargs):
        logger.debug("状态:%s， 任务:%s, id:%s" % (self.status, self.task, self.task_id) )
        task = self.task
        if task in ['trail_task', 'clean']:
            ret_code = self.trial()
        elif task in ['official_clean']:
                ret_code = self.clean()
        return general_json_response(status.HTTP_200_OK, ret_code)


class SurveyOverviewListView(WdListAPIView):
    u"""总揽表的创建与展示"""
    model = SurveyOverview
    serializer_class = SurveyOverviewSerializer
    SEARCH_FIELDS = ("enterprise_name", "assess_name", "survey_name")
    FILTER_FIELDS = ("enterprise_id", "assess_id", "clean_status")
    POST_DATA_RESPONSE = True
    POST_DATA_ID_RESPONSE = True


class TrialCleanTaskListCreateView(WdListCreateAPIView):
    u"""试清洗任务创建与展示"""
    model = CleanTask
    serializer_class = CleanTaskListSerializer
    POST_CHECK_REQUEST_PARAMETER = ('task_name', 'num_of_consistency_check', 'min_time_of_answer',
                                    'max_count_of_less_time', 'score_difference_of_each_group',
                                    'social_desirability_score', 'survey_overview_ids',
                                    )
    POST_DATA_RESPONSE = True
    POST_DATA_ID_RESPONSE = True

    def get_queryset(self):
        qs = super(TrialCleanTaskListCreateView, self).get_queryset()
        qs = qs.filter(parent_id=0)
        return qs

    def perform_create(self, serializer):
        super(TrialCleanTaskListCreateView, self).perform_create(serializer)
        survey_overview_ids = self.request.data.get('survey_overview_ids', None)
        SurveyOverview.objects.filter_active(id__in=eval(survey_overview_ids)).update(clean_status=20)


class CleanTaskListCreateView(WdListCreateAPIView):
    u"""清洗任务创建与展示"""
    model = CleanTask
    p_serializer_class = OfficialCleanTaskSerializer
    g_serializer_class = CleanTaskListSerializer
    serializer_class = p_serializer_class
    POST_CHECK_REQUEST_PARAMETER = ('parent_id',)
    POST_DATA_RESPONSE = True
    POST_DATA_ID_RESPONSE = True

    def get_queryset(self):
        qs = super(CleanTaskListCreateView, self).get_queryset()
        qs = qs.filter(parent_id__gt=1)
        return qs

    # def get_serializer_class(self):
    #     return self.p_serializer_class

    def perform_create(self, serializer):
        super(CleanTaskListCreateView, self).perform_create(serializer)
        clean_task = CleanTask.objects.get(id=self.parent_id)
        obj = self.model.objects.get(id=serializer.data["id"])
        obj.task_name = clean_task.task_name
        obj.num_of_consistency_check = clean_task.num_of_consistency_check
        obj.min_time_of_answer = clean_task.min_time_of_answer
        obj.max_count_of_less_time = clean_task.max_count_of_less_time
        obj.score_difference_of_each_group = clean_task.score_difference_of_each_group
        obj.social_desirability_score = clean_task.social_desirability_score
        obj.survey_overview_ids = clean_task.survey_overview_ids
        obj.clean_status = 40
        obj.save()
        bulk_list = []
        survey_overview_ids = clean_task.survey_overview_ids
        SurveyOverview.objects.filter_active(id__in=eval(survey_overview_ids)).update(clean_status=40)
        for survey_overview_id in eval(survey_overview_ids):
            survey_overview = SurveyOverview.objects.get(id=survey_overview_id)
            bulk_list.append(SurveyOverviewCleanTask(
                survey_overview_id=survey_overview_id,
                clean_task_id=serializer.data["id"],
                enterprise_id=survey_overview.enterprise_id,
                assess_id=survey_overview.assess_id,
                creator_id=self.request.user.id,
                survey_id=survey_overview.survey_id,
            ))
        SurveyOverviewCleanTask.objects.bulk_create(bulk_list)


class CleanTaskDetailView(WdRetrieveUpdateAPIView):
    """ 清洗任务详情与更新"""
    model = CleanTask
    serializer_class = CleanTaskListSerializer
    POST_DATA_ID_RESPONSE = True

    def get(self, request, *args, **kwargs):
        auto_update_clean_status(self.get_id())
        return super(CleanTaskDetailView, self).get(request, *args, **kwargs)


class EscapeTaskListCreateView(WdListCreateAPIView):
    u"""转义任务创建与展示"""
    model = EscapeTask
    p_serializer_class = EscapeTaskSerializer
    g_serializer_class = EscapeTaskListSerializer
    POST_CHECK_REQUEST_PARAMETER = ('task_name', 'clean_task_id', 'escape_model_name')
    POST_DATA_ID_RESPONSE = True

    def perform_create(self, serializer):
        super(EscapeTaskListCreateView, self).perform_create(serializer)
        bulk_list = []
        survey_overview_ids = CleanTask.objects.get(id=self.request.data.get('clean_task_id', None)).survey_overview_ids
        survey_overview = SurveyOverview.objects.filter_active(id__in=eval(survey_overview_ids))
        survey_overview.update(escape_status=20)
        survey_ids = survey_overview.values_list('survey_id', flat=True).distinct()
        surveys = Survey.objects.filter(id__in=survey_ids)
        model_ids = surveys.values_list('model_id', flat=True)
        models = ResearchModel.objects.filter(id__in=model_ids)
        algorithm_id = models[0].algorithm_id
        escape_model_obj = ResearchModel.objects.create(
            name=self.request.data.get('escape_model_name', None), model_type=30, algorithm_id=algorithm_id,
            model_ids_of_escape=str(list(model_ids)))
        obj = self.model.objects.get(id=serializer.data["id"])
        obj.survey_overview_ids = survey_overview_ids
        obj.escape_model_id = escape_model_obj.id
        obj.save()
        for survey_overview_id in eval(survey_overview_ids):
            survey_overview = SurveyOverview.objects.get(id=survey_overview_id)
            bulk_list.append(SurveyOverviewEscapeTask(
                survey_overview_id=survey_overview_id,
                enterprise_id=survey_overview.enterprise_id,
                assess_id=survey_overview.assess_id,
                creator_id=self.request.user.id,
                survey_id=survey_overview.survey_id,
                ))
        SurveyOverviewEscapeTask.objects.bulk_create(bulk_list)
        l = []
        for survey in surveys:
            dimensions = ResearchDimension.objects.filter_active(model_id=survey.model_id)
            for dimension in dimensions:
                l.append((dimension, survey.id))
        print(l)
        for dimension, survey_id in l:
            # 为转义模型deepcopy所有维度，根据之前接口即可拿到新模型下的所有信息
            DimensionUtils.deep_copy(dimension, survey_id, model_id=escape_model_obj.id, task_id=obj.id)


class EscapeTaskDetailView(WdRetrieveUpdateAPIView):
    u"""转义任务检索与更新"""
    model = EscapeTask
    serializer_class = EscapeTaskListSerializer
    POST_DATA_ID_RESPONSE = True


class AnalysisTaskListCreateView(WdListCreateAPIView):
    u"""解析任务创建与展示"""
    model = AnalysisTask
    p_serializer_class = AnalysisTaskSerializer
    g_serializer_class = AnalysisTaskListSerializer
    POST_CHECK_REQUEST_PARAMETER = ('escape_task_id', 'task_name')
    POST_DATA_ID_RESPONSE = True

    def perform_create(self, serializer):
        super(AnalysisTaskListCreateView, self).perform_create(serializer)
        bulk_list = []
        escape_task = EscapeTask.objects.get(id=self.request.data.get('escape_task_id', None))
        survey_overview_ids = escape_task.survey_overview_ids
        obj = self.model.objects.get(id=serializer.data["id"])
        obj.escape_model_id = escape_task.escape_model_id
        obj.survey_overview_ids = survey_overview_ids
        obj.save()
        SurveyOverview.objects.filter_active(id__in=eval(survey_overview_ids)).update(analysis_status=20)
        for survey_overview_id in eval(survey_overview_ids):
            survey_overview = SurveyOverview.objects.get(id=survey_overview_id)
            bulk_list.append(SurveyOverviewAnalysisTask(
                survey_overview_id=survey_overview_id,
                analysis_task_id=serializer.data["id"],
                enterprise_id=survey_overview.enterprise_id,
                assess_id=survey_overview.assess_id,
                creator_id=self.request.user.id,
                survey_id=survey_overview.survey_id,
                ))
        SurveyOverviewAnalysisTask.objects.bulk_create(bulk_list)


class AnalysisTaskDetailView(WdRetrieveUpdateAPIView):
    u"""解析任务检索与更新"""
    model = AnalysisTask
    serializer_class = AnalysisTaskListSerializer


class SurveyModelFacetQuestionRelationOpsView(WdListCreateAPIView, WdDestroyAPIView):
    u"""问卷模型维度指标关联构面题目"""

    OPS_TYPE_REPLACE = 'new-replace' # 全部替换
    OPS_TYPE_ADD = 'add' # 新增 添加
    OPS_TYPE_VIEW_ALL = 'view_all'
    OPS_TYPE_VIEW_UNIFORMITY = 'view_uniformity'
    OPS_TYPE_VIEW_PRAISE = 'view_praise'

    POST_CHECK_REQUEST_PARAMETER = (
        "ops_type", "task_id", "model_id", "facet_infos", "related_type",
        "related_obj_id", "related_obj_type")
    # facet_infos = [{"id":xx,"weight":xxx}, {"id":xx,"weight":xxx}]
    DELETE_CHECK_REQUEST_PARAMETER = ("task_id", "question_ids", "related_obj_id", "related_obj_type")
    GET_CHECK_REQUEST_PARAMETER = ("task_id", "ops_type", "related_obj_type", "related_obj_id")

    def remove_old_relations(self):
        qs = SM.objects.filter_active(
            model_id=self.model_id, escape_task_id=self.task_id,
            related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id
        )
        ids = list(qs.values_list("id", flat=True))
        qs.update(is_active=False)
        SQ.objects.filter_active(model_facet_relation_id__in=ids).update(is_active=False)

    def ops_manual(self):
        u"""手动选题"""
        questions = self.request.data.get("questions", None)
        is_question_passage = self.request.data.get("is_question_passage", False)
        if questions is None:
            return ErrorCode.INVALID_INPUT
        if self.ops_type == self.OPS_TYPE_REPLACE:
            self.remove_old_relations()
        related_objs = []
        survey_id = SM.objects.filter(
            model_id=self.model_id, escape_task_id=eval(self.task_id),
            related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id
        ).first().survey_id
        related_obj = SM.objects.create(
            survey_id=survey_id, model_id=self.model_id, escape_task_id=self.task_id,
            related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id,
            facet_ids=json.dumps(self.facet_infos)
        )
        related_objs.append(related_obj)
        relation_qs = []
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
        else:
            if is_question_passage:
                questions = Question.objects.filter_active(
                    question_passage_id__in=questions).values_list("id", flat=True)
        for question_id in questions:
            relation_qs.append(SQ(
                survey_id=survey_id, model_facet_relation_id=related_obj.id, question_id=question_id,
                escape_task_id=self.task_id
            ))
        SQ.objects.bulk_create(relation_qs)
        return ErrorCode.SUCCESS

    def ops_view_all(self):
        # related_obj_type = self.request.GET.get("related_obj_type", None)
        # related_obj_id = self.request.GET.get("related_obj_id", None)
        # if related_obj_type is None or related_obj_id is None:
        #     return ErrorCode.INVALID_INPUT, None
        smfrqs = SM.objects.filter_active(
            related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id,
            escape_task_id=self.task_id
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
        question_ids = SQ.objects.filter_active(
            # survey_id=self.survey_id, model_facet_relation_id__in=smfrqs.values_list("id", flat=True),
            model_facet_relation_id__in=smfrqs.values_list("id", flat=True),
            escape_task_id=self.task_id
        ).values_list("question_id", flat=True)
        questions = Question.objects.filter_active(id__in=question_ids)
        question_data = QuestionSerializer(instance=questions, many=True).data
        return ErrorCode.SUCCESS, {"facet_infos": facet_infos, "question_data": question_data}

    def ops_view_uniformity(self):
        # related_obj_type = self.request.GET.get("related_obj_type", None)
        # related_obj_id = self.request.GET.get("related_obj_id", None)
        # if related_obj_type is None or related_obj_id is None:
        #     return ErrorCode.INVALID_INPUT, None
        smfrqs = SM.objects.filter_active(
            related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id)
        if not smfrqs.exists():
            return ErrorCode.SURVEY_MODEL_SUBSTANDARD_NOT_RELATED_QUESTION, None
        # smrf = smfrqs[0]
        question_ids = SQ.objects.filter_active(
            model_facet_relation_id__in=smfrqs.values_list("id", flat=True),
            escape_task_id=self.task_id
        ).values_list("question_id", flat=True)
        questions = Question.objects.filter_active(id__in=question_ids, question_category=Question.CATEGORY_UNIFORMITY)
        question_data = QuestionSerializer(instance=questions, many=True).data
        return ErrorCode.SUCCESS, {"question_data": question_data}

    def ops_view_praise(self):
        # related_obj_type = self.request.GET.get("related_obj_type", None)
        # related_obj_id = self.request.GET.get("related_obj_id", None)
        # if related_obj_type is None or related_obj_id is None:
        #     return ErrorCode.INVALID_INPUT, None
        smfrqs = SM.objects.filter_active(
            related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id,
            escape_task_id=self.task_id
        )
        if not smfrqs.exists():
            return ErrorCode.SURVEY_MODEL_SUBSTANDARD_NOT_RELATED_QUESTION, None
        # smrf = smfrqs[0]
        question_ids = SQ.objects.filter_active(
            model_facet_relation_id__in=smfrqs.values_list("id", flat=True),
            escape_task_id=self.task_id
            ).values_list("question_id", flat=True)
        questions = Question.objects.filter_active(id__in=question_ids, question_category=Question.CATEGORY_PRAISE)
        question_data = QuestionSerializer(instance=questions, many=True).data
        return ErrorCode.SUCCESS, {"question_data": question_data}

    def post(self, request, *args, **kwargs):
        u"""模型维度指标与构面的关联，以及选择题目
        支持新增题目，或者全部替换
        """
        rst_code = self.ops_manual()
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
        # print(rst_code, rst_data)
        return general_json_response(status.HTTP_200_OK, rst_code, rst_data)

    def delete(self, request, *args, **kwargs):
        u"""维度指标关联题目删除调整"""
        if "," in self.question_ids:
            self.question_ids = [int(obj_id) for obj_id in self.question_ids.split(",")]
        else:
            self.question_ids = [int(self.question_ids)]
        sm_ids = SM.objects.filter_active(
            related_obj_type=self.related_obj_type, related_obj_id=self.related_obj_id,
            escape_task_id=self.task_id
        ).values_list('id', flat=True)
        SQ.objects.filter_active(
            model_facet_relation_id__in=sm_ids,
            question_id__in=self.question_ids,
            escape_task_id=self.task_id
        ).update(is_active=False)
        # SurveyQuestionResult.objects.filter_active(
        #     survey_id=self.survey_id,
        #     question_id__in=self.question_ids
        # ).update(is_active=False)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def get(self, request, *args, **kwargs):
        u"""查看当前所有题目 测谎题 社会称许题
        迫选组卷，仅能查看指标/维度下选的全部题目，最终迫选结果在预览里面
        """
        # survey = Survey.objects.get(id=self.survey_id)
        # rst_code = ErrorCode.SUCCESS
        # if survey.form_type == Survey.FORM_TYPE_NORMAL:
        #     rst_code, data = self.ops_view_normal()
        # else:
        #     pass
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


class QuestionFacetListView(WdListAPIView):
    u"""构面的列表"""

    model = QuestionFacet
    serializer_class = QuestionFacetSerializer
    GET_CHECK_REQUEST_PARAMETER = ('task_id',)

    def get_queryset(self):
        qs = super(QuestionFacetListView, self).get_queryset()
        facet_ids = SM.objects.filter(escape_task_id=self.task_id).values_list('facet_ids', flat=True).distinct()
        facet_ids = map(lambda x: eval(x)[0]['id'], facet_ids)
        facet_ids = list(set(facet_ids))
        qs = qs.filter(id__in=facet_ids)
        return qs



