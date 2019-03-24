# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json
import random

from assessment.models import AssessProject
from front.models import SurveyQuestionInfo
from question.models import Question, QuestionOption
from question.serializers import QuestionDetailSerializer
from research.models import ResearchModel, ResearchDimension, ResearchSubstandard
from survey.models import Survey, SurveyModelFacetRelation, SurveyQuestionRelation, SurveyQuestionResult
from survey.serializers import SurveyBasicSerializer, SurveyForceQuestionResultSerializer
from utils.logger import get_logger
from utils.response import ErrorCode

logger = get_logger('survey')


class SurveyUtils(object):

    def __init__(self, survey_id, force_option_num=0, force_base_level=Survey.BASE_LEVEL_SUBSTANDARD, is_test=False, context=None,):
        self.survey_id = survey_id
        self.survey = Survey.objects.get(id=self.survey_id)
        self.force_option_num = force_option_num
        self.force_base_level = force_base_level
        self.context = context
        self.is_test = is_test
        if self.context is None:
            self.context = {}
        self.context["is_test"] = is_test
        self.context["survey_id"] = survey_id

    def preview(self):
        u"""
        两个地方的预览：
        1， 问卷组卷
        2， 项目预览编辑，项目发布后，题目不能再变化

        """
        survey_data = SurveyBasicSerializer(instance=self.survey).data
        # if self.survey.form_type == Survey.FORM_TYPE_FORCE:
        #     survey_data["force_option_num"] = self.force_option_num

        # @version: 20180804 @summary: 项目预览中，项目只要发布过，问题就保持不变
        request = self.context.get("request", None)
        if request and request.GET.get("with_custom_config"):
            assess_id = request.GET.get("assess_id", 0)
            survey_id = request.GET.get("survey_id", 0)
            if assess_id and survey_id:
                survey_question_qs = SurveyQuestionInfo.objects.filter_active(
                    survey_id=survey_id, project_id=assess_id)
                question_data = []
                block_ids = []
                if survey_question_qs.exists():
                    for survey_question in survey_question_qs:
                        if survey_question.block_id not in block_ids:
                            question_data += json.loads(survey_question.question_info)
                            block_ids.append(survey_question.block_id)
                    if question_data:
                        return ErrorCode.SUCCESS, survey_data, question_data

        if self.survey.form_type == Survey.FORM_TYPE_FORCE:
            rst_code, question_data = self.preview_force_question()
            survey_data["force_option_num"] = self.force_option_num
        else:
            rst_code, question_data = self.preview_normal_question()
        return rst_code, survey_data, question_data

    def preview_force_question(self):
        u"""确认迫选题组卷流程，选定维度，选定一个构面下面需要几个同质题。
        比如选择了三个维度，下面有90个同质题，90个同质题构成选项池，
        基于选项池，做组卷工作。假设一个题目有3个选项，则有30道题。
        组卷规则注意同一个能力的同质题不能在一个题下面。 """
        # self.force_option_num = int(self.request.GET.get("force_option_num", 0))
        # if self.force_option_num == 0:
        #     return ErrorCode.INVALID_INPUT, None
        if self.is_test:
            sqr_qs = SurveyQuestionResult.objects.filter_active(
                survey_id=self.survey_id).order_by('order_num')
            return ErrorCode.SUCCESS, SurveyForceQuestionResultSerializer(
                instance=sqr_qs, many=True, context=self.context).data
        # 问卷模型构面关联
        # 关联模型？ 关联构面？
        smfr_qs = SurveyModelFacetRelation.objects.filter_active(survey_id=self.survey_id)
        if not smfr_qs.exists() or len(set(list(smfr_qs.values_list("model_id", flat=True)))) > 1:
            return ErrorCode.SURVEY_MODEL_RELATION_ERROR, None
        smfr_datas = smfr_qs.values("id", "related_obj_type", "related_obj_id").order_by("related_obj_id")
        question_id_map = {}
        option_count = 0
        for smfr_data in smfr_datas:
            related_q_ids = list(SurveyQuestionRelation.objects.filter_active(
                survey_id=self.survey_id, model_facet_relation_id=smfr_data["id"]).values_list("question_id", flat=True))
            option_count += len(related_q_ids)
            # 按维度分类
            if Survey.BASE_LEVEL_DIMENSION == self.force_base_level:
                # 如果type是维度temp-key
                if smfr_data["related_obj_type"] == Survey.BASE_LEVEL_DIMENSION:
                    temp_key = "%s_%s" % (smfr_data["related_obj_type"], smfr_data["related_obj_id"])
                # 如果type是子标，找到父维度的id得到temp-key
                else:
                    fu_weidu_id = ResearchSubstandard.objects.get(id=smfr_data["related_obj_id"]).dimension_id
                    temp_key = "%s_%s" % (Survey.BASE_LEVEL_DIMENSION, fu_weidu_id)
            else:
                temp_key = "%s_%s" %(smfr_data["related_obj_type"], smfr_data["related_obj_id"])
            if temp_key in question_id_map:
                question_id_map[temp_key] += related_q_ids
            else:
                question_id_map[temp_key] = related_q_ids
        # if option_count % self.force_option_num > 0 or self.force_option_num > len(question_id_map):
        re_preview = False
        if self.survey.force_option_num != 0 and self.force_option_num == 0:
            self.force_option_num = self.survey.force_option_num
        if self.force_option_num == 0:
            re_preview = True
            self.force_option_num = len(question_id_map)
        if self.force_option_num != self.survey.force_option_num:
            re_preview = True
        if SurveyModelFacetRelation.is_need_rebuild(self.survey_id):
            re_preview = True
        # re_preview = True
        if re_preview:
            if self.force_option_num > len(question_id_map):
                if Survey.BASE_LEVEL_DIMENSION == self.force_base_level:
                    return ErrorCode.SURVEY_FORCE_OPTION_DIMENSION_ERROR, None  #  迫选维度数量错误
                return ErrorCode.SURVEY_FORCE_OPTION_RELATED_ERROR, None
            question_count = option_count / self.force_option_num
            question_data = []
            related_id_index = 0
            related_ids = question_id_map.keys()
            try:
                for index in range(1, question_count+1):
                    force_question_data = {
                        'title': SurveyQuestionResult.DEFAULT_FORCE_QUESTION_TITLE,
                        'en_title': SurveyQuestionResult.EN_DEFAULT_FORCE_QUESTION_TITLE,
                        "force_titles": SurveyQuestionResult.DEFAULT_FORCE_TITLES,
                        "en_force_titles": SurveyQuestionResult.EN_DEFAULT_FORCE_TITLES,
                        "options": []
                    }
                    for option_index in range(1, len(related_ids)+1):
                        if len(force_question_data["options"]) >= self.force_option_num:
                            break
                        if related_id_index > len(related_ids) - 1:
                            related_id_index = 0
                        if question_id_map[related_ids[related_id_index]]:
                            question_id = question_id_map[related_ids[related_id_index]].pop(
                                random.randint(0, len(question_id_map[related_ids[related_id_index]])-1))
                            # question_id = question_related_info["question_id"]
                            question = Question.objects.get(id=question_id)
                            scores = []
                            try:
                                scores = list(QuestionOption.objects.filter_active(
                                    question_id=question.id).order_by("order_number").values_list("score", flat=True))
                            except Exception, e:
                                logger.error("get question score error, msg: %s" % e)
                            force_question_data["options"].append({
                                "content": question.title,
                                "en_content": question.en_title,
                                "id": question.id,
                                "scores": scores
                            })
                        related_id_index += 1
                    if force_question_data["options"]:
                        question_data.append(force_question_data)
                return ErrorCode.SUCCESS, question_data
            except Exception, e:
                logger.error("force survey error, msg: %s" % e)
                if Survey.BASE_LEVEL_DIMENSION == self.force_base_level:
                    return ErrorCode.SURVEY_FORCE_OPTION_DIMENSION_ERROR, None  # 迫选维度数量错误
                return ErrorCode.SURVEY_FORCE_OPTION_RELATED_ERROR, None
        else:
            sqr_qs = SurveyQuestionResult.objects.filter_active(
                survey_id=self.survey_id).order_by('order_num')
            return ErrorCode.SUCCESS, SurveyForceQuestionResultSerializer(
                instance=sqr_qs, many=True, context=self.context).data

    def preview_normal_question(self):
        smfr_qs = SurveyModelFacetRelation.objects.filter_active(survey_id=self.survey_id)
        if not smfr_qs.exists() or len(set(list(smfr_qs.values_list("model_id", flat=True)))) > 1:
            return ErrorCode.SURVEY_MODEL_RELATION_ERROR, None
        re_preview = False
        if SurveyModelFacetRelation.is_need_rebuild(self.survey_id):
            re_preview = True
        if re_preview:
            question_ids = SurveyQuestionRelation.objects.filter_active(
                survey_id=self.survey_id).values_list("question_id", flat=True).distinct()   # 这个选项关联时会有重复的题
            questions = Question.objects.filter_active(id__in=question_ids)

            # go
            #   按照问卷的维度顺序排序  传入survey_id  ，返回按照维度顺序的 问题 qs
            # 获得所有的问卷模型关联的关系，子标级别的

            def order_survey_dim(survey_id):
                survey = Survey.objects.get(id=survey_id)
                dimensions = ResearchDimension.objects.filter_active(
                    model_id=survey.model_id).order_by("order_number", "id")
                # 模型的维度顺序
                finish_questions = []
                # 获得每个维度下的题目
                for dimension in dimensions:
                    # 获得该每个维度子标
                    sub_ids = ResearchSubstandard.objects.filter_active(dimension_id=dimension.id)
                    smfrqs_qs = SurveyModelFacetRelation.objects.filter_active(
                        survey_id=survey_id,
                        related_obj_type=SurveyModelFacetRelation.RELATED_SUBSTANDARD,
                        related_obj_id__in=sub_ids
                    ).order_by("id")
                    # 找到构面关联的情况
                    question_ids = SurveyQuestionRelation.objects.filter_active(
                        survey_id=survey_id, model_facet_relation_id__in=smfrqs_qs.values_list("id", flat=True)
                    ).order_by("id").values_list("question_id", flat=True)
                    # 找到所有题
                    finish_questions.extend(list(question_ids))
                return finish_questions
                # smfrqs_qs = SurveyModelFacetRelation.objects.filter_active(survey_id=survey_id,
                #                                                            related_obj_type=SurveyModelFacetRelation.RELATED_SUBSTANDARD)
                # dim_question_order_map = {}
                # # dim_question_order_map = {'id':{'order':1,'question':[1,2,3,4]}}
                # order_map = []
                # for smfr_obj in smfrqs_qs:
                #     # 找到每个子标对应的维度
                #     subt_obj = ResearchSubstandard.objects.get(id=smfr_obj.related_obj_id)
                #     question_ids = SurveyQuestionRelation.objects.filter_active(
                #         survey_id=survey_id, model_facet_relation_id=smfr_obj.id
                #     ).values_list("question_id", flat=True)
                #     dim_obj = ResearchDimension.objects.get(id=subt_obj.dimension_id)
                #     if dim_obj.id in dim_question_order_map:
                #         dim_question_order_map[dim_obj.id]["question"].extend(list(question_ids))
                #     else:
                #         if dim_obj.order_number not in order_map:
                #             order_map.append(dim_obj.order_number)
                #         dim_question_order_map[dim_obj.id] = {'question': list(question_ids),
                #                                               "order": dim_obj.order_number}
                # # 给得到的数据排序
                # finish_questions = []
                # order_map.sort()
                # if order_map and dim_question_order_map:
                #     for x in order_map:
                #         for y in dim_question_order_map:
                #             if dim_question_order_map[y]["order"] == x:
                #                 finish_questions.extend(dim_question_order_map[y]["question"])
            question_ids_order = order_survey_dim(self.survey_id)
            if len(question_ids_order) == len(question_ids):  # 此处，即 排序的问题有问题则用原来的题
                question_ids = question_ids_order
                questions = Question.objects.filter_active(id__in=question_ids)
                ordering = 'FIELD(`id`, %s)' % ','.join(str(qid) for qid in question_ids)
                questions = questions.extra(select={'ordering': ordering}, order_by=('ordering',))
            # end
        else:
            sqr_qs = list(SurveyQuestionResult.objects.filter_active(
                survey_id=self.survey_id).order_by('order_num').values_list("question_id", flat=True))
            qs = Question.objects.filter_active(id__in=sqr_qs).distinct()
            ordering = 'FIELD(`id`, %s)' % ','.join(str(qid) for qid in sqr_qs)
            questions = qs.extra(select={'ordering': ordering}, order_by=('ordering',))
        return ErrorCode.SUCCESS, QuestionDetailSerializer(
            instance=questions, many=True, context=self.context).data