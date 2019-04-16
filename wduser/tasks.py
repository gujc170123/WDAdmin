# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import traceback
import copy

from celery import shared_task

from assessment.models import AssessProject, AssessOrganization
from front.models import PeopleSurveyRelation
from utils import str_check
from utils.aliyun.email import EmailUtils
from utils.aliyun.sms.newsms import Sms
from utils.excel import ExcelUtils
from utils.logger import get_logger
from utils.response import ErrorCode
from wduser.models import Organization, EnterpriseInfo
from wduser.user_utils import OrgImportExport, OrganizationUtils

logger = get_logger("wduser")


@shared_task
def import_org_task_old(assess_id, file_path, email=None):
    data = ExcelUtils().read_rows(file_path)
    try:
        for index, org in enumerate(data):
            if index == 0:
                continue
            ops_type = org[5]
            level = org[0]
            name = org[1]
            code = org[2]
            parent_name = org[3]
            parent_code = org[4]
            if not ops_type:
                continue
            if type(ops_type) == int:
                ops_type = str(ops_type)
            elif type(ops_type) == float:
                ops_type = str(int(ops_type))
            if ops_type in OrgImportExport.ORG_OPS_EXISTS:
                continue
            elif ops_type in OrgImportExport.ORG_OPS_DELETE:
                org = Organization.objects.get(is_active=True, assess_id=assess_id, identification_code=code)
                child_ids = OrganizationUtils.get_child_orgs(assess_id, org.id)[1]
                child_ids.append(org.id)
                Organization.objects.filter_active(id__in=child_ids).update(is_active=False)
            elif ops_type in OrgImportExport.ORG_OPS_UPDATE:
                org = Organization.objects.get(is_active=True, assess_id=assess_id, identification_code=code)
                is_modify = False
                if org.name != name:
                    org.name = name
                    is_modify = True
                if code and code != org.identification_code:
                    org.identification_code = code
                    is_modify = True
                if parent_code:
                    porg = Organization.objects.get(is_active=True, assess_id=assess_id,
                                                    identification_code=parent_code)
                    if porg.id != org.parent_id:
                        org.parent_id = porg.id
                        is_modify = True
                elif parent_name:
                    porg = Organization.objects.get(is_active=True, assess_id=assess_id,
                                                    name=parent_name)
                    if porg.id != org.parent_id:
                        org.parent_id = porg.id
                        is_modify = True
                else:
                    if org.parent_id > 0:
                        org.parent_id = 0
                        is_modify = True
                if is_modify:
                    org.save()
            elif ops_type in OrgImportExport.ORG_OPS_CREATED:
                parent_id = 0
                if parent_code:
                    porg = Organization.objects.get(is_active=True, assess_id=assess_id, identification_code=parent_code)
                    parent_id = porg.id
                elif parent_name:
                    porg = Organization.objects.get(is_active=True, assess_id=assess_id,
                                                    name=parent_name)
                    parent_id = porg.id
                if type(name) == str:
                    try:
                        name = name.encode("utf-8")
                    except Exception, e:
                        logger.error("org name encode utf8 error: %s" %e)
                # if not code:
                #     code = OrganizationUtils.generate_org_code(enterprise_id, name)
                # code 全部由系统生成
                code = OrganizationUtils.generate_org_code(assess_id, name)
                Organization.objects.create(
                    name=name, assess_id=assess_id, parent_id=parent_id,
                    identification_code=code)
        return ErrorCode.SUCCESS
    except Exception, e:
        traceback.print_exc()
        logger.error("import org data error, msg: %s, enterprise id: %s" %(e, assess_id))
        return ErrorCode.ORG_IMPORT_DATA_ERROR


@shared_task
def import_org_task(assess_id, file_path, email=None):
    data = ExcelUtils().read_rows(file_path)
    try:
        # 一:获得另一个data, 二:创建的地方全部拿出来,一起创建,下一个创建要用到前一个id, 所以1
        # 要检查一遍参数再遍历一个创建,那么就遍历2遍
        org_list_list = []
        new_parent_list = []
        for index, org in enumerate(data):
            # 一行组织
            org_list_list.append(org)
            if index == 0:
                continue
            #  所有分组不得与某分组的一级分组相同
            if len(org) > 0:
                new_parent_list.append(str_check(org[0]))
            for index, org_name in enumerate(org):
                # 一个组织
                if not org_name:
                    break
                # 检查新数据对新数据合法
                if index != 0:
                    # 次级组织名不能与某一级的一级名相同
                    if org_name in new_parent_list:
                        return ErrorCode.ORG_NAME_DOUBLE_ERROR
                org_name = str_check(org_name)
                # 检查新数据对旧数据合法
                def check_org_name(name, assess_id):
                    org_qs = Organization.objects.filter_active(name=name, assess_id=assess_id, parent_id=0)
                    # 分两次导入的话,后台不知道是同名的组织,还是一个新组织,所以还是不允许导入拓展,拓展请手动.
                    # get_or_create的话也可以不用判断
                    if org_qs.count() > 0:
                        return ErrorCode.ORG_NAME_DOUBLE_ERROR
                    else:
                        return ErrorCode.SUCCESS
                ret = check_org_name(org_name, assess_id)
                if ret != ErrorCode.SUCCESS:
                    return ret
        # 至此数据合法
        for index, org in enumerate(org_list_list):
        # for index, org in enumerate(data):
            if index == 0:
                # title
                continue
            parent_id = 0
            for org_name in org:
                # 一行组织中的每一个组织的创建
                if not org_name:
                    break
                org_name = str_check(org_name)
                org_obj, is_created = Organization.objects.get_or_create(
                    is_active=True,
                    assess_id=assess_id,
                    name=org_name,
                    parent_id=parent_id
                )
                if is_created:
                    # 仅刚创建的时候才需要关联
                    org_obj.identification_code = OrganizationUtils.generate_org_code(assess_id, org_name)
                    org_obj.save()
                    AssessOrganization.objects.create(
                        assess_id=assess_id,
                        organization_id=org_obj.id,
                        organization_code=org_obj.identification_code
                    )
                parent_id = org_obj.id
        return ErrorCode.SUCCESS
    except Exception, e:
        traceback.print_exc()
        logger.error("import org data error, msg: %s, assess_id id: %s" %(e, assess_id))
        return ErrorCode.ORG_IMPORT_DATA_ERROR


@shared_task
def send_general_code(code, phone=None, email=None):
    if phone:
        Sms.send_general_code(code, [phone])
    if email:
        EmailUtils().send_general_code(code, email)


@shared_task
def enterprise_statistics_test_user():
    u"""企业参测人次统计"""
    enterprise_qs = EnterpriseInfo.objects.filter_active()
    for enterprise in enterprise_qs:
        # project_ids = list(AssessProject.objects.filter_active(enterprise_id=enterprise.id).values_list("id", flat=True))
        # test_count = PeopleSurveyRelation.objects.filter_active(
        #     project_id__in=project_ids
        # ).count()
        # if enterprise.test_count != test_count:
        #     enterprise.test_count = test_count
        #     enterprise.save()
        project_user_counts = AssessProject.objects.filter_active(enterprise_id=enterprise.id).values_list(
            "user_count", flat=True)
        count = 0
        for project_user_count in project_user_counts:
            count += project_user_count
        # 企业完成人次
        if enterprise.test_count != count:
            enterprise.test_count = count
            enterprise.save()






