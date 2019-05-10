# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json
import os
import time

import datetime
from django.core.management import BaseCommand
from django.db import transaction

from assessment.models import AssessOrganization, AssessProject
from front.models import PeopleSurveyRelation, UserQuestionAnswerInfo, SurveyInfo, SurveyQuestionInfo
from front.serializers import PeopleSurveySerializer
from front.tasks import algorithm_task, get_report
from question.models import Question
from research.models import ResearchDimension, ResearchSubstandard, ResearchModel
from survey.models import SurveyQuestionRelation, Survey, SurveyQuestionResult
from utils import time_format
from utils.logger import info_logger
from wduser.models import People, PeopleOrganization, EnterpriseInfo, Organization


def utf8_more_info(more_info):
    mi = json.loads(more_info)
    nmi = []

    for o in mi:
        nmi.append({"key_name": o["key_name"], "key_value": o["key_value"]})
    return json.dumps(nmi, ensure_ascii=False)


def etl_people_info(project_id, survey_id, enterprise_info, t, limit_num=None):
    if not project_id:
        return
    ename = enterprise_info.cn_name
    eid = enterprise_info.id
    pids = PeopleSurveyRelation.objects.filter_active(
        project_id=project_id, status=20, model_score__gt=0).values_list("people_id", flat=True).distinct()
    if limit_num:
        pids = pids[:limit_num]
    pids = list(pids)
    people_info_list = []
    people_survey_info = []
    question_answer_info = []
    for pid in pids:
        pobj = People.objects.get(id=pid)
        org_codes = PeopleOrganization.objects.filter_active(people_id=pid).values_list("org_code",flat=True)
        orgid = 0
        if org_codes.exists():
            org_code = org_codes[0]
            org_ids = AssessOrganization.objects.filter_active(
                assess_id=project_id, organization_code=org_code).values_list("organization_id", flat=True)
            if org_ids.exists():
                orgid = org_ids[0]
        line = u"%s+%s+%s+%s+%s+%s+%s+%s+%s+%s+%s\r\n" % (
        pobj.id, pobj.username, eid, ename, orgid,
        pobj.get_info_value(u"性别", u"未知"),
        pobj.get_info_value(u"年龄", u"未知"),
        pobj.phone, pobj.email, utf8_more_info(pobj.more_info), t)
        people_info_list.append(line.encode("utf-8"))

        # 添加人员问卷信息到 people_survey_info
        people_surveys = PeopleSurveyRelation.objects.filter_active(
            survey_id=survey_id,
            project_id=project_id,
            people_id=pid
        )
        if people_surveys.exists():
            people_survey = people_surveys[0]
            result_info = etl_people_survey_result(people_survey, pid, project_id, survey_id, enterprise_info, orgid, t)
            if result_info:
                people_survey_info.append(result_info)
            survey_info_obj = SurveyInfo.objects.filter_active(survey_id=survey_id, project_id=project_id)[0]
            question_answer_info += etl_answer_question_info(people_survey, pid, project_id, survey_id, survey_info_obj, t)
    return people_info_list, people_survey_info, question_answer_info


def etl_people_survey_result(people_survey, pid, project_id, survey_id, enterprise_info, orgid, t):
    # 添加人员问卷信息到 people_survey_info
    if people_survey.begin_answer_time == None or people_survey.finish_time == None:
        people_survey_info = [
            people_survey.id,
            pid, survey_id, project_id, enterprise_info.id, orgid,
            people_survey.begin_answer_time, people_survey.finish_time,
            people_survey.model_score, people_survey.dimension_score,
            people_survey.substandard_score, people_survey.facet_score,
            people_survey.happy_score, people_survey.happy_ability_score,
            people_survey.happy_efficacy_score, people_survey.praise_score,
            people_survey.uniformity_score, t
        ]
    else:
        people_survey_info = [
            people_survey.id,
            pid, survey_id, project_id, enterprise_info.id, orgid,
            time_format(people_survey.begin_answer_time), time_format(people_survey.finish_time),
            people_survey.model_score, people_survey.dimension_score,
            people_survey.substandard_score, people_survey.facet_score,
            people_survey.happy_score, people_survey.happy_ability_score,
            people_survey.happy_efficacy_score, people_survey.praise_score,
            people_survey.uniformity_score, t
        ]

    print('tttt%s' % people_survey.begin_answer_time)

    return people_survey_info


