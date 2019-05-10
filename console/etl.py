# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import datetime

from console.models import CleanTask, SurveyOverview
from console.tasks import etl_start
# rom console.ssh_linux import con_linux
from utils.cache.cache_utils import NormalHashSet
from survey.models import Survey, SurveyQuestionRelation
from front.models import PeopleSurveyRelation, UserQuestionAnswerInfo
from utils.logger import debug_logger
from wduser.models import People,Organization
from assessment.models import AssessProject


class EtlBase(object):
    u"""ETL基类"""
    STATUS_WAITING = u"waiting"
    STATUS_ONGOING = u"ongoing"
    STATUS_STOP = u"stop"
    STATUS_FINISHED = u"finished"
    STATUS_FAILED = u"failed"

    def __init__(self, etl_key, **kwargs):
        self.etl_key = etl_key
        self.kwargs = kwargs
        self.etl_store = NormalHashSet(etl_key)

    def do_etl(self):
        pass

    def start(self):
        debug_logger.debug("%s etl start of %s" % (self.__class__.__name__, self.etl_key))
        etl_start.delay(self.etl_key, self.__class__.__name__, **self.kwargs)

    def stop(self):
        self.etl_store.set_field_value("status", self.STATUS_STOP)

    @property
    def begin_time(self):
        return self.etl_store.get_field_value("begin_time")

    @begin_time.setter
    def begin_time(self, value):
        self.etl_store.set_field_value("begin_time", value)

    @property
    def end_time(self):
        return self.etl_store.get_field_value("end_time")

    @end_time.setter
    def end_time(self, value):
        self.etl_store.set_field_value("end_time", value)

    @property
    def count(self):
        return self.etl_store.get_field_value("count")

    @count.setter
    def count(self, value):
        self.etl_store.set_field_value("count", value)

    @property
    def current(self):
        current = self.etl_store.get_field_value("current")
        if not current:
            return 0
        return current

    @current.setter
    def current(self, value):
        self.etl_store.set_field_value("current", value)

    @property
    def status(self):
        return self.etl_store.get_field_value("status")

    @status.setter
    def status(self, value):
        self.etl_store.set_field_value("status", value)

    @property
    def progress(self):
        if not self.count:
            return 0
        else:
            return round(self.current*1.00 / self.count*1.00 * 100, 2)

    @property
    def dimension_score(self):
        return self.etl_store.get_field_value("dimension_score")

    @dimension_score.setter
    def dimension_score(self, value):
        self.etl_store.set_field_value("dimension_score", value)

    @property
    def happy_score(self):
        return self.etl_store.get_field_value("happy_score")

    @happy_score.setter
    def happy_score(self, value):
        self.etl_store.set_field_value("happy_score", value)

    @property
    def valid(self):
        return self.etl_store.get_field_value("valid")

    @valid.setter
    def valid(self, value):
        self.etl_store.set_field_value("valid", value)

    @property
    def result(self):

        return self.happy_score, self.valid, self.dimension_score


