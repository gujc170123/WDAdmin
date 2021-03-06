# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import copy
import json

import datetime, time
from celery import shared_task

from assessment.models import AssessSurveyRelation, AssessProject, AssessProjectSurveyConfig, \
    AssessSurveyUserDistribute, AssessUser
from front.front_utils import SurveyAlgorithm
from front.models import SurveyQuestionInfo, UserSurveyBlockStatus, PeopleSurveyRelation, SurveyInfo
from question.models import Question
from question.serializers import QuestionDetailSerializer
from research.models import ResearchModel, ResearchDimension, ResearchSubstandard
from survey.models import Survey, SurveyQuestionResult, SurveyModelFacetRelation, SurveyQuestionRelation
from survey.serializers import SurveyForceQuestionResultSerializer
from utils.cache.config_cache import ConfigCache
from utils.logger import get_logger
from utils.rpc_service.report_service import ReportService
from utils.response import ErrorCode
from wduser.models import People

logger = get_logger("front")


def check_survey_open(people_id, project_id, surveyid, role_type, evaluated_people_id, check_page=None):
    project = AssessProject.objects.get(id=project_id)
    rst_info = {}
    if project.is_answer_survey_by_order:
        survey_ids = PeopleSurveyRelation.objects.filter_active(
            people_id=people_id, project_id=project_id
        ).values_list("survey_id", flat=True)
        survey_ids = AssessSurveyRelation.objects.filter_active(
            assess_id=project_id, survey_id__in=list(survey_ids)
        ).values_list("survey_id", flat=True).order_by('order_number')
        for survey_id in survey_ids:
            if survey_id == long(surveyid):
                break
            if not PeopleSurveyRelation.objects.filter_active(
                    people_id=people_id,
                    survey_id=survey_id,
                    project_id=project_id,
                    role_type=role_type,
                    evaluated_people_id=evaluated_people_id,
                    status__in=[PeopleSurveyRelation.STATUS_FINISH, PeopleSurveyRelation.STATUS_EXPIRED]
            ).exists():
                try:
                    survey_info = SurveyInfo.objects.filter_active(survey_id=survey_id, project_id=project_id)[0]
                    survey_name = survey_info.survey_name
                except:
                    survey = Survey.objects.get(id=survey_id)
                    survey_name = survey.title
                return ErrorCode.USER_ANSWER_SURVEY_ORDER_ERROR, {"survey_name": survey_name}

    try:
        relation_qs = PeopleSurveyRelation.objects.filter_active(
            people_id=people_id,
            survey_id=surveyid,
            project_id=project_id,
            role_type=role_type,
            evaluated_people_id=evaluated_people_id
        )
        if relation_qs.exists():
            relation_obj = relation_qs[0]
            survey_info_qs = SurveyInfo.objects.filter_active(
                survey_id=surveyid, project_id=project_id)
            if survey_info_qs.exists():
                survey_info = survey_info_qs[0]
                now = datetime.datetime.now()
                if survey_info.time_limit:
                    if not relation_obj.begin_answer_time:
                        rst_info["time_limit"] = survey_info.time_limit
                    else:
                        if relation_obj.begin_answer_time + datetime.timedelta(minutes=int(survey_info.time_limit)) < now:
                            time_limit = -1
                        else:
                            time_limit = survey_info.time_limit - ((now - relation_obj.begin_answer_time).seconds) / 60
                        rst_info["time_limit"] = time_limit
                if not relation_obj.begin_answer_time and check_page == "question_list_page":
                    relation_obj.begin_answer_time = now
                    relation_obj.save()
    except:
        pass

    return ErrorCode.SUCCESS, rst_info


