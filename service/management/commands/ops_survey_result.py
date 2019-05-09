# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import time
from django.core.management import BaseCommand
from django.db import transaction

from front.models import PeopleSurveyRelation
from front.tasks import algorithm_task
from utils.logger import debug_logger, info_logger


def ops_survey_result(project_id, survey_id, from_num, end_num, report_create):
    u"""处理项目问卷，重新生成分值和报告"""
    pqs = PeopleSurveyRelation.objects.filter_active(
        project_id=project_id, survey_id=survey_id,
        status=PeopleSurveyRelation.STATUS_FINISH
    ).values_list("id", flat=True)[from_num:end_num]
    for result_id in pqs:
        debug_logger.debug("process result_id %s" % result_id)
        if report_create:
            algorithm_task.delay(result_id, True, True)
        else:
            algorithm_task.delay(result_id, False, False)
        time.sleep(0.2)


class Command(BaseCommand):
    help = "parse tag system excel"

    def add_arguments(self, parser):
        parser.add_argument("--project_id", dest="project_id", action="store", type=int,
                            help="project id that will be processed")
        parser.add_argument("--survey_id", dest="survey_id", action="store", type=int,
                            help="survey id that will be processed")
        parser.add_argument("--from_num", dest="from_num", action="store", type=int,
                            help="from_num that will be processed")
        parser.add_argument("--end_num", dest="end_num", action="store", type=int,
                            help="end_num that will be processed")
        parser.add_argument("--report_create", dest="end_num", action="store", type=int,
                            help="report_create that will be processed")

    @transaction.atomic
    def handle(self, *args, **options):
        project_id = options["project_id"]
        survey_id = options["survey_id"]
        from_num = options.get("from_num", 0)
        end_num = options.get("end_num", 1000000)
        report_create = int(options.get("report_create", 0))
        info_logger.info("ops_survey_result process %s %s" % (project_id, survey_id))
        ops_survey_result(project_id, survey_id, from_num, end_num, report_create)