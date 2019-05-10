# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from celery import shared_task
from assessment.models import AssessSurveyRelation, AssessProject
from console.models import SurveyOverview, CleanTask, EscapeTask, AnalysisTask, SurveyOverviewCleanTask,\
    SurveyOverviewEscapeTask, SurveyOverviewAnalysisTask
from survey.models import Survey
from wduser.models import EnterpriseInfo
from datetime import datetime, timedelta
from utils.logger import debug_logger
from front.models import PeopleSurveyRelation
import requests



@shared_task
def etl_start(etl_key, etl_class, **kwargs):
    from console.etl import do_etl
    debug_logger.debug("etl_start of %s(%s)" % (etl_class, etl_key))
    eval(etl_class)(etl_key, **kwargs).do_etl()


@shared_task
def auto_update_database():
    """ 定时查看获取创建总揽表"""
    print(u'定时获取总揽数据')
    now = datetime.now()
    # two_day_ago_point = now - timedelta(days=10)
    assess_ids = AssessProject.objects.filter(is_active=True, end_time__lt=now).values_list('id', flat=True)
    update_qs = AssessSurveyRelation.objects.filter(is_active=True, assess_id__in=assess_ids)
    for obj in update_qs:
        assess = AssessProject.objects.get(id=obj.assess_id)
        people_survey = PeopleSurveyRelation.objects.filter(is_active=True, project_id=assess.id, survey_id=obj.survey_id)
        total_num = people_survey.count()
        effective_num = people_survey.filter(is_active=True, status=20).count()
        SurveyOverview.objects.get_or_create(
            enterprise_id=assess.enterprise_id,
            enterprise_name=EnterpriseInfo.objects.get(id=assess.enterprise_id).cn_name,
            survey_id=obj.survey_id,
            survey_name=Survey.objects.get(id=obj.survey_id).title,
            assess_id=assess.id,
            assess_name=assess.name,
            begin_time=assess.begin_time,
            end_time=assess.end_time,
            total_num=total_num,
            creator_id=obj.creator_id,
            create_time=obj.create_time,
            effective_num=effective_num
            )


@shared_task
def auto_update_clean_status(task_id=None):
    from console.etl import EtlTrialClean
    """试清洗状态更新"""
    if not task_id:
        qs = CleanTask.objects.filter_active(clean_status=10)
    else:
        qs = CleanTask.objects.filter_active(id=task_id)
        if qs.first() and qs.first().clean_status == 30:
            return
    # {survey_overview_id: [1,2,3,], survey_overview_id: [3,5,7]}
    status_dic = {}
    for ret in qs:
        etl = EtlTrialClean(ret.id)
        ret.schedule = etl.progress if etl.progress else 0.00
        status = etl.status
        if status == "ongoing":
            ret.clean_status = 20
        elif status == "finished":
            ret.clean_status = 30
        elif status == "stop":
            ret.clean_status = 70
        if etl.end_time:
            ret.end_time = datetime.strptime(etl.end_time, "%Y-%m-%d %H:%M:%S")
            print("end_time:%s" % ret.end_time)
        print("schedule:%s, clean_status:%s" % (ret.schedule, ret.clean_status))
        ret.save()

        survey_overview_ids = eval(ret.survey_overview_ids)
        for survey_overview_id in survey_overview_ids:
            if ret.clean_status < 40:
                if status_dic.has_key(survey_overview_id):
                    status_dic[survey_overview_id].append(ret.clean_status)
                else:
                    status_dic.update({survey_overview_id: [ret.clean_status]})

    # [(survey_overview_id: 1), (survey_overview_id: 3)] 元祖第二个元素是最小状态
    status_list = map(lambda x: (x, min(status_dic[x])), status_dic)
    for survey_overview_id, status in status_list:
        survey_overview = SurveyOverview.objects.get(id=survey_overview_id)
        survey_overview.clean_status = status
        survey_overview.save()


@shared_task
def auto_update_escape_status():
    """转义状态更新"""
    qs = EscapeTask.objects.filter_active(escape_status=10)
    survey_overview_ids = []
    for obj in qs:
        # TODO 下面当4个数据需要从数据中心拿
        obj.end_time = datetime.now()
        obj.schedule = 0
        obj.escape_status = 0
        obj.save()
        survey_overview_ids += eval(obj.survey_overview_ids)
    survey_overview_ids = list(set(survey_overview_ids))
    for survey_overview_id in survey_overview_ids:
        escape_task_ids = SurveyOverviewEscapeTask.objects.filter_active(id=survey_overview_id).values_list('escape_task_id', flat=True)
        ids = qs.filter(id__in=list(escape_task_ids)).values_list('id', flat=True)
        # TODO min_status 从数据中心拿
        min_status = "拿到的最小状态值"
        survey_overview = SurveyOverview.objects.get(id=survey_overview_id)
        if min_status == 30:
            survey_overview.escape_status = 30
            survey_overview.save()


@shared_task
def auto_update_analysis_status():
    """转义状态更新"""
    qs = AnalysisTask.objects.filter_active(analysis_status=10)
    survey_overview_ids = []
    for obj in qs:
        # TODO 下面当4个数据需要从数据中心拿
        obj.end_time = datetime.now()
        obj.schedule = 0
        obj.analysis_status = 0
        obj.save()
        survey_overview_ids += eval(obj.survey_overview_ids)
    survey_overview_ids = list(set(survey_overview_ids))
    for survey_overview_id in survey_overview_ids:
        analysis_task_ids = SurveyOverviewAnalysisTask.objects.filter_active(id=survey_overview_id).values_list('analysis_task_id', flat=True)
        ids = qs.filter(id__in=list(analysis_task_ids)).values_list('id', flat=True)
        # TODO min_status 从数据中心拿
        min_status = "拿到的最小状态值"
        survey_overview = SurveyOverview.objects.get(id=survey_overview_id)
        if min_status == 30:
            survey_overview.escape_status = 30
            survey_overview.save()
