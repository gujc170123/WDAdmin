# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import copy
import json

from front.models import UserQuestionAnswerInfo, PeopleSurveyRelation, SurveyQuestionInfo
from question.models import QuestionFacet, Question
from question.serializers import QuestionBasicSerializer
from research.models import ResearchSubstandard, ResearchDimension, ResearchModel, Tag, SubstandardTagRelation, \
    DimensionTagRelation
from research.serializers import ResearchModelDetailSerializer
from survey.models import SurveyQuestionRelation, SurveyModelFacetRelation, Survey
from utils.cache.obj_cache import BaseObjCache
from utils.logger import debug_logger
from utils.math_utils import normsdist


class SurveyAlgorithm(object):

    LANGUAGE_ZH = "ZH"
    LANGUAGE_EN = "EN"
    LANGUAGE_ALL = "ALL"

    PRAISE_PATTERN = u"社会称许"
    DEFAULT_SUBSTANDARD_SCORE = {
        "score": 0,
        "name": "",
        "dimension_id": 0,
        "count": 0  # 题目个数
    }
    DEFAULT_DIMENSION_SCORE = {
        "score": 0,
        "name": "",
        "uniformity_score": {},
        "praise_score": 0,
        "count": 0  # 题目个数
    }

    @classmethod
    def get_question_basic_info(cls, question_id):
        question_info = BaseObjCache(Question, question_id, 'questionBasicInfo').get_obj()
        if not question_info:
            debug_logger.debug("get_question_basic_info from db not from cache")
            question = Question.objects.get(id=question_id)
            question_info = QuestionBasicSerializer(instance=question).data
            BaseObjCache(Question, question_id, 'questionBasicInfo').set_obj(question_info)
        return question_info

    @classmethod
    def process_question_answer(cls, question_answers, question_type):
        question_answers = question_answers.order_by("-id")
        if question_type in [
            Question.QUESTION_TYPE_SINGLE,
            Question.QUESTION_TYPE_SINGLE_FILLIN,
            Question.QUESTION_TYPE_SLIDE,
            Question.QUESTION_TYPE_NINE_SLIDE
        ]:
            if question_answers.count() == 1:
                return question_answers
            else:
                answer_ids = list(question_answers.values_list("id", flat=True))
                answer_id = answer_ids.pop(0)
                UserQuestionAnswerInfo.objects.filter(id__in=answer_ids).update(is_active=False)
                return UserQuestionAnswerInfo.objects.filter(id=answer_id)
        if question_type in [Question.QUESTION_TYPE_MUTEXT]:
            if question_answers.count() == 2:
                return question_answers
            left_answer_ids = []
            false_active_ids = []
            answer_ids = []  # 选项的ID
            for answer_obj in question_answers:
                if len(left_answer_ids) > 2:
                    false_active_ids.append(answer_obj.id)
                    continue
                if answer_obj.answer_id not in answer_ids:
                    left_answer_ids.append(answer_obj.id)
                    answer_ids.append(answer_obj.answer_id)
                else:
                    false_active_ids.append(answer_obj.id)
            UserQuestionAnswerInfo.objects.filter(id__in=false_active_ids).update(is_active=False)
            return UserQuestionAnswerInfo.objects.filter(id__in=left_answer_ids)
        return question_answers

    @classmethod
    def get_model_detail_info(cls, research_model):
        model_info = BaseObjCache(ResearchModel, research_model.id, 'detailSerializer').get_obj()
        if not model_info:
            debug_logger.debug("get model info from db not from cache")
            model_info = ResearchModelDetailSerializer(instance=research_model).data
            BaseObjCache(ResearchModel, research_model.id, 'detailSerializer').set_obj(model_info)
        return model_info

    @classmethod
    def get_substandard_facet_map(cls, substandard, survey):
        u""""""
        facet_id_map = BaseObjCache(Survey, substandard["id"], 'substandardQuestionRelation').get_obj()
        if not facet_id_map:
            debug_logger.debug("get_substandard_facet_map from db not from cache")
            relation_qs = SurveyAlgorithm.get_relation_qs(survey.id, survey.model_id, substandard)
            if not relation_qs:
                return None
            facet_id_map = {}
            for relation in relation_qs:
                facet_ids = json.loads(relation.facet_ids)
                for facet_info in facet_ids:
                    if facet_info['id'] not in facet_id_map:
                        weight = facet_info.get("weight", 1)
                        if weight is None:
                            weight = 1
                        facet_id_map[facet_info['id']] = {
                            'weight': weight,
                            'questions': [],
                            'name': QuestionFacet.objects.get(id=facet_info['id']).name,
                            "related_obj_id": relation.related_obj_id,
                            "related_obj_name": ResearchSubstandard.objects.get(id=relation.related_obj_id).name
                        }
                    question_ids = SurveyQuestionRelation.objects.filter_active(
                        survey_id=survey.id,
                        model_facet_relation_id=relation.id
                    ).values_list("question_id", flat=True).distinct()
                    temp_questions = facet_id_map[facet_info['id']]['questions'] + list(question_ids)
                    facet_id_map[facet_info['id']]['questions'] = list(set(temp_questions))
                    # facet_id_map[facet_info['id']]['questions'] += list(question_ids)
            BaseObjCache(Survey, substandard["id"], 'substandardQuestionRelation').set_obj(facet_id_map)
        return facet_id_map

    @classmethod
    def get_dimension_facet_map(cls, dimension, survey):
        facet_id_map = BaseObjCache(Survey, dimension["id"], 'dimensionQuestionRelation').get_obj()
        if not facet_id_map:
            debug_logger.debug("get_dimension_facet_map from db not from cache")
            relation_qs = SurveyModelFacetRelation.objects.filter_active(
                survey_id=survey.id,
                model_id=survey.model_id,
                related_obj_type=SurveyModelFacetRelation.RELATED_DIMENSION,
                related_obj_id=dimension["id"]
            )
            if not relation_qs:
                return None
            facet_id_map = {}
            for relation in relation_qs:
                facet_ids = json.loads(relation.facet_ids)
                for facet_info in facet_ids:
                    if facet_info['id'] not in facet_id_map:
                        facet_id_map[facet_info['id']] = {
                            'weight': facet_info['weight'],
                            'questions': [],
                            'name': QuestionFacet.objects.get(id=facet_info['id']).name
                        }
                    question_ids = SurveyQuestionRelation.objects.filter_active(
                        survey_id=survey.id,
                        model_facet_relation_id=relation.id
                    ).values_list("question_id", flat=True)
                    facet_id_map[facet_info['id']]['questions'] += list(question_ids)
            BaseObjCache(Survey, dimension["id"], 'dimensionQuestionRelation').set_obj(facet_id_map)
        return facet_id_map

    @classmethod
    def get_relation_qs(cls, survey_id, model_id, substandard_info):
        u"""获取模型的组卷题目关联"""
        qs = SurveyModelFacetRelation.objects.filter_active(
            survey_id=survey_id,
            model_id=model_id,
            related_obj_type=SurveyModelFacetRelation.RELATED_SUBSTANDARD,
            related_obj_id=substandard_info["id"]
        )
        if qs.exists():
            return qs
        elif substandard_info['substandards']:
            relations = []
            for child_substandard in substandard_info['substandards']:
                result = cls.get_relation_qs(survey_id, model_id, child_substandard)
                if result:
                    relations += list(result)
            return relations
        else:
            return None

    @classmethod
    def save_score(cls, people_survey_result_id,
                   model_score, dimension_score, substandard_score,
                   praise_score=0, uniformity_score=None, facet_score=None,
                   happy_score=0, happy_ability_score=0, happy_efficacy_score=0):
        u"""题目分值保存"""
        debug_logger.debug("begin save_score of people_survey_result_id of %s, model_score: %s" % (people_survey_result_id, model_score))
        if uniformity_score:
            uniformity_score = json.dumps(uniformity_score)
        if facet_score:
            facet_score = json.dumps(facet_score)
        PeopleSurveyRelation.objects.filter_active(
            id=people_survey_result_id
        ).update(
            model_score=model_score,
            dimension_score=json.dumps(dimension_score),
            substandard_score=json.dumps(substandard_score),
            praise_score=praise_score,
            uniformity_score=uniformity_score,
            facet_score=facet_score,
            happy_score=happy_score,
            happy_ability_score=happy_ability_score,
            happy_efficacy_score=happy_efficacy_score
        )
        result = PeopleSurveyRelation.objects.get(id=people_survey_result_id)
        if result.model_score != model_score and not result.dimension_score != json.dumps(dimension_score):
            result.model_score = model_score
            result.dimension_score = json.dumps(dimension_score)
            result.substandard_score = json.dumps(substandard_score)
            result.praise_score = praise_score
            result.uniformity_score = uniformity_score
            result.facet_score = facet_score
            result.happy_score = happy_score
            result.happy_ability_score = happy_ability_score
            result.happy_efficacy_score = happy_efficacy_score
            result.save()
        debug_logger.debug("end save_score of people_survey_result_id of %s, model_score: %s" % (people_survey_result_id, model_score))

    @classmethod
    def get_question_answer(cls, people_id, survey_id, project_id, role_type, evaluated_people_id):
        u"""获取题目答案"""
        debug_logger.debug("SurveyAlgorithm->get_question_answer: %s, %s, %s, %s, %s" % (
            people_id, survey_id, project_id, role_type, evaluated_people_id))
        question_answers = UserQuestionAnswerInfo.objects.filter_active(
            people_id=people_id,
            survey_id=survey_id,
            project_id=project_id,
            role_type=role_type,
            evaluated_people_id=evaluated_people_id
        )
        return question_answers

    @classmethod
    def algorithm_average_weight(cls, people_survey_result_id, form_type=Survey.FORM_TYPE_FORCE,
                             remove_weight_zero=True, multiply_weight=True, score_handler=None):
        u"""普通加权算法
        指标分=（题目分的和/题目个数）*指标权重
        维度分=（指标分的和/指标个数）*维度权重   // 指标分和指标个数，均指计入维度分的指标，标签：是否计入维度分
        模型分=  维度分的和/维度个数
        支持项目:
        云南移动
        """

        def process_substandard_score(dimension, substandard):
            substandard_score[substandard["id"]] = {
                "score": 0,
                "name": substandard["name"],
                "dimension_id": dimension["id"]
            }
            if substandard["substandards"]:
                all_child_score = 0
                all_child_count = 0
                for child_substandard in substandard["substandards"]:
                    process_substandard_score(dimension, child_substandard)
                    all_child_count += 1
                    all_child_score += substandard_score[child_substandard["id"]]["score"]
                substandard_score[substandard["id"]]["score"] = (all_child_score*1.00/all_child_count)*substandard["weight"]
                debug_logger.debug("process_substandard_score --> process substandard of %s, %s, %s" % (
                substandard["id"], substandard["name"], substandard_score[substandard["id"]]["score"]))
            else:
                debug_logger.debug("begin process_substandard_score --> process substandard of %s, %s" % (
                    substandard["id"], substandard["name"]))
                facet_id_map = cls.get_substandard_facet_map(substandard, survey)
                question_ids = []
                question_substandard_score = 0
                for facet_id in facet_id_map:
                    facet_info = facet_id_map[facet_id]
                    question_ids += facet_info["questions"]
                    if facet_id not in facet_score:
                        facet_score[facet_id] = {
                            "score": 0,
                            "name": facet_id_map[facet_id]["name"],
                            "substandard_id": substandard["id"],
                            "dimension_id": dimension["id"]
                        }
                    facet_question_count = len(facet_info["questions"])
                    question_score = 0
                    for question_id in facet_info["questions"]:
                        if form_type == Survey.FORM_TYPE_FORCE:
                            question_answer_infos = question_answers.filter(answer_id=question_id)
                        else:
                            question_answer_infos = question_answers.filter(question_id=question_id)
                        if not question_answer_infos:
                            continue
                        question_info = cls.get_question_basic_info(question_id)
                        question_answer_infos = cls.process_question_answer(question_answer_infos, question_info["question_type"])                        
                        for question_answer in question_answer_infos:
                            question_score += question_answer.answer_score
                            question_substandard_score += question_answer.answer_score
                    if facet_question_count:
                        facet_score[facet_id]["score"] = (question_score*1.00 / facet_question_count*1.00) * facet_id_map[facet_id]["weight"]
                    else:
                        facet_score[facet_id]["score"] = 0

                question_count = len(question_ids)
                if question_count:
                    substandard_score[substandard["id"]]["score"] = (question_substandard_score*1.00 / question_count*1.00) * substandard["weight"]
                else:
                    substandard_score[substandard["id"]]["score"] = 0
                debug_logger.debug("process_substandard_score --> process substandard of %s, %s, %s, %s, %s, %s" % (
                    substandard["id"], substandard["name"], substandard_score[substandard["id"]]["score"],
                    question_substandard_score, question_count, substandard["weight"]))

        facet_score = {}
        substandard_score = {}
        dimension_score = {}
        model_score = 0  # 总分
        debug_logger.debug("algorithm_average_weight --> people_survey_result_id is %s" % people_survey_result_id)
        people_survey_result = PeopleSurveyRelation.objects.get(id=people_survey_result_id)
        survey = Survey.objects.get(id=people_survey_result.survey_id)
        research_model = ResearchModel.objects.get(id=survey.model_id)
        model_info = cls.get_model_detail_info(research_model)
        question_answers = cls.get_question_answer(
            people_survey_result.people_id,
            people_survey_result.survey_id,
            people_survey_result.project_id,
            people_survey_result.role_type,
            people_survey_result.evaluated_people_id
        )
        dimensions = model_info['dimension']
        dimension_count = 0
        dimension_total_score = 0
        for dimension in dimensions:
            substandards = dimension['substandards']
            dimension_score[dimension["id"]] = {
                "score": 0,
                "name": dimension["name"]
            }
            if not substandards:
                pass
            else:
                substandard_count = 0
                score = 0
                for substandard in substandards:
                    process_substandard_score(dimension, substandard)
                    tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_SUBSTANDARD, tag_name=u"是否计入维度分").order_by("-id")
                    if tag_qs.exists():
                        tag = tag_qs[0]
                        str_qs = SubstandardTagRelation.objects.filter_active(tag_id=tag.id, object_id=substandard["id"]).order_by("-id")
                        if str_qs.exists():
                            str_tag = str_qs[0]
                            if str_tag == u"否":
                                pass
                            else:
                                substandard_count += 1
                                score += substandard_score[substandard["id"]]["score"]
                        else:
                            substandard_count += 1
                            score += substandard_score[substandard["id"]]["score"]
                    else:
                        substandard_count += 1
                        score += substandard_score[substandard["id"]]["score"]
                dimension_score[dimension["id"]]["score"] = (score*1.00/substandard_count*1.00)*dimension["weight"]
            tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_DIMENSION, tag_name=u"是否计入模型分").order_by("-id")
            if tag_qs.exists():
                tag = tag_qs[0]
                str_qs = DimensionTagRelation.objects.filter_active(tag_id=tag.id, object_id=dimension["id"]).order_by(
                    "-id")
                if str_qs.exists():
                    str_tag = str_qs[0]
                    if str_tag == u"否":
                        pass
                    else:
                        dimension_count += 1
                        dimension_total_score += dimension_score[dimension["id"]]["score"]
                else:
                    dimension_count += 1
                    dimension_total_score += dimension_score[dimension["id"]]["score"]
            else:
                dimension_count += 1
                dimension_total_score += dimension_score[dimension["id"]]["score"]
        model_score = (dimension_total_score*1.00 / dimension_count*1.00)
        if score_handler:
            score_handler(model_score, dimension_score, substandard_score)
        cls.save_score(people_survey_result_id, model_score, dimension_score, substandard_score, facet_score=facet_score)


    @classmethod
    def algorithm_sum_app_up(cls, people_survey_result_id, form_type=Survey.FORM_TYPE_FORCE,
                             remove_weight_zero=True, multiply_weight=True, score_handler=None):
        u"""特殊加权算法"""

        def add_substandard_score(substandard_score, substandard, score):
            if substandard.weight == 0 and remove_weight_zero:
                return
            weight = substandard.weight
            if not multiply_weight:
                weight = 1
            if substandard.id in substandard_score:
                substandard_score[substandard.id]["score"] += score * weight
                substandard_score[substandard.id]["count"] += 1
            else:
                substandard_score[substandard.id] = copy.deepcopy(cls.DEFAULT_SUBSTANDARD_SCORE)
                substandard_score[substandard.id]["score"] = score * weight
                substandard_score[substandard.id]["count"] = 1
                substandard_score[substandard.id]["name"] = substandard.name
                substandard_score[substandard.id]["dimension_id"] = substandard.dimension_id
            if substandard.parent_id:
                psubstandard = ResearchSubstandard.objects.get(id=substandard.parent_id)
                add_substandard_score(substandard_score, psubstandard, score)
            return

        people_survey_result = PeopleSurveyRelation.objects.get(id=people_survey_result_id)
        question_answers = cls.get_question_answer(
            people_survey_result.people_id,
            people_survey_result.survey_id,
            people_survey_result.project_id,
            people_survey_result.role_type,
            people_survey_result.evaluated_people_id
        )
        substandard_score = {}
        dimension_score = {}
        model_score = 0
        praise_score = 0
        for question_answer in question_answers:
            if form_type == Survey. FORM_TYPE_FORCE:
                question_id = question_answer.answer_id
            else:
                question_id = question_answer.question_id
            score = question_answer.answer_score
            model_question_relation_qs = SurveyQuestionRelation.objects.filter_active(
                survey_id=people_survey_result.survey_id,
                question_id=question_id
            )
            debug_logger.debug("SurveyAlgorithm->algorithm_sum_app_up: %s, %s" % (question_id, score))
            if model_question_relation_qs.exists():
                relation_id = model_question_relation_qs[0].model_facet_relation_id
                relation_obj = SurveyModelFacetRelation.objects.get(id=relation_id)
                # debug_logger.debug("SurveyAlgorithm->algorithm_sum_app_up: %s, %s" % (
                # relation_obj.related_obj_type, relation_obj.related_obj_id))
                if relation_obj.related_obj_type == SurveyModelFacetRelation.RELATED_SUBSTANDARD:
                    substandard_id = relation_obj.related_obj_id
                    substandard = ResearchSubstandard.objects.get(id=substandard_id)
                    add_substandard_score(substandard_score, substandard, score)
                    dismension = ResearchDimension.objects.get(id=substandard.dimension_id)
                    if dismension.weight == 0 and remove_weight_zero:
                        continue
                    weight = dismension.weight
                    if not multiply_weight:
                        weight = 1
                    if dismension.id in dimension_score:
                        dimension_score[dismension.id]["score"] += score * weight
                        dimension_score[dismension.id]["count"] += 1
                    else:
                        dimension_score[dismension.id] = {
                            "score": score * weight,
                            "name": dismension.name,
                            "count": 1
                        }
                    if dismension.name.find(cls.PRAISE_PATTERN) > 0:
                        praise_score += dimension_score[dismension.id]["score"]
                    debug_logger.debug("SurveyAlgorithm->algorithm_sum_app_up:%s, %s-%s, %s, %s-%s" % (
                        score, substandard.id, substandard.name, score, dismension.id, dismension.name
                    ))
                    model_score += score
                else:
                    dismension = ResearchDimension.objects.get(id=relation_obj.related_obj_id)
                    if dismension.weight == 0 and remove_weight_zero:
                        continue
                    weight = dismension.weight
                    if not multiply_weight:
                        weight = 1
                    if dismension.id in dimension_score:
                        dimension_score[dismension.id]["score"] += score * weight
                        dimension_score[dismension.id]["count"] += 1
                    else:
                        dimension_score[dismension.id] = {
                            "score": score * weight,
                            "name": dismension.name,
                            "count": 1
                        }
                    if dismension.name.find(cls.PRAISE_PATTERN) > 0:
                        praise_score += dimension_score[dismension.id]["score"]
                    debug_logger.debug("SurveyAlgorithm->algorithm_sum_app_up:%s, %s-%s, %s, %s-%s" % (
                        score, substandard.id, substandard.name, score, dismension.id, dismension.name
                    ))
                    model_score += score
        if score_handler:
            score_handler(model_score, dimension_score, substandard_score)
        cls.save_score(people_survey_result_id, model_score, dimension_score, substandard_score, praise_score)

    @classmethod
    def algorithm_gzjzg(cls, people_survey_result_id):
        u"""工作价值观算法"""
        cls.algorithm_sum_app_up(people_survey_result_id)

    @classmethod
    def algorithm_rgfx(cls, people_survey_result_id):
        u""" """
        cls.algorithm_sum_app_up(people_survey_result_id, form_type=Survey.FORM_TYPE_NORMAL)

    @classmethod
    def algorithm_xljk(cls, people_survey_result_id):
        u"""心理健康算法"""
        cls.algorithm_sum_app_up(people_survey_result_id, remove_weight_zero=False, multiply_weight=False, form_type=Survey.FORM_TYPE_NORMAL)

    @classmethod
    def algorithm_xljk_en(cls, people_survey_result_id):
        u"""心理健康算法英文"""
        cls.algorithm_sum_app_up(people_survey_result_id, remove_weight_zero=False, multiply_weight=False,
                                 form_type=Survey.FORM_TYPE_NORMAL)

    @classmethod
    def algorithm_swqn(cls, people_survey_result_id):
        u"""思维潜能算法"""
        people_survey_result = PeopleSurveyRelation.objects.get(id=people_survey_result_id)
        question_answers = cls.get_question_answer(
            people_survey_result.people_id,
            people_survey_result.survey_id,
            people_survey_result.project_id,
            people_survey_result.role_type,
            people_survey_result.evaluated_people_id
        )
        substandard_score = {}
        dimension_score = {}
        model_score = 0
        single_question_ids = []

        for question_answer in question_answers:
            question_id = question_answer.question_id
            score = question_answer.answer_score
            model_question_relation_qs = SurveyQuestionRelation.objects.filter_active(
                survey_id=people_survey_result.survey_id,
                question_id=question_id
            )
            if int(score) != 1:
                score = 0
            debug_logger.debug("SurveyAlgorithm->algorithm_swqn: %s, %s, %s" % (people_survey_result_id, question_id, score))
            if model_question_relation_qs.exists():
                relation_id = model_question_relation_qs[0].model_facet_relation_id
                relation_obj = SurveyModelFacetRelation.objects.get(id=relation_id)
                # debug_logger.debug("SurveyAlgorithm->algorithm_swqn: %s, %s" % (
                #     relation_obj.related_obj_type, relation_obj.related_obj_id))
                if question_id in single_question_ids:
                    continue
                single_question_ids.append(question_id)

                if relation_obj.related_obj_type == SurveyModelFacetRelation.RELATED_SUBSTANDARD:
                    substandard_id = relation_obj.related_obj_id
                    substandard = ResearchSubstandard.objects.get(id=substandard_id)
                    if substandard_id in substandard_score:
                        substandard_score[substandard_id]["score"] += score
                        # substandard_score[substandard_id]["count"] += 1
                    else:
                        substandard_score[substandard_id] = copy.deepcopy(cls.DEFAULT_SUBSTANDARD_SCORE)
                        substandard_score[substandard_id]["score"] = score
                        # substandard_score[substandard_id]["count"] = 1
                        substandard_score[substandard_id]["name"] = substandard.name
                        substandard_score[substandard_id]["dimension_id"] = substandard.dimension_id
                        relation_ids = SurveyModelFacetRelation.objects.filter_active(
                            survey_id=people_survey_result.survey_id,
                            related_obj_type=SurveyModelFacetRelation.RELATED_SUBSTANDARD,
                            related_obj_id=substandard_id
                        ).values_list("id", flat=True)
                        question_count = SurveyQuestionRelation.objects.filter_active(
                            survey_id=people_survey_result.survey_id,
                            model_facet_relation_id__in=relation_ids
                        ).values_list("question_id", flat=True).distinct().count()
                        substandard_score[substandard_id]["count"] = question_count

                    dismension = ResearchDimension.objects.get(id=substandard.dimension_id)
                    if dismension.id in dimension_score:
                        dimension_score[dismension.id]["score"] += score
                        # dimension_score[dismension.id]["count"] += 1
                    else:
                        substandard_ids = ResearchSubstandard.objects.filter_active(
                            dimension_id=dismension.id).values_list("id", flat=True)
                        relation_ids = SurveyModelFacetRelation.objects.filter_active(
                            survey_id=people_survey_result.survey_id,
                            related_obj_type=SurveyModelFacetRelation.RELATED_SUBSTANDARD,
                            related_obj_id__in=substandard_ids
                        ).values_list("id", flat=True)
                        question_count = SurveyQuestionRelation.objects.filter_active(
                            survey_id=people_survey_result.survey_id,
                            model_facet_relation_id__in=relation_ids
                        ).values_list("question_id", flat=True).distinct().count()
                        dimension_score[dismension.id] = {
                            "score": score,
                            "name": dismension.name,
                            "count": question_count
                        }
                    # debug_logger.debug("SurveyAlgorithm->algorithm_swqn:%s, %s-%s, %s, %s-%s" % (
                    #     score, substandard.id, substandard.name, score, dismension.id, dismension.name
                    # ))
                    model_score += score
                else:
                    dismension = ResearchDimension.objects.get(id=relation_obj.related_obj_id)
                    if dismension.id in dimension_score:
                        dimension_score[dismension.id]["score"] += score
                        # dimension_score[dismension.id]["count"] += 1
                    else:
                        relation_ids = SurveyModelFacetRelation.objects.filter_active(
                            survey_id=people_survey_result.survey_id,
                            related_obj_type=SurveyModelFacetRelation.RELATED_DIMENSION,
                            related_obj_id=dismension.id
                        ).values_list("id", flat=True)
                        question_count = SurveyQuestionRelation.objects.filter_active(
                            survey_id=people_survey_result.survey_id,
                            model_facet_relation_id__in=relation_ids
                        ).values_list("question_id", flat=True).distinct().count()
                        dimension_score[dismension.id] = {
                            "score": score,
                            "name": dismension.name,
                            "count": question_count
                        }
                    # debug_logger.debug("SurveyAlgorithm->algorithm_sum_app_up:%s, %s-%s, %s, %s-%s" % (
                    #     score, substandard.id, substandard.name, score, dismension.id, dismension.name
                    # ))
                    model_score += score
        #
        for substandard_id in substandard_score:
            substandard_score[substandard_id]["score"] = (
                                                             substandard_score[substandard_id]["score"]*1.00 / substandard_score[substandard_id]["count"]*1.00
                                                         )*100
        dismension_count_score = 0
        dismension_count = 0
        for dismension_id in dimension_score:
            dismension_count += 1
            dimension_score[dismension_id]["score"] = (
                                                          dimension_score[dismension_id]["score"]*1.00 / dimension_score[dismension_id]["count"]*1.00
                                                      ) * 100
            dismension_count_score += dimension_score[dismension_id]["score"]
        model_score = dismension_count_score*1.00 / 5*1.00
        #
        cls.save_score(people_survey_result_id, model_score, dimension_score, substandard_score)

    @classmethod
    def algorithm_disc(cls, people_survey_result_id):
        u"""DISC 职业个性算法"""
        people_survey_result = PeopleSurveyRelation.objects.get(id=people_survey_result_id)
        question_answers = cls.get_question_answer(
            people_survey_result.people_id,
            people_survey_result.survey_id,
            people_survey_result.project_id,
            people_survey_result.role_type,
            people_survey_result.evaluated_people_id
        )
        substandard_score = {}
        dimension_score = {}
        model_score = 0

        like_score_map = {'1':'D', '2':'I', '4':'S', "8":"C"}
        not_like_score_map = {'16':'D', '32':'I', '64':'S', "128":"C"}

        like_count = {"D": 0, "I": 0, "S": 0, "C": 0}
        not_like_count = {"D": 0, "I": 0, "S": 0, "C": 0}
        difference_count = {"D": 0, "I": 0, "S": 0, "C": 0}
        for question_answer in question_answers:
            score = int(question_answer.answer_score)
            if str(score) in like_score_map.keys():
                like_count[like_score_map[str(score)]] += 1
            if str(score) in not_like_score_map.keys():
                not_like_count[not_like_score_map[str(score)]] += 1
        for key in like_count.keys():
            difference_count[key] = like_count[key] - not_like_count[key]
        substandard_score = {
            'like': like_count,
            'not_like': not_like_count,
            'difference': difference_count
        }
        #
        cls.save_score(people_survey_result_id, model_score, dimension_score, substandard_score)

    @classmethod
    def algorithm_xlzb(cls, people_survey_result_id):
        u"""心理资本算法"""
        def xlzb_score_handler(model_score, dimension_score, substandard_score):
            u"""标准差"""
            DEFALUT_AVERAGE_VALUE = 9.8341
            DEFAULT_DIFF_VALUE = 2.4225
            standard_average_map = {
                u"进取性": 9.9218,
                u"支配性": 7.8741,
                u"亲和性": 10.7492,
                u"开放性": 11.4568,
                u"乐观性": 10.7943,
                u"变通性": 9.3143,
                u"内省性": 9.8525,
                u"独立性": 10.5365,
                u"坚韧性": 8.3136,
                u"自律性": 7.3937,
                u"悦纳性": 11.2215,
                u"稳定性": 8.3257,
                u"自信心": 10.9360,
                u"尽责性": 11.3242,
                u"容人性": 8.2866,
                u"利他性": 11.0449
            }
            standard_diff_map = {
                u"进取性": 2.8134,
                u"支配性": 2.2837,
                u"亲和性": 2.2237,
                u"开放性": 2.2386,
                u"乐观性": 2.3240,
                u"变通性": 2.3754,
                u"内省性": 2.3303,
                u"独立性": 2.4590,
                u"坚韧性": 2.7231,
                u"自律性": 2.1991,
                u"悦纳性": 2.4083,
                u"稳定性": 3.2422,
                u"自信心": 2.7135,
                u"尽责性": 2.0987,
                u"容人性": 2.1231,
                u"利他性": 2.2026
            }
            for score_info_id in substandard_score:
                score_info = substandard_score[score_info_id]
                score_info["average_score"] = standard_average_map.get(score_info["name"], DEFALUT_AVERAGE_VALUE) # round((score_info["score"]*1.00) / (score_info["count"]*1.00), 6)
                score_info["normsdist_score"] = normsdist(
                    (score_info["score"] - score_info["average_score"]) /
                    standard_diff_map.get(score_info["name"], DEFAULT_DIFF_VALUE)
                ) * 100
        cls.algorithm_sum_app_up(people_survey_result_id, form_type=Survey.FORM_TYPE_NORMAL, remove_weight_zero=False, multiply_weight=False, score_handler=xlzb_score_handler)

    @classmethod
    def algorithm_xfzs(cls, people_survey_result_id):
        u"""幸福指数算法
        幸福指数分就是总分，然后还需要幸福指数模型中的维度分、指标分、构面分，幸福指数模型包括六个维度和幸福效能及幸福能力
        """
        QUESTION_WEIGHT = 20  # 题目分是1～5，需要乘以20，变成百分制
        QUESTION_ABILITY_WEIGHT = 25
        substandard_score = {}
        dimension_score = {}
        facet_score = {}
        model_score = 0  # 总分
        happy_score = 0  # 维度总分
        uniformity_score = {}  # 总的一致性得分
        praise_score = 0  # 总的社会称许题得分
        happy_ability_score = 0  # 幸福能力分
        happy_efficacy_score = 0  # 幸福效能分
        efficacy_substandard_count = 0 # 幸福效能指标个数
        # 幸福能力常模
        DEFAULT_VALUE_CONFIG = {
            "average_value": 69.898,
            "standard_diff_value": 18.912
        }
        happy_ability_config_map = {
            u"自主定向": {
                 "average_value": 62.64,
                 "standard_diff_value": 18.09
            },
            u"意义寻求": {
                "average_value": 74.13,
                "standard_diff_value": 18.87
            },
            u"自我悦纳": {
                "average_value": 73.43,
                "standard_diff_value": 18.67
            },
            u"自我拓展": {
                "average_value": 69.75,
                "standard_diff_value": 17.14
            },
            u"情绪调节": {
                "average_value": 72.1,
                "standard_diff_value": 19.24
            },
            u"专注投入": {
                "average_value": 66.86,
                "standard_diff_value": 18.92
            },
            u"亲和利他": {
                "average_value": 60.94,
                "standard_diff_value": 16.8
            },
            u"包容差异": {
                "average_value": 73.23,
                "standard_diff_value": 20.86
            },
            u"乐观积极": {
                "average_value": 73.53,
                "standard_diff_value": 19.6
            },
            u"自信坚韧": {
                "average_value": 71.59,
                "standard_diff_value": 21.68
            },
            u"合理归因": {
                "average_value": 71.96,
                "standard_diff_value": 18.47
            },
            u"灵活变通": {
                "average_value": 68.62,
                "standard_diff_value": 18.6
            }

        }
        happy_ability_substandard_score_range = {

        }
        #
        UA_MAP = {
            "048001009001001": "GCH1",
            "048001003001001": "G3",
            "048006006001001": "SCH1",
            "048006005002001": "S9",
            "048002006001001": "CCH1",
            "048002003001001": "C3",
            "048005005001001": "RCH1",
            "048005001002001": "R2",
            "048004010001001": "LCH1",
            "048004002001001": "L5",
            "048008010001001": "ZCH1",
            "048008004001001": "Z5"
        }
        UA_SCORE = {
            "GCH1": 0,
            "G3": 0,
            "SCH1": 0,
            "S9": 0,
            "CCH1": 0,
            "C3": 0,
            "RCH1": 0,
            "R2": 0,
            "LCH1": 0,
            "L5": 0,
            "ZCH1": 0,
            "Z5": 0,
        }
        UB_MAP = {
            "048001010001001": "GCH2",
            "048006007001001": "SCH2",
            "048002007001001": "CCH2",
            "048005006001001": "RCH2",
            "048004011001001": "LCH2",
            "048008011001001": "ZCH2"
        }
        UB_SCORE = {
            "GCH2": 0,
            "SCH2": 0,
            "CCH2": 0,
            "RCH2": 0,
            "LCH2": 0,
            "ZCH2": 0
        }

        def get_question_weight(name=None):
            if name == u"个人幸福能力":
                return QUESTION_ABILITY_WEIGHT
            else:
                return QUESTION_WEIGHT

        def question_score_process(answer_score, project_id):
            u"""分值由整形改为是浮点数，人保项目保留按整数"""
            # if project_id == 9:
            #     return int(answer_score)
            # else:
            #     return answer_score
            return answer_score

        def get_model_detail_info():
            model_info = BaseObjCache(ResearchModel, research_model.id, 'detailSerializer').get_obj()
            if not model_info:
                debug_logger.debug("algorithm_xfzs --> get model info from db not from cache")
                model_info = ResearchModelDetailSerializer(instance=research_model).data
                BaseObjCache(ResearchModel, research_model.id, 'detailSerializer').set_obj(model_info)
            return model_info

        def get_substandard_facet_map(substandard):
            facet_id_map = BaseObjCache(Survey, substandard["id"], 'substandardQuestionRelation').get_obj()
            if not facet_id_map:
                debug_logger.debug("algorithm_xfzs --> get_substandard_facet_map from db not from cache")
                relation_qs = SurveyAlgorithm.get_relation_qs(survey.id, survey.model_id, substandard)
                if not relation_qs:
                    return None
                facet_id_map = {}
                for relation in relation_qs:
                    facet_ids = json.loads(relation.facet_ids)
                    for facet_info in facet_ids:
                        if facet_info['id'] not in facet_id_map:
                            facet_id_map[facet_info['id']] = {
                                'weight': facet_info['weight'],
                                'questions': [],
                                'name': QuestionFacet.objects.get(id=facet_info['id']).name,
                                "related_obj_id": relation.related_obj_id,
                                "related_obj_name": ResearchSubstandard.objects.get(id=relation.related_obj_id).name
                            }
                        question_ids = SurveyQuestionRelation.objects.filter_active(
                            survey_id=survey.id,
                            model_facet_relation_id=relation.id
                        ).values_list("question_id", flat=True).distinct()
                        temp_questions = facet_id_map[facet_info['id']]['questions'] + list(question_ids)
                        facet_id_map[facet_info['id']]['questions'] = list(set(temp_questions))

                BaseObjCache(Survey, substandard["id"], 'substandardQuestionRelation').set_obj(facet_id_map)
            return facet_id_map

        def get_dimension_facet_map(dimension):
            facet_id_map = BaseObjCache(Survey, dimension["id"], 'dimensionQuestionRelation').get_obj()
            if not facet_id_map:
                debug_logger.debug("algorithm_xfzs --> get_dimension_facet_map from db not from cache")
                relation_qs = SurveyModelFacetRelation.objects.filter_active(
                    survey_id=survey.id,
                    model_id=survey.model_id,
                    related_obj_type=SurveyModelFacetRelation.RELATED_DIMENSION,
                    related_obj_id=dimension["id"]
                )
                if not relation_qs:
                    return None
                facet_id_map = {}
                for relation in relation_qs:
                    facet_ids = json.loads(relation.facet_ids)
                    for facet_info in facet_ids:
                        if facet_info['id'] not in facet_id_map:
                            facet_id_map[facet_info['id']] = {
                                'weight': facet_info['weight'],
                                'questions': [],
                                'name': QuestionFacet.objects.get(id=facet_info['id']).name
                            }
                        question_ids = SurveyQuestionRelation.objects.filter_active(
                            survey_id=survey.id,
                            model_facet_relation_id=relation.id
                        ).values_list("question_id", flat=True)
                        facet_id_map[facet_info['id']]['questions'] += list(question_ids)
                BaseObjCache(Survey, dimension["id"], 'dimensionQuestionRelation').set_obj(facet_id_map)
            return facet_id_map

        def get_question_basic_info(question_id):
            question_info = BaseObjCache(Question, question_id, 'questionBasicInfo').get_obj()
            if not question_info:
                debug_logger.debug("algorithm_xfzs --> get_question_basic_info from db not from cache")
                question = Question.objects.get(id=question_id)
                question_info = QuestionBasicSerializer(instance=question).data
                BaseObjCache(Question, question_id, 'questionBasicInfo').set_obj(question_info)
            return question_info

        debug_logger.debug("algorithm_xfzs --> people_survey_result_id is %s" % people_survey_result_id)
        people_survey_result = PeopleSurveyRelation.objects.get(id=people_survey_result_id)
        survey = Survey.objects.get(id=people_survey_result.survey_id)
        research_model = ResearchModel.objects.get(id=survey.model_id)
        model_info = get_model_detail_info()
        question_answers = cls.get_question_answer(
            people_survey_result.people_id,
            people_survey_result.survey_id,
            people_survey_result.project_id,
            people_survey_result.role_type,
            people_survey_result.evaluated_people_id
        )
        dimensions = model_info['dimension']
        for dimension in dimensions:
            substandards = dimension['substandards']
            dimension_score[dimension["id"]] = {
                "score": 0,
                "name": dimension["name"],
                "uniformity_score": {},
                "praise_score": 0
            }
            if not substandards:
                pass
            else:
                for substandard in substandards:
                    debug_logger.debug("algorithm_xfzs --> process substandard of %s" % substandard["id"])
                    substandard_score[substandard["id"]] = {
                        "score": 0,
                        "name": substandard["name"],
                        "dimension_id": dimension["id"],
                        "child_substandard": {}  # 幸福效能 包含子指标
                    }
                    child_substandard = {}
                    if substandard["name"] == u"幸福效能":
                        for child_substandard_info in substandard["substandards"]:
                            child_substandard[child_substandard_info["id"]] = child_substandard_info
                    facet_id_map = get_substandard_facet_map(substandard)
                    if not facet_id_map:
                        continue
                    for facet_id in facet_id_map:
                        question_ids = facet_id_map[facet_id]["questions"]
                        question_count = len(question_ids)
                        if facet_id not in facet_score:
                            facet_score[facet_id] = {
                                "score": 0,
                                "name": facet_id_map[facet_id]["name"],
                                "substandard_id": substandard["id"],
                                "dimension_id": dimension["id"]
                            }
                        for question_id in question_ids:
                            question_info = get_question_basic_info(question_id)
                            question_answer_infos = question_answers.filter(question_id=question_id).order_by(
                                "-id")
                            question_answer_infos = cls.process_question_answer(question_answer_infos, question_info["question_type"])
                            processed_question_ids = []
                            for question_answer in question_answer_infos:
                                if question_info["question_type"] in [
                                    Question.QUESTION_TYPE_SLIDE,
                                    Question.QUESTION_TYPE_SINGLE,
                                    Question.QUESTION_TYPE_SINGLE_FILLIN
                                ]:
                                    if question_answer.question_id in processed_question_ids:
                                        continue

                                processed_question_ids.append(question_answer.question_id)
                                question_answer_score = question_score_process(question_answer.answer_score, people_survey_result.project_id)
                                facet_score[facet_id]["score"] += question_answer_score * get_question_weight(dimension["name"])
                                # question_info = get_question_basic_info(question_answer.question_id)
                                # 计算 一致性 掩饰性题目分值
                                if question_info["question_category"] == Question.CATEGORY_PRAISE:
                                    dimension_score[dimension["id"]]["praise_score"] += question_answer_score
                                    praise_score += question_answer_score
                                if question_info["question_category"] == Question.CATEGORY_UNIFORMITY:
                                    uniformity_question_id = question_info["uniformity_question_id"]
                                    uniformity_answers = question_answers.filter(question_id=uniformity_question_id)
                                    if uniformity_answers.exists():
                                        uniformity_answer_score = question_score_process(uniformity_answers[0].answer_score, people_survey_result.project_id)
                                    else:
                                        uniformity_answer_score = 0
                                    dimension_score[dimension["id"]]["uniformity_score"][question_answer.question_id] = {
                                        "src_score": question_answer_score,
                                        "uniformity_q_score": uniformity_answer_score,
                                        "uniformity_q_id": uniformity_question_id
                                    }
                                if question_info["code"] in UA_MAP:
                                    UA_SCORE[UA_MAP[question_info["code"]]] = question_answer_score
                                elif question_info["code"] in UB_MAP:
                                    UB_SCORE[UB_MAP[question_info["code"]]] = question_answer_score
                        facet_score[facet_id]["score"] = facet_score[facet_id]["score"]*1.00 / question_count
                        add_substandard_score = facet_score[facet_id]["score"] * facet_id_map[facet_id]["weight"] / 100

                        if substandard["name"] == u"幸福效能":
                            child_substandard_id = facet_id_map[facet_id]["related_obj_id"]
                            if child_substandard_id not in substandard_score[substandard["id"]]["child_substandard"]:
                                substandard_score[substandard["id"]]["child_substandard"][child_substandard_id] = {
                                    "score": add_substandard_score,
                                    "name": facet_id_map[facet_id]["related_obj_name"]
                                }
                            else:
                                substandard_score[substandard["id"]]["child_substandard"][child_substandard_id]["score"] += add_substandard_score
                            substandard_score[substandard["id"]]["score"] += add_substandard_score * child_substandard[child_substandard_id]["weight"] / 100
                        else:
                            substandard_score[substandard["id"]]["score"] += add_substandard_score
                    dimension_score[dimension["id"]]["score"] += substandard_score[substandard["id"]]["score"] * substandard["weight"] / 100
                    if substandard["name"] == u"幸福效能":
                        efficacy_substandard_count += 1
                        happy_efficacy_score += substandard_score[substandard["id"]]["score"]
                    if dimension["name"] == u"个人幸福能力":
                        substandard_score[substandard["id"]]["average_score"] = happy_ability_config_map.get(
                            substandard["name"], DEFAULT_VALUE_CONFIG
                        )["average_value"]
                        substandard_score[substandard["id"]]["normsdist_score"] = normsdist(
                            ((substandard_score[substandard["id"]]["score"] - substandard_score[substandard["id"]]["average_score"]) *1.00) /
                            (happy_ability_config_map.get(substandard["name"], DEFAULT_VALUE_CONFIG)["standard_diff_value"]*1.00)
                        ) * 100
            # 幸福维度分 == 6个幸福维度 * 权重 （幸福能力的权重为0，一起计算不影响）
            happy_score += dimension_score[dimension["id"]]["score"] * dimension["weight"] / 100
            if dimension["name"] == u"个人幸福能力":
                # 幸福能力分 == 幸福能力维度分
                happy_ability_score = dimension_score[dimension["id"]]["score"]
        # 幸福效能分 = 各个维度下的幸福效能指标分平均
        happy_efficacy_score = happy_efficacy_score * 1.00 / efficacy_substandard_count
        # 幸福指数分
        model_score = happy_score * 0.8 + happy_ability_score * 0.2
        # 测谎题A：得分=[(GCH1-G3)+(SCH1-S9)+(CCH1-C3)+(RCH1-R2)+(LCH1-L5)+(ZCH1-Z5)]/6
        ua_score = (
            abs(UA_SCORE["GCH1"]-UA_SCORE["G3"]) +
            abs(UA_SCORE["SCH1"]-UA_SCORE["S9"]) +
            abs(UA_SCORE["CCH1"]-UA_SCORE["C3"]) +
            abs(UA_SCORE["RCH1"]-UA_SCORE["R2"]) +
            abs(UA_SCORE["LCH1"]-UA_SCORE["L5"]) +
            abs(UA_SCORE["ZCH1"]-UA_SCORE["Z5"])
        )*1.00 / 6
        # 测谎题B：得分=(GCH2+SCH2+CCH2+RCH2+LCH2+ZCH2)/6
        ub_score = (
                             UB_SCORE["GCH2"]+UB_SCORE["SCH2"]+UB_SCORE["CCH2"] +
                             UB_SCORE["RCH2"]+UB_SCORE["LCH2"]+UB_SCORE["ZCH2"]
                         )*1.00/6
        # 靠谱度：得分=[(5-测谎题A得分)*20+(6-测谎题B得分)*20]/2
        k_score = ((5-ua_score)*20+(6-ub_score)*20) / 2
        uniformity_score = {"A": ua_score, "B": ub_score, "K": k_score}
        cls.save_score(people_survey_result_id, model_score, dimension_score, substandard_score,
                       praise_score, uniformity_score, facet_score,
                       happy_score, happy_ability_score, happy_efficacy_score)

    @classmethod
    def algorithm_xfzs_en(cls, people_survey_result_id):
        u"""幸福指数算法英文
        幸福指数分就是总分，然后还需要幸福指数模型中的维度分、指标分、构面分，幸福指数模型包括六个维度和幸福效能及幸福能力
        """
        cls.algorithm_xfzs(people_survey_result_id)



    @classmethod
    def algorithm_xfxq(cls, people_survey_result_id):
        u"""幸福需求算分"""

        def get_model_detail_info():
            u"""获取模型基本信息"""
            model_info = BaseObjCache(ResearchModel, research_model.id, 'detailSerializer').get_obj()
            if not model_info:
                debug_logger.debug("algorithm_xfxq --> get model info from db not from cache")
                model_info = ResearchModelDetailSerializer(instance=research_model).data
                BaseObjCache(ResearchModel, research_model.id, 'detailSerializer').set_obj(model_info)
            return model_info

        def get_option_relation_substandard_info(option_id):
            substandard_id = BaseObjCache(Survey, option_id, 'substandardOptionRelation').get_obj()
            if not substandard_id:
                qs = SurveyQuestionRelation.objects.filter_active(
                    survey_id=survey.id,
                    question_option_id=option_id,
                    related_facet_type=SurveyQuestionRelation.RELATED_FACET_TYPE_OPTION

                ).values_list("model_facet_relation_id", flat=True)
                if qs.exists():
                    relation_qs = SurveyModelFacetRelation.objects.filter_active(id__in=qs)
                    if relation_qs.exists():
                        substandard_id = relation_qs[0].related_obj_id
                        BaseObjCache(Survey, option_id, 'substandardOptionRelation').set_obj(substandard_id)
            return substandard_id

        people_survey_result = PeopleSurveyRelation.objects.get(id=people_survey_result_id)
        survey = Survey.objects.get(id=people_survey_result.survey_id)
        research_model = ResearchModel.objects.get(id=survey.model_id)

        # 1 所有题目
        survey_question_infos = SurveyQuestionInfo.objects.filter_active(
            survey_id=people_survey_result.survey_id, project_id=people_survey_result.project_id)
        block_infos = []
        question_infos = []
        for survey_question_info in survey_question_infos:
            if survey_question_info.block_id not in block_infos:
                question_infos += json.loads(survey_question_info.question_info)
        # 2 逐题算分, 指标粗分
        substandard_score_map = {}
        for question_info in question_infos:
            options = question_info["options"]["options"]
            for option in options:
                user_results = UserQuestionAnswerInfo.objects.filter_active(
                    survey_id=survey.id,
                    people_id=people_survey_result.people_id,
                    project_id=people_survey_result.project_id,
                    question_id=question_info["id"],
                    answer_id=option["id"]
                ).order_by("-id")
                if user_results.count() == 1:
                    score = user_results[0].answer_score
                elif user_results.count() > 1:
                    answer_result = user_results[0]
                    score = answer_result.answer_score
                    user_results.exclude(id=answer_result.id).update(is_active=False)
                else:
                    score = 0
                substandard_id = get_option_relation_substandard_info(option["id"])
                if substandard_id and substandard_id not in substandard_score_map:
                    substandard_score_map[substandard_id] = score
                else:
                    substandard_score_map[substandard_id] += score
        #
        # 模型信息
        model_info = get_model_detail_info()
        dimension_infos = model_info["dimension"]
        model_score = 0
        dimension_map = {}
        substandard_info_map = {}
        substandard_whole_map = {}
        for dimension_info in dimension_infos:
            dimension_score = 0
            dimension_map[dimension_info["id"]] = {
                "id": dimension_info["id"],
                "name": dimension_info["name"],
                "score": dimension_score
            }
            substandards = dimension_info["substandards"]
            for substandard in substandards:
                score = 0
                substandard_info_map[substandard["id"]] = {
                    "name": substandard["name"],
                    "dismension_name": dimension_info["name"],
                    "dismension_id": dimension_info["id"],
                    "id": substandard["id"],
                    "child_substandard": [],
                    "score": score,
                    "whole_score": 0  # 整体分 （相同名称相同级别的分数和
                }

                if substandard["substandards"]:
                    for c_substandard in substandard["substandards"]:
                        c_substandard_info = {
                            "name": c_substandard["name"],
                            "id": c_substandard["id"],
                            "thick_score": 0,  # 指标粗分
                            "score": 0,  # 指标分
                            "whole_score": 0  # 整体分 （相同名称相同级别的分数和）
                        }
                        if c_substandard["id"] in substandard_score_map:
                            c_substandard_info["thick_score"] = substandard_score_map[c_substandard["id"]]
                            c_substandard_info["score"] = substandard_score_map[c_substandard["id"]] * 20
                            score += c_substandard_info["score"] * 0.2
                            if c_substandard["name"] in substandard_whole_map:
                                substandard_whole_map[c_substandard["name"]]["count"] += 1
                                substandard_whole_map[c_substandard["name"]]["score"] += c_substandard_info["score"]
                            else:
                                substandard_whole_map[c_substandard["name"]] = {
                                    "count": 1,
                                    "score": c_substandard_info["score"]
                                }
                        substandard_info_map[substandard["id"]]["child_substandard"].append(c_substandard_info)
                substandard_info_map[substandard["id"]]["score"] = score
                if substandard["name"] in substandard_whole_map:
                    substandard_whole_map[substandard["name"]]["count"] += 1
                    substandard_whole_map[substandard["name"]]["score"] += substandard_info_map[substandard["id"]]["score"]
                else:
                    substandard_whole_map[substandard["name"]] = {
                        "count": 1,
                        "score": substandard_info_map[substandard["id"]]["score"]
                    }
                dimension_score += substandard_info_map[substandard["id"]]["score"] * 0.2
            dimension_map[dimension_info["id"]]["score"] = dimension_score
            model_score += dimension_score
            # 处理整体分
            for substandard_id in substandard_info_map:
                substandard_info = substandard_info_map[substandard_id]
                if substandard_info["name"] in substandard_whole_map:
                    substandard_info["whole_score"] = (substandard_whole_map[substandard_info["name"]]["score"]*1.00) / \
                                                      (substandard_whole_map[substandard_info["name"]]["count"]*1.00)
                for csubstandard_info in substandard_info["child_substandard"]:
                    if csubstandard_info["name"] in substandard_whole_map:
                        csubstandard_info["whole_score"] = (substandard_whole_map[csubstandard_info["name"]]["score"] * 1.00) / \
                                                           (substandard_whole_map[csubstandard_info["name"]]["count"] * 1.00)
        cls.save_score(people_survey_result_id, model_score, dimension_map, substandard_info_map)

    @classmethod
    def algorithm_zgc(cls, people_survey_result_id, form_type=Survey.FORM_TYPE_FORCE,
                             remove_weight_zero=True, multiply_weight=True, score_handler=None, for_other=False):
        u"""
        中高层算法， 包括 90，
        计算方式：
        自评：
        行为原始分为整数，最小为-3分，最大为+3分；最终得分介于0-5分之间
        最终得分=（行为原始分+3)/1.2
        他评：
        行为原始分最小为1分，最大为5分；最终得分介于1-5分之间
        他评=各个评价人分数的平均
        default_data = {
            "report_type": "中高层90模板",
            "msg": {
                "Name": "666",
                "Sex": "男",
                "Age": "25",
                "TestTime": "2018.10.12",
                # name  维度名称，score: 维度分    自评
                "chart": [
                    {"name": "积极进取", "score": 2},
                    {"name": "勇于担当", "score": 2},
                    {"name": "正直诚信", "score": 2},
                    {"name": "系统思维", "score": 3},
                    {"name": "变革管理", "score": 2},
                    {"name": "客户导向", "score": 2},
                    {"name": "创新优化", "score": 3},
                    {"name": "团队领导", "score": 3},
                    {"name": "跨界协同", "score": 4},
                    {"name": "资源整合", "score": 2},
                ],
            # name1  维度名称，name  指标（即行为）   score: 指标分     自评
                "chart2": [
                    {"name1": "积极进取", 'name': '为自己设置挑战性目标', "score": 2},
                    {"name1": "积极进取", 'name': '自我激发，从内心寻求动力', "score": 2},
                    {"name1": "积极进取", 'name': '会付出额外的努力', "score": 2},
                    {"name1": "积极进取", 'name': '积极寻求解决办法，坚持不懈', "score": 2},
                    {"name1": "勇于担当", 'name': '明确职责，主动承担责任', "score": 2},
                    {"name1": "勇于担当", 'name': '以目标为导向，完成工作', "score": 2},
                    {"name1": "勇于担当", 'name': '有责无疆，积极推进', "score": 2},
                    {"name1": "勇于担当", 'name': '挺身而出，成为依靠', "score": 2},
                    {"name1": "正直诚信", 'name': '做事规范坦率真诚', "score": 3},
                    {"name1": "正直诚信", 'name': '言行一致遵守承诺', "score": 3},
                    {"name1": "正直诚信", 'name': '处事公平公正', "score": 3},
                    {"name1": "正直诚信", 'name': '敢于当面直谏', "score": 3},
                    {"name1": "系统思维", 'name': '原因识别及构建解决方案', "score": 3},
                    {"name1": "系统思维", 'name': '过程管控与跟踪', "score": 3},
                    {"name1": "系统思维", 'name': '前瞻性分析', "score": 3},
                    {"name1": "系统思维", 'name': '问题发现及分析', "score": 3},
                    {"name1": "变革管理", 'name': '理解变革', "score": 2},
                    {"name1": "变革管理", 'name': '愿景塑造', "score": 2},
                    {"name1": "变革管理", 'name': '管理阻抗', "score": 2},
                    {"name1": "变革管理", 'name': '捍卫变革', "score": 2},
                    {"name1": "客户导向", 'name': '换位思考，构建解决方案', "score": 2},
                    {"name1": "客户导向", 'name': '倾听并及时反馈', "score": 2},
                    {"name1": "客户导向", 'name': '主动关注提升满意度', "score": 2},
                    {"name1": "客户导向", 'name': '协调资源超越期望', "score": 2},
                    {"name1": "创新优化", 'name': '打造创新机制及氛围', "score": 3},
                    {"name1": "创新优化", 'name': '主动关注新事物', "score": 3},
                    {"name1": "创新优化", 'name': '勇于尝试持续创新', "score": 3},
                    {"name1": "创新优化", 'name': '借鉴经验，快速有效优化', "score": 3},
                    {"name1": "团队领导", 'name': '理解高效团队的重要性', "score": 3},
                    {"name1": "团队领导", 'name': '高效合理授权', "score": 3},
                    {"name1": "团队领导", 'name': '塑造团队文化', "score": 3},
                    {"name1": "团队领导", 'name': '多形式学习交流', "score": 3},
                    {"name1": "跨界协同", 'name': '调节冲突，达至双赢', "score": 2},
                    {"name1": "跨界协同", 'name': '建立合作机制，实现效能最大化', "score": 2},
                    {"name1": "跨界协同", 'name': '理解其他部门需求及利益', "score": 2},
                    {"name1": "跨界协同", 'name': '换位思考，促进协作', "score": 2},
                    {"name1": "资源整合", 'name': '主动共享信息', "score": 2},
                    {"name1": "资源整合", 'name': '形成固有并可持续的模式', "score": 2},
                    {"name1": "资源整合", 'name': '主动争取和协调资源', "score": 2},
                    {"name1": "资源整合", 'name': '转变思维，扩展资源渠道', "score": 2},
                ],
            }
        }
        """

        # 中高层的算法先写在这里， 但是出报告的时候不是正常答完题调用的，
        # 是所有人完成答卷 或者项目结束时调用

        def process_substandard_score(dimension, substandard, for_other=False):
            substandard_score[substandard["id"]] = {
                "score": 0,
                "name": substandard["name"],
                "dimension_id": dimension["id"],
                "name1": dimension["name"]
            }
            if substandard["substandards"]:
                all_child_score = 0
                all_child_count = 0
                for child_substandard in substandard["substandards"]:
                    process_substandard_score(dimension, child_substandard)
                    all_child_count += 1
                    all_child_score += substandard_score[child_substandard["id"]]["score"]
                substandard_score[substandard["id"]]["score"] = all_child_score
                # logger.debug("process_substandard_score --> process substandard of %s, %s, %s" % (
                # substandard["id"], substandard["name"], substandard_score[substandard["id"]]["score"]))
            else:
                # logger.debug("begin process_substandard_score --> process substandard of %s, %s" % (
                #     substandard["id"], substandard["name"]))
                facet_id_map = SurveyAlgorithm.get_substandard_facet_map(substandard, survey)
                question_ids = []
                question_substandard_score = 0
                for facet_id in facet_id_map:
                    facet_info = facet_id_map[facet_id]
                    question_ids += facet_info["questions"]
                    if facet_id not in facet_score:
                        facet_score[facet_id] = {
                            "score": 0,
                            "name": facet_id_map[facet_id]["name"],
                            "substandard_id": substandard["id"],
                            "dimension_id": dimension["id"]
                        }
                    facet_question_count = len(facet_info["questions"])
                    if form_type == Survey.FORM_TYPE_FORCE:
                        question_answer_infos = question_answers.filter(answer_id__in=facet_info["questions"])
                    else:
                        question_answer_infos = question_answers.filter(question_id__in=facet_info["questions"])
                    question_score = 0
                    for question_answer in question_answer_infos:
                        # 自评
                        if not for_other:
                            question_score += question_answer.answer_score
                            question_substandard_score += question_answer.answer_score
                            # if question_substandard_score > 5:
                            #     question_substandard_score = 5
                            # if question_substandard_score < 0:
                            #     question_substandard_score = 0
                        # 评价他人
                        else:
                            question_score += question_answer.answer_score
                            question_substandard_score += question_answer.answer_score
                            # if question_substandard_score > 5:
                            #     question_substandard_score = 5
                            # if question_substandard_score < 1:
                            #     question_substandard_score = 1

                    if facet_question_count:
                        facet_score[facet_id]["score"] = int(round((question_score*1.00 / facet_question_count*1.00) * facet_id_map[facet_id]["weight"], 1))
                    else:
                        facet_score[facet_id]["score"] = 0

                question_count = len(question_ids)
                if question_count:
                    if not for_other:
                        question_substandard_score = round((question_substandard_score + 3) / 1.2, 2)
                    substandard_score[substandard["id"]]["score"] = question_substandard_score
                else:
                    substandard_score[substandard["id"]]["score"] = 0
                # logger.debug("process_substandard_score --> process substandard of %s, %s, %s, %s, %s, %s" % (
                #     substandard["id"], substandard["name"], substandard_score[substandard["id"]]["score"],
                #     question_substandard_score, question_count, substandard["weight"]))

        # 自己对他人的评价分数
        for_other_dimension_score = {}
        for_other_substandard_score = {}

        facet_score = {}
        substandard_score = {}
        dimension_score = {}
        model_score = 0  # 总分
        # logger.debug("algorithm_average_weight --> people_survey_result_id is %s" % people_survey_result_id)
        people_survey_result = PeopleSurveyRelation.objects.get(id=people_survey_result_id)
        survey = Survey.objects.get(id=people_survey_result.survey_id)
        research_model = ResearchModel.objects.get(id=survey.model_id)
        model_info = SurveyAlgorithm.get_model_detail_info(research_model)
        question_answers = SurveyAlgorithm.get_question_answer(
            people_survey_result.people_id,
            people_survey_result.survey_id,
            people_survey_result.project_id,
            people_survey_result.role_type,
            people_survey_result.evaluated_people_id
        )
        dimensions = model_info['dimension']
        dimension_count = 0
        dimension_total_score = 0
        # 评价他人
        if for_other:
            for dimension in dimensions:
                substandards = dimension['substandards']
                dimension_score[dimension["id"]] = {
                    "score": 0,
                    "name": dimension["name"],
                    "row_score": 0
                }
                if not substandards:
                    pass
                else:
                    substandard_count = 0
                    score = 0
                    for substandard in substandards:
                        process_substandard_score(dimension, substandard, for_other=True)
                        tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_SUBSTANDARD,
                                                           tag_name=u"是否计入维度分").order_by("-id")
                        if tag_qs.exists():
                            tag = tag_qs[0]
                            str_qs = SubstandardTagRelation.objects.filter_active(tag_id=tag.id,
                                                                                  object_id=substandard["id"]).order_by(
                                "-id")
                            if str_qs.exists():
                                str_tag = str_qs[0]
                                if str_tag == u"否":
                                    pass
                            else:
                                substandard_count += 1
                                score += substandard_score[substandard["id"]]["score"]
                        else:
                            substandard_count += 1
                            score += substandard_score[substandard["id"]]["score"]
                    # 能力 即 维度，  能力分 = 行为分求平均
                    d_score = int(round((score * 1.00 / substandard_count * 1.00)))
                    if d_score > 5:
                        d_score = 5
                    if d_score < 0:
                        d_score = 0
                    dimension_score[dimension["id"]]["score"] = d_score
                    dimension_score[dimension["id"]]["row_score"] = round((score * 1.00 / substandard_count * 1.00), 3)
                tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_DIMENSION, tag_name=u"是否计入模型分").order_by(
                    "-id")
                if tag_qs.exists():
                    tag = tag_qs[0]
                    str_qs = DimensionTagRelation.objects.filter_active(tag_id=tag.id,
                                                                        object_id=dimension["id"]).order_by(
                        "-id")
                    if str_qs.exists():
                        str_tag = str_qs[0]
                        if str_tag == u"否":
                            pass
                    else:
                        dimension_count += 1
                        dimension_total_score += dimension_score[dimension["id"]]["score"]
                else:
                    dimension_count += 1
                    dimension_total_score += dimension_score[dimension["id"]]["score"]
            model_score = int(round((dimension_total_score * 1.00 / dimension_count * 1.00), 1))
            if score_handler:
                score_handler(model_score, dimension_score, substandard_score)
            # 找到所有他评人员， 找他们的对此人的分
            dimension_score = {"self": {}, "others": {},
                               "for_other": dimension_score}
            substandard_score = {"self": {}, "others": {},
                                 "for_other": substandard_score}
            cls.save_score(people_survey_result_id, model_score, dimension_score, substandard_score,
                           facet_score=facet_score)
        # 自评，以及获取他评
        else:
            for dimension in dimensions:
                substandards = dimension['substandards']
                dimension_score[dimension["id"]] = {
                    "score": 0,
                    "name": dimension["name"],
                    "row_score": 0,
                }
                if not substandards:
                    pass
                else:
                    substandard_count = 0
                    score = 0
                    for substandard in substandards:
                        process_substandard_score(dimension, substandard)
                        tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_SUBSTANDARD, tag_name=u"是否计入维度分").order_by("-id")
                        if tag_qs.exists():
                            tag = tag_qs[0]
                            str_qs = SubstandardTagRelation.objects.filter_active(tag_id=tag.id, object_id=substandard["id"]).order_by("-id")
                            if str_qs.exists():
                                str_tag = str_qs[0]
                                if str_tag == u"否":
                                    pass
                            else:
                                substandard_count += 1
                                score += substandard_score[substandard["id"]]["score"]
                        else:
                            substandard_count += 1
                            score += substandard_score[substandard["id"]]["score"]
                    # 能力 即 维度，  能力分 = 行为分求平均
                    d_score = int(round((score*1.00/substandard_count*1.00)))
                    dimension_score[dimension["id"]]["row_score"] = round((score*1.00/substandard_count*1.00), 3)
                    if d_score > 5:
                        d_score = 5
                    if d_score < 0:
                        d_score = 0
                    dimension_score[dimension["id"]]["score"] = d_score
                tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_DIMENSION, tag_name=u"是否计入模型分").order_by("-id")
                if tag_qs.exists():
                    tag = tag_qs[0]
                    str_qs = DimensionTagRelation.objects.filter_active(tag_id=tag.id, object_id=dimension["id"]).order_by(
                        "-id")
                    if str_qs.exists():
                        str_tag = str_qs[0]
                        if str_tag == u"否":
                            pass
                    else:
                        dimension_count += 1
                        dimension_total_score += dimension_score[dimension["id"]]["score"]
                else:
                    dimension_count += 1
                    dimension_total_score += dimension_score[dimension["id"]]["score"]
            model_score = int(round((dimension_total_score*1.00 / dimension_count*1.00), 1))
            if score_handler:
                score_handler(model_score, dimension_score, substandard_score)
            # 自评和他评的计算方式不同， 所以加一个参数作为标志位
            # 检查有哪些人评价了他， 然后计算，

            # 他人对自己的评价分数
            other_dimension_score = {}
            other_substandard_score = {}

            evaluated_people_id = people_survey_result.people_id
            project_id = people_survey_result.project_id
            evaluate_qs = PeopleSurveyRelation.objects.filter_active(evaluated_people_id=evaluated_people_id, project_id=project_id,
                                                       status=PeopleSurveyRelation.STATUS_FINISH)
            others_count = evaluate_qs.count()
            if others_count:
                for evaluate_obj in evaluate_qs:
                    if evaluate_obj.people_id == evaluated_people_id:
                        others_count -= 1
                        if not others_count:
                            break
                    else:
                        cls.algorithm_zgc(evaluate_obj.id, form_type=Survey.FORM_TYPE_NORMAL, for_other=True)
                        evaluate_obj = PeopleSurveyRelation.objects.get(id=evaluate_obj.id)
                        one_other_dimension_score = evaluate_obj.dimension_score_map["for_other"]
                        one_other_substandard_score = evaluate_obj.substandard_score_map["for_other"]
                        if not other_dimension_score:
                            other_dimension_score = one_other_dimension_score
                            other_substandard_score = one_other_substandard_score
                        else:
                            for other_dimension in other_dimension_score:
                                for one_other_dimension in one_other_dimension_score:
                                    if other_dimension == one_other_dimension:
                                        other_dimension_score[other_dimension]["score"] += one_other_dimension_score[one_other_dimension]["score"]
                            for other_substandard in other_substandard_score:
                                for one_other_substandard in one_other_substandard_score:
                                    if other_substandard == one_other_substandard:
                                        other_substandard_score[other_substandard]["score"] += one_other_substandard_score[one_other_substandard]["score"]
                if others_count:
                    for other_dimension in other_dimension_score:
                        other_dimension_score[other_dimension]["score"] = int(round(other_dimension_score[other_dimension]["score"] / (others_count * 1.00), 1))
                    for other_substandard in other_substandard_score:
                        other_substandard_score[other_substandard]["score"] = int(round(other_substandard_score[other_substandard]["score"] / (others_count * 1.00), 1))

            # 找到所有他评人员， 找他们的对此人的分
            dimension_score = {"self": dimension_score, "others": other_dimension_score, "for_other": for_other_dimension_score}
            substandard_score = {"self": substandard_score, "others": other_substandard_score, "for_other": for_other_substandard_score}
            cls.save_score(people_survey_result_id, model_score, dimension_score, substandard_score, facet_score=facet_score)

    @classmethod
    def algorithm_zgc180(cls, people_survey_result_id, form_type=Survey.FORM_TYPE_FORCE,
                      remove_weight_zero=True, multiply_weight=True, score_handler=None, for_other=False):
        u"""
        中高层算法， 包括 180.
        计算方式：
        自评：
        行为原始分为整数，最小为-3分，最大为+3分；最终得分介于0-5分之间
        最终得分=（行为原始分+3)/1.2
        他评：
        行为原始分最小为1分，最大为5分；最终得分介于1-5分之间
        他评=各个评价人分数的平均
        default_data = {
            "report_type": "中高层90模板",
            "msg": {
                "Name": "666",
                "Sex": "男",
                "Age": "25",
                "TestTime": "2018.10.12",
                # name  维度名称，score: 维度分    自评
                "chart": [
                    {"name": "积极进取", "score": 2},
                    {"name": "勇于担当", "score": 2},
                    {"name": "正直诚信", "score": 2},
                    {"name": "系统思维", "score": 3},
                    {"name": "变革管理", "score": 2},
                    {"name": "客户导向", "score": 2},
                    {"name": "创新优化", "score": 3},
                    {"name": "团队领导", "score": 3},
                    {"name": "跨界协同", "score": 4},
                    {"name": "资源整合", "score": 2},
                ],
            # name1  维度名称，name  指标（即行为）   score: 指标分     自评
                "chart2": [
                    {"name1": "积极进取", 'name': '为自己设置挑战性目标', "score": 2},
                    {"name1": "积极进取", 'name': '自我激发，从内心寻求动力', "score": 2},
                    {"name1": "积极进取", 'name': '会付出额外的努力', "score": 2},
                    {"name1": "积极进取", 'name': '积极寻求解决办法，坚持不懈', "score": 2},
                    {"name1": "勇于担当", 'name': '明确职责，主动承担责任', "score": 2},
                    {"name1": "勇于担当", 'name': '以目标为导向，完成工作', "score": 2},
                    {"name1": "勇于担当", 'name': '有责无疆，积极推进', "score": 2},
                    {"name1": "勇于担当", 'name': '挺身而出，成为依靠', "score": 2},
                    {"name1": "正直诚信", 'name': '做事规范坦率真诚', "score": 3},
                    {"name1": "正直诚信", 'name': '言行一致遵守承诺', "score": 3},
                    {"name1": "正直诚信", 'name': '处事公平公正', "score": 3},
                    {"name1": "正直诚信", 'name': '敢于当面直谏', "score": 3},
                    {"name1": "系统思维", 'name': '原因识别及构建解决方案', "score": 3},
                    {"name1": "系统思维", 'name': '过程管控与跟踪', "score": 3},
                    {"name1": "系统思维", 'name': '前瞻性分析', "score": 3},
                    {"name1": "系统思维", 'name': '问题发现及分析', "score": 3},
                    {"name1": "变革管理", 'name': '理解变革', "score": 2},
                    {"name1": "变革管理", 'name': '愿景塑造', "score": 2},
                    {"name1": "变革管理", 'name': '管理阻抗', "score": 2},
                    {"name1": "变革管理", 'name': '捍卫变革', "score": 2},
                    {"name1": "客户导向", 'name': '换位思考，构建解决方案', "score": 2},
                    {"name1": "客户导向", 'name': '倾听并及时反馈', "score": 2},
                    {"name1": "客户导向", 'name': '主动关注提升满意度', "score": 2},
                    {"name1": "客户导向", 'name': '协调资源超越期望', "score": 2},
                    {"name1": "创新优化", 'name': '打造创新机制及氛围', "score": 3},
                    {"name1": "创新优化", 'name': '主动关注新事物', "score": 3},
                    {"name1": "创新优化", 'name': '勇于尝试持续创新', "score": 3},
                    {"name1": "创新优化", 'name': '借鉴经验，快速有效优化', "score": 3},
                    {"name1": "团队领导", 'name': '理解高效团队的重要性', "score": 3},
                    {"name1": "团队领导", 'name': '高效合理授权', "score": 3},
                    {"name1": "团队领导", 'name': '塑造团队文化', "score": 3},
                    {"name1": "团队领导", 'name': '多形式学习交流', "score": 3},
                    {"name1": "跨界协同", 'name': '调节冲突，达至双赢', "score": 2},
                    {"name1": "跨界协同", 'name': '建立合作机制，实现效能最大化', "score": 2},
                    {"name1": "跨界协同", 'name': '理解其他部门需求及利益', "score": 2},
                    {"name1": "跨界协同", 'name': '换位思考，促进协作', "score": 2},
                    {"name1": "资源整合", 'name': '主动共享信息', "score": 2},
                    {"name1": "资源整合", 'name': '形成固有并可持续的模式', "score": 2},
                    {"name1": "资源整合", 'name': '主动争取和协调资源', "score": 2},
                    {"name1": "资源整合", 'name': '转变思维，扩展资源渠道', "score": 2},
                ],
            }
        }
        """

        # 中高层的算法先写在这里， 但是出报告的时候不是正常答完题调用的，
        # 是所有人完成答卷 或者项目结束时调用

        def process_substandard_score(dimension, substandard, for_other=False):
            substandard_score[substandard["id"]] = {
                "score": 0,
                "name": substandard["name"],
                "dimension_id": dimension["id"],
                "name1": dimension["name"]
            }
            if substandard["substandards"]:
                all_child_score = 0
                all_child_count = 0
                for child_substandard in substandard["substandards"]:
                    process_substandard_score(dimension, child_substandard)
                    all_child_count += 1
                    all_child_score += substandard_score[child_substandard["id"]]["score"]
                substandard_score[substandard["id"]]["score"] = all_child_score
            else:
                facet_id_map = SurveyAlgorithm.get_substandard_facet_map(substandard, survey)
                question_ids = []
                question_substandard_score = 0
                for facet_id in facet_id_map:
                    facet_info = facet_id_map[facet_id]
                    question_ids += facet_info["questions"]
                    if facet_id not in facet_score:
                        facet_score[facet_id] = {
                            "score": 0,
                            "name": facet_id_map[facet_id]["name"],
                            "substandard_id": substandard["id"],
                            "dimension_id": dimension["id"]
                        }
                    facet_question_count = len(facet_info["questions"])
                    if form_type == Survey.FORM_TYPE_FORCE:
                        question_answer_infos = question_answers.filter(answer_id__in=facet_info["questions"])
                    else:
                        question_answer_infos = question_answers.filter(question_id__in=facet_info["questions"])
                    question_score = 0
                    for question_answer in question_answer_infos:
                        # 自评
                        if not for_other:
                            question_score += question_answer.answer_score
                            question_substandard_score += question_answer.answer_score

                        # 评价他人
                        else:
                            question_score += question_answer.answer_score
                            question_substandard_score += question_answer.answer_score
                    if facet_question_count:
                        facet_score[facet_id]["score"] = int(round(
                            (question_score * 1.00 / facet_question_count * 1.00) * facet_id_map[facet_id]["weight"],
                            1))
                    else:
                        facet_score[facet_id]["score"] = 0

                question_count = len(question_ids)
                if question_count:
                    if not for_other:
                        question_substandard_score = round((question_substandard_score + 3) / 1.2, 2)
                    substandard_score[substandard["id"]]["score"] = question_substandard_score
                else:
                    substandard_score[substandard["id"]]["score"] = 0

        # 他评 ， 这里修改为评价人的访问， 改为被评人的分
        psr_qs = PeopleSurveyRelation.objects.get(id=people_survey_result_id)
        o_qs = PeopleSurveyRelation.objects.filter(project_id=psr_qs.project_id,
                                            evaluated_people_id=psr_qs.evaluated_people_id,
                                            people_id=psr_qs.evaluated_people_id,
                                            status=PeopleSurveyRelation.STATUS_FINISH)
        if not o_qs.exists():
            # 该他评没有自评
            # logger.info("%s for ZGC180 not self ZGC180" % people_survey_result_id)
            return
        else:
            print(people_survey_result_id)
            people_survey_result_id = o_qs[0].id
            print(people_survey_result_id)
        # 自己对他人的评价分数
        for_other_dimension_score = {}
        for_other_substandard_score = {}
        psr_qs = PeopleSurveyRelation.objects.filter(id=people_survey_result_id)
        self_d = {}
        self_s = {}
        if psr_qs.exists():
            psr_obj = psr_qs[0]
            self_d = psr_obj.dimension_score_map["self"]
            self_s = psr_obj.substandard_score_map["self"]
        facet_score = {}
        substandard_score = {}
        dimension_score = {}
        model_score = 0  # 总分
        # logger.debug("algorithm_average_weight --> people_survey_result_id is %s" % people_survey_result_id)
        people_survey_result = PeopleSurveyRelation.objects.get(id=people_survey_result_id)
        survey = Survey.objects.get(id=people_survey_result.survey_id)
        research_model = ResearchModel.objects.get(id=survey.model_id)
        model_info = SurveyAlgorithm.get_model_detail_info(research_model)
        question_answers = SurveyAlgorithm.get_question_answer(
            people_survey_result.people_id,
            people_survey_result.survey_id,
            people_survey_result.project_id,
            people_survey_result.role_type,
            people_survey_result.evaluated_people_id
        )
        dimensions = model_info['dimension']
        dimension_count = 0
        dimension_total_score = 0
        # 评价他人
        if for_other:
            for dimension in dimensions:
                substandards = dimension['substandards']
                dimension_score[dimension["id"]] = {
                    "score": 0,
                    "name": dimension["name"],
                    "row_score": 0
                }
                if not substandards:
                    pass
                else:
                    substandard_count = 0
                    score = 0
                    for substandard in substandards:
                        process_substandard_score(dimension, substandard, for_other=True)
                        tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_SUBSTANDARD,
                                                           tag_name=u"是否计入维度分").order_by("-id")
                        if tag_qs.exists():
                            tag = tag_qs[0]
                            str_qs = SubstandardTagRelation.objects.filter_active(tag_id=tag.id,
                                                                                  object_id=substandard["id"]).order_by(
                                "-id")
                            if str_qs.exists():
                                str_tag = str_qs[0]
                                if str_tag == u"否":
                                    pass
                            else:
                                substandard_count += 1
                                score += substandard_score[substandard["id"]]["score"]
                        else:
                            substandard_count += 1
                            score += substandard_score[substandard["id"]]["score"]
                    # 能力 即 维度，  能力分 = 行为分求平均
                    d_score = int(round((score * 1.00 / substandard_count * 1.00)))
                    if d_score > 5:
                        d_score = 5
                    if d_score < 0:
                        d_score = 0
                    dimension_score[dimension["id"]]["score"] = d_score
                    dimension_score[dimension["id"]]["row_score"] = round((score * 1.00 / substandard_count * 1.00), 3)
                tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_DIMENSION, tag_name=u"是否计入模型分").order_by(
                    "-id")
                if tag_qs.exists():
                    tag = tag_qs[0]
                    str_qs = DimensionTagRelation.objects.filter_active(tag_id=tag.id,
                                                                        object_id=dimension["id"]).order_by(
                        "-id")
                    if str_qs.exists():
                        str_tag = str_qs[0]
                        if str_tag == u"否":
                            pass
                    else:
                        dimension_count += 1
                        dimension_total_score += dimension_score[dimension["id"]]["score"]
                else:
                    dimension_count += 1
                    dimension_total_score += dimension_score[dimension["id"]]["score"]
            model_score = int(round((dimension_total_score * 1.00 / dimension_count * 1.00), 1))
            if score_handler:
                score_handler(model_score, dimension_score, substandard_score)
            # 找到所有他评人员， 找他们的对此人的分
            dimension_score = {"self": {}, "others": {},
                               "for_other": dimension_score}
            substandard_score = {"self": {}, "others": {},
                                 "for_other": substandard_score}
            cls.save_score(people_survey_result_id, model_score, dimension_score, substandard_score,
                           facet_score=facet_score)
        # 自评，以及获取他评
        else:
            for dimension in dimensions:
                substandards = dimension['substandards']
                dimension_score[dimension["id"]] = {
                    "score": 0,
                    "name": dimension["name"],
                    "row_score": 0,
                }
                if not substandards:
                    pass
                else:
                    substandard_count = 0
                    score = 0
                    for substandard in substandards:
                        process_substandard_score(dimension, substandard)
                        tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_SUBSTANDARD,
                                                           tag_name=u"是否计入维度分").order_by("-id")
                        if tag_qs.exists():
                            tag = tag_qs[0]
                            str_qs = SubstandardTagRelation.objects.filter_active(tag_id=tag.id,
                                                                                  object_id=substandard["id"]).order_by(
                                "-id")
                            if str_qs.exists():
                                str_tag = str_qs[0]
                                if str_tag == u"否":
                                    pass
                            else:
                                substandard_count += 1
                                score += substandard_score[substandard["id"]]["score"]
                        else:
                            substandard_count += 1
                            score += substandard_score[substandard["id"]]["score"]
                    # 能力 即 维度，  能力分 = 行为分求平均
                    d_score = int(round((score * 1.00 / substandard_count * 1.00)))
                    dimension_score[dimension["id"]]["row_score"] = round((score * 1.00 / substandard_count * 1.00), 3)
                    if d_score > 5:
                        d_score = 5
                    if d_score < 0:
                        d_score = 0
                    dimension_score[dimension["id"]]["score"] = d_score
                tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_DIMENSION, tag_name=u"是否计入模型分").order_by(
                    "-id")
                if tag_qs.exists():
                    tag = tag_qs[0]
                    str_qs = DimensionTagRelation.objects.filter_active(tag_id=tag.id,
                                                                        object_id=dimension["id"]).order_by(
                        "-id")
                    if str_qs.exists():
                        str_tag = str_qs[0]
                        if str_tag == u"否":
                            pass
                    else:
                        dimension_count += 1
                        dimension_total_score += dimension_score[dimension["id"]]["score"]
                else:
                    dimension_count += 1
                    dimension_total_score += dimension_score[dimension["id"]]["score"]
            model_score = int(round((dimension_total_score * 1.00 / dimension_count * 1.00), 1))
            if score_handler:
                score_handler(model_score, dimension_score, substandard_score)
            # 自评和他评的计算方式不同， 所以加一个参数作为标志位
            # 检查有哪些人评价了他， 然后计算，
            #
            # 他人对自己的评价分数
            other_dimension_score = {}
            other_substandard_score = {}

            evaluated_people_id = people_survey_result.people_id
            project_id = people_survey_result.project_id
            evaluate_qs = PeopleSurveyRelation.objects.filter_active(evaluated_people_id=evaluated_people_id,
                                                                     project_id=project_id,
                                                                     status=PeopleSurveyRelation.STATUS_FINISH)
            others_count = evaluate_qs.count()
            if others_count:
                for evaluate_obj in evaluate_qs:
                    if evaluate_obj.people_id == evaluated_people_id:
                        others_count -= 1
                        if not others_count:
                            break
                    else:
                        cls.algorithm_zgc(evaluate_obj.id, form_type=Survey.FORM_TYPE_NORMAL, for_other=True)
                        evaluate_obj = PeopleSurveyRelation.objects.get(id=evaluate_obj.id)
                        one_other_dimension_score = evaluate_obj.dimension_score_map["for_other"]
                        one_other_substandard_score = evaluate_obj.substandard_score_map["for_other"]
                        if not other_dimension_score:
                            other_dimension_score = one_other_dimension_score
                            other_substandard_score = one_other_substandard_score
                        else:
                            for other_dimension in other_dimension_score:
                                for one_other_dimension in one_other_dimension_score:
                                    if other_dimension == one_other_dimension:
                                        other_dimension_score[other_dimension]["row_score"] += \
                                        one_other_dimension_score[one_other_dimension]["row_score"]
                            for other_substandard in other_substandard_score:
                                for one_other_substandard in one_other_substandard_score:
                                    if other_substandard == one_other_substandard:
                                        other_substandard_score[other_substandard]["score"] += \
                                        one_other_substandard_score[one_other_substandard]["score"]
                if others_count:
                    for other_dimension in other_dimension_score:
                        other_dimension_score[other_dimension]["score"] = round((other_dimension_score[other_dimension]["row_score"] / (others_count * 1.00)), 3)
                    for other_substandard in other_substandard_score:
                        other_substandard_score[other_substandard]["score"] = round((other_substandard_score[other_substandard]["score"] / (others_count * 1.00)), 2)

            # 找到所有他评人员， 找他们的对此人的分
            if self_d and self_s:
                dimension_score = {"self": self_d, "others": other_dimension_score,
                                   "for_other": for_other_dimension_score}
                substandard_score = {"self": self_s, "others": other_substandard_score,
                                     "for_other": for_other_substandard_score}
            else:
                dimension_score = {"self": dimension_score, "others": other_dimension_score,
                                   "for_other": for_other_dimension_score}
                substandard_score = {"self": substandard_score, "others": other_substandard_score,
                                     "for_other": for_other_substandard_score}
            cls.save_score(people_survey_result_id, model_score, dimension_score, substandard_score,
                           facet_score=facet_score)


    #     行为风格 和 职业定向
    @classmethod
    def algorithm_xwfg(cls, people_survey_result_id, form_type=Survey.FORM_TYPE_FORCE,
                             remove_weight_zero=True, multiply_weight=True, score_handler=None):
        u"""
        行为风格
        计算方式：

        """
        def process_substandard_score(dimension, substandard, dimension_question_count, dimension_question_count_neg, index):
            # 算某维度的子标分
            # 子标的样式
            substandard_score[substandard["id"]] = {
                "score": 0,
                "name": substandard["name"],
                "dimension_id": dimension["id"]
            }
            if substandard["substandards"]:
                all_child_score = 0
                all_child_count = 0
                for child_substandard in substandard["substandards"]:
                    process_substandard_score(dimension, child_substandard, dimension_question_count)
                    all_child_count += 1
                    all_child_score += substandard_score[child_substandard["id"]]["score"]
                substandard_score[substandard["id"]]["score"] = all_child_score
                debug_logger.debug("process_substandard_score --> process substandard of %s, %s, %s" % (
                substandard["id"], substandard["name"], substandard_score[substandard["id"]]["score"]))
            else:
                debug_logger.debug("begin process_substandard_score --> process substandard of %s, %s" % (
                    substandard["id"], substandard["name"]))
                facet_id_map = cls.get_substandard_facet_map(substandard, survey)
                question_ids = []
                question_substandard_score = 0
                for facet_id in facet_id_map:
                    facet_info = facet_id_map[facet_id]
                    question_ids += facet_info["questions"]
                    if facet_id not in facet_score:
                        facet_score[facet_id] = {
                            "score": 0,
                            "name": facet_id_map[facet_id]["name"],
                            "substandard_id": substandard["id"],
                            "dimension_id": dimension["id"]
                        }
                    facet_question_count = len(facet_info["questions"])
                    if form_type == Survey.FORM_TYPE_FORCE:
                        question_answer_infos = question_answers.filter(answer_id__in=facet_info["questions"])
                    else:
                        question_answer_infos = question_answers.filter(question_id__in=facet_info["questions"])
                    question_score = 0
                    for question_answer in question_answer_infos:
                        dimension_question_count[index] += 1
                        here_score = 1
                        if question_answer.answer_score != 1:
                            here_score = 0
                            dimension_question_count_neg[index] += 1
                        question_score += here_score
                        question_substandard_score += here_score
                    if facet_question_count:
                        facet_score[facet_id]["score"] = round((question_score*1.00 / facet_question_count*1.00), 2)
                    else:
                        facet_score[facet_id]["score"] = 0

                question_count = len(question_ids)
                if question_count:
                    substandard_score[substandard["id"]]["score"] = question_substandard_score
                else:
                    substandard_score[substandard["id"]]["score"] = 0
                debug_logger.debug("process_substandard_score --> process substandard of %s, %s, %s, %s, %s, %s" % (
                    substandard["id"], substandard["name"], substandard_score[substandard["id"]]["score"],
                    question_substandard_score, question_count, substandard["weight"]))

        facet_score = {}
        substandard_score = {}
        dimension_score = {}
        model_score = 0  # 总分
        debug_logger.debug("algorithm_average_weight --> people_survey_result_id is %s" % people_survey_result_id)
        people_survey_result = PeopleSurveyRelation.objects.get(id=people_survey_result_id)
        survey = Survey.objects.get(id=people_survey_result.survey_id)
        research_model = ResearchModel.objects.get(id=survey.model_id)
        model_info = cls.get_model_detail_info(research_model)
        question_answers = cls.get_question_answer(
            people_survey_result.people_id,
            people_survey_result.survey_id,
            people_survey_result.project_id,
            people_survey_result.role_type,
            people_survey_result.evaluated_people_id
        )
        dimensions = model_info['dimension']
        dimension_count = 0
        dimension_total_score = 0
        dimension_question_count = []
        dimension_question_count_neg = []
        for index, dimension in enumerate(dimensions):
            dimension_question_count.append(0)
            dimension_question_count_neg.append(0)
            substandards = dimension['substandards']
            dimension_score[dimension["id"]] = {
                "score": 0,  # 就是强度， = 正 - 反向分
                "name": dimension["name"],
                "change_score": 0,  # 即强度 转换, 就是 强度+题数， 强度 = 正 - 反向分（反向=题数-正）
                "percente_name": "",
                "percente_score": 0,   # 百分比分数 强度 / 题目数量
                "question_count": 0
            }
            if not substandards:
                pass
            else:
                substandard_count = 0
                score = 0
                for substandard in substandards:
                    process_substandard_score(dimension, substandard, dimension_question_count, dimension_question_count_neg, index)
                    tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_SUBSTANDARD, tag_name=u"是否计入维度分").order_by("-id")
                    if tag_qs.exists():
                        tag = tag_qs[0]
                        str_qs = SubstandardTagRelation.objects.filter_active(tag_id=tag.id, object_id=substandard["id"]).order_by("-id")
                        if str_qs.exists():
                            str_tag = str_qs[0]
                            if str_tag == u"否":
                                pass
                        else:
                            substandard_count += 1
                            score += substandard_score[substandard["id"]]["score"]
                    else:
                        substandard_count += 1
                        score += substandard_score[substandard["id"]]["score"]
                dimension_score[dimension["id"]]["score"] = score - (dimension_question_count[index] - score)  # 强度 = 正向 -  反向
                #
                # score 是正向分， 反向分就是 score - (dimension_question_count[index] - score)
                dimension_score[dimension["id"]]["change_score"] = score - (dimension_question_count[index] - score) + dimension_question_count[index]  # 强度转换 = 强度 + 题数
                try:
                    try:
                        dimension_score[dimension["id"]]["percente_name"] = dimension["name"][-3:-1]
                    except:
                        try:
                            dimension_score[dimension["id"]]["percente_name"] = dimension["name"].split("-")[1].split("）")[0]
                        except:
                            dimension_score[dimension["id"]]["percente_name"] = dimension["name"].split("—")[1].split("）")[
                                0]
                except:
                    try:
                        dimension_score[dimension["id"]]["percente_name"] = dimension["name"].split("-")[1].split(")")[
                            0]
                    except:
                        dimension_score[dimension["id"]]["percente_name"] = dimension["name"].split("-")[1]
                if dimension_question_count:
                    if dimension_question_count > score:
                        # 强度 百分比： 强度 / 题数  改为 正反向百分比
                        dimension_score[dimension["id"]]["percente_score"] = round((score*1.00 / dimension_question_count[index]*1.00), 2) * 100
                    else:
                        dimension_score[dimension["id"]]["percente_score"] = 100
                else:
                    dimension_score[dimension["id"]]["percente_score"] = 0
                dimension_score[dimension["id"]]["question_count"] = dimension_question_count[index]
            tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_DIMENSION, tag_name=u"是否计入模型分").order_by("-id")
            if tag_qs.exists():
                tag = tag_qs[0]
                str_qs = DimensionTagRelation.objects.filter_active(tag_id=tag.id, object_id=dimension["id"]).order_by(
                    "-id")
                if str_qs.exists():
                    str_tag = str_qs[0]
                    if str_tag == u"否":
                        pass
                else:
                    dimension_count += 1
                    dimension_total_score += dimension_score[dimension["id"]]["score"]
            else:
                dimension_count += 1
                dimension_total_score += dimension_score[dimension["id"]]["score"]
        model_score = round((dimension_total_score*1.00 / dimension_count*1.00), 2)
        if score_handler:
            score_handler(model_score, dimension_score, substandard_score)

        cls.save_score(people_survey_result_id, model_score, dimension_score, substandard_score, facet_score=facet_score)

    @classmethod
    def algorithm_zydx(cls, people_survey_result_id, form_type=Survey.FORM_TYPE_FORCE,
                             remove_weight_zero=True, multiply_weight=True, score_handler=None):
        u"""
        职业定向
        计算方式：

        "1.测试题为40道关于职业的描述，每题选择一个代表你真实想法的分数。除非你非常明确，否则不需要做出极端的选择，例如：1或6。
        2.维度分=该维度下分数的总和"

        """

        def process_substandard_score(dimension, substandard):
            substandard_score[substandard["id"]] = {
                "score": 0,
                "name": substandard["name"],
                "dimension_id": dimension["id"]
            }
            if substandard["substandards"]:
                all_child_score = 0
                all_child_count = 0
                for child_substandard in substandard["substandards"]:
                    process_substandard_score(dimension, child_substandard)
                    all_child_count += 1
                    all_child_score += substandard_score[child_substandard["id"]]["score"]
                substandard_score[substandard["id"]]["score"] = all_child_score
                debug_logger.debug("process_substandard_score --> process substandard of %s, %s, %s" % (
                substandard["id"], substandard["name"], substandard_score[substandard["id"]]["score"]))
            else:
                debug_logger.debug("begin process_substandard_score --> process substandard of %s, %s" % (
                    substandard["id"], substandard["name"]))
                facet_id_map = cls.get_substandard_facet_map(substandard, survey)
                question_ids = []
                question_substandard_score = 0
                for facet_id in facet_id_map:
                    facet_info = facet_id_map[facet_id]
                    question_ids += facet_info["questions"]
                    if facet_id not in facet_score:
                        facet_score[facet_id] = {
                            "score": 0,
                            "name": facet_id_map[facet_id]["name"],
                            "substandard_id": substandard["id"],
                            "dimension_id": dimension["id"]
                        }
                    facet_question_count = len(facet_info["questions"])
                    if form_type == Survey.FORM_TYPE_FORCE:
                        question_answer_infos = question_answers.filter(answer_id__in=facet_info["questions"])
                    else:
                        question_answer_infos = question_answers.filter(question_id__in=facet_info["questions"])
                    question_score = 0
                    for question_answer in question_answer_infos:
                        question_score += question_answer.answer_score
                        question_substandard_score += question_answer.answer_score
                    if facet_question_count:
                        facet_score[facet_id]["score"] = question_score / facet_question_count
                    else:
                        facet_score[facet_id]["score"] = 0

                question_count = len(question_ids)
                if question_count:
                    substandard_score[substandard["id"]]["score"] = question_substandard_score
                else:
                    substandard_score[substandard["id"]]["score"] = 0
                debug_logger.debug("process_substandard_score --> process substandard of %s, %s, %s, %s, %s, %s" % (
                    substandard["id"], substandard["name"], substandard_score[substandard["id"]]["score"],
                    question_substandard_score, question_count, substandard["weight"]))

        facet_score = {}
        substandard_score = {}
        dimension_score = {}
        model_score = 0  # 总分
        debug_logger.debug("algorithm_average_weight --> people_survey_result_id is %s" % people_survey_result_id)
        people_survey_result = PeopleSurveyRelation.objects.get(id=people_survey_result_id)
        survey = Survey.objects.get(id=people_survey_result.survey_id)
        research_model = ResearchModel.objects.get(id=survey.model_id)
        model_info = cls.get_model_detail_info(research_model)
        question_answers = cls.get_question_answer(
            people_survey_result.people_id,
            people_survey_result.survey_id,
            people_survey_result.project_id,
            people_survey_result.role_type,
            people_survey_result.evaluated_people_id
        )
        dimensions = model_info['dimension']
        dimension_count = 0
        dimension_total_score = 0
        for dimension in dimensions:
            substandards = dimension['substandards']
            name = dimension["name"][:-4]
            dimension_score[dimension["id"]] = {
                "score": 0,
                # "name": dimension["name"]
                "name": name
            }
            if not substandards:
                pass
            else:
                substandard_count = 0
                score = 0
                for substandard in substandards:
                    process_substandard_score(dimension, substandard)
                    tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_SUBSTANDARD, tag_name=u"是否计入维度分").order_by("-id")
                    if tag_qs.exists():
                        tag = tag_qs[0]
                        str_qs = SubstandardTagRelation.objects.filter_active(tag_id=tag.id, object_id=substandard["id"]).order_by("-id")
                        if str_qs.exists():
                            str_tag = str_qs[0]
                            if str_tag == u"否":
                                pass
                        else:
                            substandard_count += 1
                            score += substandard_score[substandard["id"]]["score"]
                    else:
                        substandard_count += 1
                        score += substandard_score[substandard["id"]]["score"]
                if score > 30:
                    score = 30
                if score < 5:
                    score = 5
                dimension_score[dimension["id"]]["score"] = score
            tag_qs = Tag.objects.filter_active(business_model=Tag.MODEL_DIMENSION, tag_name=u"是否计入模型分").order_by("-id")
            if tag_qs.exists():
                tag = tag_qs[0]
                str_qs = DimensionTagRelation.objects.filter_active(tag_id=tag.id, object_id=dimension["id"]).order_by(
                    "-id")
                if str_qs.exists():
                    str_tag = str_qs[0]
                    if str_tag == u"否":
                        pass
                else:
                    dimension_count += 1
                    dimension_total_score += dimension_score[dimension["id"]]["score"]
            else:
                dimension_count += 1
                dimension_total_score += dimension_score[dimension["id"]]["score"]
        model_score = dimension_total_score / dimension_count
        if score_handler:
            score_handler(model_score, dimension_score, substandard_score)
        cls.save_score(people_survey_result_id, model_score, dimension_score, substandard_score, facet_score=facet_score)