def survey_sync(survey_id, project_id):
    # 项目与问卷
    try:
        survey = Survey.objects.get(id=survey_id)
    except:
        logger.error("survey id is not found: %s" % survey_id)
        return None
    assess_survey_qs = AssessSurveyRelation.objects.filter_active(
        assess_id=project_id, survey_id=survey_id)
    if not assess_survey_qs.exists():
        logger.error("project(%s) survey id(%s) is not found" % (project_id, survey_id))
        return None
    assess_survey_obj = assess_survey_qs[0]
    try:
        assess_project = AssessProject.objects.get(id=project_id)
        project_name = assess_project.name
        en_project_name = assess_project.en_name
        project_type = assess_project.assess_type
    except:
        project_name = ""
        en_project_name = ""
        project_type = AssessProject.TYPE_ORGANIZATION
    model = ResearchModel.objects.get(id=survey.model_id)
    rd_qs = list(ResearchDimension.objects.filter_active(model_id=model.id).order_by("order_number").values("desc", "id", "name", "en_name", "en_desc", "order_number"))
    assess_project_config_qs = AssessProjectSurveyConfig.objects.filter_active(
        assess_id=project_id, survey_id=survey_id,
        model_type=AssessProjectSurveyConfig.MODEL_TYPE_DIMENSION).values("model_id", "content", "en_content")
    assess_project_desc_config_qs = AssessProjectSurveyConfig.objects.filter_active(
        assess_id=project_id, survey_id=survey_id,
        model_type=AssessProjectSurveyConfig.MODEL_TYPE_DIMENSION_DESC).values("model_id", "content", "en_content")

    # config_block_info = {}
    # for config_info in assess_project_config_qs:
    #     config_block_info[config_info["model_id"]] = config_info["content"]
    # config_block_desc_info = {}
    # for config_info in assess_project_desc_config_qs:
    #     config_block_desc_info[config_info["model_id"]] = config_info["content"]

    config_block_info = {}
    for config_info in assess_project_config_qs:
        config_block_info[config_info["model_id"]] = {"content": config_info["content"], "en_content": config_info["en_content"]}
    config_block_desc_info = {}
    for config_info in assess_project_desc_config_qs:
        config_block_desc_info[config_info["model_id"]] = {"content": config_info["content"], "en_content": config_info["en_content"]}

    # for block in rd_qs:
    #     if block["id"] in config_block_info:
    #         block["name"] = config_block_info[block["id"]]
    #     if block["id"] in config_block_desc_info:
    #         block["desc"] = config_block_desc_info[block["id"]]
    for block in rd_qs:
        if block["id"] in config_block_info:
            block["name"] = config_block_info[block["id"]]["content"]
            block["en_name"] = config_block_info[block["id"]]["en_content"]
        if block["id"] in config_block_desc_info:
            block["desc"] = config_block_desc_info[block["id"]]["content"]
            block["en_desc"] = config_block_desc_info[block["id"]]["en_content"]
    config_info = survey.config_info
    set_config_info = copy.deepcopy(SurveyInfo.DEFAULT_CONFIG)
    if config_info:
        config_info = json.loads(config_info)
        for key in set_config_info:
            if key in config_info:
                set_config_info[key] = config_info[key]
    else:
        pass
    set_config_info["assess_logo"] = assess_survey_obj.assess_logo

    survey_info_qs = SurveyInfo.objects.filter_active(survey_id=survey_id, project_id=project_id)
    # 更新或创建 问卷信息
    if assess_survey_obj.custom_config:    #  10.9 ，360问卷json.loads(None)
        config = json.loads(assess_survey_obj.custom_config)
    else:
        config = None
    if config:
        survey_name = config.get("survey_name", None)
        en_survey_name = config.get("en_survey_name", None)
        if not survey_name:
            survey_name = survey.title
            en_survey_name = survey.en_title
    else:
        survey_name = survey.title
        en_survey_name = survey.en_title
    if survey_info_qs.exists():
        survey_info_obj = survey_info_qs[0]
        survey_info_qs.update(
            survey_name=survey_name,
            en_survey_name=en_survey_name,
            survey_desc=survey.desc,
            en_survey_desc=survey.en_desc,
            begin_time=assess_survey_obj.begin_time,
            end_time=assess_survey_obj.end_time,
            project_name=project_name,
            survey_type=survey.survey_type,
            en_project_name=en_project_name,
            project_type=project_type,
            config_info=json.dumps(set_config_info),
            block_info=json.dumps(rd_qs),
            form_type=survey.form_type,
            time_limit=survey.time_limit
        )
    else:
        survey_info_obj = SurveyInfo.objects.create(
            survey_id=survey_id,
            project_id=project_id,
            survey_name=survey_name,
            en_survey_name=en_survey_name,
            survey_desc=survey.desc,
            en_survey_desc=survey.en_desc,
            begin_time=assess_survey_obj.begin_time,
            end_time=assess_survey_obj.end_time,
            project_name=project_name,
            en_project_name=en_project_name,
            survey_type=survey.survey_type,
            project_type=project_type,
            config_info=json.dumps(set_config_info),
            block_info=json.dumps(rd_qs),
            form_type=survey.form_type,
            time_limit=survey.time_limit
        )
    return survey_info_obj