class EtlTrialClean(EtlBase):
    u"""试清洗"""

    def do_etl(self):
        debug_logger.debug("EtlTrialClean do_etl of %s" % self.etl_key)
        self.count = 0
        self.current = 0
        self.status = self.STATUS_ONGOING
        self.begin_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.dimension_score = 0
        self.happy_score = 0
        self.valid = 0
        task = CleanTask.objects.get(id=self.etl_key)
        survey_overview_qs = SurveyOverview.objects.filter_active(id__in=eval(task.survey_overview_ids))

        people_total_list = []
        for obj in survey_overview_qs:
            # 单个问卷
            # 做该问卷的人
            people_survey_list = PeopleSurveyRelation.objects.filter_active(
                survey_id=obj.survey_id, project_id=obj.assess_id)
            for people in people_survey_list:
                people_total_list.append(people.people_id)
        # 实际总人数的id
        people_id_total = list(set(people_total_list))
        self.count = len(people_id_total)
        debug_logger.debug("实际总人数:%s" % self.count)

        if True:

            clean_dimension_score = []
            clean_happy_score = []
            clean_effective_people_id = []
            clean_invalid_people_id = []
            for people_id in people_id_total:

                for obj in survey_overview_qs:
                    people_survey_list_info = PeopleSurveyRelation.objects.filter(
                        survey_id=obj.survey_id,
                        project_id=obj.assess_id,
                        people_id=people_id
                    )
                    if len(people_survey_list_info) == 0:
                        continue
                    people_survey = people_survey_list_info[0]
                    # 社会称许总分判断
                    if people_survey.praise_score < task.social_desirability_score:
                        clean_invalid_people_id.append(people_id)
                        continue

                    # 一致性题目判断
                    uniformity_num = 0
                    dimension_score_map = people_survey.dimension_score_map
                    for dimension_id in dimension_score_map:
                        if "uniformity_score" in dimension_score_map[dimension_id]:
                            uniformity_score = dimension_score_map[dimension_id]["uniformity_score"]
                            for uniformity in uniformity_score:
                                diff_uniformity_score = uniformity["src_score"] - uniformity['uniformity_q_score']
                                if diff_uniformity_score > task.score_difference_of_each_group:
                                    uniformity_num += 1
                    # 一致性题目数量判断
                    if uniformity_num > task.num_of_consistency_check:
                        clean_invalid_people_id.append(people_id)
                        continue
                    # 获取问卷的所有题目
                    question_id_list = SurveyQuestionRelation.objects.filter_active(survey_id=obj.survey_id)
                    # 回答时间不足题目数
                    question_num = 0
                    # 遍历该问卷的所有题目
                    for question in question_id_list:

                        user_question_answer_info_qs = UserQuestionAnswerInfo.objects.filter(
                            people_id=people_survey.people_id,
                            survey_id=people_survey.survey_id,
                            project_id=people_survey.project_id,
                            question_id=question.question_id
                        )
                        if len(user_question_answer_info_qs) == 0:
                            question_num += 1
                            continue
                        # 每道题答题时间判断
                        if user_question_answer_info_qs[0].answer_time < task.min_time_of_answer:
                            question_num += 1
                    # 答题时间不足数目判断
                    if question_num <= task.max_count_of_less_time:
                        clean_dimension_score.append({people_id: dimension_score_map})
                        clean_happy_score.append({people_id: people_survey.happy_score})
                        clean_effective_people_id.append(people_id)
                    else:
                        clean_invalid_people_id.append(people_id)
                self.current += 1
                debug_logger.debug("有效人数:%s" % self.current)
            # 无效人数和有效人数交集 id
            invalid_effective_id = []

            for people_id in clean_invalid_people_id:
                if people_id in clean_effective_people_id:
                    invalid_effective_id.append(people_id)

            ls = list(set(invalid_effective_id))
            # 去除无效的people_id
            for i in ls:
                while i in clean_effective_people_id:
                    clean_effective_people_id.remove(i)
            # 此时 clean_effective_people_id 有效人员ID列表中，people_id是重复的，
            #  可视为  该任务所有问卷 使用总有效人次
            num = len(clean_effective_people_id)

            # 去重后可得到 实际的有效人员ID
            clean_effective_people_id = list(set(clean_effective_people_id))

            # 去除无效的指数分，维度分
            # clean_happy_score = [{people_id: people_survey.happy_score},{people_id: people_survey.happy_score}]
            # clean_dimension_score_effective=[{people_id: {'did':{'score':2}}, people_id: {'did':{'score':2}},}]

            clean_happy_score_effective = []
            clean_dimension_score_effective = []

            # 有效指数分列表
            for happy_score in clean_happy_score:
                for people_id in happy_score:
                    if people_id not in clean_invalid_people_id:
                        clean_happy_score_effective.append(happy_score)
            # 有效维度分列表
            for dimension_score in clean_dimension_score:
                for people_id in dimension_score:
                    if people_id not in clean_invalid_people_id:
                        clean_dimension_score_effective.append(dimension_score)
            # 实际总人数
            people_id_total_num = len(people_id_total)
            # 有效人数
            clean_effective_people_num = len(clean_effective_people_id)
            # 有效率

            debug_logger.debug('总人数：%s,有效人数：%s'%(people_id_total_num, clean_effective_people_num))

            if people_id_total_num:
                valid = '%.2f%%' % (clean_effective_people_num / people_id_total_num * 100)
            else:
                valid = '0%'
            self.valid = valid

            happy_score_total = 0
            try:
                for i in clean_happy_score_effective:
                    debug_logger.debug('单个问卷指数分%s' % i['people_id'])
                    print ('单个问卷指数分%s' % i['people_id'])
                    happy_score_total += i['people_id']
                # 有效指数分
                if num:
                    print('测试有效人次%s' % num)
                    happy_score = '%.2f' % (happy_score_total/num)
                else:
                    happy_score = 0
                self.happy_score = happy_score
            except Exception as e:
                self.happy_score = happy_score


            # clean_dimension_score_effective = [{people_id: {'did': {'score': 2}}}, {people_id: {'did': {'score': 2}}}]
            # 有效维度总分
            try:
                dimension_score_d = {}
                for obj in clean_dimension_score_effective:
                    for people_id in obj:
                        for did in obj[people_id]:
                            if did in dimension_score_d:
                                dimension_score_d[did]["score"] += obj[people_id][did]["score"]
                            else:
                                dimension_score_d[did] = obj[people_id][did]
                debug_logger.debug('有效维度总分：%s' % dimension_score_d)

                # 有效维度分
                dimension_score = {}
                for k in dimension_score_d:
                    if num:
                        a = '%.2f' % (dimension_score_d[k]['score'] / num)
                    else:
                        a = 0
                    dimension_score[k] = a
            except Exception as e:
                self.dimension_score = dimension_score

            self.dimension_score = dimension_score
            self.status = self.STATUS_FINISHED
            self.end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # logger.debug("EtlTrialClean do_etl success of %s,结束时间:%s 状态:%s" % (self.etl_key, self.end_time, self.status))
            debug_logger.debug("再次打印EtlTrialClean do_etl success of  %s,结束时间:%s 状态:%s" % (self.etl_key, self.end_time, self.status))

        #except Exception as e:
            # logger.error("EtlTrialClean do_etl error of %s, msg is %s" % (self.etl_key, e))
            # self.status = self.STATUS_FAILED
            # self.end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# class EtlClean(EtlBase):
