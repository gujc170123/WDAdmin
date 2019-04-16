# -*- coding:utf-8 -*-
from __future__ import unicode_literals
import os
from front.models import PeopleSurveyRelation, UserQuestionAnswerInfo, SurveyInfo, SurveyQuestionInfo
import datetime
import time
from console.models import CleanTask, SurveyOverview
from console.tasks import etl_start
# from console.ssh_linux import con_linux
from utils.cache.cache_utils import NormalHashSet
from survey.models import Survey, SurveyQuestionRelation
from front.models import PeopleSurveyRelation, UserQuestionAnswerInfo
from utils.logger import get_logger
from wduser.models import People, Organization, EnterpriseAccount, EnterpriseInfo
from assessment.models import AssessProject
from research.models import ResearchModel,ResearchDimension,ResearchSubstandard
from console.write_hive_utils import etl_people_info,etl_answer_question_info,etl_company_info,\
    etl_dimension_substandard_info,etl_model_info,etl_org_info,etl_people_survey_result,\
    etl_project_info,etl_survey_info,etl_write_file,utf8_more_info,etl_write_people_info_file,etl_write_sign_info_file


logger = get_logger("etl")

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
        logger.debug("%s etl start of %s" % (self.__class__.__name__, self.etl_key))
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
        logger.debug("EtlTrialClean do_etl of %s" % self.etl_key)
        logger.debug(" 22222" )
        print('333333')

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
        logger.debug("实际总人数:%s" % self.count)
        print('实际总人数id%s'% people_id_total)
        print("该次试请洗任务答题实际总人数:%s" % self.count)

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
                    print('问卷id%s' % obj.survey_id)
                    if len(people_survey_list_info) == 0:
                        continue
                    people_survey = people_survey_list_info[0]
                    # 社会称许总分判断

                    print('社会称许分%s' % people_survey.praise_score)
                    if people_survey.praise_score < task.social_desirability_score:
                        print('无效人员id %s' % people_id)
                        clean_invalid_people_id.append(people_id)
                        continue

                    # 一致性题目判断
                    uniformity_num = 0
                    dimension_score_map = people_survey.dimension_score_map
                    print('维度分集合%s' % dimension_score_map)
                    for dimension_id in dimension_score_map:
                        if "uniformity_score" in dimension_score_map[dimension_id]:
                            uniformity_score = dimension_score_map[dimension_id]["uniformity_score"]
                            print('一致性题目分 %s' % uniformity_score)
                            for uniformity in uniformity_score:
                                diff_uniformity_score = uniformity_score[uniformity]["src_score"] - uniformity_score[uniformity]['uniformity_q_score']
                                print('一致性题目分差值%s' % diff_uniformity_score)
                                if diff_uniformity_score > task.score_difference_of_each_group:
                                    uniformity_num += 1
                    # 一致性题目数量判断
                    print('一致性题目数量%s'% uniformity_num)
                    if uniformity_num > task.num_of_consistency_check:
                        clean_invalid_people_id.append(people_id)
                        continue
                    # 获取问卷的所有题目
                    question_id_list = SurveyQuestionRelation.objects.filter_active(survey_id=obj.survey_id)
                    # 回答时间不足题目数
                    question_num = 0
                    # 遍历该问卷的所有题目
                    print('问卷题目数量%s' % (len(question_id_list)))
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
                        print('题目回答时间%s' % user_question_answer_info_qs[0].answer_time)
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
                logger.debug("已清洗人数:%s" % self.current)
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
            print('清洗任务的总有效人次%s'%num)
            # 去重后可得到 实际的有效人员ID
            clean_effective_people_id = list(set(clean_effective_people_id))
            print('实际的有效人员ID %s ' % clean_effective_people_id)
            print('清洗任务的实际有效人次%s' % num)
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
            print('指数分列表%s'%clean_happy_score_effective)
            # 有效维度分列表
            for dimension_score in clean_dimension_score:
                for people_id in dimension_score:
                    if people_id not in clean_invalid_people_id:
                        clean_dimension_score_effective.append(dimension_score)
            print('有效维度分列表%s' % clean_dimension_score_effective)
            # 实际总人数
            people_id_total_num = len(people_id_total)
            # 有效人数
            clean_effective_people_num = len(clean_effective_people_id)
            # 有效率

            logger.debug('总人数：%s,有效人数：%s'%(people_id_total_num, clean_effective_people_num))
            print('总人数：%s,有效人数：%s'%(people_id_total_num, clean_effective_people_num))

            if people_id_total_num:
                valid = '%.2f%%' % (clean_effective_people_num / people_id_total_num * 100)
            else:
                valid = '0%'
            self.valid = valid


            happy_score_total = 0
            print('指数分test1')
            happy_score = 0
            try:

                for i in clean_happy_score_effective:
                    print('指数分test2')
                    # logger.debug('单个问卷指数分%s' % i['people_id'])
                    for k in i:

                        print ('单个问卷指数分%s' % i[k])
                        happy_score_total += i[k]
                # 有效指数分
                print('指数分总计%s'%happy_score_total)
                if num:
                    print('测试有效人次%s' % num)
                    happy_score += '%.2f' % (happy_score_total/num)
                else:
                    happy_score += 0
                print('指数分：%s' % happy_score )

            except Exception as e:
                self.happy_score = 0
            self.happy_score = happy_score

            # clean_dimension_score_effective = [{people_id: {'did': {'score': 2,'name':'维度名'}}}, {people_id: {'did': {'score': 2}}}]
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
                logger.debug('有效维度总分：%s' % dimension_score_d)
                print('有效维度总分：%s' % dimension_score_d)


                # 有效维度分
                dimension_score = {}
                for k in dimension_score_d:
                    if num:
                        a = '%.2f' % (dimension_score_d[k]['score'] / num)
                    else:
                        a = 0
                    dimension_score[dimension_score_d[k]['name']] = a
            except Exception as e:
                self.dimension_score = 0
            print('最终维度分%s'% dimension_score)
            self.dimension_score = dimension_score
            self.status = self.STATUS_FINISHED
            self.end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # logger.debug("EtlTrialClean do_etl success of %s,结束时间:%s 状态:%s" % (self.etl_key, self.end_time, self.status))
            logger.debug("再次打印EtlTrialClean do_etl success of  %s,结束时间:%s 状态:%s" % (self.etl_key, self.end_time, self.status))