@shared_task
def survey_question_sync(survey_id, project_id, block_id):
    logger.debug("survey_question_sync: %s, %s, %s" % (survey_id, project_id, block_id))
    survey_qs = SurveyInfo.objects.filter_active(survey_id=survey_id, project_id=project_id)
    src_survey = Survey.objects.get(id=survey_id)
    if not survey_qs.exists():
        return []
    else:
        survey = survey_qs[0]
    if survey.form_type == Survey.FORM_TYPE_FORCE:
        logger.debug("survey_question_sync of force survey")
        # 迫选题
        sqr_qs = SurveyQuestionResult.objects.filter_active(
            survey_id=survey_id).order_by('order_num')
        question_data = SurveyForceQuestionResultSerializer(instance=sqr_qs, many=True).data
        survey_question_info_qs = SurveyQuestionInfo.objects.filter_active(
            survey_id=survey_id, project_id=project_id, block_id=block_id)
        if survey_question_info_qs.exists():
            survey_question_info = survey_question_info_qs[0]
            survey_question_info.question_info = json.dumps(question_data)
            survey_question_info.config_info = survey.config_info
            survey_question_info.save()
        else:
            survey_question_info = SurveyQuestionInfo.objects.create(
                survey_id=survey_id, project_id=project_id, question_info=json.dumps(question_data),
                config_info=survey.config_info, block_id=block_id
            )
        return survey_question_info
    else:
        # 普通组卷
        logger.debug("survey_question_sync of normal survey")
        if survey.test_type == Survey.TEST_TYPE_BY_QUESTION:
            # 逐题测试
            logger.debug("survey_question_sync, test_type == TEST_TYPE_BY_QUESTION")
            sqr_qs = list(SurveyQuestionResult.objects.filter_active(
                survey_id=survey_id).order_by('order_num').values_list("question_id", flat=True))
            qs = Question.objects.filter_active(id__in=sqr_qs)
            ordering = 'FIELD(`id`, %s)' % ','.join(str(qid) for qid in sqr_qs)
            questions = qs.extra(select={'ordering': ordering}, order_by=('ordering',))
            question_data = QuestionDetailSerializer(
                instance=questions, many=True,
                context={"with_tags": False, "is_test": True, "survey_id": survey_id, "assess_id": project_id}
            ).data
            survey_question_info_qs = SurveyQuestionInfo.objects.filter_active(
                survey_id=survey_id, project_id=project_id, block_id=block_id)
            if survey_question_info_qs.exists():
                survey_question_info = survey_question_info_qs[0]
                survey_question_info.question_info = json.dumps(question_data)
                survey_question_info.config_info = survey.config_info
                survey_question_info.save()
            else:
                survey_question_info = SurveyQuestionInfo.objects.create(
                    survey_id=survey_id, project_id=project_id, question_info=json.dumps(question_data),
                    config_info=survey.config_info, block_id=block_id
                )
            return survey_question_info
        else:
            # 分块测试
            # 所有维度
            logger.debug("survey_question_sync, test_type == TEST_TYPE_BY_PART")
            # rd_qs = ResearchDimension.objects.filter(model_id=survey.model_id)
            dimension = ResearchDimension.objects.get(id=block_id)
            #for dimension in rd_qs:
            # 每个维度/块 关联的题目
            relation_ids = list(SurveyModelFacetRelation.objects.filter_active(
                survey_id=survey_id, model_id=src_survey.model_id,
                related_obj_type=SurveyModelFacetRelation.RELATED_DIMENSION,
                related_obj_id=dimension.id
            ).values_list("id", flat=True))
            substandards = ResearchSubstandard.objects.filter_active(
                dimension_id=dimension.id).values_list("id", flat=True)
            relation_ids += list(SurveyModelFacetRelation.objects.filter_active(
                survey_id=survey_id, model_id=src_survey.model_id, related_obj_type=SurveyModelFacetRelation.RELATED_SUBSTANDARD,
                related_obj_id__in=list(substandards)
            ).values_list("id", flat=True))
            # 找到问卷关联的所有题目， 选项上线会有重复的question_id
            q_ids = list(SurveyQuestionRelation.objects.filter_active(
                survey_id=survey_id, model_facet_relation_id__in=relation_ids).values_list("question_id", flat=True))
            sqr_qs = list(SurveyQuestionResult.objects.filter_active(
                survey_id=survey_id, question_id__in=q_ids).order_by('order_num').values_list("question_id", flat=True))
            qs = Question.objects.filter_active(id__in=sqr_qs)
            ordering = 'FIELD(`id`, %s)' % ','.join(str(qid) for qid in sqr_qs)
            questions = qs.extra(select={'ordering': ordering}, order_by=('ordering',))
            question_data = QuestionDetailSerializer(
                instance=questions, many=True,
                context={"with_tags": False, "is_test": True, "survey_id": survey_id, "assess_id": project_id}).data
            survey_question_info_qs = SurveyQuestionInfo.objects.filter_active(
                survey_id=survey_id, project_id=project_id, block_id=block_id)
            if survey_question_info_qs.exists():
                survey_question_info = survey_question_info_qs[0]
                survey_question_info.question_info = json.dumps(question_data)
                survey_question_info.config_info = survey.config_info
                survey_question_info.save()
            else:
                survey_question_info = SurveyQuestionInfo.objects.create(
                    survey_id=survey_id, project_id=project_id, question_info=json.dumps(question_data),
                    config_info=survey.config_info, block_id=block_id
                )
            return survey_question_info