def etl_answer_question_info(people_survey, pid, project_id, survey_id, survey_info_obj, t):
    # 获取问卷的所有题目
    question_info_qs = SurveyQuestionInfo.objects.filter_active(
        survey_id=survey_id, project_id=project_id)
    block_question_map = []
    if survey_info_obj.form_type == Survey.FORM_TYPE_FORCE:
        # 迫选组卷 title 栏字段
        question_info_obj = question_info_qs.filter(block_id=0)[0]
        question_info = json.loads(question_info_obj.question_info)
    else:
        if survey_info_obj.test_type == Survey.TEST_TYPE_BY_QUESTION:
            question_info_obj = question_info_qs.filter(block_id=0)[0]
            question_info = json.loads(question_info_obj.question_info)
        else:
            question_info = []
            for question_info_obj in question_info_qs:
                if question_info_obj.block_id == 0:
                    continue
                if question_info_obj.block_id not in block_question_map:
                    temp_question_info = json.loads(question_info_obj.question_info)
                    if temp_question_info:
                        question_info += temp_question_info
                        block_question_map.append(question_info_obj.block_id)
    # 遍历该问卷的所有题目
    question_answer_info = []
    for question in question_info:
        # 添加答题信息到 question_answer_info
        question_answer_list = UserQuestionAnswerInfo.objects.filter_active(
            people_id=pid,
            survey_id=survey_id,
            project_id=project_id,
            question_id=question["id"]
        ).order_by("-id")
        if question_answer_list.exists():
            if question["question_type"] in [
                Question.QUESTION_TYPE_SINGLE,
                Question.QUESTION_TYPE_SINGLE_FILLIN,
                Question.QUESTION_TYPE_SLIDE,
                Question.QUESTION_TYPE_NINE_SLIDE
            ]:
                question_answer = question_answer_list[0]
                question_answer_info.append([
                    question_answer.id, question_answer.question_id, people_survey.id,
                    question_answer.people_id, question_answer.survey_id, question_answer.project_id,
                    question_answer.order_num, question_answer.answer_id, question_answer.answer_score,
                    question_answer.answer_index, question_answer.answer_time, t
                ])
            elif question["question_type"] == Question.QUESTION_TYPE_MUTEXT:
                question_answers = question_answer_list[:2]
                for question_answer in question_answers:
                    question_answer_info.append([
                        question_answer.id, question_answer.question_id, people_survey.id,
                        question_answer.people_id, question_answer.survey_id, question_answer.project_id,
                        question_answer.order_num, question_answer.answer_id, question_answer.answer_score,
                        question_answer.answer_index, question_answer.answer_time, t
                    ])
            elif question["question_type"] == Question.QUESTION_TYPE_FORCE_ORDER_QUESTION:
                question_answers = question_answer_list[:5]
                for question_answer in question_answers:
                    question_answer_info.append([
                        question_answer.id, question_answer.question_id, people_survey.id,
                        question_answer.people_id, question_answer.survey_id, question_answer.project_id,
                        question_answer.order_num, question_answer.answer_id, question_answer.answer_score,
                        question_answer.answer_index, question_answer.answer_time, t
                    ])
            elif question["question_type"] in [Question.QUESTION_TYPE_MULTI, Question.QUESTION_TYPE_MULTI_FILLIN]:
                for question_answer in question_answer_list:
                    question_answer_info.append([
                        question_answer.id, question_answer.question_id, people_survey.id,
                        question_answer.people_id, question_answer.survey_id, question_answer.project_id,
                        question_answer.order_num, question_answer.answer_id, question_answer.answer_score,
                        question_answer.answer_index, question_answer.answer_time, t
                    ])
    return question_answer_info


def etl_company_info(enterpriseinfo, t):
    enterprise_info = []
    enterprise_info.append([
        enterpriseinfo.id, enterpriseinfo.cn_name, enterpriseinfo.en_name,
        enterpriseinfo.short_name, enterpriseinfo.linkman, enterpriseinfo.fax_number,
        enterpriseinfo.email, enterpriseinfo.remark, t
    ])
    return enterprise_info


def etl_survey_info(survey_info, survey_obj, model_id, project_id, t):
    # 添加问卷信息到 survey_info
    survey_info_list = [[
        survey_info.survey_id, model_id, project_id, survey_info.survey_name,
        survey_info.en_survey_name, survey_info.survey_type, survey_info.form_type,
        20, survey_info.survey_desc, survey_obj.use_count, t
    ]]
    return survey_info_list


def etl_project_info(assess, enterpriseinfo, t):
    # 添加项目信息到  assess_info
    assess_info = [[
        assess.id, assess.name, enterpriseinfo.id,
        time_format(assess.begin_time), time_format(assess.end_time), assess.assess_type,
        assess.user_count, t

    ]]
    return assess_info


def etl_org_info(project_id, t):
    org_ids = AssessOrganization.objects.filter_active(assess_id=project_id).values_list("organization_id", flat=True)
    organization_list = []
    for org_id in org_ids:
        organization_info = Organization.objects.get(id=org_id)
        organization_list.append([
            organization_info.id, organization_info.name, organization_info.enterprise_id,
            0,
            organization_info.parent_id, organization_info.identification_code, t
        ])
    return organization_list


