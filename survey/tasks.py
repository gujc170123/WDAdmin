# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from celery import shared_task

from assessment.models import AssessSurveyRelation
from question.models import Question
from survey.models import SurveyQuestionRelation, Survey
from utils.logger import get_logger

logger = get_logger("survey_task")

@shared_task
def statistics_question_count(survey_id):
    # 迫排题题目可能会重复  题目使用次数加一
    question_ids = SurveyQuestionRelation.objects.filter_active(survey_id=survey_id).values_list("question_id", flat=True).distinct()
    for question_id in question_ids:
        obj = Question.objects.get(id=question_id)
        obj.use_count += 1
        obj.save()


@shared_task
def survey_used_count():
    survey_obj_list = Survey.objects.filter_active()
    logger.debug("process survey_used_count")
    for survey_obj in survey_obj_list:
        count = AssessSurveyRelation.objects.filter_active(survey_id=survey_obj.id).count()
        if survey_obj.use_count != count:
            survey_obj.use_count = count
            survey_obj.save()