@shared_task
def user_get_survey_ops(people_id, survey_id, project_id, block_id,
                        role_type=PeopleSurveyRelation.ROLE_TYPE_NORMAL, evaluated_people_id=0):
    u"""获取问卷题目的时候：
    1. 更新块或问卷的已读状态
    2. 更新问卷的状态为进行中（统计用）
    """
    people_block_qs = UserSurveyBlockStatus.objects.filter_active(
        people_id=people_id,
        survey_id=survey_id,
        project_id=project_id,
        block_id=block_id,
        role_type=role_type,
        evaluated_people_id=evaluated_people_id
    )
    people_survey_rel = PeopleSurveyRelation.objects.filter_active(
        people_id=people_id,
        survey_id=survey_id,
        project_id=project_id,
        role_type=role_type,
        evaluated_people_id=evaluated_people_id
    )
    if people_block_qs.exists():
        people_block = people_block_qs[0]
        if people_block.status != UserSurveyBlockStatus.STATUS_READ:
            people_block.status = UserSurveyBlockStatus.STATUS_READ
            people_block.save()

    else:
        UserSurveyBlockStatus.objects.create(
            people_id=people_id,
            survey_id=survey_id,
            project_id=project_id,
            block_id=block_id,
            role_type=role_type,
            evaluated_people_id=evaluated_people_id,
            status=UserSurveyBlockStatus.STATUS_READ
        )
    if people_survey_rel.exists():
        people_survey = people_survey_rel[0]
        is_modify = False
        if people_survey.status == PeopleSurveyRelation.STATUS_NOT_BEGIN:
            people_survey.status = PeopleSurveyRelation.STATUS_DOING
            is_modify = True
        # if not people_survey.begin_answer_time:
        #     people_survey.begin_answer_time = datetime.datetime.now()
        #     is_modify = True
        if is_modify:
            people_survey.save()


@shared_task
def check_report_beat():
    from front.serializers import PeopleSurveySerializer
    now = datetime.datetime.now()
    one_hour_finish = now - datetime.timedelta(hours=1)
    qs = PeopleSurveyRelation.objects.filter_active(
        status=PeopleSurveyRelation.STATUS_FINISH,
        report_status=PeopleSurveyRelation.REPORT_GENERATING,
        finish_time__lt=one_hour_finish
    ).order_by("-finish_time")[:100]
    count = qs.count()
    page_size = 10
    page_count = count / page_size + 1
    qs_data = PeopleSurveySerializer(instance=qs, many=True).data
    logger.debug("check_report_beat count is %s" % count)
    for page_index in range(page_count):
        try:
            logger.debug("check_report_beat process page index of %s" % page_index)
            page_qs = qs_data[page_index*page_size:(page_index+1)*page_size]
            report_request_data = {"results": page_qs}
            get_report(report_request_data, force_recreate=True)
        except Exception, e:
            logger.error("check_report_beat error, page_index: %s, msg: %s" %(page_index, e))
        time.sleep(60)


