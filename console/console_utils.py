# -*- coding:utf-8 -*-

from research.research_utils import ResearchDimensionUtils, ResearchSubstandardUtils
from survey.models import SurveyModelFacetRelation, SurveyQuestionRelation
from question.models import QuestionFacet, Question
from research.models import QuestionFacetTagRelation, QuestionTagRelation
from research.models import ResearchDimension, DimensionTagRelation, ResearchSubstandard, SubstandardTagRelation
from console.models import ConsoleSurveyModelFacetRelation as SM, ConsoleSurveyQuestionRelation as SQ


class DimensionUtils(object):
    u"""维度操作类"""

    @classmethod
    def deep_copy(cls, src_dimension, survey_id, model_id, task_id):
        src_obj = src_dimension
        if type(src_obj) == int or type(src_obj) == long:
            src_obj = ResearchDimension.objects.get(id=src_dimension)
        obj = ResearchDimension.objects.create(
            model_id=model_id,
            name=src_obj.name,
            en_name=src_obj.en_name,
            weight=src_obj.weight,
            model_category=src_obj.model_category
        )
        tags = DimensionTagRelation.objects.filter_active(
            object_id=src_obj.id
        )
        tag_bulk_list = []
        for tag in tags:
            tag_bulk_list.append(DimensionTagRelation(
                tag_id=tag.tag_id,
                object_id=obj.id,
                tag_value=tag.tag_value
            ))
        DimensionTagRelation.objects.bulk_create(tag_bulk_list)
        substandards = ResearchSubstandard.objects.filter_active(dimension_id=src_obj.id, parent_id=0)
        for substandard in substandards:
            SubstandardUtils.deep_copy(substandard, survey_id, model_id, obj.id, task_id)
        survey_facet_relations = SurveyModelFacetRelation.objects.filter_active(
            related_obj_type=1,
            related_obj_id=src_dimension.id,
            survey_id=survey_id
        )
        print(survey_facet_relations.count())
        for survey_facet_relation in survey_facet_relations:
            SurveyEscapeModelFacetRelationUtils.deep_copy(survey_facet_relation, task_id, model_id, 1, obj.id)
            print('111111111111111111111')
        return obj


class SubstandardUtils(object):
    u"""指标操作类"""

    @classmethod
    def deep_copy(cls, src_substandard, survey_id, model_id, dimension_id, task_id, parent_id=0):
        src_substandard_obj = src_substandard
        if type(src_substandard) == int or type(src_substandard) == long:
            src_substandard_obj = ResearchSubstandard.objects.get(id=src_substandard)
        obj = ResearchSubstandard.objects.create(
            model_id=model_id,
            dimension_id=dimension_id,
            parent_id=parent_id,
            name=src_substandard_obj.name,
            en_name=src_substandard_obj.en_name,
            weight=src_substandard_obj.weight,
            model_category=src_substandard_obj.model_category
        )
        tags = SubstandardTagRelation.objects.filter_active(
            object_id=src_substandard_obj.id
        )
        tag_bulk_list = []
        for tag in tags:
            tag_bulk_list.append(SubstandardTagRelation(
                tag_id=tag.tag_id,
                object_id=obj.id,
                tag_value=tag.tag_value
            ))
        SubstandardTagRelation.objects.bulk_create(tag_bulk_list)
        children = ResearchSubstandard.objects.filter_active(parent_id=src_substandard_obj.id)
        for child in children:
            cls.deep_copy(child, survey_id, model_id, dimension_id, task_id, obj.id)
        survey_facet_relations = SurveyModelFacetRelation.objects.filter_active(
            related_obj_type=2,
            related_obj_id=src_substandard.id,
            survey_id=survey_id
        )
        for survey_facet_relation in survey_facet_relations:
            print('22222222222222222')
            SurveyEscapeModelFacetRelationUtils.deep_copy(survey_facet_relation, task_id, model_id, 2, obj.id)
        return obj


class SurveyEscapeModelFacetRelationUtils(object):
    u"""问卷 子标/维度 构面 关联关系 deepcopy"""
    @classmethod
    def deep_copy(cls, src_survey_facet_relation, task_id, model_id, related_obj_type, related_obj_id):
        src_obj = src_survey_facet_relation
        if type(src_obj) == int or type(src_obj) == long:
            src_obj = SurveyModelFacetRelation.objects.get(id=src_survey_facet_relation)
        obj = SM.objects.create(
            survey_id=src_obj.survey_id,
            model_id=model_id,
            related_obj_type=related_obj_type,
            related_obj_id=related_obj_id,
            facet_ids=src_obj.facet_ids,
            question_count=src_obj.question_count,
            escape_task_id=task_id,
            )
        print(obj.id)
        survey_question_relations = SurveyQuestionRelation.objects.filter_active(model_facet_relation_id=src_obj.id)
        bulk_list = []
        for survey_question_relation in survey_question_relations:
            bulk_list.append(SQ(
                survey_id=survey_question_relation.survey_id,
                question_id=survey_question_relation.question_id,
                model_facet_relation_id=obj.id,
                escape_task_id=task_id,
            ))
        SQ.objects.bulk_create(bulk_list)
        return obj


class QuestionFacetUtils(object):
    u"""构面deepcopy"""

    @classmethod
    def deep_copy(cls, src_question_facet, quetion_folder_id, question_bank_id):
        src_obj = src_question_facet
        if type(src_obj) == int or type(src_obj) == long:
            src_obj = SurveyModelFacetRelation.objects.get(id=src_question_facet)
        obj = QuestionFacet.objects.create(
            question_bank_id=question_bank_id,
            quetion_folder_id=quetion_folder_id,
            name=src_obj.name,
            code=src_obj.code,
            desc=src_obj.desc,
            weight=src_obj.weight,
            config_info=src_obj.config_info
        )
        tags = QuestionFacetTagRelation.objects.filter_active(
            object_id=src_obj.id
        )
        tag_bulk_list = []
        for tag in tags:
            tag_bulk_list.append(QuestionFacetTagRelation(
                tag_id=tag.tag_id,
                object_id=obj.id,
                tag_value=tag.tag_value
            ))
        QuestionFacetTagRelation.objects.bulk_create(tag_bulk_list)
        questions = Question.objects.filter_active(question_facet_id=src_obj.id)
        for question in questions:
            QuestionUtils.deep_copy(question, obj.id, quetion_folder_id, question_bank_id)
        return obj


class QuestionUtils(object):
    u"""question deepcopy"""

    @classmethod
    def deep_copy(cls, src_question, question_facet_id, question_folder_id, question_bank_id):
        src_obj = src_question
        if type(src_obj) == int or type(src_obj) == long:
            src_obj = Question.objects.get(id=src_question)
        obj = Question.objects.create(
            question_bank_id=question_bank_id,
            question_folder_id=question_folder_id,
            question_facet_id=question_facet_id,
            title=src_obj.title,
            code=src_obj.code,
            question_type=src_obj.question_type,
            question_category=src_obj.question_category,
            uniformity_question_id=src_obj.uniformity_question_id,
            config_info=src_obj.config_info,
            use_count=src_obj.use_count,
            average_score=src_obj.average_score,
            standard_deviation=src_obj.standard_deviation
        )
        tags = QuestionTagRelation.objects.filter_active(
            object_id=src_obj.id
        )
        tag_bulk_list = []
        for tag in tags:
            tag_bulk_list.append(QuestionFacetTagRelation(
                tag_id=tag.tag_id,
                object_id=obj.id,
                tag_value=tag.tag_value
            ))
        QuestionTagRelation.objects.bulk_create(tag_bulk_list)
        return obj













