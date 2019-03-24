# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from django.core.management import BaseCommand
from django.db import transaction

from assessment.models import AssessUser
from assessment.tasks import zip_excel_back
from front.models import UserQuestionAnswerInfo
from survey.models import SurveyQuestionResult
from utils.aliyun.email import EmailUtils
from utils.aliyun.oss import AliyunOss
from utils.excel import ExcelUtils
from wduser.models import AuthUser, People


def time_assess_out(assess_id, people_ids, survey_id, x):
    title = [u'账号', ]
    name = "survey_%s_assess%s_part_%s_answertime.xlsx" % (assess_id, survey_id, x)
    data = []
    for index, people_id in enumerate(people_ids):
        if index % 100 == 0:
            print(index)
        if index == 0:
            sqr_q_ids = SurveyQuestionResult.objects.filter_active(survey_id=survey_id).values_list('question_id', flat=True).order_by('question_id').distinct()
            title_2 = list(sqr_q_ids)
            title.extend(title_2)
        try:
            q_a_time = UserQuestionAnswerInfo.objects.filter_active(question_id__in=title_2,
                             people_id=people_id, survey_id=survey_id,
                             project_id=assess_id).order_by("question_id").values_list("question_id", 'answer_time')
            p_u_id = People.objects.filter(id=people_id)[0].user_id
            a_n = AuthUser.objects.filter(id=p_u_id)[0].account_name
            one_data = [a_n]
            q_id_row = []
            for id, time in q_a_time:
                if id not in q_id_row:
                    one_data.append(time)
                    q_id_row.append(id)
                else:
                    pass
        except:
            print('error')
            one_data = [people_id]
        data.append(one_data)
    file_path = ExcelUtils().create_excel(name, title, data, sheet_name=u"s_id_%s,a_id_%s" % (survey_id, assess_id),
                                          force_save=True, sheet_index=0)
    return file_path, name


def get_people_answer_time(assess_id, survey_id, email, num_p=0):
    # 一共哪些人
    people_ids = list(AssessUser.objects.filter_active(assess_id=assess_id).values_list('people_id', flat=True))
    PEOPLE_NUM = 5000 if num_p == 0 else num_p
    num = (len(people_ids) // PEOPLE_NUM) + 1
    all_files_path = []
    for x in range(num):
        file_path, default_export_file_name = time_assess_out(assess_id,
                                                              people_ids[x * PEOPLE_NUM:(x + 1) * PEOPLE_NUM],
                                                              survey_id, x)
        all_files_path.append(file_path)
    zip_path, zip_name = zip_excel_back(all_files_path, assess_id)
    oss_keys = AliyunOss().upload_file(1, zip_name, zip_path, prefix='wdadmin')
    EmailUtils().send_oss_people_list(oss_keys, email)


class Command(BaseCommand):
    help = "parse tag system excel"

    def add_arguments(self, parser):
        parser.add_argument("--assess_survey", dest="assess_survey", action="store", type=str,
                            help="process user to deactive, user join with',', like: account1,account2")

    @transaction.atomic
    def handle(self, *args, **options):
        process_users = options["assess_survey"]
        accounts = process_users.split(",")
        assess_id = int(accounts[0])
        survey_id = int(accounts[1])
        print(assess_id, survey_id)
        email = '1360820124@qq.com'
        get_people_answer_time(assess_id, survey_id, email, num_p=0)