@shared_task
def get_report(detail, user_id=0, force_recreate=False, language=SurveyAlgorithm.LANGUAGE_ZH):
    report_request_data = []
    enterprise_id = 0
    psr_id = 0
    is_360 = False
    for data in detail["results"]:


        if not psr_id:
            psr_id = data["id"]
            psr_obj = PeopleSurveyRelation.objects.get(id=psr_id)
            pro_obj = AssessProject.objects.get(id=psr_obj.project_id)
            if pro_obj.assess_type == AssessProject.TYPE_360:
                is_360 = True
                force_recreate = True
        # if is_360:
        #     # 如果自评， ok, 如果他评，检查是否完成。
        #     people_survey_result = PeopleSurveyRelation.objects.get(id=data["id"])
        #     survey = Survey.objects.get(id=people_survey_result.survey_id)
        #     research_model = ResearchModel.objects.get(id=survey.model_id)
        #     if research_model.algorithm_id == ResearchModel.ALGORITHM_ZGC180:
        #         evaluated_people_id = people_survey_result.evaluated_people_id
        #         if PeopleSurveyRelation.objects.filter_active(evaluated_people_id=evaluated_people_id, survey_id=survey.id,
        #                                                    project_id=people_survey_result.project_id, status__in=[PeopleSurveyRelation.STATUS_DOING_PART, PeopleSurveyRelation.STATUS_DOING, PeopleSurveyRelation.STATUS_NOT_BEGIN]).exists():
        #             # 中高层的报告， 这个地方是， 某人的所有他评未完成
        #             continue
        #         else:
        #             report_request_data = []
        #             people_result_id = \
        #                 PeopleSurveyRelation.objects.filter_active(evaluated_people_id=evaluated_people_id,
        #                                                            project_id=people_survey_result.project_id,
        #                                                            people_id=evaluated_people_id)[0].id
        #             report_request_data.append(
        #                 {
        #                     "report_type_id": "ZGC180",
        #                     "people_result_id": people_result_id,
        #                     "force_recreate": force_recreate
        #                 }
        #             )
        #             # 给这个被评价人， 但是他只有自评发一个请求 中高层180的， 但是会覆盖自评的报告。
        #             report_result = ReportService.get_report(report_request_data)
        #             continue
        # 不判断是否是自评， 他评， 在获取报告数据的地方判断。他评的话， 重定义获取改数据的被评价者
        # if data["report_status"] != PeopleSurveyRelation.REPORT_SUCCESS or force_recreate:
        survey_info = data["survey_info"]
        cn_report_id, en_report_id = ReportService.get_report_template_id(survey_info["survey_id"], survey_info["project_id"])
        # 加快 ProfessionalPpersonalit， WorkValueQuestionnaire 的处理
        report_filter = ConfigCache().get_config_report_filter()
        if report_filter and cn_report_id not in report_filter:
            continue
        project_id = data["project_id"]
        if not enterprise_id:
            enterprise_id = AssessProject.objects.get(id=project_id).enterprise_id
        if language in [SurveyAlgorithm.LANGUAGE_ZH, SurveyAlgorithm.LANGUAGE_ALL] and cn_report_id:
            if data["report_status"] != PeopleSurveyRelation.REPORT_SUCCESS or force_recreate or not data["report_url"]:
                logger.debug("[report request] people_result_id: %s, cn_report_id: %s, force_recreate: %s" %(data["id"], cn_report_id, force_recreate))

                report_request_data.append(
                    {
                        "report_type_id": cn_report_id,
                        "people_result_id": data["id"],
                        "force_recreate": force_recreate
                    }
                )
        if language in [SurveyAlgorithm.LANGUAGE_EN, SurveyAlgorithm.LANGUAGE_ALL] and en_report_id:
            if data["report_status"] != PeopleSurveyRelation.REPORT_SUCCESS or force_recreate or not data["en_report_url"]:
                logger.debug("[report request] people_result_id: %s, en_report_id: %s, force_recreate: %s" % (data["id"], en_report_id, force_recreate))
                report_request_data.append(
                    {
                        "report_type_id": en_report_id,
                        "people_result_id": data["id"],
                        "force_recreate": force_recreate
                    }
                )
    if not report_request_data:
        return
    report_result = None
    try:
        report_result = ReportService.get_report(report_request_data, enterprise_id)
        report_info = report_result["detail"]
        for index, data in enumerate(report_request_data):
            if int(report_info[str(index)]["status"]) == 1:
                report_result = PeopleSurveyRelation.objects.get(id=data["people_result_id"])
                if "url" in report_info[str(index)] and report_info[str(index)]["url"]:
                    report_result.report_url = report_info[str(index)]["url"]
                if "en_url" in report_info[str(index)] and report_info[str(index)]["en_url"]:
                    report_result.en_report_url = report_info[str(index)]["en_url"]
                report_result.report_status = PeopleSurveyRelation.REPORT_SUCCESS
                report_result.save()
            elif int(report_info[str(index)]["status"]) == 2:
                report_result = PeopleSurveyRelation.objects.get(id=data["people_result_id"])
                if report_result != PeopleSurveyRelation.REPORT_FAILED and report_result != PeopleSurveyRelation.REPORT_SUCCESS:
                    report_result.report_status = PeopleSurveyRelation.REPORT_FAILED
                    report_result.save()
    except Exception, e:
        logger.error("report create error: msg: %s, report data is %s" % (e, report_result))


