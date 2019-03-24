# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import random

from WeiDuAdmin import settings
from research.models import ResearchModel, ReportSurveyAssessmentProjectRelation, Report
from survey.models import Survey
from utils.rpc_service import HttpService


class ReportService(HttpService):
    HOST = settings.REPORT_HOST

    @classmethod
    def get_host(cls, enterprise_id=0):
        try:
            if enterprise_id == 25:
                host_length = len(settings.CUSTOM_HOSTS)
                return settings.CUSTOM_HOSTS[random.randint(0, host_length - 1)]
            else:
                host_length = len(settings.REPORT_HOSTS)
                return settings.REPORT_HOSTS[random.randint(0, host_length-1)]
        except:
            return settings.REPORT_HOST

    @classmethod
    def get_report_template_id(cls, survey_id, project_id):
        rsapr_id_qs = ReportSurveyAssessmentProjectRelation.objects.filter_active(survey_id=survey_id,
                                    assessment_project_id=project_id).values_list("report_id", flat=True)
        r_rti_ids = Report.objects.filter_active(id__in=rsapr_id_qs).values_list("report_type_id", flat=True)
        if r_rti_ids.count() == 0:
            # 兼容旧数据
            survey = Survey.objects.get(id=survey_id)
            model = ResearchModel.objects.get(id=survey.model_id)
            if model.algorithm_id == ResearchModel.ALGORITHM_GZJZG:
                return "WorkValueQuestionnaire", None
            elif model.algorithm_id == ResearchModel.ALGORITHM_DISC:
                # return "ProfessionalPpersonalit", None
                return "DISC_NEW", None
            elif model.algorithm_id == ResearchModel.ALGORITHM_XLZB:
                return "PsychologicalCapital", None
            elif model.algorithm_id == ResearchModel.ALGORITHM_XFZS:
                return "HAMeasurePersonal", "HAMeasurePersonal_EN"
            elif model.algorithm_id == ResearchModel.ALGORITHM_YGXLJK:
                return "EmployeeMentalHealth", "EmployeeMentalHealth_EN"
            elif model.algorithm_id == ResearchModel.ALGORITHM_XFXQ:
                return "HappinessNeeds", None
            #  领导风格
            # elif model.algorithm_id == ResearchModel.ALGORITHM_LDFG:
            #     return "LeaderStyle", None
            # 行为风格
            elif model.algorithm_id == ResearchModel.ALGORITHM_XWFG:
                return "BehavioralStyle", None
            # 职业定向
            elif model.algorithm_id == ResearchModel.ALGORITHM_ZYDX:
                return "ZYDX", None
            return None, None   # 默认不出报告
            # return "CapacityEvaluation", None
        else:
            zn_report_id = None
            en_report_id = None
            for report_id in r_rti_ids:
                if report_id.find("_EN") > -1:
                    en_report_id = report_id
                else:
                    zn_report_id = report_id
            return zn_report_id, en_report_id

    @classmethod
    def get_report(cls, data, enterprise_id=0):
        uri = "/report/user_get_specific_report/"
        rst = cls.do_request(uri, data, enterprise_id)
        return rst