def etl_model_info(research_model, project_id, survey_id, t):
    research_model_info = [[
        research_model.id, research_model.root_model_id, research_model.parent_model_id,
        survey_id, project_id, research_model.name, research_model.en_name,
        research_model.desc, research_model.model_type,
        research_model.algorithm_id, research_model.inherit_count,
        research_model.used_count, research_model.model_category, t
    ]]
    return research_model_info


def etl_dimension_substandard_info(research_model, project_id, survey_id, t):
    # 添加维度信息到 research_dimension_info
    research_dimension_info = []
    research_substandard_info = []
    research_dimension_list = ResearchDimension.objects.filter_active(model_id=research_model.id)
    for research_dimension in research_dimension_list:
        research_dimension_info.append([
            research_dimension.id, survey_id, project_id, research_dimension.model_id,
            research_dimension.name, research_dimension.en_name,
            research_dimension.weight,
            research_dimension.model_type, research_dimension.model_category, t
        ])
        # 添加指标信息到 research_substandard_info
        research_substandard_list = ResearchSubstandard.objects.filter_active(
            dimension_id=research_dimension.id)
        for research_substandard in research_substandard_list:
            research_substandard_info.append([
                research_substandard.id, survey_id, project_id, research_substandard.model_id,
                research_substandard.dimension_id, research_substandard.parent_id,
                research_substandard.name, research_substandard.en_name,
                research_substandard.weight,
                research_substandard.model_type, research_substandard.model_category, t
            ])
    return research_dimension_info, research_substandard_info


def etl_write_file(file_name, contents, t, timestamp):
    new_contents = []
    for content in contents:
        line = []
        for item in content:
            if type(item) == int or type(item) == long or type(item) == float:
                if type(item) == 'NoneType' or item == None:
                    item = ''
                line.append(str(item))
            else:
                line.append(item)

        line = ",".join('%s' % i for i in line)
        line += "\r\n"
        new_contents.append(line.encode("utf-8"))
    file_path = os.path.join("download", "etl", t, timestamp)
    if not os.path.exists(file_path):
        os.makedirs(file_path)
    file_full_path = os.path.join(file_path, file_name)
    with open(file_full_path, 'a+', ) as f:
            f.writelines(new_contents)


class Command(BaseCommand):
    help = "parse tag system excel"

    def add_arguments(self, parser):
        parser.add_argument("--project_id", dest="project_id", action="store", type=int,
                            help="project id that will be processed")
        parser.add_argument("--survey_id", dest="survey_id", action="store", type=int,
                            help="survey id that will be processed")
        parser.add_argument("--limit_num", dest="limit_num", action="store", type=int,
                            help="limit_num that will be processed")

    @transaction.atomic
    def handle(self, *args, **options):
        project_id = options.get("project_id", None)
        survey_id = options.get("survey_id", None)
        limit_num = options.get("limit_num", None)
        info_logger.info("ope etl process %s %s" % (project_id, survey_id))
        if not project_id:
            return
        t = datetime.datetime.now().strftime('%Y-%m-%d')
        timestamp = str(int(time.time()*1000))
        project_info = AssessProject.objects.get(id=project_id)
        survey_obj = Survey.objects.get(id=survey_id)
        survey_info = SurveyInfo.objects.filter_active(survey_id=survey_id, project_id=project_id)[0]
        enterprise_info = EnterpriseInfo.objects.get(id=project_info.enterprise_id)
        research_model = ResearchModel.objects.get(id=survey_obj.model_id)
        company_list = etl_company_info(enterprise_info, t)
        survey_list = etl_survey_info(survey_info, survey_obj, survey_obj.model_id, project_id, t)
        project_list = etl_project_info(project_info, enterprise_info, t)
        org_list = etl_org_info(project_id, t)
        model_list = etl_model_info(research_model, project_id, survey_id, t)
        dimension_list, substandard_list = etl_dimension_substandard_info(research_model, project_id, survey_id, t)
        people_info_list, people_result_list, people_answer_list = etl_people_info(project_id, survey_id, enterprise_info, t, limit_num)
        # etl_write_file("company.txt", company_list, t, timestamp)
        # etl_write_file("project_info.txt", project_list, t, timestamp)
        # etl_write_file("survey_info.txt", survey_list, t, timestamp)
        # etl_write_file("research_model_info.txt", model_list, t, timestamp)
        # etl_write_file("dimension_info.txt", dimension_list, t, timestamp)
        # etl_write_file("substandard_info.txt", substandard_list, t, timestamp)
        # etl_write_file("org.txt", org_list, t, timestamp)
        # etl_write_file("people_survey.txt", people_result_list, t, timestamp)
        etl_write_file("answer_info1383.txt", people_answer_list, t, timestamp)