@shared_task
def algorithm_task(people_survey_result_id, create_report=True, force_recreate=False):
    from front.serializers import PeopleSurveySerializer
    people_survey_result = PeopleSurveyRelation.objects.get(id=people_survey_result_id)
    survey = Survey.objects.get(id=people_survey_result.survey_id)
    model = ResearchModel.objects.get(id=survey.model_id)
    algorithm_id = model.algorithm_id
    if algorithm_id == ResearchModel.ALGORITHM_WEIGHTED:
        SurveyAlgorithm.algorithm_average_weight(people_survey_result_id, form_type=survey.form_type)
    elif algorithm_id == ResearchModel.ALGORITHM_GZJZG:
        SurveyAlgorithm.algorithm_gzjzg(people_survey_result_id)
    elif algorithm_id == ResearchModel.ALGORITHM_RGFX:
        SurveyAlgorithm.algorithm_rgfx(people_survey_result_id)
    elif algorithm_id == ResearchModel.ALGORITHM_SWQN:
        SurveyAlgorithm.algorithm_swqn(people_survey_result_id)
    elif algorithm_id == ResearchModel.ALGORITHM_DISC:
        SurveyAlgorithm.algorithm_disc(people_survey_result_id)
    elif algorithm_id == ResearchModel.ALGORITHM_XLZB:
        SurveyAlgorithm.algorithm_xlzb(people_survey_result_id)
    elif algorithm_id == ResearchModel.ALGORITHM_XFZS:
        SurveyAlgorithm.algorithm_xfzs(people_survey_result_id)
    elif algorithm_id == ResearchModel.ALGORITHM_YGXLJK:
        SurveyAlgorithm.algorithm_xljk(people_survey_result_id)
    elif algorithm_id == ResearchModel.ALGORITHM_XFZS_EN:
        SurveyAlgorithm.algorithm_xfzs_en(people_survey_result_id)
    elif algorithm_id == ResearchModel.ALGORITHM_YGXLJK_EN:
        SurveyAlgorithm.algorithm_xljk_en(people_survey_result_id)
    elif algorithm_id == ResearchModel.ALGORITHM_XFXQ:
        SurveyAlgorithm.algorithm_xfxq(people_survey_result_id)
    else:
        SurveyAlgorithm.algorithm_average_weight(people_survey_result_id, form_type=survey.form_type)
    if create_report:
        get_report.delay({"results": [
            PeopleSurveySerializer(instance=people_survey_result).data
        ]}, force_recreate=force_recreate, language=SurveyAlgorithm.LANGUAGE_ALL)


@shared_task
def auto_submit_of_time_limit():
    pass
    # begin_time = datetime.datetime.now()
    # end_time = datetime.datetime.now() - datetime.timedelta(hours=2)  # 项目截止再宽松2个小时
    # project_qs = AssessProject.objects.filter_active(begin_time__lt=begin_time, end_time__gt=end_time).values_list("id", flat=True)
    # survey_qs = Survey.objects.filter_active(survey_status=Survey.SURVEY_STATUS_RELEASE, time_limit__gt=0).values_list("id", flat=True)
    # limit_qs = AssessSurveyRelation.objects.filter_active(assess_id__in=project_qs, survey_id__in=survey_qs).order_by("assess_id", "survey_id")
    # now = datetime.datetime.now() - datetime.timedelta(minutes=5)  # 5分钟宽松时间
    # for limit_relation in limit_qs:
    #     survey = Survey.objects.get(id=limit_relation.survey_id)
    #     time_limit = survey.time_limit
    #     people_result_qs = PeopleSurveyRelation.objects.filter_active(
    #         survey_id=limit_relation.survey_id,
    #         project_id=limit_relation.assess_id,
    #         status=PeopleSurveyRelation.STATUS_DOING_PART
    #     )
    #     for people_result in people_result_qs:
    #         used_time = now - people_result.begin_answer_time
    #         if used_time > time_limit and people_result.status != PeopleSurveyRelation.STATUS_FINISH:
    #             # 超时
    #             logger.debug("EXPIRED: set people_result %s to STATUS_FINISH" % people_result.id)
    #             people_result.status = PeopleSurveyRelation.STATUS_FINISH
    #             people_result.finish_time = now
    #             people_result.is_overtime = True
    #             people_result.save()
    #             algorithm_task.delay(people_result.id)
    # time.sleep(60*5)
    # auto_submit_of_time_limit.delay()

auto_submit_of_time_limit.delay()


