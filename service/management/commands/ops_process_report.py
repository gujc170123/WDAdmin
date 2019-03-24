# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import time
from django.core.management import BaseCommand
from django.db import transaction

from front.models import PeopleSurveyRelation
from front.serializers import PeopleSurveySerializer
from front.tasks import algorithm_task, get_report
from utils.logger import get_logger

logger = get_logger("ops_process_report")


def ops_process_report(project_id, survey_id, finish_time, is_test):
    u"""处理项目问卷，重新报告"""
    pqs = PeopleSurveyRelation.objects.filter_active(
        project_id=project_id, survey_id=survey_id,
        status=PeopleSurveyRelation.STATUS_FINISH,
        report_status__in=[
            PeopleSurveyRelation.REPORT_INIT,
            PeopleSurveyRelation.REPORT_GENERATING,
            PeopleSurveyRelation.REPORT_FAILED
        ],
        finish_time__lt=finish_time
    )
    logger.debug("process result count: %s" % pqs.count())
    # datas = PeopleSurveySerializer(instance=pqs, many=True).data
    for obj in pqs:
        data = PeopleSurveySerializer(instance=obj).data
        logger.debug("process result_id %s" % data["id"])
        get_report({"results": [data]}, user_id=0, force_recreate=True)
        if is_test == 1:
            break
        time.sleep(10)


class Command(BaseCommand):
    help = "parse tag system excel"

    def add_arguments(self, parser):
        parser.add_argument("--project_id", dest="project_id", action="store", type=int,
                            help="project id that will be processed")
        parser.add_argument("--survey_id", dest="survey_id", action="store", type=int,
                            help="survey id that will be processed")
        parser.add_argument("--finish_time", dest="finish_time", action="store", type=str,
                            help="finish_time")
        parser.add_argument("--is_test", dest="is_test", action="store", type=int,
                            help="is_test")

    @transaction.atomic
    def handle(self, *args, **options):
        project_id = options["project_id"]
        survey_id = options["survey_id"]
        finish_time = options["finish_time"]
        is_test = int(options.get("is_test", 1))
        logger.info("ops_survey_result process %s %s" % (project_id, survey_id))
        ops_process_report(project_id, survey_id, finish_time, is_test)