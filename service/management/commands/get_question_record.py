# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.core.management import BaseCommand
from survey.models import Survey, SurveyQuestionRelation
from front.models import PeopleSurveyRelation, UserQuestionAnswerInfo


class Command(BaseCommand):

    # 继承BaseCommand类，类名请保证为Command
    def handle(self, *args, **options):
        # 重写handle方法，该方法写入自定义命令要做的事（逻辑代码）
        pids = list(PeopleSurveyRelation.objects.filter_active(project_id=172, survey_id=152, status=20,
                                                               model_score__gt=0).values_list("people_id", flat=True))
        q = []
        for people_id in pids:
            people_survey = PeopleSurveyRelation.objects.filter(survey_id=152, project_id=172, people_id=people_id)[0]
            question_id_list = SurveyQuestionRelation.objects.filter(survey_id=152)
            for question in question_id_list:
                question_answer_list = UserQuestionAnswerInfo.objects.filter(people_id=people_id, survey_id=152,
                                                                             project_id=172,
                                                                        question_id=question.question_id)
                for question_answer in question_answer_list:
                    with open('/home/wd/production/project/admin/WeiDuAdmin/qinfo.txt', 'a') as f:
                        s = [question_answer.id, question_answer.question_id, people_survey.id,
                             question_answer.people_id,
                             question_answer.survey_id, question_answer.project_id, question_answer.order_num,
                             question_answer.answer_id, question_answer.answer_score, question_answer.answer_index,
                             question_answer.answer_time, '2018-11-22']
                        s1 = str(s)[1:-1]

                        f.write(s1 + '\n')