def send_one_user_survey(assess_id, people_id):
    people = People.objects.get(id=people_id)
    project = AssessProject.objects.get(id=assess_id)
    all_survey_ids = AssessSurveyRelation.objects.filter_active(assess_id=project.id).values_list(
        "survey_id", flat=True).order_by("-order_number")
    logger.debug("add people(%s) to survey(%s)" % (people_id, all_survey_ids))
    survey_ids = AssessSurveyRelation.objects.filter_active(
        assess_id=project.id, survey_been_random=False).values_list("survey_id", flat=True)
    random_survey_ids = AssessSurveyRelation.objects.filter_active(
        assess_id=project.id, survey_been_random=True).values_list("survey_id", flat=True)
    status = PeopleSurveyRelation.STATUS_NOT_BEGIN
    # 刚发卷子统一为未开始
    if project.project_status == AssessProject.STATUS_WORKING:
        status = PeopleSurveyRelation.STATUS_DOING
    # 如果项目有随机的话
    has_random_survey_ids, random_index = [], 0
    if random_survey_ids:
        # 检查在随机问卷中是不是有这个人做过的问卷，如果有，则不计
        random_num = project.survey_random_number
        if random_num is None:
            random_num = 0
        if len(random_survey_ids) < random_num:
            random_num = len(random_survey_ids)
        if random_num > 0:
            random_index = project.survey_random_index  # 随机标志位
            polling_list = list(random_survey_ids)

            def polling_survey(random_num, random_index, polling_list):
                y = random_num * random_index % len(polling_list)
                his_survey_list = polling_list[y:y + random_num]
                if y + random_num > len(polling_list):
                    his_survey_list += polling_list[0: (random_num - (len(polling_list) - y))]
                return his_survey_list, random_index + 1

            def check_survey_if_has_distributed(assess_id, survey_id):
                distribute_users = AssessSurveyUserDistribute.objects.filter_active(
                    assess_id=assess_id, survey_id=survey_id
                )
                if distribute_users.exists():
                    distribute_user_ids = json.loads(
                        distribute_users.values_list("people_ids", flat=True)[0])
                else:
                    # 否则就是空
                    distribute_user_ids = []
                return distribute_user_ids, distribute_users

            def get_random_survey_distribute_info(assess_id, random_survey_ids):
                random_survey_total_ids = []
                for random_survey_id in random_survey_ids:
                    distribute_user_ids, distribute_users = check_survey_if_has_distributed(assess_id,
                                                                                            random_survey_id)
                    if distribute_user_ids:
                        random_survey_total_ids.extend(distribute_user_ids)
                return random_survey_total_ids

            random_distribute_ids = get_random_survey_distribute_info(assess_id, polling_list)
            if people.id not in random_distribute_ids:
                has_random_survey_ids, random_index = polling_survey(random_num, random_index, polling_list)
                project.survey_random_index = random_index  # 随机标志位
                project.save()

    if random_survey_ids:
        random_survey_ids, random_index = has_random_survey_ids, random_index
        logger.info('suiji wenjuan %s' % random_survey_ids)
    else:
        random_survey_ids, random_index = [], random_index
    if survey_ids:
        logger.info('normal wenjuan %s' % survey_ids)
    else:
        survey_ids = []
    person_survey_ids_list = []
    for i in all_survey_ids:
        if (i in random_survey_ids) or (i in survey_ids):
            person_survey_ids_list.append(i)
    logger.info('finish ids %s' % person_survey_ids_list)

    def distribute_one_people_survey(survey_ids, people_id, assess_id, status):
        # 只有不随机问卷需要判断有没有发过
        people_survey_list = []
        for survey_id in survey_ids:
            survey_qs = Survey.objects.filter_active(id=survey_id)
            if survey_qs.count() == 1:
                survey = survey_qs[0]
            else:
                logger.error("survey_id %d filter ERROR" % survey_id)
                continue
            asud_qs = AssessSurveyUserDistribute.objects.filter_active(assess_id=assess_id,
                                                                       survey_id=survey_id)
            if asud_qs.exists():
                asud_obj = asud_qs[0]
                distribute_users = json.loads(asud_obj.people_ids)
            else:
                asud_obj = AssessSurveyUserDistribute.objects.create(assess_id=assess_id,
                                                                     survey_id=survey_id,
                                                                     people_ids=json.dumps([]))
                distribute_users = json.loads(asud_obj.people_ids)
            if True:
                if people_id not in distribute_users:
                    people_survey_list.append(PeopleSurveyRelation(
                        people_id=people_id,
                        survey_id=survey_id,
                        project_id=assess_id,
                        survey_name=survey.title,
                        status=status
                    ))
                    distribute_users.append(people_id)
                    asud_obj.people_ids = json.dumps(distribute_users)
                    asud_obj.save()
        PeopleSurveyRelation.objects.bulk_create(people_survey_list)
        return None

    distribute_one_people_survey(person_survey_ids_list, people.id, assess_id, status)
    AssessUser.objects.get_or_create(
        assess_id=assess_id, people_id=people.id
    )


