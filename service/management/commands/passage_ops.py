# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import time
from django.core.management import BaseCommand
from django.db import transaction

from front.models import PeopleSurveyRelation
from front.tasks import algorithm_task
from question.models import QuestionPassage, QuestionFacet, Question, QuestionPassageRelation


def ops_passage_update():
    u"""处理项目问卷，重新生成分值和报告
    信息分析 facet_id=491
031004001005001 ～ 031004001005150
信息分析-C facet_id=485
031004001004001 ～ 031004001004015
信息分析-B  facet_id=484
031004001003001 ～ 031004001003015
信息分析-A  facet_id=205
031004001002002 ～ 031004001002016
    """
    # 信息分析 facet_id=491
    facet = QuestionFacet.objects.get(id=491)
    facet.facet_type = QuestionFacet.FACET_TYPE_PASSAGE
    facet.save()
    passage_id = 0
    for i in range(0, 150):
        index = i + 1
        code = '031004001005%03d' % index
        print code
        question = Question.objects.filter_active(code=code)[0]
        if index % 5 == 1:
            passage_rel = QuestionPassageRelation.objects.get(question_id=question.id)
            passage = QuestionPassage.objects.get(id=passage_rel.passage_id)
            passage_id = passage.id
            passage.question_facet_id = facet.id
            passage.save()
        question.question_passage_id = passage_id
        question.save()
    # 信息分析-C facet_id=485
    facet = QuestionFacet.objects.get(id=485)
    facet.facet_type = QuestionFacet.FACET_TYPE_PASSAGE
    facet.save()
    passage_id = 0
    for i in range(0, 15):
        index = i + 1
        code = '0310040010040%02d' % index
        print code
        question = Question.objects.filter_active(code=code)[0]
        if index % 5 == 1:
            passage_rel = QuestionPassageRelation.objects.get(question_id=question.id)
            passage = QuestionPassage.objects.get(id=passage_rel.passage_id)
            passage_id = passage.id
            passage.question_facet_id = facet.id
            passage.save()
        question.question_passage_id = passage_id
        question.save()
    # 信息分析-B  facet_id=484
    facet = QuestionFacet.objects.get(id=484)
    facet.facet_type = QuestionFacet.FACET_TYPE_PASSAGE
    facet.save()
    passage_id = 0
    for i in range(0, 15):
        index = i + 1
        code = '0310040010030%02d' % index
        print code
        question = Question.objects.filter_active(code=code)[0]
        if index % 5 == 1:
            passage_rel = QuestionPassageRelation.objects.get(question_id=question.id)
            passage = QuestionPassage.objects.get(id=passage_rel.passage_id)
            passage_id = passage.id
            passage.question_facet_id = facet.id
            passage.save()
        question.question_passage_id = passage_id
        question.save()

    # 信息分析-A  facet_id=205
    facet = QuestionFacet.objects.get(id=205)
    facet.facet_type = QuestionFacet.FACET_TYPE_PASSAGE
    facet.save()
    passage_id = 0
    for i in range(1, 16):
        index = i + 1
        code = '0310040010020%02d' % index
        print code
        question = Question.objects.filter_active(code=code)[0]
        if index % 5 == 2:
            passage_rel = QuestionPassageRelation.objects.get(question_id=question.id)
            passage = QuestionPassage.objects.get(id=passage_rel.passage_id)
            passage_id = passage.id
            passage.question_facet_id = facet.id
            passage.save()
        question.question_passage_id = passage_id
        question.save()





class Command(BaseCommand):

    @transaction.atomic
    def handle(self, *args, **options):
        ops_passage_update()