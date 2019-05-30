# -*- coding:utf-8 -*-
from __future__ import division
from rest_framework import status
from utils.views import AuthenticationExceptView, WdListCreateAPIView
from utils.response import general_json_response, ErrorCode
from utils.logger import err_logger
from wduser.models import BaseOrganization, BaseOrganizationPaths
from django.db.models import Count, Avg
from workspace.models import FactOEI
from workspace.util.redispool import redis_pool


class Dedication(AuthenticationExceptView, WdListCreateAPIView):
    api_mapping = {
        # 敬业投入-整体分布
        "distribution": 'self.get_distribution',
        # 敬业投入-具体表现
        "expression": 'self.get_expression',
        # 敬业投入-整体特征
        "feature": 'self.get_feature'
    }

    def get_distribution(self, **kwargs):
        org = kwargs.get("org_id")
        department = kwargs.get('department')  # 团队比较，查下属部门
        select_id = kwargs.get('select_id')
        if not org:
            return {}, ErrorCode.INVALID_INPUT
        ret = {}
        try:
            query_dict, org = self.get_organization(org)  # org=[xxx, xxx]
            query_dicts = {u"整体": query_dict}  # {'民生xx': {'org1': '民生xxx'}}
            if department and not select_id:  # 查下属部门
                children_org = self.get_child_org(query_dict)
                for child_tpl in children_org:
                    child_org = [i for i in child_tpl if i]  # 总行.xx.xx
                    child_query_dict, org = self.get_organization(child_org)
                    query_dicts[org[-1]] = child_query_dict
            if select_id in ('profile1', 'profile2', 'profile4') and not department:  # 按条件搜索
                # 查所有类别
                types_tpl = FactOEI.objects.complex_filter(query_dict).values_list(select_id).distinct()
                types = [tpl[0] for tpl in types_tpl]  # 所有年龄分类
                for tp in types:
                    query_dict.update({select_id: tp})
                    query_dicts[tp] = query_dict
            for key in query_dicts:
                res = FactOEI.objects.complex_filter(query_dicts[key]).values_list('quota39')
                # 判断各区间分数的数量
                if res.exists():
                    total = res.count()
                    group_res = res.annotate(c=Count('id'))  # [(score, count), ...]
                    numbers = [0 for i in xrange(6)]
                    for tpl in group_res:
                        score, count = tpl
                        if score < 65:
                            numbers[0] += count
                        elif score < 70:
                            numbers[1] += count
                        elif score < 75:
                            numbers[2] += count
                        elif score < 80:
                            numbers[3] += count
                        elif score < 85:
                            numbers[4] += count
                        else:
                            numbers[5] += count
                    rates = [round(number*100/total, 2) for number in numbers]
                    ret[key] = rates
            if ret:
                return ret, ErrorCode.SUCCESS
            else:
                return {}, ErrorCode.NOT_EXISTED
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return {}, ErrorCode.INTERNAL_ERROR

    def get_expression(self, **kwargs):
        org = kwargs.get("org_id")
        department = kwargs.get('department')
        select_id = kwargs.get('select_id')
        if not org:
            return {}, ErrorCode.INVALID_INPUT
        ret = {}
        try:
            query_dict, org = self.get_organization(org)
            query_dicts = {u"整体": query_dict}
            if department and not select_id:
                children_org = self.get_child_org(query_dict)
                for child_tpl in children_org:
                    child_org = [i for i in child_tpl if i]  # 总行.xx.xx
                    child_query_dict, org = self.get_organization(child_org)
                    query_dicts[org[-1]] = child_query_dict
            if select_id in ('profile1', 'profile2', 'profile4') and not department:
                # 查所有类别
                types_tpl = FactOEI.objects.complex_filter(query_dict).values_list(select_id).distinct()
                types = [tpl[0] for tpl in types_tpl]  # 所有年龄分类
                for tp in types:
                    query_dict.update({select_id: tp})
                    query_dicts[tp] = query_dict

            for key in query_dicts:
                res = FactOEI.objects.complex_filter(query_dicts[key]).aggregate(Avg("X13"), Avg("X14"), Avg("X15"))
                # 判断各区间分数的数量
                if res:
                    res = [round(res[i]*20, 2) for i in res]
                    ret[key] = res
            if ret:
                return ret, ErrorCode.SUCCESS
            else:
                return {}, ErrorCode.NOT_EXISTED
        except Exception, e:
            err_logger.error("get report data error, msg: %s " % e)
            return {}, ErrorCode.INTERNAL_ERROR

    def get_feature(self, **kwargs):
        res = {}
        # org: org1.org2.org3.....
        org = kwargs.get("org_id")
        department = kwargs.get('department')
        select_id = kwargs.get('select_id')
        if not org:
            return res, ErrorCode.INVALID_INPUT
        try:
            query_dict = self.get_organization(org)[0]
            model = FactOEI.objects.complex_filter(query_dict).aggregate(Avg("model")).get('model__avg')
            if model:
                res = {u'整体': round(model, 2)}
                if department and not select_id:
                    children_org = self.get_child_org(query_dict)
                    child_res = {}
                    for child_tpl in children_org:
                        child_org = [i for i in child_tpl if i]  # 总行.xx.xx
                        child_query_dict, org = self.get_organization(child_org)
                        model = FactOEI.objects.complex_filter(child_query_dict).aggregate(Avg("model")).get(
                            'model__avg')
                        child_res[child_org[-1]] = round(model, 2)
                    res.update(child_res)
                if select_id in ('profile1', 'profile2', 'profile4') and not department:
                    types_tpl = FactOEI.objects.complex_filter(query_dict).values_list(select_id).distinct()
                    types = [tpl[0] for tpl in types_tpl]
                    for tp in types:
                        score = FactOEI.objects.complex_filter(query_dict).complex_filter({select_id: tp}).aggregate(
                            Avg("model")).get('model__avg')
                        res[tp] = round(score, 2)
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

    def get_child_org(self, query_dict):
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
            child_org = [[]]
        return child_org

    def get_organization(self, org):
        organization = (
            'organization1', 'organization2', 'organization3', 'organization4', 'organization5', 'organization6'
        )
        if not isinstance(org, list):
            org = org.split('.')
        query_dict = dict(zip(organization, org))
        query_dict.update({'AssessKey': self.assess_id})
        return query_dict, org

    def post(self, request, *args, **kwargs):
        api_id = self.request.data.get("api", None)
        org_id = self.request.data.get("org", None)
        assess_id = self.request.data.get('assess', None)
        department = self.request.data.get('dpt', None)
        select_id = self.request.data.get('select', None)
        try:
            if org_id:
                org_id = self.get_org_siblings(org_id)
            self.assess_id = assess_id
            data, err_code = eval(self.api_mapping[api_id])(
                org_id=org_id,
                department=department,
                select_id=select_id,
            )
            if err_code != ErrorCode.SUCCESS:
                return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT, {"msg": err_code})
            else:
                return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": data})
        except Exception, e:
            err_logger.error("dashboard error, msg is %s" % e)
            return general_json_response(status.HTTP_200_OK, ErrorCode.INTERNAL_ERROR, {"msg": "%s" % e})