#     u"""正式清洗"""
#
#     def do_etl(self):
#         debug_logger.debug("EtlTrialClean do_etl of %s" % self.etl_key)
#         self.count = 0
#         self.current = 0
#         self.status = self.STATUS_ONGOING
#         self.begin_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         self.dimension_score = 0
#         self.happy_score = 0
#         self.valid = 0
#         task = CleanTask.objects.get(id=self.etl_key)
#         survey_overview_qs = SurveyOverview.objects.filter_active(id__in=eval(task.survey_overview_ids))
#
#         people_total_list = []
#         for obj in survey_overview_qs:
#             # 单个问卷
#             # 做该问卷的人
#             people_survey_list = PeopleSurveyRelation.objects.filter_active(
#                 survey_id=obj.survey_id, project_id=obj.assess_id)
#             for people in people_survey_list:
#                 people_total_list.append(people.people_id)
#         # 实际总人数的id
#         people_id_total = list(set(people_total_list))
#         self.count = len(people_id_total)
#         debug_logger.debug("实际总人数:%s" % self.count)
#         if True:
#
#             clean_dimension_score = []
#             clean_happy_score = []
#             clean_effective_people_id = []
#             clean_invalid_people_id = []
#             for people_id in people_id_total:
#
#                 for obj in survey_overview_qs:
#                     people_survey = PeopleSurveyRelation.objects.get(
#                         survey_id=obj.survey_id,
#                         project_id=obj.assess_id,
#                         people_id=people_id
#                     )
#                     # 社会称许总分判断
#                     if people_survey.praise_score < task.social_desirability_score:
#                         clean_invalid_people_id.append(people_id)
#                         continue
#
#                     # 一致性题目判断
#                     uniformity_num = 0
#                     dimension_score_map = people_survey.dimension_score_map
#                     for dimension_id in dimension_score_map:
#                         if "uniformity_score" in dimension_score_map[dimension_id]:
#                             uniformity_score = dimension_score_map[dimension_id]["uniformity_score"]
#                             for uniformity in uniformity_score:
#                                 diff_uniformity_score = uniformity["src_score"] - uniformity['uniformity_q_score']
#                                 if diff_uniformity_score > task.score_difference_of_each_group:
#                                     uniformity_num += 1
#                     # 一致性题目数量判断
#                     if uniformity_num > task.num_of_consistency_check:
#                         clean_invalid_people_id.append(people_id)
#                         continue
#                     # 获取问卷的所有题目
#                     question_id_list = SurveyQuestionRelation.objects.filter_active(survey_id=obj.survey_id)
#                     # 回答时间不足题目数
#                     question_num = 0
#                     # 遍历该问卷的所有题目
#                     for question in question_id_list:
#
#                         user_question_answer_info_qs = UserQuestionAnswerInfo.objects.get(
#                             people_id=people_survey.people_id,
#                             survey_id=people_survey.survey_id,
#                             project_id=people_survey.project_id,
#                             question_id=question.question_id
#                         )
#                         if not user_question_answer_info_qs.exists():
#                             question_num += 1
#                         # 每道题答题时间判断
#                         if user_question_answer_info_qs.answer_time < task.min_time_of_answer:
#                             question_num += 1
#                     # 答题时间不足数目判断
#                     if question_num <= task.max_count_of_less_time:
#                         clean_dimension_score.append({people_id: dimension_score_map})
#                         clean_happy_score.append({people_id: people_survey.happy_score})
#                         clean_effective_people_id.append(people_id)
#                     else:
#                         clean_invalid_people_id.append(people_id)
#                 self.current += 1
#                 debug_logger.debug("有效人数:%s" % self.current)
#             # 无效人数和有效人数交集 id
#             invalid_effective_id = []
#
#             for people_id in clean_invalid_people_id:
#                 if people_id in clean_effective_people_id:
#                     invalid_effective_id.append(people_id)
#
#             ls = list(set(invalid_effective_id))
#             # 去除无效的people_id
#             for i in ls:
#                 while i in clean_effective_people_id:
#                     clean_effective_people_id.remove(i)
#             # 人员问卷信息 weidudb.people_survey_info
#             people_survey_info = []
#             # 人员信息
#             people_info = []
#             # 项目问卷信息
#             assess_survey_info = []
#             # 组织信息
#             organization = []
#
#             for people_id in clean_effective_people_id:
#                 # 添加人员信息到 people_info
#                 people_obj = People.objects.get(user_id=people_id)
#                 people_info.append([
#                     people_id,people_obj.username,people_obj.phone,
#                     people_obj.email,people_obj.more_info
#                 ])
#
#                 for obj in survey_overview_qs:
#                     people_survey = PeopleSurveyRelation.objects.get(
#                         survey_id=obj.survey_id,
#                         project_id=obj.assess_id,
#                         people_id=people_id
#                     )
#                     # 添加人员问卷信息到 people_survey_info
#                     people_survey_info.append(
#                         [people_id, obj.survey_id, obj.assess_id,
#                          people_survey.model_score,people_survey.dimension_score,
#                          people_survey.substandard_score,people_survey.facet_score,
#                          people_survey.happy_score,people_survey.happy_ability_score,
#                          people_survey.happy_efficacy_score,people_survey.praise_score,
#                          people_survey.uniformity_score,task.score_difference_of_each_group,
#                          task.num_of_consistency_check,task.min_time_of_answer,
#                          task.max_count_of_less_time,task.social_desirability_score,
#                          ]
#                     )
#                     assess = AssessProject.objects.get(id=obj.assess_id)
#                     survey = Survey.objects.get(id=obj.survey_id)
#                     # 添加项目问卷信息到  assess_survey_info
#                     assess_survey_info.append([
#                         assess.id, assess.name, assess.en_name, assess.assess_type, assess.user_count,
#                         survey.id, survey.title, survey.en_title, survey.survey_type, survey.form_type,
#
#                     ])
#                     # 添加组织信息到  organization
#                     organization_info = Organization.objects.get(assess_id=assess.id)
#                     organization.append([
#                         organization_info.name,organization_info.en_name,organization_info.enterprise_id,
#                         organization_info.identification_code,
#                     ])
#
#             con_linux(people_survey_info, people_info, assess_survey_info, organization)
#             self.status = self.STATUS_FINISHED
#             self.end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#
#             debug_logger.debug("EtlClean do_etl success of %s,结束时间:%s 状态:%s" % (self.etl_key, self.end_time, self.status))





