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
        "temperature": "self.get_temperature",
        "feature": "self.get_feature",
        "distribution": "self.get_distribution",
        "expression": "self.get_expression",
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
            res = FactOEI.objects.complex_filter(query_dict).aggregate(
                Avg("model"), Avg("scale2"), Avg("dimension1"), Avg("dimension2"),
                Avg("dimension3"), Avg("dimension4"), Avg("dimension5"), Avg("dimension6")
            )
            if res:
                res = {i: round(res[i]) for i in res}
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
                    res[i] = round(res[i]*100/total, 2)
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
            #
            len_query = len(query_dict)
            if len_query == 1:
                child_org = FactOEI.objects.complex_filter(query_dict).values_list("organization1", "organization2").distinct()
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
                return {}, ErrorCode.INVALID_INPUT
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
                        child_depart = FactOEI.objects.complex_filter(child_query_dict).aggregate(Avg(dimension_dict[dimension]))
                    else:
                        child_depart = FactOEI.objects.complex_filter(child_query_dict).aggregate(Avg("model"), Avg("scale2"))
                    res[child_org_list[-1]] = child_depart

            if res:
                for dic in res:
                    for item in res[dic]:
                        res[dic][item] = round(res[dic][item])

                return res, ErrorCode.SUCCESS
            else:
                return res, ErrorCode.NOT_EXISTED

        except Exception, e:
            logger.error("get report data error, msg: %s " % e)
            return res, ErrorCode.INTERNAL_ERROR

    def get_organization(self, org):
        organization = (
            'organization1', 'organization2', 'organization3', 'organization4', 'organization5', 'organization6'
        )
        org_list = org.split('.')
        query_dict = dict(zip(organization, org_list))
        return query_dict, org_list

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

        args = {"org_id": org_id,
                "profile_id": profile_id,
                "dimension_id": dimension_id,
                "population_id": population_id}
        
        try:
            #retrieve chart's data
            data, err_code = eval(self.api_mapping[api_id])(org_id=org_id,
                                                            profile_id=profile_id,
                                                            dimension_id=dimension_id,
                                                            population_id=population_id,
                                                            scale_id=scale_id)
            if err_code != ErrorCode.SUCCESS:
                return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT, {"msg": err_code})
            else:
                return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": data})
        except Exception, e:
            logger.error("dashboard error, msg is %s" % e)
            return general_json_response(status.HTTP_200_OK, ErrorCode.INTERNAL_ERROR, {"msg": "%s" %e})