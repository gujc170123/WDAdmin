# -*- coding:utf-8 -*-
from __future__ import division

from utils.views import AuthenticationExceptView, WdListCreateAPIView
from utils.response import general_json_response, ErrorCode
from rest_framework import status
from utils.logger import get_logger
from workspace.models import FactOEI
from wduser.models import BaseOrganization
from .helper import OrganizationHelper
from django.db.models import Avg

logger = get_logger("front")

class Dashboard(AuthenticationExceptView, WdListCreateAPIView):
    """Dashboard"""

    api_mapping = {
        "organtree": 'self.get_organtree',
        "facet": 'self.get_get_facet',
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
        "": "self.get_",
    }


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
                res = {i: round(res[i]) for i in res}
                return res, ErrorCode.SUCCESS
            else:
                return res, ErrorCode.NOT_EXISTED
        except Exception, e:
            logger.error("get report data error, msg: %s " % e)
            return res, ErrorCode.INTERNAL_ERROR

    def get_feature(self, **kwargs):
        res = {}
        org = kwargs.get("org_id")
        if not org:
            return res, ErrorCode.INVALID_INPUT
        try:
            query_dict = self.get_organization(org)[0]
            res2 = FactOEI.objects.complex_filter(query_dict).aggregate(
                Avg("model"), Avg("scale2"), Avg("dimension1"), Avg("dimension2"), Avg("dimension3"),
                Avg("dimension4"), Avg("dimension5"), Avg("dimension6"), Avg("dimension7")
            )
            if res2:
                res[u"企业幸福指数"] = round(res2["model__avg"])
                res[u"压力指数"] = round(res2["scale2__avg"])
                res[u"工作投入"] = round(res2["dimension1__avg"])
                res[u"生活愉悦"] = round(res2["dimension2__avg"])
                res[u"成长有力"] = round(res2["dimension3__avg"])
                res[u"人际和谐"] = round(res2["dimension4__avg"])
                res[u"领导激发"] = round(res2["dimension5__avg"])
                res[u"组织卓越"] = round(res2["dimension6__avg"])
                res[u"员工幸福能力"] = round(res2["dimension7__avg"])
                return res, ErrorCode.SUCCESS
            else:
                return res, ErrorCode.NOT_EXISTED
        except Exception, e:
            logger.error("get report data error, msg: %s " % e)
            return res, ErrorCode.INTERNAL_ERROR

    def get_distribution(self, **kwargs):
        res = {}
        org = kwargs.get("org_id")
        scale = kwargs.get("scale_id")
        if not org or not scale:
            return res, ErrorCode.INVALID_INPUT
        try:
            organization = (
                'organization1', 'organization2', 'organization3', 'organization4', 'organization5', 'organization6')
            org_list = org.split('.')
            query_dict = dict(zip(organization, org_list))
            # find company
            result = FactOEI.objects.complex_filter(query_dict).values_list(scale, 'model')
            total = result.count()
            if total:
                res = {
                    "r1c1": 0, "r1c2": 0, "r1c3": 0, "r1c4": 0, "r1c5": 0, "r1c6": 0, "r1c7": 0,
                    "r2c1": 0, "r2c2": 0, "r2c3": 0, "r2c4": 0, "r2c5": 0, "r2c6": 0, "r2c7": 0,
                    "r3c1": 0, "r3c2": 0, "r3c3": 0, "r3c4": 0, "r3c5": 0, "r3c6": 0, "r3c7": 0,
                    "r4c1": 0, "r4c2": 0, "r4c3": 0, "r4c4": 0, "r4c5": 0, "r4c6": 0, "r4c7": 0,
                    "r5c1": 0, "r5c2": 0, "r5c3": 0, "r5c4": 0, "r5c5": 0, "r5c6": 0, "r5c7": 0,
                    "r6c1": 0, "r6c2": 0, "r6c3": 0, "r6c4": 0, "r6c5": 0, "r6c6": 0, "r6c7": 0,
                    "r7c1": 0, "r7c2": 0, "r7c3": 0, "r7c4": 0, "r7c5": 0, "r7c6": 0, "r7c7": 0,
                }
                for scale, model in result:
                    if 80 < scale <= 100:
                        if 0 < model <= 40:
                            res["r1c1"] += 1
                        elif 40 < model < 60:
                            res["r1c2"] += 1
                        elif 60 < model < 65:
                            res["r1c3"] += 1
                        elif 65 < model < 70:
                            res["r1c4"] += 1
                        elif 70 < model < 75:
                            res["r1c5"] += 1
                        elif 75 < model < 80:
                            res["r1c6"] += 1
                        else:
                            res["r1c7"] += 1
                    elif 75 < scale <= 80:
                        if 0 < model <= 40:
                            res["r2c1"] += 1
                        elif 40 < model < 60:
                            res["r2c2"] += 1
                        elif 60 < model < 65:
                            res["r2c3"] += 1
                        elif 65 < model < 70:
                            res["r2c4"] += 1
                        elif 70 < model < 75:
                            res["r2c5"] += 1
                        elif 75 < model < 80:
                            res["r2c6"] += 1
                        else:
                            res["r2c7"] += 1
                    elif 70 < scale <= 75:
                        if 0 < model <= 40:
                            res["r3c1"] += 1
                        elif 40 < model < 60:
                            res["r3c2"] += 1
                        elif 60 < model < 65:
                            res["r3c3"] += 1
                        elif 65 < model < 70:
                            res["r3c4"] += 1
                        elif 70 < model < 75:
                            res["r3c5"] += 1
                        elif 75 < model < 80:
                            res["r3c6"] += 1
                        else:
                            res["r3c7"] += 1
                    elif 65 < scale <= 70:
                        if 0 < model <= 40:
                            res["r4c1"] += 1
                        elif 40 < model < 60:
                            res["r4c2"] += 1
                        elif 60 < model < 65:
                            res["r4c3"] += 1
                        elif 65 < model < 70:
                            res["r4c4"] += 1
                        elif 70 < model < 75:
                            res["r4c5"] += 1
                        elif 75 < model < 80:
                            res["r4c6"] += 1
                        else:
                            res["r4c7"] += 1
                    elif 60 < scale <= 65:
                        if 0 < model <= 40:
                            res["r5c1"] += 1
                        elif 40 < model < 60:
                            res["r5c2"] += 1
                        elif 60 < model < 65:
                            res["r5c3"] += 1
                        elif 65 < model < 70:
                            res["r5c4"] += 1
                        elif 70 < model < 75:
                            res["r5c5"] += 1
                        elif 75 < model < 80:
                            res["r5c6"] += 1
                        else:
                            res["r5c7"] += 1
                    elif 40 < scale <= 60:
                        if 0 < model <= 40:
                            res["r6c1"] += 1
                        elif 40 < model < 60:
                            res["r6c2"] += 1
                        elif 60 < model < 65:
                            res["r6c3"] += 1
                        elif 65 < model < 70:
                            res["r6c4"] += 1
                        elif 70 < model < 75:
                            res["r6c5"] += 1
                        elif 75 < model < 80:
                            res["r6c6"] += 1
                        else:
                            res["r6c7"] += 1
                    else:
                        if 0 < model <= 40:
                            res["r7c1"] += 1
                        elif 40 < model < 60:
                            res["r7c2"] += 1
                        elif 60 < model < 65:
                            res["r7c3"] += 1
                        elif 65 < model < 70:
                            res["r7c4"] += 1
                        elif 70 < model < 75:
                            res["r7c5"] += 1
                        elif 75 < model < 80:
                            res["r7c6"] += 1
                        else:
                            res["r7c7"] += 1
                for i in res:
                    res[i] = round(res[i] * 100 / total, 2)
                return res, ErrorCode.SUCCESS
            else:
                return res, ErrorCode.NOT_EXISTED
        except Exception, e:
            logger.error("get report data error, msg: %s " % e)
            return res, ErrorCode.INTERNAL_ERROR

    def get_expression(self, **kwargs):
        res = {}
        org = kwargs.get("org_id")
        dimension = kwargs.get("dimension_id")
        select = kwargs.get("select_id")
        if not org:
            return res, ErrorCode.INVALID_INPUT
        try:
            query_dict, org_list = self.get_organization(org)
            if dimension:
                dimension_dict = {
                    u"工作投入": "dimension1",
                    u"生活愉悦": "dimension2",
                    u"成长有力": "dimension3",
                    u"人际和谐": "dimension4",
                    u"领导激发": "dimension5",
                    u"组织卓越": "dimension6",
                    u"员工幸福能力": "dimension7",
                }
                company = FactOEI.objects.complex_filter(query_dict).aggregate(Avg(dimension_dict[dimension]))
            else:
                company = FactOEI.objects.complex_filter(query_dict).aggregate(Avg("model"), Avg("scale2"))
            res[org_list[-1]] = company
            # 查下属机构
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
                            u"工作投入": "dimension1",
                            u"生活愉悦": "dimension2",
                            u"成长有力": "dimension3",
                            u"人际和谐": "dimension4",
                            u"领导激发": "dimension5",
                            u"组织卓越": "dimension6",
                            u"员工幸福能力": "dimension7",
                        }
                        child_depart = FactOEI.objects.complex_filter(child_query_dict).aggregate(
                            Avg(dimension_dict[dimension]))
                    else:
                        child_depart = FactOEI.objects.complex_filter(child_query_dict).aggregate(Avg("model"),
                                                                                                  Avg("scale2"))
                    res[child_org_list[-1]] = child_depart

            if res:
                head, name, score, score2 = {}, [], [], []
                for dic in res:
                    if dic == org_list[-1]:
                        if not dimension:
                            head = {dic: [round(res[dic]["model__avg"]), round(res[dic]["scale2__avg"])]}
                        else:
                            head = {dic: round(tuple(res[dic].values())[0])}

                    else:
                        name.append(dic)
                        if not dimension:
                            score.append(round(res[dic]["model__avg"]))
                            score2.append(round(res[dic]["scale2__avg"]))
                        else:
                            score.append(round(tuple(res[dic].values())[0]))
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
            logger.error("get report data error, msg: %s " % e)
            return res, ErrorCode.INTERNAL_ERROR

    def get_focus_group(self, **kwargs):
        org = kwargs.get("org_id")
        profile = kwargs.get("profile_id")
        profile_dict = {u"年龄": "profile1", u"性别": "profile2", u"序列": "profile3", u"司龄": "profile4", u"层级": "profile5"}

        query_dict, org_list = self.get_organization(org)
        company_obj = FactOEI.objects.complex_filter(query_dict)
        res = {}
        if profile in profile_dict:
            types = company_obj.values_list(profile_dict[profile]).distinct()
            types = [i[0] for i in types]

        else:
            # 查下属部门
            child_org = self.get_child_org(query_dict)
            if child_org:
                types = []
                for tpl in child_org:
                    j = '.'.join([i for i in tpl if i])
                    if j not in types:
                        types.append(j)
            else:
                types = None
                return {}, ErrorCode.NOT_EXISTED
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
            res[i][u"工作投入"] = round(scores["dimension1__avg"], 2)
            res[i][u"生活愉悦"] = round(scores["dimension2__avg"], 2)
            res[i][u"成长有力"] = round(scores["dimension3__avg"], 2)
            res[i][u"人际和谐"] = round(scores["dimension4__avg"], 2)
            res[i][u"领导激发"] = round(scores["dimension5__avg"], 2)
            res[i][u"组织卓越"] = round(scores["dimension6__avg"], 2)
            level = self.get_level(scores["model__avg"])
            res[i][u"区间"] = level
        return res, ErrorCode.SUCCESS

    # 获取梯队区间
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

    # 员工幸福整体分布
    def get_overall(self, **kwargs):
        org = kwargs.get("org_id")
        query_dict = self.get_organization(org)[0]
        company_query_set = FactOEI.objects.complex_filter(query_dict)
        target = ["model", "scale2", "dimension1", "dimension2", "dimension3", "dimension4",
                  "dimension5", "dimension6", "dimension7"]
        ret = {}
        for i in target:
            ret[i] = {}
            ret[i]["total"] = company_query_set.values_list(i)
            ret[i][u"优势区"] = []
            ret[i][u"保持区"] = []
            ret[i][u"潜力区"] = []
            ret[i][u"需提升"] = []
            ret[i][u"提升区"] = []
            ret[i][u"改进区"] = []
            ret[i][u"障碍区"] = []
            for j in ret[i]["total"]:
                level = self.get_level(j[0])
                ret[i][level].append(j[0])

        for i in ret:
            for j in ret[i]:
                if j != "total":
                    ret[i][j] = round(len(ret[i][j]) * 100 / len(ret[i]["total"]))
        res = {}
        res_zip = {u"企业幸福指数": "model", u"压力指数": "scale2", u"工作投入": "dimension1", u"生活愉悦": "dimension2",
                   u"成长有力": "dimension3", u"人际和谐": "dimension4", u"领导激发": "dimension5",
                   u"组织卓越": "dimension6", u"员工幸福能力": "dimension7"}
        for i in res_zip:
            res[i] = ret[res_zip[i]]
        return res, ErrorCode.SUCCESS

    def get_organization(self, org):
        organization = (
            'organization1', 'organization2', 'organization3', 'organization4', 'organization5', 'organization6'
        )
        org_list = org.split('.')
        query_dict = dict(zip(organization, org_list))
        return query_dict, org_list

    def get_child_org(self, query_dict):
        len_query = len(query_dict)
        if len_query == 1:
            child_org = FactOEI.objects.complex_filter(query_dict).values_list("organization1",
                                                                               "organization2").distinct()
        elif len_query == 2:
            child_org = FactOEI.objects.complex_filter(query_dict).values_list(
                "organization1", "organization2", "organization3"
            ).distinct()
        elif len_query == 3:
            child_org = FactOEI.objects.complex_filter(query_dict).values_list(
                "organization1", "organization2", "organization3", "organization4"
            ).distinct()
        elif len_query == 4:
            child_org = FactOEI.objects.complex_filter(query_dict).values_list(
                "organization1", "organization2", "organization3", "organization4", "organization5"
            ).distinct()
        elif len_query == 5:
            child_org = FactOEI.objects.complex_filter(query_dict).values_list(
                "organization1", "organization2", "organization3", "organization4", "organization5", "organization6"
            ).distinct()
        else:
            child_org = None
        return child_org

    def get_organtree(self,**kargs):
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
            logger.error("get report data error, msg: %s " % e)
            return res, ErrorCode.INTERNAL_ERROR

    def get_facet(org):
        """return facet list of eoi"""
        return []

    def get_eoi(org):
        """return current organization's oei"""
        return 0

    def get_eoi_std(org):
        """return oei benchmark"""
        return 65

    def get_oeistress_dist(org):
        """return oei-stress population distribution"""
        return []
    
    def get_oeidevote_dist(org):
        """return oei-devotion population distribution"""
        return 0

    def get_oei_advantage(org):
        """return advantage behaviour of oei"""
        return []

    def get_oei_disadvantage(org):
        """return disadvantage behaviour of oei"""
        return []
    
    def get_oei_ranking(org):
        """return oei ranking of current org"""
        return []

    def get_oei_dimension(org):
        """return oei dimension matrix of current org"""
        return []
    
    def get_oei_profilefacet(org,profile):
        """return oei table of selected profile facet"""
        return []

    def get_oei_dist(org):
        """return oei popluation distribution"""
        return []
    
    def get_oei_pop_dist(org,model,dimension,pop):
        """return population facet distribution of """
        return []

    def post(self, request, *args, **kwargs):
        api_id = self.request.data.get("api", None)
        org_id = self.request.data.get("org", None)
        profile_id = self.request.data.get("profile", None)
        dimension_id = self.request.data.get("dimension", None)
        population_id = self.request.data.get("population", None)
        scale_id = self.request.data.get("scale", None)
        select_id = self.request.data.get("select", None)
        args = {"org_id": org_id,
                "profile_id": profile_id,
                "dimension_id": dimension_id,
                "population_id": population_id}
        try:
            # retrieve chart's data

            data, err_code = eval(self.api_mapping[api_id])(org_id=org_id,
                                                            profile_id=profile_id,
                                                            dimension_id=dimension_id,
                                                            population_id=population_id,
                                                            scale_id=scale_id,
                                                            select_id=select_id, )
            if err_code != ErrorCode.SUCCESS:
                return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT, {"msg": err_code})
            else:
                return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": data})
        except Exception, e:
            logger.error("dashboard error, msg is %s" % e)
            return general_json_response(status.HTTP_200_OK, ErrorCode.INTERNAL_ERROR, {"msg": "%s" % e})