# 360 自评他评的异步任务：
@shared_task
def get_360_report(enterprise_id):
    logger.info("get_360_report")
    ap_qs = AssessProject.objects.filter_active(assess_type=AssessProject.TYPE_360, enterprise_id=enterprise_id)
    for ap_obj in ap_qs:
        need = False
        if PeopleSurveyRelation.objects.filter_active(project_id=ap_obj.id,
                                                      status__in=[PeopleSurveyRelation.STATUS_NOT_BEGIN,
                                                                  PeopleSurveyRelation.STATUS_DOING,
                                                                  PeopleSurveyRelation.STATUS_DOING_PART]).exists():
            pass
        else:
            need = True
            # auto_get_360_report.delay(assess_id=ap_obj.id)
        if ap_obj.project_status > AssessProject.STATUS_WORKING:
            need = True
            # 处理掉一些不用统计的
        if need:
            logger.info("auto_get_360_report assess_id=%s" % ap_obj.id)
            auto_get_360_report.delay(assess_id=ap_obj.id)


@shared_task
def auto_get_360_report(assess_id=0):
    def somebody_need_report(people_result_id, cn_report_id, en_report_id, force_recreate=False):
        report_request_data = []
        if cn_report_id:
            report_request_data.append(
                    {
                        "report_type_id": "ZGC180",
                        "people_result_id": people_result_id,
                        "force_recreate": force_recreate
                    }
                )
        if en_report_id:
            report_request_data.append(
                {
                    "report_type_id": en_report_id,
                    "people_result_id": people_result_id,
                    "force_recreate": force_recreate
                    }
                )
        if not report_request_data:
            return
        report_result = None
        try:
            report_result = ReportService.get_report(report_request_data)
            report_info = report_result["detail"]
            for index, data in enumerate(report_request_data):
                if int(report_info[str(index)]["status"]) == 1:
                    report_result = PeopleSurveyRelation.objects.get(id=data["people_result_id"])
                    if "url" in report_info[str(index)] and report_info[str(index)]["url"]:
                        logger.info("peoplesurveyrelation {} has new report {}".format(people_result_id, report_info[str(index)]["url"]))
                        report_result.report_url = report_info[str(index)]["url"]
                    if "en_url" in report_info[str(index)] and report_info[str(index)]["en_url"]:
                        report_result.en_report_url = report_info[str(index)]["en_url"]
                    report_result.report_status = PeopleSurveyRelation.REPORT_SUCCESS
                    report_result.save()
                elif int(report_info[str(index)]["status"]) == 2:
                    report_result = PeopleSurveyRelation.objects.get(id=data["people_result_id"])
                    if report_result != PeopleSurveyRelation.REPORT_FAILED and report_result != PeopleSurveyRelation.REPORT_SUCCESS:
                        report_result.report_status = PeopleSurveyRelation.REPORT_FAILED
                        report_result.save()
        except Exception, e:
            logger.error("report create error: msg: %s, report data is %s" % (e, report_result))
        pass

    # 需要生产报告的项目
    logger.info("auto_get_360_report assess_id=%s" % assess_id)
    if not assess_id:
        return
    psr_qs = PeopleSurveyRelation.objects.filter_active(project_id=assess_id, status=PeopleSurveyRelation.STATUS_FINISH)
    # 有哪些被评价人
    evaluated_people_ids = list(psr_qs.values_list("evaluated_people_id", flat=True).distinct())
    # 暂时没有 一个人只有他评，没有自评的情况
    # 这些人需要出报告：
    need_psr_qs = psr_qs.filter(people_id__in=evaluated_people_ids)
    for need_obj in need_psr_qs:
        if need_obj.report_url:
            # 已经有报告的人不需要出报告
            pass
        else:
            survey_id = need_obj.survey_id
            zn_report_id, en_report_id = ReportService.get_report_template_id(survey_id, assess_id)
            # if zn_report_id == "ZGC90":
                # 自评改成了做完就出
                # continue
            somebody_need_report(need_obj.id, zn_report_id, en_report_id)