class EtlClean(EtlBase):
    u"""正式清洗"""

    def do_etl(self):
        logger.debug("EtlClean do_etl of %s" % self.etl_key)
        logger.debug("正式清洗接口已被控制台触发")
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

        logger.debug("开始正式清洗问卷" )
        # logger.debug("实际总人数:%s" % self.count)
        print('实际总人数id%s'% people_id_total)
        # print("该次试请洗任务答题实际总人数:%s" % self.count)

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
                    print('问卷id%s' % obj.survey_id)
                    logger.debug('问卷id%s' % obj.survey_id)
                    if len(people_survey_list_info) == 0:
                        continue
                    people_survey = people_survey_list_info[0]
                    # 社会称许总分判断

                    print('社会称许分%s' % people_survey.praise_score)
                    logger.debug('社会称许分%s' % people_survey.praise_score)
                    if people_survey.praise_score < task.social_desirability_score:
                        print('无效人员id %s' % people_id)
                        logger.debug('无效人员id %s' % people_id)
                        clean_invalid_people_id.append(people_id)
                        continue

                    # 一致性题目判断
                    uniformity_num = 0
                    dimension_score_map = people_survey.dimension_score_map
                    print('维度分集合%s' % dimension_score_map)
                    for dimension_id in dimension_score_map:
                        if "uniformity_score" in dimension_score_map[dimension_id]:
                            uniformity_score = dimension_score_map[dimension_id]["uniformity_score"]
                            print('一致性题目分 %s' % uniformity_score)
                            for uniformity in uniformity_score:
                                diff_uniformity_score = uniformity_score[uniformity]["src_score"] - uniformity_score[uniformity]['uniformity_q_score']
                                print('一致性题目分差值%s' % diff_uniformity_score)
                                if diff_uniformity_score > task.score_difference_of_each_group:
                                    uniformity_num += 1
                    # 一致性题目数量判断
                    print('一致性题目数量%s'% uniformity_num)
                    if uniformity_num > task.num_of_consistency_check:
                        clean_invalid_people_id.append(people_id)
                        continue
                    # 获取问卷的所有题目
                    question_id_list = SurveyQuestionRelation.objects.filter_active(survey_id=obj.survey_id)
                    # 回答时间不足题目数
                    question_num = 0
                    # 遍历该问卷的所有题目
                    print('问卷题目数量%s' % (len(question_id_list)))
                    logger.debug('问卷题目数量%s' % (len(question_id_list)))
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
                        # print('题目回答时间%s' % user_question_answer_info_qs[0].answer_time)
                        if user_question_answer_info_qs[0].answer_time < task.min_time_of_answer:
                            question_num += 1
                    # 答题时间不足数目判断
                    if question_num <= task.max_count_of_less_time:
                        clean_dimension_score.append({people_id: dimension_score_map})
                        clean_happy_score.append({people_id: people_survey.happy_score})
                        clean_effective_people_id.append(people_id)
                    else:
                        clean_invalid_people_id.append(people_id)

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
            print('清洗任务的总有效人次%s'%num)

            # 去重后可得到 实际的有效人员ID
            clean_effective_people_id = list(set(clean_effective_people_id))
            print('实际的有效人员ID %s ' % clean_effective_people_id)
            print('清洗任务的实际有效人次%s' % num)
            t = datetime.datetime.now().strftime('%Y-%m-%d')
            timestamp = str(int(time.time() * 1000))
            self.count = len(clean_effective_people_id)
            logger.debug("需清数量:%s" % self.count)
            logger.debug("正式清洗问卷结束，开始准备向文件写入数据")
            for pid in clean_effective_people_id:
                for obj in survey_overview_qs:
                    people_survey_list = PeopleSurveyRelation.objects.filter_active(
                        survey_id=obj.survey_id, project_id=obj.assess_id)
                    for people in people_survey_list:
                        if people.people_id == pid:
                            project_info = AssessProject.objects.get(id=people.project_id)
                            survey_obj = Survey.objects.get(id=people.survey_id)
                            survey_info = \
                            SurveyInfo.objects.filter_active(survey_id=people.survey_id, project_id=people.project_id)[
                                0]
                            enterprise_info = EnterpriseInfo.objects.get(id=project_info.enterprise_id)
                            research_model = ResearchModel.objects.get(id=survey_obj.model_id)
                            try:
                                company_list = etl_company_info(enterprise_info, t)
                                etl_write_file("company.txt", company_list, t, timestamp)
                                print ('写入company.txt成功')
                                # TODO scp 发送到 hive所在机器
                            except Exception as e:
                                print ('写入company.txt出现错误')
                            try:
                                project_list = etl_project_info(project_info, enterprise_info, t)
                                etl_write_file("project_info.txt", project_list, t, timestamp)
                                print('写入project_info.txt成功')
                                # TODO scp 发送到 hive所在机器
                            except Exception as e:
                                print ('写入project_info.txt出现错误')

                            try:
                                org_list = etl_org_info(people.project_id, t)
                                etl_write_file("org.txt", org_list, t, timestamp)
                                print ('写入org.txt出现成功')
                                # TODO scp 发送到 hive所在机器
                            except Exception as e:
                                print ('写入org.txt出现错误')

                            try:
                                survey_list = etl_survey_info(survey_info, survey_obj, survey_obj.model_id,
                                                              people.project_id, t)
                                etl_write_file("survey_info.txt", survey_list, t, timestamp)
                                print ('写入survey_info.txt成功')
                                # TODO scp 发送到 hive所在机器
                            except Exception as e:
                                print ('写入survey_info.txt出现错误')
                            try:
                                model_list = etl_model_info(research_model, people.project_id, people.survey_id, t)
                                etl_write_file("research_model_info.txt", model_list, t, timestamp)
                                print ('写入research_model_info.txt成功')
                                # TODO scp 发送到 hive所在机器
                            except Exception as e:
                                print ('写入research_model_info.txt出现错误')
                            try:
                                dimension_list, substandard_list = etl_dimension_substandard_info \
                                    (research_model, people.project_id, people.survey_id, t)
                                etl_write_file("dimension_info.txt", dimension_list, t, timestamp)
                                print ('写入dimension_info.txt成功')
                                # TODO scp 发送到 hive所在机器
                            except Exception as e:
                                print ('写入dimension_info.txt出现错误')
                            try:
                                dimension_list, substandard_list = etl_dimension_substandard_info \
                                    (research_model, people.project_id, people.survey_id, t)
                                etl_write_file("substandard_info.txt", substandard_list, t, timestamp)
                                print ('写入substandard_info.txt成功')
                                # TODO scp 发送到 hive所在机器
                            except Exception as e:
                                print ('写入substandard_info.txt出现错误')
                            try:
                                people_info_list, people_result_list, people_answer_list = etl_people_info(
                                    people.project_id, people.survey_id, enterprise_info, t, )
                                # print('人员信息：%s' % people_info_list)
                                etl_write_people_info_file("people_info.txt", people_info_list, t, timestamp)
                                print ('写入people_info.txt成功')
                                # TODO scp 发送到 hive所在机器
                            except Exception as e:
                                print ('写入people_info.txt出现错误')
                            try:
                                people_info_list, people_result_list, people_answer_list = etl_people_info(
                                    people.project_id, people.survey_id, enterprise_info, t, )
                                etl_write_file("people_survey.txt", people_result_list, t, timestamp)
                                print ('写入people_survey.txt成功')
                                # TODO scp 发送到 hive所在机器
                            except Exception as e:
                                print ('写入people_survey.txt出现错误')
                            try:
                                people_info_list, people_result_list, people_answer_list = etl_people_info(
                                    people.project_id, people.survey_id, enterprise_info, t, )
                                etl_write_file("people_answer.txt", people_answer_list, t, timestamp)
                                print ('写入people_answer.txt成功')
                                # TODO scp 发送到 hive所在机器
                            except Exception as e:
                                print ('写入people_answer.txt出现错误')

                self.current += 1
                logger.debug("已清数量:%s" % self.current)
                print("已清洗数量:%s" % self.current)
                logger.debug('清洗进度%s' % self.progress)
                print('清洗进度%s' % self.progress)



            self.end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print('清洗状态结束时间%s ' % self.end_time)

            # logger.debug("EtlTrialClean do_etl success of %s,结束时间:%s 状态:%s" % (self.etl_key, self.end_time, self.status))
            self.status = self.STATUS_FINISHED
            logger.debug(
                "再次打印EtlClean do_etl success of  %s,结束时间:%s 状态:%s" % (self.etl_key, self.end_time, self.status))

            print('清洗状态%s ' % self.status)
            print("再次打印EtlClean do_etl success of  %s,结束时间:%s 状态:%s" % (self.etl_key, self.end_time, self.status))
            logger.debug("向文件写入数据结束")
            # 发送组织信息文件
            try:
                t1 = time.time() * 100000
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_data/org%s.txt' % (t,timestamp,'org.txt',int(t1)))
                con = 'org_sign'
                etl_write_sign_info_file("org_sign.txt",con , t, timestamp)
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_sign/org.txt' % (t,timestamp,'org_sign.txt'))
                print('org.txt，org_sign.txt传输成功')
            except Exception as e:
                print('org.txt或org_sign.txt传输失败')
            # 发送项目信息文件
            try:
                t1 = time.time() * 100000
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_data/assess%s.txt' % (t,timestamp,'project_info.txt',int(t1)))
                con = 'project_sign'
                etl_write_sign_info_file("project_sign.txt",con, t, timestamp)
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_sign/assess.txt' % (t,timestamp,'project_sign.txt'))
                print('project_info.txt，project_sign.txt传输成功')
            except Exception as e:
                print('project_info.txt，project_sign.txt传输失败')
            # 发送问卷信息文件
            try:
                t1 = time.time() * 100000
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_data/survey%s.txt' % (t,timestamp,'survey_info.txt',int(t1)))
                con = 'survey_sign'
                etl_write_sign_info_file("survey_sign.txt",con , t, timestamp)
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_sign/survey.txt' % (t,timestamp,'survey_sign.txt'))
                print('survey_info.txt，survey_sign.txt传输成功')
            except Exception as e:
                print('survey_info.txt，survey_sign.txt传输失败')
            # 发送企业信息文件
            try:
                t1 = time.time() * 100000
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_data/enterprise%s.txt' % (t, timestamp, 'company.txt', int(t1)))
                con = 'enterprise'
                etl_write_sign_info_file("enterprise_sign.txt",con, t, timestamp)
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_sign/enterprise.txt' % (t, timestamp, 'enterprise_sign.txt'))
                print('enterprise_info.txt，enterprise_sign.txt传输成功')
            except Exception as e:
                print('enterprise_info.txt，enterprise_sign.txt传输失败')
            # 发送模型信息文件
            try:
                t1 = time.time() * 100000
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_data/model%s.txt' % (t, timestamp, 'research_model_info.txt', int(t1)))
                con = 'model_sign'
                etl_write_sign_info_file("model_sign.txt",con, t, timestamp)
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_sign/model.txt' % (t, timestamp, 'model_sign.txt'))
                print('model_info.txt，model_sign.txt传输成功')
            except Exception as e:
                print('model_info.txt，model_sign.txt传输失败')
            # 发送维度信息文件
            try:
                t1 = time.time() * 100000
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_data/dimension%s.txt' % (t, timestamp, 'research_model_info.txt', int(t1)))
                con = 'dimension_sign'
                etl_write_sign_info_file("dimension_sign.txt",con, t, timestamp)
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_sign/dimension.txt' % (t, timestamp, 'model_sign.txt'))
                print('dimension_info.txt，dimension_sign.txt传输成功')
            except Exception as e:
                print('dimension_info.txt，dimension_sign.txt传输失败')
            # 发送指标信息文件
            try:
                t1 = time.time() * 100000
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_data/substandard%s.txt' % (t, timestamp, 'substandard_info.txt', int(t1)))
                con = 'substandard_sign'
                etl_write_sign_info_file("substandard_sign.txt",con, t, timestamp)
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_sign/substandard.txt' % (t, timestamp, 'substandard_sign.txt'))
                print('substandard_info.txt，substandard.txt_sign.txt传输成功')
            except Exception as e:
                print('substandard_info.txt，substandard_sign.txt传输失败')
            # 发送人员信息文件
            try:
                t1 = time.time() * 100000
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_data/people%s.txt' % (t, timestamp, 'people_info.txt', int(t1)))
                con = 'people_sign'
                etl_write_sign_info_file("people_sign.txt",con, t, timestamp)
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_sign/people.txt' % (t, timestamp, 'people_sign.txt'))
                print('people_info.txt，people_sign.txt传输成功')
            except Exception as e:
                print('substandard_info.txt，substandard.txt_sign.txt传输失败')

            # 发送人员问卷信息文件
            try:
                t1 = time.time() * 100000
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_data/people_survey%s.txt' % (t, timestamp, 'people_answer.txt', int(t1)))
                con = 'people_survey_sign'
                etl_write_sign_info_file("people_survey_sign.txt",con, t, timestamp)
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_sign/people_survey.txt' % (t, timestamp, 'people_survey_sign.txt'))
                print('people_survey_info.txt，people_survey_sign.txt传输成功')
            except Exception as e:
                print('people_survey_info.txt，people_survey_sign.txt传输失败')
            # 答题记录文件
            try:
                t1 = time.time() * 100000
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_data/question_answer%s.txt' % (t, timestamp, 'people_answer.txt', int(t1)))
                con = 'people_answer_sign'
                etl_write_sign_info_file("people_answer_sign.txt",con, t, timestamp)
                os.system('scp /home/wd/production/project/WeiDuAdmin/download/etl/%s/%s/%s pro-dw1:/home/wd/hdfs_sign/question_answer.txt' % (t, timestamp, 'people_answer_sign.txt'))
                print('people_answer_info.txt，people_answer_sign.txt传输成功')
            except Exception as e:
                print('people_answer_info.txt，people_answer_sign.txt传输失败')

            logger.debug("发送文件结束,正式清洗过程完全结束")






