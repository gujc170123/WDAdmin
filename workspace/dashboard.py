# -*- coding:utf-8 -*-
from __future__ import division
import time
import collections
from utils.views import AuthenticationExceptView, WdListCreateAPIView
from utils.response import general_json_response, ErrorCode
from rest_framework import status
from utils.logger import err_logger
from workspace.models import FactOEI
from wduser.models import BaseOrganization, BaseOrganizationPaths
from .helper import OrganizationHelper
from django.db.models import Avg
from assessment.models import AssessSurveyRelation
from workspace.tasks import main
from workspace.util.redispool import redis_pool
from django.shortcuts import HttpResponse
import numpy as np
from django.db.models import Count
from collections import OrderedDict
from django.db import connection
import json


class Dashboard(AuthenticationExceptView, WdListCreateAPIView):
    """Dashboard"""

    profile_matrix ={u'年龄':[u'25岁及以下',
                            u'26-30岁',
                            u'31-35岁',
                            u'36-40岁',
                            u'41-45岁',
                            u'46-50岁',
                            u'50岁及以上'],
                    u'学历':[u'大专及以下',
                            u'本科',
                            u'硕士及以上'],
                    u'政治面貌':[u'中共党员',
                            u'中共预备党员',
                            u'共青团员',
                            u'其他党派',
                            u'群众'],
                    u'司龄':[u'1年及以下',
                            u'1-3年',
                            u'3-5年',
                            u'6-10年',
                            u'11-15年',
                            u'16年及以上']}

    api_mapping = {
        "organtree": 'self.get_organtree',
        # 团队幸福温度
        "temperature": "self.get_temperature",
        # 团队幸福指数整体特征
        "feature": "self.get_feature",
        # 员工幸福与压力/敬业整体分布
        "distribution": "self.get_distribution",
        # 下属机构幸福指数表现 && 幸福指数各维度特征
        "expression": "self.get_expression",
        # 幸福指数关注群体
        "group": "self.get_focus_group",
        # 员工幸福整体分布
        "overall": "self.get_overall",
        # 企业幸福指数
        "business_index": "self.get_business_index",
        # 团队幸福指数特征
        "wdindex": "self.WDindex",
        # 计算维度分，生成报告
        "get_report": "self.get_report",

        "get_assess": "self.get_assess_id",
        # 整体特征与总行对比
        "zhdb": "self.get_zhdb",
        # 活力分布
        "vitality_distribute": "self.get_vitality_distribute",
        # 机构特征-分行机关
        "jgtz": "self.get_jgtz_fhjg",
        # 领导方式
        "leadership_style": "self.get_leadership_style",
        # 群体聚焦
        "focus_group": "self.focus_group",
        # 聚焦问题
        "focus_problem": "self.get_focus_problem",
        # 工作环境-群体分布
        "qtfb": "self.get_qtfb",
    }

    def get_qtfb(self, **kwargs):
        res = {}
        org = kwargs.get("org_id")
        query_dict = self.get_organization(org)[0]
        child_org = self.get_child_org(query_dict)
        if child_org:
            child_list = []
            for tpl in child_org:
                j = '.'.join([i for i in tpl if i])
                if j not in child_list:
                    child_list.append(j)
            for child in child_list:
                child_query_dict, child_name = self.get_organization(child)
                total = FactOEI.objects.complex_filter(child_query_dict).count()
                negative = FactOEI.objects.complex_filter(child_query_dict).filter(model__lt=65).count()
                if total:
                    res[child_name[-1]] = round(negative*100/total, 2)
        return res, ErrorCode.SUCCESS

    def get_focus_problem(self, **kwargs):
        org = kwargs.get("org_id")
        query_dict = self.get_organization(org)[0]
        score = FactOEI.objects.complex_filter(query_dict).aggregate(
            Avg('G2'), Avg('G8'),
            Avg('S2'), Avg('S3'), Avg('S4'), Avg('S5'), Avg('S6'), Avg('S7'), Avg('S8'), Avg('S9'),
            Avg('C1'), Avg('C2'), Avg('C3'), Avg('C4'), Avg('C5'), Avg('C6'), Avg('C7'), Avg('C8'), Avg('C9'),
            Avg('C10'), Avg('L19'), Avg('Z7'), Avg('Z13'), Avg('Z14'),
            Avg('N1'), Avg('N2'), Avg('N3'), Avg('N4'), Avg('N5'), Avg('N6'), Avg('N7'), Avg('N8'), Avg('N9'),
            Avg('N10'), Avg('N11'), Avg('N12'), Avg('N13'), Avg('N14'), Avg('N15'), Avg('N16'), Avg('N17'),
            Avg('N18'), Avg('N19'), Avg('N20'), Avg('N21'), Avg('N22'), Avg('N23'), Avg('N24')
        )
        # 成长开发
        czkf = ['G8', 'N1', 'N2', 'C8', 'N7', 'N8', 'N23', 'N24', 'C2', 'C4', 'C10',
                'C7', 'N3', 'N4', 'C1', 'C6', 'C3', 'C9', 'Z14', 'Z7', 'N19', 'N20',
                'C5', 'N11', 'N12', 'Z13', 'N21', 'N22', 'N15', 'N16', 'L19', 'N5',
                'N6', 'N13', 'N14', 'N9', 'N10', 'N17', 'N18']
        # 深耕关爱
        sgga = ['G2', 'S2', 'S8', 'S9', 'S4', 'S5', 'S3', 'S7', 'S6']
        czkf_score_keys = ['%s__avg' % c for c in czkf]
        sgga_score_keys = ['%s__avg' % s for s in sgga]

        sgga_score = [round(score[s]*20, 2) for s in sgga_score_keys]
        sgga_score.insert(0, u'得分')
        czkf_score_pre = [round(score[c]*20, 2) for c in czkf_score_keys]
        n1 = [round(sum(czkf_score_pre[1: 3]) / 2, 2)]
        n2 = [round(sum(czkf_score_pre[4: 6]) / 2, 2), round(sum(czkf_score_pre[6: 8]) / 2, 2)]
        n3 = [round(sum(czkf_score_pre[12: 14]) / 2, 2)]
        n4 = [round(sum(czkf_score_pre[20: 22]) / 2, 2)]
        n5 = [round(sum(czkf_score_pre[23: 25]) / 2, 2)]
        n6 = [round(sum(czkf_score_pre[26: 28]) / 2, 2), round(sum(czkf_score_pre[28: 30]) / 2, 2)]
        n7 = [round(sum(czkf_score_pre[31: 33]) / 2, 2), round(sum(czkf_score_pre[33: 35]) / 2, 2),
              round(sum(czkf_score_pre[35: 37]) / 2, 2), round(sum(czkf_score_pre[37:]) / 2, 2)]
        czkf_score = [u'得分'] + [czkf_score_pre[0]] + n1 + [czkf_score_pre[3]] + n2 + czkf_score_pre[8: 12] + n3 + \
                     czkf_score_pre[14: 20] + n4 + [czkf_score_pre[22]] + n5 + [czkf_score_pre[25]] + \
                     n6 + [czkf_score_pre[30]] + n7
        from workspace.util.indicators import czkf_act, czkf_indi, sgga_act, sgga_indi
        czkf_res = [czkf_indi, czkf_act, czkf_score]
        sgga_res = [sgga_indi, sgga_act, sgga_score]
        res = {'sgga': sgga_res, 'czkf': czkf_res}
        return res, ErrorCode.SUCCESS

    def focus_group(self, **kwargs):
        org = kwargs.get("org_id")
        profile = kwargs.get("profile_id")
        if profile and profile == 'profile1':
            select_profile = [u'26-30岁', u'31-35岁']
        else:
            select_profile = [u'初级管理人员']
        query_dict = self.get_organization(org)[0]
        score = FactOEI.objects.complex_filter(query_dict).filter(profile1__in=select_profile).aggregate(
            Avg('G1'), Avg('G2'), Avg('G3'), Avg('G4'), Avg('G5'), Avg('G6'), Avg('G7'), Avg('G8'),
            Avg('S1'), Avg('S2'), Avg('S3'), Avg('S4'), Avg('S5'), Avg('S6'), Avg('S7'), Avg('S8'), Avg('S9'),
            Avg('C1'), Avg('C2'), Avg('C3'), Avg('C4'), Avg('C5'), Avg('C6'), Avg('C7'), Avg('C8'), Avg('C9'), Avg('C10'),
            Avg('R1'), Avg('R2'), Avg('R3'), Avg('R4'), Avg('R5'), Avg('R6'), Avg('R7'), Avg('R8'),
            Avg('L1'), Avg('L2'), Avg('L3'), Avg('L4'), Avg('L5'), Avg('L6'), Avg('L7'), Avg('L8'), Avg('L9'), Avg('L10'),
            Avg('L11'), Avg('L12'), Avg('L13'), Avg('L14'), Avg('L15'), Avg('L16'), Avg('L17'), Avg('L18'), Avg('L19'), Avg('L20'),
            Avg('Z1'), Avg('Z2'), Avg('Z3'), Avg('Z4'), Avg('Z5'), Avg('Z6'), Avg('Z7'), Avg('Z8'), Avg('Z9'),
            Avg('Z10'), Avg('Z11'), Avg('Z12'), Avg('Z13'), Avg('Z14'), Avg('Z15'), Avg('Z16'), Avg('Z17'),
            Avg('Z18'), Avg('Z19'), Avg('Z20'), Avg('Z21'),  Avg('Z22'), Avg('Z23'),
            Avg('N1'), Avg('N2'), Avg('N3'), Avg('N4'), Avg('N5'), Avg('N6'), Avg('N7'), Avg('N8'), Avg('N9'),
            Avg('N10'), Avg('N11'), Avg('N12'), Avg('N13'), Avg('N14'), Avg('N15'),  Avg('N16'), Avg('N17'),
            Avg('N18'), Avg('N19'), Avg('N20'), Avg('N21'), Avg('N22'), Avg('N23'), Avg('N24')
        )
        G = ['G%s__avg' % g for g in xrange(1, 9)]
        S = ['S%s__avg' % s for s in xrange(1, 10)]
        C = ['C%s__avg' % c for c in xrange(1, 11)]
        R = ['R%s__avg' % r for r in xrange(1, 9)]
        L = ['L%s__avg' % l for l in xrange(1, 21)]
        Z = ['Z%s__avg' % z for z in xrange(1, 24)]
        N = ['N%s__avg' % n for n in xrange(1, 25)]
        score_keys = G + S + C + R + L + Z
        # 百分制7个维度的所有指标分
        indicators_score = [u'得分']
        indicators_score.extend([round(score[key]*20, 2) for key in score_keys])
        indicators_score.extend([round(score[key]*25, 2) for key in N])
        from workspace.util.indicators import indicator, action
        res = [indicator, action, indicators_score]
        return res, ErrorCode.SUCCESS

    def get_leadership_style(self, **kwargs):
        # 查下属机构，按model排名，取前5后5，然后取各自机构的领导激发维度下所有的指标分
        res = {}
        org = kwargs.get("org_id")
        query_dict = self.get_organization(org)[0]
        child_org = self.get_child_org(query_dict)
        if child_org:
            child_list = []
            for tpl in child_org:
                j = '.'.join([i for i in tpl if i])
                if j not in child_list:
                    child_list.append(j)
            child_org_data = []
            for i in child_list:
                child_query_dict, child_org_list = self.get_organization(i)
                child_org_name = i.split('.')[-1]  # 分行机关名字
                scores = FactOEI.objects.complex_filter(child_query_dict).aggregate(
                    Avg('model'), Avg('L1'), Avg('L2'), Avg('L3'), Avg('L4'), Avg('L5'),
                    Avg('L6'), Avg('L7'), Avg('L8'), Avg('L9'), Avg('L10'),
                    Avg('L11'), Avg('L12'), Avg('L13'), Avg('L14'), Avg('L15'),
                    Avg('L16'), Avg('L17'), Avg('L18'), Avg('L19'), Avg('L20'),
                )
                org_res = [
                    child_org_name,
                    round(scores["model__avg"] * 20, 2), round(scores["L1__avg"] * 20, 2),
                    round(scores["L2__avg"] * 20, 2),
                    round(scores["L3__avg"] * 20, 2), round(scores["L4__avg"] * 20, 2),
                    round(scores["L5__avg"] * 20, 2),
                    round(scores["L6__avg"] * 20, 2), round(scores["L7__avg"] * 20, 2),
                    round(scores["L8__avg"] * 20, 2),
                    round(scores["L9__avg"] * 20, 2), round(scores["L10__avg"] * 20, 2),
                    round(scores["L11__avg"] * 20, 2),
                    round(scores["L12__avg"] * 20, 2), round(scores["L13__avg"] * 20, 2),
                    round(scores["L14__avg"] * 20, 2),
                    round(scores["L15__avg"] * 20, 2), round(scores["L16__avg"] * 20, 2),
                    round(scores["L17__avg"] * 20, 2),
                    round(scores["L18__avg"] * 20, 2), round(scores["L19__avg"] * 20, 2),
                    round(scores["L20__avg"] * 20, 2)
                ]
                child_org_data.append(org_res)
            child_org_data.sort(key=lambda x: x[1], reverse=True)
            if len(child_org_data) > 10:
                child_org_data = child_org_data[:5] + child_org_data[-5:]
            # 处理数据
            for data in child_org_data:
                del data[1]  # 幸福指数分只用来排序
            indicator = [u'指标', u'目标引领', u'目标引领', u'目标引领', u'系统把握', u'系统把握', u'激发信任',
                         u'激发信任', u'激发信任', u'激发信任', u'激发信任', u'激发信任', u'激发信任', u'激发信任',
                         u'读懂他人', u'读懂他人', u'释放潜能', u'释放潜能', u'释放潜能', u'促进成长', u'促进成长']
            define = [u'行为', u'与团队一起讨论形成目标与思路', u'设置高目标并追求绩效改善的程度',
                      u'帮助团队建立目标实现的共同意义', u'能够把握团队任务解决的关键问题',
                      u'把注意力放到首要目标和节点的把握上', u'能与团队成员一起面对难题和挑战',
                      u'主动承担团队工作失误中的责任', u'能根据标准和规则对待团队成员的关切',
                      u'能及时兑现对员工的承诺，言行一致', u'能主动倾听团队成员心声并平等交流',
                      u'能主动关心团队成员的困难并帮助和支持', u'向团队成员明确表达对其工作的期望',
                      u'主动向团队成员分享各种变化和信息', u'能关注和把握团队成员的需求和特征',
                      u'能根据团队成员需求和特征进行沟通和安排', u'员工的表现能够得到及时肯定和鼓励',
                      u'给员工自主空间让员工成为工作主角', u'主动接纳员工不同意见和建议',
                      u'能讨论团队成员的职业发展并予以鼓励', u'能定期给团队成员反馈和建设性辅导']
            res_data = [indicator, define]
            res_data.extend(child_org_data)
            res = res_data

        return res, ErrorCode.SUCCESS

    def get_jgtz_fhjg(self, **kwargs):
        res = {}
        org = kwargs.get("org_id")
        if not org:
            return res, ErrorCode.INVALID_INPUT
        query_dict = self.get_organization(org)[0]
        child_org = self.get_child_org(query_dict)
        if child_org:
            child_list = []
            for tpl in child_org:
                j = '.'.join([i for i in tpl if i])
                if j not in child_list:
                    child_list.append(j)
            child_org_data = []
            for i in child_list:
                child_query_dict, child_org_list = self.get_organization(i)
                child_org_name = i[-1]  # 分行机关名字
                child_org_qs = FactOEI.objects.complex_filter(child_query_dict)
                # child_org_num = child_org_qs.count()  # 有效样本
                scores = child_org_qs.aggregate(
                    Avg('quota41'), Avg('model'), Avg('dimension1'), Avg('dimension2'), Avg('dimension3'),
                    Avg('dimension4'), Avg('dimension5'), Avg('dimension6'), Avg('dimension7'), Count("id")
                )
                org_res = [
                    '', child_org_name, scores['id__count'], round(scores['quota41__avg'], 2),
                    round(scores['model__avg'], 2), 0, 0, round(scores['dimension1__avg'], 2),
                    round(scores['dimension2__avg'], 2), round(scores['dimension3__avg'], 2),
                    round(scores['dimension4__avg'], 2), round(scores['dimension5__avg'], 2),
                    round(scores['dimension6__avg'], 2), round(scores['dimension7__avg'], 2),
                ]
                # 判断区间
                org_res[0] = self.get_level(org_res[4])
                child_org_data.append(org_res)
            child_org_data.sort(key=lambda x: x[4], reverse=True)
            if len(child_org_data) > 10:
                child_org_data = child_org_data[:5] + child_org_data[-5:]
            res = child_org_data

        return res, ErrorCode.SUCCESS

    def get_vitality_distribute(self, **kwargs):
        # 查下属机构的平均幸福分
        res = {}
        org = kwargs.get("org_id")
        query_dict = self.get_organization(org)[0]
        child_org = self.get_child_org(query_dict)
        if child_org:
            child_list = []
            for tpl in child_org:
                j = '.'.join([i for i in tpl if i])
                if j not in child_list:
                    child_list.append(j)
            model_score = []
            for i in child_list:
                child_query_dict, child_org_list = self.get_organization(i)
                avg_model = FactOEI.objects.complex_filter(child_query_dict).aggregate(Avg("model"))
                model_score.append(round(avg_model["model__avg"], 2))

            types = [0 for num in xrange(6)]
            for score in model_score:
                if score <= 40:
                    types[0] += 1
                elif 40 < score <= 60:
                    types[1] += 1
                elif 60 < score < 65:
                    types[2] += 1
                elif 65 <= score < 70:
                    types[3] += 1
                elif 70 <= score < 75:
                    types[4] += 1
                elif 75 <= score < 80:
                    types[5] += 1
                else:
                    types[6] += 1
            length = sum(types)
            rate = [round(i * 100 / length, 2) for i in types]
            res['rate'] = rate
            res['number'] = types
        return res, ErrorCode.SUCCESS

    def get_zhdb(self, **kwargs):
        org = kwargs.get("org_id")
        current_org_data = self.get_feature(org_id=org)[0]
        company_name = org.split('.')[0]  # 总行
        company_data = self.get_feature(org_id=company_name)[0]
        title = current_org_data.keys()
        current_res = current_org_data.values()
        company_res = company_data.values()
        res = [title, current_res, company_res]
        res_arr = np.array(res)
        res = res_arr.transpose().tolist()
        return res, ErrorCode.SUCCESS

    def get_temperature(self, **kwargs):
        res = {}
        # org: org1.org2.org3.....
        org = kwargs.get("org_id")
        if not org:
            return res, ErrorCode.INVALID_INPUT
        try:
            query_dict = self.get_organization(org)[0]
            res = FactOEI.objects.complex_filter(query_dict).aggregate(Avg("model"))
            if res:
                res = {i: round(res[i], 2) for i in res}
                return res, ErrorCode.SUCCESS
            else:
                return res, ErrorCode.NOT_EXISTED
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return res, ErrorCode.INTERNAL_ERROR

    def get_feature(self, **kwargs):
        res = OrderedDict()
        org = kwargs.get("org_id")
        if not org:
            return res, ErrorCode.INVALID_INPUT
        try:
            query_dict = self.get_organization(org)[0]
            res2 = FactOEI.objects.complex_filter(query_dict).aggregate(
                Avg("model"), Avg("quota41"), Avg("dimension1"), Avg("dimension2"), Avg("dimension3"),
                Avg("dimension4"), Avg("dimension5"), Avg("dimension6"), Avg("dimension7")
            )
            if res2:
                res[u"企业幸福指数"] = round(res2["model__avg"], 2)
                res[u"压力承受"] = round(res2["quota41__avg"], 2)
                res[u"工作环境"] = round(res2["dimension1__avg"], 2)
                res[u"生活愉悦"] = round(res2["dimension2__avg"], 2)
                res[u"成长环境"] = round(res2["dimension3__avg"], 2)
                res[u"人际环境"] = round(res2["dimension4__avg"], 2)
                res[u"领导方式"] = round(res2["dimension5__avg"], 2)
                res[u"组织环境"] = round(res2["dimension6__avg"], 2)
                res[u"心理资本"] = round(res2["dimension7__avg"], 2)
                return res, ErrorCode.SUCCESS
            else:
                return res, ErrorCode.NOT_EXISTED
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return res, ErrorCode.INTERNAL_ERROR

    def get_distribution(self, **kwargs):
        res = {}
        org = kwargs.get("org_id")
        scale = kwargs.get("scale_id")
        redis_key = "data-distribution-%s-%s" % (org, scale)
        data = redis_pool.get(redis_key)
        if data:
            return json.loads(data), ErrorCode.SUCCESS
        if not org or (scale not in ["scale1", "scale2"]):
            return res, ErrorCode.INVALID_INPUT
        try:
            query_dict = self.get_organization(org)[0]
            # find company
            scale = 'quota39' if scale == 'scale1' else 'quota41'  # scale1-敬业，实际-quota39; scale2-压力，实际-quote41
            result = FactOEI.objects.complex_filter(query_dict).values_list(scale, 'model')
            total = result.count()
            if total:
                res1 = {
                    "r1c1": 0, "r1c2": 0, "r1c3": 0, "r1c4": 0, "r1c5": 0, "r1c6": 0, "r1c7": 0,
                    "r2c1": 0, "r2c2": 0, "r2c3": 0, "r2c4": 0, "r2c5": 0, "r2c6": 0, "r2c7": 0,
                    "r3c1": 0, "r3c2": 0, "r3c3": 0, "r3c4": 0, "r3c5": 0, "r3c6": 0, "r3c7": 0,
                    "r4c1": 0, "r4c2": 0, "r4c3": 0, "r4c4": 0, "r4c5": 0, "r4c6": 0, "r4c7": 0,
                    "r5c1": 0, "r5c2": 0, "r5c3": 0, "r5c4": 0, "r5c5": 0, "r5c6": 0, "r5c7": 0,
                    "r6c1": 0, "r6c2": 0, "r6c3": 0, "r6c4": 0, "r6c5": 0, "r6c6": 0, "r6c7": 0,
                    "r7c1": 0, "r7c2": 0, "r7c3": 0, "r7c4": 0, "r7c5": 0, "r7c6": 0, "r7c7": 0,
                }
                res2 = {
                    "r1c1": 0, "r1c2": 0, "r1c3": 0, "r1c4": 0, "r1c5": 0, "r1c6": 0, "r1c7": 0,
                    "r2c1": 0, "r2c2": 0, "r2c3": 0, "r2c4": 0, "r2c5": 0, "r2c6": 0, "r2c7": 0,
                    "r3c1": 0, "r3c2": 0, "r3c3": 0, "r3c4": 0, "r3c5": 0, "r3c6": 0, "r3c7": 0,
                    "r4c1": 0, "r4c2": 0, "r4c3": 0, "r4c4": 0, "r4c5": 0, "r4c6": 0, "r4c7": 0,
                    "r5c1": 0, "r5c2": 0, "r5c3": 0, "r5c4": 0, "r5c5": 0, "r5c6": 0, "r5c7": 0,
                }
                for s, model in result:
                    if scale == "quota39":
                        res1 = self.get_dedication_res(s, model, res1)
                    else:
                        res2 = self.get_stress_res(s, model, res2)
                res = res1 if scale == "quota39" else res2
                for i in res:
                    res[i] = round(res[i] * 100 / total, 2)
                if scale == 'quota39':
                    low = res['r1c5'] + res['r1c6'] + res['r1c7'] + res['r2c5'] + res['r2c6'] + res['r2c7']
                    high = res["r6c1"] + res["r6c2"] + res["r7c1"] + res["r7c2"]
                else:
                    low = res["r4c5"] + res["r4c6"] + res["r4c7"] + res["r5c5"] + res["r5c6"] + res["r5c7"]
                    high = res['r1c1'] + res['r1c2'] + res['r2c1'] + res['r2c2']
                res['low'] = round(low, 2)
                res['high'] = round(high, 2)
                redis_pool.set(redis_key, json.dumps(res))
                return res, ErrorCode.SUCCESS
            else:
                return res, ErrorCode.NOT_EXISTED
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return res, ErrorCode.INTERNAL_ERROR

    def get_dedication_res(self, scale, model, res):
        if 80 <= scale <= 100:
            if 0 <= model <= 40:
                res["r1c1"] += 1
            elif 40 < model <= 60:
                res["r1c2"] += 1
            elif 60 < model < 65:
                res["r1c3"] += 1
            elif 65 <= model < 70:
                res["r1c4"] += 1
            elif 70 <= model < 75:
                res["r1c5"] += 1
            elif 75 <= model < 80:
                res["r1c6"] += 1
            else:
                res["r1c7"] += 1
        elif 75 <= scale < 80:
            if 0 <= model <= 40:
                res["r2c1"] += 1
            elif 40 < model <= 60:
                res["r2c2"] += 1
            elif 60 < model < 65:
                res["r2c3"] += 1
            elif 65 <= model < 70:
                res["r2c4"] += 1
            elif 70 <= model < 75:
                res["r2c5"] += 1
            elif 75 <= model < 80:
                res["r2c6"] += 1
            else:
                res["r2c7"] += 1
        elif 70 <= scale < 75:
            if 0 <= model <= 40:
                res["r3c1"] += 1
            elif 40 < model <= 60:
                res["r3c2"] += 1
            elif 60 < model < 65:
                res["r3c3"] += 1
            elif 65 <= model < 70:
                res["r3c4"] += 1
            elif 70 <= model < 75:
                res["r3c5"] += 1
            elif 75 <= model < 80:
                res["r3c6"] += 1
            else:
                res["r3c7"] += 1
        elif 65 <= scale < 70:
            if 0 <= model <= 40:
                res["r4c1"] += 1
            elif 40 < model <= 60:
                res["r4c2"] += 1
            elif 60 < model < 65:
                res["r4c3"] += 1
            elif 65 <= model < 70:
                res["r4c4"] += 1
            elif 70 <= model < 75:
                res["r4c5"] += 1
            elif 75 <= model < 80:
                res["r4c6"] += 1
            else:
                res["r4c7"] += 1
        elif 60 < scale < 65:
            if 0 <= model <= 40:
                res["r5c1"] += 1
            elif 40 < model <= 60:
                res["r5c2"] += 1
            elif 60 < model < 65:
                res["r5c3"] += 1
            elif 65 <= model < 70:
                res["r5c4"] += 1
            elif 70 <= model < 75:
                res["r5c5"] += 1
            elif 75 <= model < 80:
                res["r5c6"] += 1
            else:
                res["r5c7"] += 1
        elif 40 < scale <= 60:
            if 0 <= model <= 40:
                res["r6c1"] += 1
            elif 40 < model <= 60:
                res["r6c2"] += 1
            elif 60 < model < 65:
                res["r6c3"] += 1
            elif 65 <= model < 70:
                res["r6c4"] += 1
            elif 70 <= model < 75:
                res["r6c5"] += 1
            elif 75 <= model < 80:
                res["r6c6"] += 1
            else:
                res["r6c7"] += 1
        else:
            if 0 <= model <= 40:
                res["r7c1"] += 1
            elif 40 < model <= 60:
                res["r7c2"] += 1
            elif 60 < model < 65:
                res["r7c3"] += 1
            elif 65 <= model < 70:
                res["r7c4"] += 1
            elif 70 <= model < 75:
                res["r7c5"] += 1
            elif 75 <= model < 80:
                res["r7c6"] += 1
            else:
                res["r7c7"] += 1
        return res

    def get_stress_res(self, scale, model, res):
        if 80 <= scale <= 100:
            if 0 <= model <= 40:
                res["r1c1"] += 1
            elif 40 < model <= 60:
                res["r1c2"] += 1
            elif 60 < model < 65:
                res["r1c3"] += 1
            elif 65 <= model < 70:
                res["r1c4"] += 1
            elif 70 <= model < 75:
                res["r1c5"] += 1
            elif 75 <= model < 80:
                res["r1c6"] += 1
            else:
                res["r1c7"] += 1
        elif 70 <= scale < 80:
            if 0 <= model <= 40:
                res["r2c1"] += 1
            elif 40 < model <= 60:
                res["r2c2"] += 1
            elif 60 < model < 65:
                res["r2c3"] += 1
            elif 65 <= model < 70:
                res["r2c4"] += 1
            elif 70 <= model < 75:
                res["r2c5"] += 1
            elif 75 <= model < 80:
                res["r2c6"] += 1
            else:
                res["r2c7"] += 1
        elif 60 <= scale < 70:
            if 0 <= model <= 40:
                res["r3c1"] += 1
            elif 40 < model <= 60:
                res["r3c2"] += 1
            elif 60 < model < 65:
                res["r3c3"] += 1
            elif 65 <= model < 70:
                res["r3c4"] += 1
            elif 70 <= model < 75:
                res["r3c5"] += 1
            elif 75 <= model < 80:
                res["r3c6"] += 1
            else:
                res["r3c7"] += 1
        elif 50 <= scale < 60:
            if 0 <= model <= 40:
                res["r4c1"] += 1
            elif 40 < model <= 60:
                res["r4c2"] += 1
            elif 60 < model < 65:
                res["r4c3"] += 1
            elif 65 <= model < 70:
                res["r4c4"] += 1
            elif 70 <= model < 75:
                res["r4c5"] += 1
            elif 75 <= model < 80:
                res["r4c6"] += 1
            else:
                res["r4c7"] += 1
        else:
            if 0 <= model <= 40:
                res["r5c1"] += 1
            elif 40 < model <= 60:
                res["r5c2"] += 1
            elif 60 < model < 65:
                res["r5c3"] += 1
            elif 65 <= model < 70:
                res["r5c4"] += 1
            elif 70 <= model < 75:
                res["r5c5"] += 1
            elif 75 <= model < 80:
                res["r5c6"] += 1
            else:
                res["r5c7"] += 1
        return res

    def get_expression(self, **kwargs):
        res = {}
        org = kwargs.get("org_id")
        dimension = kwargs.get("dimension_id")
        select = kwargs.get("select_id")
        if not org:
            return res, ErrorCode.NOT_EXISTED
        try:
            query_dict, org_list = self.get_organization(org)
            if dimension:
                dimension_dict = {
                    u"工作环境": "dimension1",
                    u"生活愉悦": "dimension2",
                    u"成长环境": "dimension3",
                    u"人际环境": "dimension4",
                    u"领导方式": "dimension5",
                    u"组织环境": "dimension6",
                    u"心理资本": "dimension7",
                }
                company = FactOEI.objects.complex_filter(query_dict).aggregate(Avg(dimension_dict[dimension]))
            else:
                company = FactOEI.objects.complex_filter(query_dict).aggregate(Avg("model"), Avg("quota41"))
            res[org_list[-1]] = company
            # get child department
            child_org = self.get_child_org(query_dict)
            if child_org:
                child_list = []
                for tpl in child_org:
                    j = '.'.join([i for i in tpl if i])
                    if j not in child_list:
                        child_list.append(j)
                for i in child_list:
                    child_query_dict, child_org_list = self.get_organization(i)
                    if dimension:
                        dimension_dict = {
                            u"工作环境": "dimension1",
                            u"生活愉悦": "dimension2",
                            u"成长环境": "dimension3",
                            u"人际环境": "dimension4",
                            u"领导方式": "dimension5",
                            u"组织环境": "dimension6",
                            u"心理资本": "dimension7",
                        }
                        child_depart = FactOEI.objects.complex_filter(child_query_dict).aggregate(
                            Avg(dimension_dict[dimension]))
                    else:
                        child_depart = FactOEI.objects.complex_filter(child_query_dict).aggregate(Avg("model"),
                                                                                                  Avg("quota41"))
                    res[child_org_list[-1]] = child_depart

            if res:
                head, name, score, score2 = {}, [], [], []
                for dic in res:
                    if dic == org_list[-1]:
                        if not dimension:
                            head = {dic: [round(res[dic]["model__avg"], 2), round(res[dic]["quota41__avg"], 2)]}
                        else:
                            head = {dic: round(tuple(res[dic].values())[0], 2)}

                    else:
                        name.append(dic)
                        if not dimension:
                            score.append(round(res[dic]["model__avg"], 2))
                            score2.append(round(res[dic]["quota41__avg"], 2))
                        else:
                            score.append(round(tuple(res[dic].values())[0], 2))
                if dimension:
                    result = [list(i) for i in zip(name, score)]
                    result.sort(key=lambda x: x[1], reverse=True)
                else:
                    result = [list(i) for i in zip(name, score, score2)]
                    if select:
                        if select == 'high':
                            result = [i for i in result if i[1] >= 70]
                        if select == 'mid':
                            result = [i for i in result if 60 < i[1] < 70]
                        if select == 'low':
                            result = [i for i in result if i[1] <= 60]
                res = {
                    "header": head,
                    "body": result
                }

                return res, ErrorCode.SUCCESS
            else:
                return res, ErrorCode.NOT_EXISTED

        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return res, ErrorCode.INTERNAL_ERROR

    def get_focus_group(self, **kwargs):
        org = kwargs.get("org_id")
        profile = kwargs.get("profile_id")
        profile_dict = {u"年龄": "profile1", u"性别": "profile2", u"司龄": "profile3",  u"学历": "profile5", u"政治面貌": "profile4",}

        query_dict, org_list = self.get_organization(org)
        company_obj = FactOEI.objects.complex_filter(query_dict).filter(model__lt=65)
        if not company_obj.exists():
            return {}, ErrorCode.SUCCESS
        res = OrderedDict()
        if profile in profile_dict:
            types_tpl = company_obj.values_list(profile_dict[profile]).distinct()
            if profile in (u'年龄', u"司龄"):
                types, types2 = [], []
                for tpl in types_tpl:
                    if len(tpl[0].split('-')[0]) > 1:
                        types2.append(tpl[0])
                    else:
                        types.append(tpl[0])
                types.sort()
                types2.sort()
                types.extend(types2)
            else:
                types = [i[0] for i in types_tpl]

        else:
            child_org = self.get_child_org(query_dict)
            types = []
            if child_org:

                for tpl in child_org:
                    j = '.'.join([i for i in tpl if i])
                    if j not in types:
                        types.append(j)
            else:
                return
        for i in types:
            res[i] = {}
            if profile in profile_dict:
                query_dict = {profile_dict[profile]: i}
            else:
                query_dict = self.get_organization(i)[0]
            type_obj = company_obj.complex_filter(query_dict)
            res[i][u"人数"] = type_obj.count()
            scores = type_obj.aggregate(Avg("dimension1"), Avg("dimension2"), Avg("dimension3"), Avg("dimension4"),
                                        Avg("dimension5"), Avg("dimension6"), Avg("model"))
            res[i][u"工作环境"] = round(scores["dimension1__avg"], 2)
            res[i][u"生活愉悦"] = round(scores["dimension2__avg"], 2)
            res[i][u"成长环境"] = round(scores["dimension3__avg"], 2)
            res[i][u"人际环境"] = round(scores["dimension4__avg"], 2)
            res[i][u"领导方式"] = round(scores["dimension5__avg"], 2)
            res[i][u"组织环境"] = round(scores["dimension6__avg"], 2)
            level = self.get_level(scores["model__avg"])
            res[i][u"区间"] = level
        types = [u"人数", u"区间", u"工作环境", u"生活愉悦", u"成长环境", u"人际环境", u"领导方式", u"组织环境"]
        rest = self.transe_list(res, types)
        if profile not in types:
            t = [i.split('.')[-1] for i in rest[0]]
            rest[0] = t
        return rest, ErrorCode.SUCCESS

    def transe_list(self, res, types):
        title = []
        score = [[] for i in types]
        for key in res:
            title.append(key)
            for i in range(len(types)):
                score[i].append(res[key][types[i]])
        return [title, score]

    def get_level(self, score):
        if 80 <= score <= 100:
            level = u"优势区"
        elif 75 <= score < 80:
            level = u"保持区"
        elif 70 <= score < 75:
            level = u"潜力区"
        elif 65 <= score < 70:
            level = u"需提升"
        elif 60 < score < 65:
            level = u"提升区"
        elif 40 < score <= 60:
            level = u"改进区"
        else:
            level = u"障碍区"
        return level

    def get_overall(self, **kwargs):
        org = kwargs.get("org_id")
        profile = kwargs.get("profile_id")
        query_dict = self.get_organization(org)[0]
        company_query_set = FactOEI.objects.complex_filter(query_dict)
        profile_dict = {
            u"年龄": "profile1", u"性别": "profile2", u"司龄": "profile3",  u"学历": "profile5", u"政治面貌": "profile4",
        }
        if profile in profile_dict:
            company_query_set = company_query_set.complex_filter({profile: profile_dict[profile]})
        if not company_query_set.exists():
            return {}, ErrorCode.NOT_EXISTED
        target = ["model", "dimension1", "dimension2", "dimension3", "dimension4",
                  "dimension5", "dimension6", "dimension7"]
        res = []
        length = company_query_set.count()
        for name in target:
            group_num = company_query_set.values_list(name).annotate(c=Count("id"))   # [(name, c), ...]
            types = [0 for num in xrange(7)]
            for tpl in group_num:
                score, number = tpl
                if score <= 40:
                    types[0] += number
                elif 40 < score <= 60:
                    types[1] += number
                elif 60 < score < 65:
                    types[2] += number
                elif 65 <= score < 70:
                    types[3] += number
                elif 70 <= score < 75:
                    types[4] += number
                elif 75 <= score < 80:
                    types[5] += number
                else:
                    types[6] += number
            rate = [round(i * 100 / length, 2) for i in types]
            res.append(rate)
        ret_arr = np.array(res)
        ret = ret_arr.transpose().tolist()
        title = [u"企业幸福指数", u"工作环境", u"生活愉悦", u"成长环境", u"人际环境",
                 u"领导方式", u"组织环境", u"心理资本"]
        return [title, ret], ErrorCode.SUCCESS

    def get_business_index(self, **kwargs):
        res = collections.OrderedDict()
        org = kwargs.get("org_id")
        profile = kwargs.get("profile_id")
        select = kwargs.get("select_id")
        query_dict = self.get_organization(org)[0]
        profile_options = [u"年龄", u"性别", u"司龄", u"政治面貌", u"学历"]
        # current department
        department = FactOEI.objects.complex_filter(query_dict)
        if not department.exists():
            return res, ErrorCode.NOT_EXISTED
        # get result by profile
        if profile in profile_options:
            # all optional fields
            profile_dict = {
                u"年龄": "profile1", u"性别": "profile2", u"司龄": "profile3",  u"学历": "profile5", u"政治面貌": "profile4",
            }
            # field_query_set = department.values_list(profile_dict[profile]).distinct()            
            # field_list = [i[0] for i in field_query_set if i[0]]
            field_list = self.profile_matrix[profile]
            for i in field_list:
                value_list = department.complex_filter({profile_dict[profile]: i}).values_list("model")
                if select and select == "负面":
                    value_list = [j[0] for j in value_list if j[0] and j[0] < 65]
                else:
                    value_list = [j[0] for j in value_list if j[0] and j[0] > 75]
                res[i] = value_list

        # get child department
        else:
            child_org = self.get_child_org(query_dict)
            for i in child_org:
                if not i[-1]:
                    return {'': 0}, ErrorCode.SUCCESS
                child_query_dict, org_list = self.get_organization('.'.join(i))
                value_list = department.complex_filter(child_query_dict).values_list("model")
                if select and select == "负面":
                    value_list = [j[0] for j in value_list if j[0] and j[0] < 65]
                elif select and select == "正面":
                    value_list = [j[0] for j in value_list if j[0] and j[0] > 75]
                else:
                    value_list = [j[0] for j in value_list if j[0]]
                res[org_list[-1]] = value_list

        total = sum([len(res[i]) for i in res])
        if not total:
            res = {key: len(res[key]) for key in res}
        else:
            for key in res.keys():
                res[key]= round(len(res[key]) * 100 / total, 2)
            # res = {key: round(len(res[key]) * 100 / total, 2) for key in res}
        return res, ErrorCode.SUCCESS

    def WDindex(self, **kwargs):
        org = kwargs.get("org_id")
        assess = kwargs.get("assess_id")
        cursor = connection.cursor()
        sql = """
            select m3.name,m3.description,m1.name,m2.name,c.mean
            from 
            workspace_factoeifacetdistributions c,
            workspace_dimensionoeipaths d1,
            workspace_dimensionoeipaths d2,
            workspace_dimensionoei m1,
            workspace_dimensionoei m2,
            workspace_dimensionoei m3
            where
             c.facet_id=d1.child_id
            and d1.depth=1
            and d1.parent_id=d2.child_id
            and d2.depth=1
            and m1.id=d1.parent_id
            and m2.id=d2.parent_id
            and m3.id=c.facet_id
            and c.organization_id=%s
            and c.assess_id=%s
            and d1.assess_id=0
            and d2.assess_id=0
            """
        cursor.execute(sql, (org, assess))
        res = cursor.fetchall()
        if not res:
            return {'msg': 'NOT FOUND'}, ErrorCode.NOT_EXISTED
        order_res = list(res)
        order_res.sort(key=lambda x: x[4], reverse=True)
        advantage = order_res[:5]
        disadvantage = order_res[-5:]
        disadvantage.reverse()
        keys = ['gm', 'behavior', 'index', 'dimension', 'score']
        adv_dic = [dict(zip(keys, adv)) for adv in advantage]
        disadv_dic = [dict(zip(keys, disadv)) for disadv in disadvantage]
        cursor.close()
        connection.close()
        return {'advantage': adv_dic, 'disadvantage': disadv_dic}, ErrorCode.SUCCESS

    def get_organization(self, org):
        organization = (
            'organization1', 'organization2', 'organization3', 'organization4', 'organization5', 'organization6'
        )
        org_list = org.split('.')
        query_dict = dict(zip(organization, org_list))
        query_dict.update({'AssessKey': self.assess_id, 'hidden': False})
        return query_dict, org_list

    def get_child_org(self, query_dict):
        del query_dict['hidden']
        len_query = len(query_dict)
        if len_query == 2:
            child_org = FactOEI.objects.complex_filter(query_dict).values_list("organization1",
                                                                               "organization2").distinct()
        elif len_query == 3:
            child_org = FactOEI.objects.complex_filter(query_dict).values_list(
                "organization1", "organization2", "organization3"
            ).distinct()
        elif len_query == 4:
            child_org = FactOEI.objects.complex_filter(query_dict).values_list(
                "organization1", "organization2", "organization3", "organization4"
            ).distinct()
        elif len_query == 5:
            child_org = FactOEI.objects.complex_filter(query_dict).values_list(
                "organization1", "organization2", "organization3", "organization4", "organization5"
            ).distinct()
        elif len_query == 6:
            child_org = FactOEI.objects.complex_filter(query_dict).values_list(
                "organization1", "organization2", "organization3", "organization4", "organization5", "organization6"
            ).distinct()
        else:
            child_org = []
        return child_org

    def get_organtree(self, **kargs):
        """return organization tree list"""

        res = []
        org = kargs["org_id"]
        if not org:
            return res, ErrorCode.INVALID_INPUT
        try:
            organzations = BaseOrganization.objects.filter_active(id=org)
            if organzations.exists():
                res = OrganizationHelper.get_child_orgs(organzations[0].id)
                return res, ErrorCode.SUCCESS
            else:
                return res, ErrorCode.NOT_EXISTED
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return res, ErrorCode.INTERNAL_ERROR

    def get_org_siblings(self, org_id):
        redis_key = 'org_%s' % org_id
        org = redis_pool.get(redis_key)
        if not org:
            parents = BaseOrganizationPaths.objects.filter(child_id=org_id).values_list('parent_id').order_by("-depth")
            parent_id = [i[0] for i in parents]
            orgs = BaseOrganization.objects.filter(id__in=parent_id).values_list("name")
            org = '.'.join([j[0] for j in orgs])
            redis_pool.set(redis_key, org)
        return org

    def get_assess_id(self, **kwargs):
        org_id = kwargs.get('org_id')
        survey_id = kwargs.get('survey_id')
        parents = BaseOrganizationPaths.objects.filter(child_id=org_id).values_list('parent_id').order_by("-depth")
        if not parents.exists():
            return {'msg': 'NOT FOUND'}, ErrorCode.NOT_EXISTED
        parent_id = [i[0] for i in parents]
        base_org_objs = BaseOrganization.objects.filter(id__in=parent_id)
        if not base_org_objs.exists():
            return {'msg': 'not existed'}, ErrorCode.NOT_EXISTED
        assess_list = []
        for base_obj in base_org_objs:
            assess_ids_tpl = base_obj.organization_set.values_list("assess_id")
            if not assess_ids_tpl.exists():
                return {'msg': 'not existed'}, ErrorCode.NOT_EXISTED
            ass_ids = [oid[0] for oid in assess_ids_tpl]
            assess_list.extend(ass_ids)

        assess_obj = AssessSurveyRelation.objects.filter(survey_id=survey_id, assess_id__in=assess_list)
        if not assess_obj.exists():
            return {"msg": 'not existed'}, ErrorCode.NOT_EXISTED
        assess_id = assess_obj.last().assess_id
        return {'assess_id': assess_id}, ErrorCode.SUCCESS

    def get_report(self, **kwargs):
        assess_id = kwargs.get("assess_id")
        survey_id = kwargs.get("survey_id")
        stime = kwargs.get("stime")
        reference = kwargs.get("reference")
        if not assess_id or not survey_id:
            return {}, ErrorCode.NOT_EXISTED
        redis_key = 'etl_%s_%s' % (assess_id, survey_id)
        redis_value = redis_pool.lrange(redis_key, -2, -1)
        if redis_value and redis_value[-1] == '0':
            return {'msg': u'正在生成报告，请稍后访问。', 'status': 2}, ErrorCode.SUCCESS
        elif redis_value and redis_value[-1] == '1':
            return {'msg': u'报告完成。', 'status': 1}, ErrorCode.SUCCESS
        else:
            main.delay(assess_id, survey_id, stime, reference)
            if not redis_value:
                return {'msg': u'开始生成报告。', 'status': 0}, ErrorCode.SUCCESS
            else:
                return {'msg': u'重新生成报告。', 'status': 3}, ErrorCode.SUCCESS    

    def post(self, request, *args, **kwargs):
        api_id = self.request.data.get("api", None)
        org_id = self.request.data.get("org", None)
        profile_id = self.request.data.get("profile", None)
        dimension_id = self.request.data.get("dimension", None)
        population_id = self.request.data.get("population", None)
        scale_id = self.request.data.get("scale", None)
        select_id = self.request.data.get("select", None)
        assess_id = self.request.data.get("assess", None)
        survey_id = self.request.data.get("survey", None)
        stime = self.request.data.get("stime", 3)
        reference = self.request.data.get("reference", 4.8)

        try:
            if api_id == 'get_assess':
                data, err_code = eval(self.api_mapping[api_id])(
                    org_id=org_id, survey_id=survey_id
                )
            elif api_id == 'wdindex':
                data, err_code = eval(self.api_mapping[api_id])(
                    org_id=org_id, assess_id=assess_id
                )
            else:
                self.assess_id = assess_id
                if org_id:
                    org_id = self.get_org_siblings(org_id)
                # retrieve chart's data
                data, err_code = eval(self.api_mapping[api_id])(org_id=org_id,
                                                                profile_id=profile_id,
                                                                dimension_id=dimension_id,
                                                                population_id=population_id,
                                                                scale_id=scale_id,
                                                                select_id=select_id,
                                                                assess_id=assess_id,
                                                                survey_id=survey_id,
                                                                stime=stime,
                                                                reference=reference)
            if err_code != ErrorCode.SUCCESS:
                return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT, {"msg": err_code})
            else:
                return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": data})
        except Exception, e:
            err_logger.error("dashboard error, msg is %s" % e)
            return general_json_response(status.HTTP_200_OK, ErrorCode.INTERNAL_ERROR, {"msg": "%s" % e})


def redisStatus(request):
    assess = request.GET.get("assess")
    survey = request.GET.get("survey")
    redisKey = 'etl_%s_%s' % (assess, survey)
    redis_value = redis_pool.lrange(redisKey, -2, -1)
    if not redis_value:
        return HttpResponse('4')
    stat = redis_value[-1] if redis_value[-1] != 3 else 0
    return HttpResponse(stat)
