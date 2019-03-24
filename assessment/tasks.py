# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import copy
import hashlib
import json
import operator
import shutil
import time
import traceback
import datetime
import time
import os
import re

# import openpyxl
from celery import shared_task
from django.contrib.auth.hashers import make_password

from WeiDuAdmin import settings
from assessment.assess_utils import AssessImportExport
from assessment.models import AssessUser, AssessProject, AssessSurveyRelation, AssessSurveyUserDistribute
# from assessment.views import AssessSurveyUserExport
from front.models import SurveyQuestionInfo, SurveyInfo, PeopleSurveyRelation, UserQuestionAnswerInfo
from front.tasks import survey_sync, survey_question_sync
from question.models import Question
from research.models import ResearchModel
from research.serializers import ResearchModelDetailSerializer
from survey.models import Survey
from utils import get_random_int, get_random_char, str_check, zip_folder, data2file
from utils.aliyun.email import EmailUtils
from utils.aliyun.oss import AliyunOss
from utils.aliyun.sms.newsms import Sms
from utils.excel import ExcelUtils
from utils.logger import get_logger
from utils.regular import RegularUtils
from utils.rpc_service.clientservice import ClientService
from utils.response import ErrorCode
from wduser.models import People, PeopleOrganization, AuthUser, Organization, EnterpriseAccount, PeopleAccount

logger = get_logger("assessment")

DINGZHI_4_TYPE_ACCOUNT = ['4', '5', '1', '-1']  # 模板那边,导出这里,手动新增 共3处
# 联合办公账号OA 1
# 身份证号 2
# 员工编号 3
# 飞行网账号 4


def check_account_in_enterprise(account, all_user_account, new_account_name=[]):
    if account in all_user_account:
        return ErrorCode.FAILURE
    if account in new_account_name:
        return ErrorCode.FAILURE
    return ErrorCode.SUCCESS


def get_all_account_in_enterprise(enterprise_id):
    all_user_account = EnterpriseAccount.objects.filter_active(enterprise_id=enterprise_id).values_list("account_name", flat=True)
    return all_user_account


def check_birthday(birthday):
    try:
        birthday = int(birthday)
        year = birthday / 10000
        month = (birthday % 10000 / 100)
        day = (birthday % 100)
        if (year > 1900) and (0 < month < 13) and (0 < day < 32):
            return ErrorCode.SUCCESS
        else:
            return ErrorCode.FAILURE
    except:
        return ErrorCode.FAILURE


def get_active_code():
    return get_random_int(8)


def get_orgs(org_names, assess_id):
    orgs = []
    for index in range(len(org_names)):
        org = get_org(org_names[0:index+1], assess_id)
        if org:
            orgs.append(org)
    return orgs


def get_org(org_names, assess_id, index=0, parent_id=0):
    # 根据项目id 和组织名字和父组织id找到该组织
    org_qs = Organization.objects.filter_active(assess_id=assess_id, name=org_names[index], parent_id=parent_id)
    if not org_qs or org_qs.count() > 1:
        return None
    org = org_qs[0]
    if index == len(org_names) - 1:
        return org
    return get_org(org_names, assess_id, index+1, org.id)


def str_check(str_obj):
    if type(str_obj) == int or type(str_obj) == long:
        str_obj = str(long(str_obj))
    elif type(str_obj) == float:
        str_obj = str(long(str_obj))
    return str_obj


def get_mima(mima):
    mima = str_check(mima)    # 密码
    mima = str('123456' if not mima else mima)
    return make_password(mima)


def get_moreinfos(infos, key_names, free_infos_name, free_infos):
    key_infos = [{"key_name": y, "key_value": x} for (x, y) in zip(infos, key_names[6:]) if x]
    if free_infos_name and free_infos:
        key_infos_free = [{"key_name": n, "key_value": m} for (m, n) in zip(free_infos, free_infos_name) if m]
        key_infos.extend(key_infos_free)
    str_key_info = json.dumps(key_infos)
    return str_key_info


def get_orgs_info(info):
    org_names = []
    for name in info:
        if name:
            org_names.append(name)
    return org_names


def do_old_authuser(old_authuser_obj_info_list):
    titles = AssessImportExport.get_title()
    key_names = []
    hash_mima = get_mima(u'')
    for key_name in titles:
        key_names.append(key_name.split("(")[0])
    try:
        finish_authuser = []
        for i, old_authuser_obj_info in enumerate(old_authuser_obj_info_list):
            if i % 2000 == 0:
                logger.info("old_au_change")
            old_authuser_id = old_authuser_obj_info[0]
            old_authuser_obj = AuthUser.objects.get(id=old_authuser_id)
            old_authuser_info = old_authuser_obj_info[1]
            if old_authuser_info["mima_row"]:
                mima = get_mima(old_authuser_info["mima_row"])
            else:
                mima = hash_mima
            old_authuser_info["moreinfo"] = get_moreinfos(old_authuser_info["moreinfo_row"], key_names,
                                                          old_authuser_info["free_infos_name"],
                                                          old_authuser_info["free_infos"])
            # 这里的手机邮箱都是同一个或新增的，

            del old_authuser_info["moreinfo_row"]
            del old_authuser_info["free_infos_name"]
            del old_authuser_info["free_infos"]
            is_change = False
            if old_authuser_obj.nickname != old_authuser_info["nickname"] or \
                    old_authuser_obj.phone != old_authuser_info["phone"] or \
                    old_authuser_obj.email != old_authuser_info["email"] or old_authuser_info["mima_row"]:
                is_change = True
            if is_change:
                old_authuser_obj.nickname = old_authuser_info["nickname"]
                old_authuser_obj.phone = old_authuser_info["phone"]
                old_authuser_obj.email = old_authuser_info["email"]
                old_authuser_obj.password = mima
                old_authuser_obj.save()
            finish_authuser.append((old_authuser_obj, old_authuser_info))
        return ErrorCode.SUCCESS, finish_authuser
    except Exception, e:
        logger.error("do_old_authuser, msg(%s)" % e)
        return ErrorCode.FAILURE, None, u'修改的人员不合法'


def do_new_authusers(new_authusers):
    """input info_dict_list
    return [(auther_obj,info_dict)]"""
    titles = AssessImportExport.get_title()
    key_names = []
    hash_mima = get_mima(u'')
    for key_name in titles:
        key_names.append(key_name.split("(")[0])
    try:
        finish_authusers = []
        au_b_create_list = []
        for i, new_authuser in enumerate(new_authusers):
            new_authuser["moreinfo"] = get_moreinfos(new_authuser["moreinfo_row"], key_names,
                                                     new_authuser["free_infos_name"], new_authuser["free_infos"])
            del new_authuser["moreinfo_row"]
            del new_authuser["free_infos_name"]
            del new_authuser["free_infos"]
            nickname = new_authuser["nickname"]
            account = new_authuser["account"]
            phone = new_authuser["phone"]
            email = new_authuser["email"]
            if new_authuser["mima_row"]:
                new_authuser["mima"] = get_mima(new_authuser["mima_row"])
                mima = new_authuser["mima"]
            else:
                mima = hash_mima
            randomname = account + nickname + get_random_char(6)
            au_b_create_list.append(
                AuthUser(
                    username=randomname,
                    nickname=nickname,
                    account_name=account,
                    password=mima,
                    phone=phone,
                    email=email
                )
            )
            if i % 2000 == 1:
                AuthUser.objects.bulk_create(au_b_create_list)
                logger.info("au_b_create")
                au_b_create_list = []
        #  人数太多会出现 所以 拆分 'MySQL server has gone away'
        if au_b_create_list:
            AuthUser.objects.bulk_create(au_b_create_list)
        for i, new_authuser in enumerate(new_authusers):
            nickname = new_authuser["nickname"]
            account = new_authuser["account"]
            phone = new_authuser["phone"]
            email = new_authuser["email"]
            authuser_obj = AuthUser.objects.filter(
                nickname=nickname,
                account_name=account,
                phone=phone,
                email=email
            )
            finish_authusers.append((authuser_obj[0], new_authuser))

        return ErrorCode.SUCCESS, finish_authusers
    except Exception, e:
        logger.error("do_new_authuser, msg(%s)" % e)
        return ErrorCode.FAILURE, None, u"新增的人员名字不合法"


def check_data_is_error(nickname, account, phone, email, org_names, index, project_id):
    if not nickname:
        logger.error("import data not find nickname: %s" % index)
        return ErrorCode.PROJECT_SURVEY_USER_IMPORT_ERROR, index, u"姓名为必填"
    if not phone and not email and not account:
        logger.error("import data not find phone email account: %s" % index)
        return ErrorCode.PROJECT_SURVEY_USER_IMPORT_ERROR, index, u"帐号/手机/邮箱为必填一个字段"
    if not org_names:
        logger.error("import data not find orgs: %s" % index)
        return ErrorCode.PROJECT_SURVEY_USER_IMPORT_ERROR, index, u"项目组织为必填字段"
    try:
        org = get_org(org_names, project_id)
        if not org:
            return ErrorCode.FAILURE, index, u'项目组织输入有误'
        "获得组织码"
        org_codes = [org.identification_code]
        return ErrorCode.SUCCESS, org_codes
    #     检查组织合法  获得 组织码
    except:
        return ErrorCode.PROJECT_SURVEY_USER_IMPORT_ERROR, index, u"项目组织输入有误"


def do_people(finish_authusers):
    try:
        po_b_create_list = []
        finish_peoples = []
        for i, finish_authser in enumerate(finish_authusers):
            authuser_obj = finish_authser[0]
            info_dict = finish_authser[1]
            nickname = authuser_obj.nickname
            user_id = authuser_obj.id
            phone = authuser_obj.phone
            email = authuser_obj.email
            active_code = get_active_code()
            moreinfo = info_dict["moreinfo"]
            people_obj = People.objects.filter_active(user_id=user_id)
            if people_obj:
                people_obj.update(username=nickname, phone=phone, email=email, more_info=moreinfo)
                finish_peoples.append((user_id, info_dict))
            else:
                po_b_create_list.append(
                    People(
                        username=nickname,
                        user_id=user_id,
                        phone=phone,
                        email=email,
                        active_code=active_code,
                        active_code_valid=True,
                        more_info=moreinfo
                    )
                )
                finish_peoples.append((user_id, info_dict))
            if i % 2000 == 1:
                People.objects.bulk_create(po_b_create_list)
                logger.info("po_b_create")
                po_b_create_list = []
        if po_b_create_list:
            People.objects.bulk_create(po_b_create_list)
        return ErrorCode.SUCCESS, finish_peoples
    except Exception, e:
        logger.error("do_people, msg(%s)" % e)
        return ErrorCode.FAILURE, None, u"用户参与测评失败"


def au_id_to_po_obj(finish_peoples):
    finish_people_change = []
    for x in finish_peoples:
        p_qs = People.objects.filter_active(user_id=x[0])
        finish_people_change.append((p_qs[0],x[1]))
    return finish_people_change


def do_assessuser(finish_peoples, assess_id):
    try:
        au_b_create_list = []
        for i, finish_people in enumerate(finish_peoples):
            people_id = finish_people[0].id
            if AssessUser.objects.filter_active(people_id=people_id, assess_id=assess_id):
                pass
            else:
                au_b_create_list.append(
                    AssessUser(assess_id=assess_id, people_id=people_id)
                )
            if i % 2000 == 1:
                AssessUser.objects.bulk_create(au_b_create_list)
                logger.info("au_b_create")
                au_b_create_list = []
        if au_b_create_list:
            AssessUser.objects.bulk_create(au_b_create_list)
        return ErrorCode.SUCCESS, None
    except Exception, e:
        logger.error("do_assessuser, msg(%s)" % e)
        return ErrorCode.FAILURE, None, u'用户参与项目失败'


def do_enterprise(finish_peoples, assess_id):
    try:
        ea_b_create_list = []
        enterprise_id = AssessProject.objects.get(id=assess_id).enterprise_id
        for i, finish_people in enumerate(finish_peoples):
            assess_id = assess_id
            people_obj = finish_people[0]
            infos= finish_people[1]
            ea_qs = EnterpriseAccount.objects.filter_active(user_id=people_obj.user_id, enterprise_id=enterprise_id)
            if infos["account"]:
                if not ea_qs.exists():
                    ea_b_create_list.append(
                        EnterpriseAccount(
                            enterprise_id=enterprise_id,
                            account_name=infos["account"],
                            user_id=people_obj.user_id,
                            people_id=people_obj.id
                        )
                    )
                elif ea_qs.count() == 1:
                    ea_qs.update(account_name=infos["account"])
                else:
                    logger.error("user_id %s 在企业 %s 下有2个账户 " % (str(people_obj.user_id), str(enterprise_id)))
                    return ErrorCode.FAILURE, None, u"用户在企业下有2和账户"
            if i % 2000 == 1:
                EnterpriseAccount.objects.bulk_create(ea_b_create_list)
                logger.info("ea_b_create")
                ea_b_create_list = []
        if ea_b_create_list:
            EnterpriseAccount.objects.bulk_create(ea_b_create_list)
        return ErrorCode.SUCCESS, None
    except Exception, e:
        logger.error("do_enterprise, msg(%s)" % e)
        return ErrorCode.FAILURE, None, u'用户参与企业失败'


def do_people_account(finish_peoples, assess_id):
    try:
        pa_b_create_list = []
        ep_id = AssessProject.objects.get(id=assess_id).enterprise_id
        for finish_people in finish_peoples:
            people_obj = finish_people[0]
            infos= finish_people[1]
            PeopleAccount.objects.filter_active(people_id=people_obj.id).update(is_active=False)
            for index in range(4):
                type_value = "type%s" % str(index+1)
                if infos[type_value]:
                    pa_b_create_list.append(
                        PeopleAccount(account_value=infos[type_value], account_type=int(DINGZHI_4_TYPE_ACCOUNT[index]), people_id=people_obj.id, enterprise_id=ep_id)
                    )
            if len(pa_b_create_list) > 2000:
                PeopleAccount.objects.bulk_create(pa_b_create_list)
                logger.info("pa_b_create")
                pa_b_create_list = []
        if pa_b_create_list:
            PeopleAccount.objects.bulk_create(pa_b_create_list)
        return ErrorCode.SUCCESS, None
    except Exception, e:
        logger.error("do_people_account error, msg(%s)" % e)
        return ErrorCode.FAILURE, None, u'用户创建账户失败'


def do_org(finish_peoples):
    try:
        people_org_list = []
        for i, finish_people in enumerate(finish_peoples):
            people = finish_people[0]
            org_codes = finish_people[1]["orgs_codes"]
            if finish_people[1]["ops"] == "修改":
                PeopleOrganization.objects.filter_active(people_id=people.id).update(is_active=False)
            for org_code in org_codes:
                po_qs = PeopleOrganization.objects.filter_active(
                    people_id=people.id, org_code=org_code
                    )
                if not po_qs.exists():
                    people_org_list.append(
                        PeopleOrganization(
                            people_id=people.id, org_code=org_code
                            )
                    )
                if i % 2000 == 1:
                    PeopleOrganization.objects.bulk_create(people_org_list)
                    logger.info("p_org_b_create")
                    people_org_list = []
        if people_org_list:
            PeopleOrganization.objects.bulk_create(people_org_list)
        return ErrorCode.SUCCESS, None
    except Exception, e:
        logger.error("do_org, msg(%s)" % e)
        return ErrorCode.FAILURE, None, u'组织修改失败'


def do_dedicated_link(authusers):
    try:
        for authuser in authusers:
            authuser_obj = authuser[0]
            if not authuser_obj.dedicated_link:
                id_str = "%10d" % authuser_obj.id
                sha1 = hashlib.sha1()
                sha1.update(id_str)
                dedicated_link = sha1.hexdigest()
                authuser_obj.dedicated_link = dedicated_link
                authuser_obj.save()
        return ErrorCode.SUCCESS, None
    except Exception, e:
        logger.error("do_dedicated_link, msg(%s)" % e)
        return ErrorCode.FAILURE, None, u'专属链接生成失败'


def check_phone(phone):
    authuser_phone_obj = AuthUser.objects.filter(phone=phone, is_active=True)
    if authuser_phone_obj.count() > 1:
        return ErrorCode.FAILURE, '手机号有误'
    else:
        if not authuser_phone_obj:
            return ErrorCode.SUCCESS, None
        return ErrorCode.SUCCESS, authuser_phone_obj[0]


def check_email(email):
    authuser_email_obj = AuthUser.objects.filter(email=email, is_active=True)
    if authuser_email_obj.count() > 1:
        return ErrorCode.FAILURE, 'email有误'
    else:
        if not authuser_email_obj:
            return ErrorCode.SUCCESS, None
        return ErrorCode.SUCCESS, authuser_email_obj[0]


def check_account(account, nickname):
    return ErrorCode.SUCCESS, list(AuthUser.objects.filter(account_name=account, nickname=nickname, is_active=True))


def delete_assesssurveyuserdistribute(assess_id, people_ids):
    assesssurveyuserdistribute_qs = AssessSurveyUserDistribute.objects.filter_active(assess_id=assess_id)
    for assesssurveyuserdistribute_obj in assesssurveyuserdistribute_qs:
        distribute_people_ids = json.loads(assesssurveyuserdistribute_obj.people_ids)
        for id in people_ids:
            if id in distribute_people_ids:
                distribute_people_ids.remove(id)
        new_people_ids = json.dumps(distribute_people_ids)
        assesssurveyuserdistribute_obj.people_ids = new_people_ids
        assesssurveyuserdistribute_obj.save()


def delete_obj(authuser_obj, assess_id, org_codes):
    try:
        people_ids = list(People.objects.filter_active(user_id=authuser_obj.id).values_list("id", flat=True))
        # 删除 人与组织的关系, 删除项目中的这个人, 删除项目问卷关联, 删除项目问卷发放关联, 即这个用户还在
        PeopleOrganization.objects.filter_active(people_id__in=people_ids, org_code__in=org_codes).update(is_active=False)
        AssessUser.objects.filter_active(assess_id=assess_id,people_id__in=people_ids).update(is_active=False)
        PeopleSurveyRelation.objects.filter_active(project_id=assess_id, people_id__in=people_ids).update(is_active=False)
        delete_assesssurveyuserdistribute(assess_id, people_ids)
    except Exception, e:
        logger.error("delete_people error, 没有可删除的对象, msg(%s)" % e)
        return ErrorCode.FAILURE, None, u"用户参与测评失败"


@shared_task
def send_survey_question_to_client(assess_id, survey_id, role_type):
    json_data = {u'questionList': [{u'average_score': 0.0, u'code': u'001001001001001', u'question_category': 10, u'title':
u'<p>\u5355\u9009\u9898\u6d4b\u8bd51</p>', u'uniformity_question_id': 0, u'passage': None, u'use_count': 0, u'standard_deviation': 0.0, u'question_bank_id': 1, u'question_facet_id': 1, u'question_type': 10, u'question_folder_id': 2, u'uniformity_question_info': {}, u'options': {u'option_data': [{u'is_blank': False, u'content': u'<p>\u9009\u98791</p>', u'parent_id': 0, u'score': 10.0, u'order_number': 0, u'id': 1, u'question_id': 1}, {u'is_blank': False, u'content': u'<p>\u9009\u98792</p>', u'parent_id': 0, u'score': 30.0,
u'order_number': 1, u'id': 2, u'question_id': 1}, {u'is_blank': False, u'content': u'<p>\u9009\u98793</p>', u'parent_id': 0, u'score': 30.0, u'order_number': 2, u'id': 3, u'question_id': 1}], u'config_info': {u'max_choose': None}}, u'id': 1, u'list_custom_attrs':
[], u'question_folder_parent_id': 1}, {u'average_score': 0.0, u'code': u'001001001001002', u'question_category': 10, u'title': u'<p>\u591a\u9009\u9898\u6d4b\u8bd5</p>', u'uniformity_question_id': 0, u'passage': None, u'use_count': 0, u'standard_deviation': 0.0, u'question_bank_id': 1, u'question_facet_id': 1, u'question_type': 30, u'question_folder_id': 2, u'uniformity_question_info': {}, u'options': {u'option_data': [{u'is_blank': False, u'content': u'<p>\u591a\u9009\u9009\u62e9\u98791</p>', u'parent_id': 0, u'score': 0.0, u'order_number': 0, u'id': 4, u'question_id': 2}, {u'is_blank': False, u'content': u'<p>\u591a\u9009\u9009\u62e9\u98792</p>', u'parent_id': 0, u'score': 0.0, u'order_number': 1, u'id': 5, u'question_id': 2}, {u'is_blank': False, u'content': u'<p>\u591a\u9009\u9009\u62e9\u98793</p>', u'parent_id': 0, u'score': 0.0, u'order_number': 2, u'id': 6, u'question_id': 2}, {u'is_blank': False, u'content': u'<p>\u591a\u9009\u9009\u62e9\u98794</p>', u'parent_id': 0, u'score': 0.0, u'order_number': 3, u'id': 7, u'question_id': 2}], u'config_info': {u'max_choose': 3}}, u'id': 2, u'list_custom_attrs': [], u'question_folder_parent_id': 1}, {u'average_score': 0.0, u'code': u'001001001001003', u'question_category': 10, u'title': u'<p>\u5355\u9009\u586b\u7a7a</p>', u'uniformity_question_id': 0, u'passage': None, u'use_count': 0, u'standard_deviation': 0.0, u'question_bank_id': 1, u'question_facet_id': 1, u'question_type': 11, u'question_folder_id': 2, u'uniformity_question_info': {}, u'options': {u'option_data': [{u'is_blank': False, u'content': u'<p>\u9009\u98791</p>', u'parent_id': 0, u'score': 0.0, u'order_number': 0, u'id': 8, u'question_id': 3}, {u'is_blank': False, u'content': u'<p>\u9009\u98792</p>', u'parent_id': 0, u'score': 0.0, u'order_number': 1, u'id': 9, u'question_id': 3}, {u'is_blank': False, u'content': u'<p>\u9009\u98793</p>', u'parent_id': 0, u'score': 0.0, u'order_number': 2, u'id': 10, u'question_id': 3}, {u'is_blank': False, u'content': u'<p>\u90094</p>', u'parent_id': 0, u'score': 0.0, u'order_number': 3, u'id': 11, u'question_id': 3}, {u'is_blank': True, u'content': u'<p>\u9009\u98795</p>', u'parent_id': 0, u'score': 0.0, u'order_number': 4, u'id': 12, u'question_id': 3}], u'config_info': {u'max_choose': None}}, u'id': 3, u'list_custom_attrs': [], u'question_folder_parent_id': 1}, {u'average_score': 0.0, u'code': u'001001001001004', u'question_category': 10, u'title': u'<p>\u591a\u9009\u586b\u7a7a</p>', u'uniformity_question_id': 0, u'passage': None, u'use_count': 0, u'standard_deviation': 0.0, u'question_bank_id': 1, u'question_facet_id': 1, u'question_type': 31, u'question_folder_id': 2, u'uniformity_question_info': {}, u'options': {u'option_data': [{u'is_blank': False, u'content': u'<p>\u591a\u90091</p>', u'parent_id': 0, u'score': 0.0, u'order_number': 0, u'id': 13, u'question_id': 4}, {u'is_blank': False, u'content': u'<p>\u591a\u90092</p>', u'parent_id': 0, u'score': 0.0, u'order_number': 1, u'id': 14, u'question_id': 4}, {u'is_blank': False, u'content': u'<p>\u591a\u90093</p>', u'parent_id': 0, u'score': 0.0, u'order_number': 2, u'id': 15, u'question_id': 4}, {u'is_blank': True,
u'content': u'<p>\u591a\u90094</p>', u'parent_id': 0, u'score': 0.0, u'order_number': 3, u'id': 16, u'question_id': 4}], u'config_info': {u'max_choose': None}}, u'id': 4, u'list_custom_attrs': [], u'question_folder_parent_id': 1}, {u'average_score': 0.0, u'code':
u'001001001001005', u'question_category': 10, u'title': u'<p>\u4e92\u65a5\u9898\u6d4b\u8bd51</p>', u'uniformity_question_id': 0, u'passage': None, u'use_count': 0, u'standard_deviation': 0.0, u'question_bank_id': 1, u'question_facet_id': 1, u'question_type': 50, u'question_folder_id': 2, u'uniformity_question_info': {}, u'options': {u'options': [{u'is_blank': False, u'content': u'<p>\u54c8\u54c8\u54c8\u54c8\u54c8</p>', u'parent_id': 0, u'score': 0.0, u'scores': [1.0, 2.0], u'order_number': 0, u'id': 17, u'question_id': 5}, {u'is_blank': False, u'content': u'<p>\u5566\u5566\u5566\u5566\u5566</p>', u'parent_id': 0, u'score': 0.0, u'scores': [2.0, 3.0], u'order_number': 1, u'id': 20, u'question_id': 5}, {u'is_blank': False, u'content': u'<p>\u563f\u563f\u563f\u548cIE hi \u6076\u5316&nbsp;</p>', u'parent_id': 0, u'score': 0.0, u'scores': [4.0, 3.0], u'order_number': 2, u'id': 23, u'question_id': 5}], u'options_titles': [u'\u6700\u7b26\u5408', u'\u4e0d\u6700\u7b26\u5408']}, u'id': 5, u'list_custom_attrs': [], u'question_folder_parent_id': 1}, {u'average_score': 0.0, u'code': u'001001001001006', u'question_category': 10, u'title': u'<p>\u6ed1\u5757\u9898\u6d4b\u8bd5</p>', u'uniformity_question_id': 0, u'passage': None, u'use_count': 0, u'standard_deviation': 0.0, u'question_bank_id': 1, u'question_facet_id': 1, u'question_type': 60, u'question_folder_id': 2, u'uniformity_question_info': {}, u'options': {u'default_value': u'12', u'max_desc': u'<p>zuida</p>', u'min_desc': u'<p>\u6700\u5c0f</p>', u'max_value': u'90', u'min_value': u'12', u'step_value': u'1', u'default_desc': u''}, u'id': 6, u'list_custom_attrs': [], u'question_folder_parent_id': 1}], u'project': u'\u65b0\u589e\u6d4b\u8bd5\u9879\u76ee', u'description': u'asdasdasd', u'blockList': [], u'organizationId': [u'1', u'2', u'3'], u'questionnaireId': 8, u'benchmarkType': 1, u'expiredTime': u'2018-07-11T06:07:08Z', u'carouselUrl': None, u'project_id': 6, u'createTime': u'2018-07-01T18:05:18Z', u'name': u'\u95ee\u5377\u6d4b\u8bd58'}
    # print json_data
    ClientService.send_survey_question(json_data)


@shared_task
def send_survey_active_codes(people_ids):
    u"""发送问卷的激活码"""
    for people_id in people_ids:
        people = People.objects.get(id=people_id)
        if not people.active_code:
            people.active_code = get_active_code()
            people.active_code_valid = True
            people.save()
        if people.phone:
            Sms.send_activate_code(people.active_code, [people.phone])
        if people.email:
            EmailUtils().send_active_code(people.active_code, people.email)
        if not people.active_code_valid:
            people.active_code_valid = True
            people.save()


@shared_task
def statistics_project_survey_user_count(project_id):
    try:
        project_surveys = AssessSurveyRelation.objects.filter_active(assess_id=project_id)
        for project_survey in project_surveys:
            count = PeopleSurveyRelation.objects.filter_active(
                survey_id=project_survey.survey_id, project_id=project_survey.assess_id).values_list(
                "people_id", flat=True).distinct().count()
            if count != project_survey.user_count:
                project_survey.user_count = count
                project_survey.save()
    except Exception, e:
        logger.error("statistics_project_survey_user_count error, msg: %s" % e)


@shared_task
def statistics_user_count(enterprise_id):
    if enterprise_id == 'all':
        return
    else:
        try:
            projects = AssessProject.objects.filter_active(enterprise_id=enterprise_id)
        except:
            return
    logger.debug("statistics_user_count of enterprise: %s" % enterprise_id)
    for project in projects:
        all_count = PeopleSurveyRelation.objects.filter_active(project_id=project.id).values_list(
            "people_id", flat=True
        ).distinct().count()
        unfinish_count = PeopleSurveyRelation.objects.filter_active(project_id=project.id,
                                                                    status__lt=PeopleSurveyRelation.STATUS_FINISH).values_list(
            "people_id", flat=True
        ).distinct().count()
        test_count = all_count - unfinish_count
        if project.user_count != test_count:
            logger.debug("update project user count: %s" % project.id)
            project.user_count = test_count
            project.save()


@shared_task
def distribute_project(enterprise_id=None, distribute_project_id=None):
    u"""
    项目发布后，题目和问卷（配置）信息，都不会再变化，
    即使问卷或题目做了调整，以及项目时间做了调整"""
    if distribute_project_id is None:
        if enterprise_id == 'all':
            return
        now = datetime.datetime.now()
        if enterprise_id:
            projects = AssessProject.objects.filter_active(enterprise_id=enterprise_id, begin_time__lt=now)
        else:
            projects = AssessProject.objects.filter_active(begin_time__lt=now)
        logger.debug("distribute_project of enterprise: %s" % enterprise_id)
    else:
        projects = AssessProject.objects.filter_active(id=distribute_project_id)
        logger.debug("distribute_project of enterprise project: %s" % distribute_project_id)
    # 发布过的项目，可能有新添加的问卷
    projects.filter(has_distributed=False).update(has_distributed=True)
    for project in projects:
        project_id = project.id
        logger.debug("distribute_project of enterprise: %s, project id: %s" %(enterprise_id, project_id))
        survey_ids = AssessSurveyRelation.objects.filter_active(assess_id=project_id).values_list("survey_id", flat=True)
        for survey_id in survey_ids:
            survey_infos = SurveyInfo.objects.filter_active(survey_id=survey_id, project_id=project_id)
            if survey_infos.exists():
                survey_info = survey_infos[0]
            else:
                survey_info = survey_sync(survey_id, project_id)
            if not survey_info:
                continue
            # 迫选组卷 逐题测试
            if survey_info.test_type == SurveyInfo.TEST_TYPE_BY_QUESTION or survey_info.form_type == Survey.FORM_TYPE_FORCE:
                if not SurveyQuestionInfo.objects.filter_active(
                        survey_id=survey_id, project_id=project_id, block_id=0).exists():
                    survey_question_sync(survey_id, project_id, 0)
            else:
                # 按部分测试
                # 所有部分
                block_info = json.loads(survey_info.block_info)
                for block in block_info:
                    if block["id"] and not SurveyQuestionInfo.objects.filter_active(
                            survey_id=survey_id, project_id=project_id, block_id=block["id"]).exists():
                        survey_question_sync(survey_id, project_id, block["id"])


@shared_task
def check_people_status_change(projet_id):
    pass


@shared_task
def file_task(authuser_obj_id, authuser_obj_email, people_ids, project_id):

    def down_data_to_file(url, file_name, file_path):
        import urllib2
        logger.debug("download report url is %s" % url)
        req = urllib2.Request(url.encode("utf-8"))
        rst = urllib2.urlopen(req)
        fdata = rst.read()
        if not os.path.exists(file_path):
            os.makedirs(file_path)
        data2file(fdata, file_name, file_path)

    def get_file(authuser_obj_id, people_ids, project_id):
        people_ids = [str(id) for id in people_ids]
        logger.debug("%s download report people ids is %s" % (str(authuser_obj_id), ",".join(people_ids)))
        now = datetime.datetime.now().strftime("%Y-%m-%d")
        timestamp = int(time.time()*100)
        parent_path = "%s-report-download-%s" % (str(authuser_obj_id), str(timestamp))
        zip_path = os.path.join("download", "report", now, parent_path)
        file_path = os.path.join(zip_path, 'report')
        for people_id in people_ids:
            people = People.objects.get(id=people_id)
            relations = PeopleSurveyRelation.objects.filter_active(
                    project_id=project_id,
                    people_id=people_id,
                    report_status=PeopleSurveyRelation.REPORT_SUCCESS,
                    report_url__isnull=False,
                    status=PeopleSurveyRelation.STATUS_FINISH,  # 未完成人员不参与报告下载
                )
            if relations.exists():
                if people.username is None:
                    logger.debug('people id=%s 没有username' % str(people.id))
                    people.username = 'No username'
                # people_file_path = os.path.join(file_path, "%s_%s" % (people.username, people.id))
                account_name = AuthUser.objects.filter(id=people.user_id).values_list("account_name", flat=True)
                account_b = None
                if account_name.exists():
                    account_b = account_name[0]
                phone = people.phone
                email = people.email
                if account_b:
                    fold_name_b = account_b
                elif phone:
                    fold_name_b = phone
                elif email:
                    fold_name_b = email
                else:
                    fold_name_b = people.id
                # a if a else (b if b else (c if c else d))
                # 这里只下载报告成功生成的且有报告地址的，正常不会有未完成的报告。
                people_file_path = os.path.join(file_path, "%s_%s" % (people.username, fold_name_b))
                # people_file_path = os.path.join(file_path, people.username)
                for relation in relations:
                    if relation.report_url:
                        down_data_to_file(relation.report_url, u"%s.pdf" % relation.survey_name, people_file_path)
        zip_file_path = "%s.zip" % zip_path
        if not os.path.exists(file_path):
            return None, None
        zip_folder(zip_path, zip_file_path)
        default_export_file_name = "%s.zip" % parent_path
        return zip_file_path, default_export_file_name

    def send_file_email(email, path):
        EmailUtils().send_oss_report_path(path, email)

    file_full_path, file_full_name = get_file(authuser_obj_id, people_ids, project_id)
    if file_full_path is None:
        oss_keys = u'您没有报告可以下载'
    else:
        oss_keys = AliyunOss().upload_file(authuser_obj_id, file_full_name, file_full_path, prefix='wdadmin')
    send_file_email(authuser_obj_email, oss_keys)


@shared_task
def search_key_words(qs, search_sql_people, search_sql_authuser, search_sql_org):
    query_people = reduce(operator.or_, search_sql_people)
    qs_people_raw = qs
    qs_people = qs_people_raw.filter(query_people).values_list("id", flat=True)
    # authuser_acocunt_name 中到关键字
    query_authuser = reduce(operator.or_, search_sql_authuser)
    qs_user_ids = qs.values_list('user_id', flat=True)
    qs_authuser_raw = AuthUser.objects.filter(id__in=qs_user_ids)
    qs_authuser = qs_authuser_raw.filter(query_authuser).values_list("id", flat=True)
    qs_authuser = qs.filter(user_id__in=qs_authuser).values_list("id", flat=True)
    # 组织名中找关键字
    query_org = reduce(operator.or_, search_sql_org)
    qs_ids = qs.values_list('id', flat=True)
    qs_org_codes = PeopleOrganization.objects.filter_active(people_id__in=qs_ids).values_list("org_code",
                                                                                              flat=True).distinct()
    qs_org_raw = Organization.objects.filter_active(identification_code__in=qs_org_codes)
    qs_org = qs_org_raw.filter(query_org).values_list("identification_code", flat=True)
    qs_org = PeopleOrganization.objects.filter_active(org_code__in=qs_org).values_list("people_id",
                                                                                       flat=True).distinct()
    qs_org_list = list(qs_org)
    qs_org_people = []
    for x in qs_org_list:
        if x in list(qs_ids):
            qs_org_people.append(x)

    all_qs_ids = list(qs_people) + list(qs_authuser) + qs_org_people
    qs = People.objects.filter_active(id__in=all_qs_ids).distinct()
    return qs


def get_title_task(stand_title, assess_id=None):
    a = [
            u"姓名",
            u"账户",
            u"手机",
            u"邮箱",
    ]
    b1 = [
            u"一级组织",
            u"二级组织",    #  5
            u"三级组织",
            u"四级组织",
            u"五级组织",
            u"六级组织",
            u"七级组织",     # 10
            u"八级组织",
            u"九级组织",
            u"十级组织",
            u"组织码",
    ]
    b2 = [
            u"问卷名称",
            u"问卷状态",     # 15
            u"交卷时间",
    ]
    if assess_id in settings.dingzhi_assess_ids:
        dingzhi_type_account = [y for x, y in PeopleAccount.ACCOUNT_TYPE]
        a.extend(dingzhi_type_account)
        b1 = []
    c = stand_title
    d = [
        u"模型分",
    ]
    a.extend(b1)
    a.extend(b2)
    a.extend(c)
    a.extend(d)
    return a


def get_stand_dict(peoples_more_info):
    row_stand_dict = [
        u"年龄",
        u"身份证",
        u"面试场地",
        u"性别",
        u"婚姻状况",
        u"生育情况",
        u"子女成长情况",
        u"父母健康状况",
        u"个人健康状况",
        u"配偶工作情况",
        u"是否独生子女",
        u"学历",
        u"政治面貌",
        u"司龄",
        u"工龄",
        u"用工方式",
        u"薪酬模式",
        u"职级",
        u"层级",
        u"岗位类别",
        u"内外勤",
        u"岗位序列",
    ]
    for x in peoples_more_info:
        try:
            b = json.loads(x)
            c = [x['key_name'] for x in b]
            d = list(set(c).difference(set(row_stand_dict)))
            row_stand_dict.extend(d)
        except:
            print(x)
    return row_stand_dict


def zibiao(s_name, s_id, sub_ds, n):
    u"""
    幸福需求这里用不到了 @VERSION: 2018/11/07
    :param s_name:
    :param s_id:
    :param sub_ds:
    :param n:
    :param is_XFXQ:
    :return:
    """
    sub_sub = []
    for k, y in enumerate(sub_ds):
        for j, x in enumerate(y):
            # info = "%s%s%s%s%s%s" % (str(n), u'级', str(k+1), u'父列', str(j+1), u'个')
            info = u""
            s_name.append("%s\r\n(%s)\r\n%s" % (u'指标', x["name"], info))
            s_id.append(x["id"])
            if x["substandards"]:
                sub_sub.append(x["substandards"])
    if sub_sub:
        zibiao(s_name, s_id, sub_sub, n+1)
    else:
        return None


def answer_distinct(qs):
    answer_ids = []
    answer_query = []
    answer_query_false = []
    for answer in qs:
        if answer.answer_id not in answer_ids:
            answer_query.append(answer.id)
            answer_ids.append(answer.answer_id)
        else:
            answer_query_false.append(answer.id)
    if answer_query_false:
        qs.filter(id__in=answer_query_false).update(is_active=False)
    return qs.filter(id__in=answer_query)


def get_file(assess_id, people_ids, x, is_simple=False):
    timestamp = str(int(time.time() * 1000))
    default_export_file_name = "assess_%s_part_%s_survey_user_%s_download.xlsx" % (assess_id, str(x), timestamp)
    survey_ids = list(AssessSurveyRelation.objects.filter_active(assess_id=assess_id).values_list("survey_id", flat=True).distinct())
    peoples = People.objects.filter_active(id__in=people_ids)
    peoples_more_info = peoples.values_list("more_info", flat=True)
    stand_title = get_stand_dict(peoples_more_info)
    survey_index = 0
    file_path = None
    excel_util = ExcelUtils()
    # 本次已经找到的问卷问卷
    process_survey_ids = []
    project_obj = AssessProject.objects.get(id=assess_id)
    # 每一张问卷
    people_info_same_get_one_dict = {}
    for survey_id in survey_ids:
        logger.info("survey_id %s" % survey_id)
        # 避免一张问卷出2个表格
        if survey_id in process_survey_ids:
            continue
        #  记录这次问卷
        process_survey_ids.append(survey_id)
        #  excel 标题栏人员信息
        title = get_title_task(stand_title, assess_id)
        data = []
        # 找到问卷的obj, 名字 组卷方式 ， 测试类型 模型id
        try:
            survey_info = SurveyInfo.objects.get(survey_id=survey_id, project_id=assess_id)
            survey_name = survey_info.survey_name
            form_type = survey_info.form_type
            test_type = survey_info.test_type
            survey = Survey.objects.get(id=survey_id)
            model_id = survey.model_id
        except:
            survey = Survey.objects.get(id=survey_id)
            survey_name = survey.title
            form_type = survey.form_type
            test_type = survey.test_type
            model_id = survey.model_id

        model = ResearchModel.objects.get(id=model_id)
        dismension_titles = []
        dismension_ids = []
        substandard_titles = []
        substandard_ids = []
        is_XFXQ = False
        xfxq_weidu_titles = []
        xfxq_zhibiao_zhengti_titles = []
        xfxq_zhibiao_titles = []
        xfxq_weidu_substandard_ids = []
        xfxq_zhibiao_substandard_ids = []
        xfxq_zhibiao_zhengti_substandard_ids = []

        if model.algorithm_id == ResearchModel.ALGORITHM_DISC:
            substandard_titles = [
                u'最像我—D', u'最像我—I', u'最像我—S', u'最像我—C',
                u'最不像我—D', u'最不像我—I', u'最不像我—S', u'最不像我—C',
                u'差值—D', u'差值—I', u'差值—S', u'差值—C',
            ]
            title += substandard_titles
        else:
            if model.algorithm_id == ResearchModel.ALGORITHM_XFZS:
                happy_titles = [
                    "幸福维度总分",
                    "幸福能力总分",
                    "幸福效能总分",
                    "测谎A",
                    "测谎B",
                    "靠谱度",
                ]
                title += happy_titles
            model_data = ResearchModelDetailSerializer(instance=model).data
            sub_o = []
            is_XFXQ = True if model.algorithm_id == ResearchModel.ALGORITHM_XFXQ else False

            for dismension in model_data["dimension"]:
                # 维度
                dismension_titles.append("(%s)\r\n%s" % (u"维度", dismension["name"]))
                dismension_ids.append(dismension["id"])
                one_d_s = dismension["substandards"]
                sub_o.append(one_d_s)
                if is_XFXQ:
                    if not xfxq_weidu_titles:
                        for a_s in one_d_s:
                            xfxq_weidu_titles.append(u"维度（整体）%s" %a_s["name"])
                            xfxq_weidu_substandard_ids.append("%s_whole" % a_s["id"])
                    for s in one_d_s:
                        xfxq_weidu_titles.append(u"维度(%s) %s" %(dismension["name"], s["name"]))
                        xfxq_weidu_substandard_ids.append("%s_self" % s["id"])
                        for c_s in s["substandards"]:
                            check_name = u"指标（整体）%s" % c_s["name"]
                            if check_name not in xfxq_zhibiao_zhengti_titles:
                                xfxq_zhibiao_zhengti_titles.append(check_name)
                                xfxq_zhibiao_zhengti_substandard_ids.append("%s_whole" % c_s["id"])
                            xfxq_zhibiao_titles.append(u"指标（%s）%s" % (dismension["name"], c_s["name"]))
                            xfxq_zhibiao_substandard_ids.append("%s_self" % c_s["id"])
            title += dismension_titles
            if not is_XFXQ:
                zibiao(substandard_titles, substandard_ids, sub_o, 1)
                title += substandard_titles
            else:
                title += xfxq_weidu_titles
                title += xfxq_zhibiao_zhengti_titles
                title += xfxq_zhibiao_titles
        #  以上根据模型的维度和子标给 excel 加上相应的 title
        # 题目信息
        if not is_simple:
            question_info_qs = SurveyQuestionInfo.objects.filter_active(
                survey_id=survey_id, project_id=assess_id)
            question_count = 0
            block_question_map = {}
            question_type_map = {}
            question_info = []
            if not question_info_qs.exists():
                logger.info("surveyId %s is no question" % survey_id)
            else:
                if form_type == Survey.FORM_TYPE_FORCE:
                    # 迫选组卷 title 栏字段
                    question_info_obj = question_info_qs.filter(block_id=0)[0]
                    question_info = json.loads(question_info_obj.question_info)
                    for order, x in enumerate(question_info):
                        for option in x["options"]:
                            try:
                                dr = re.compile(r'<[^>]+>', re.S)
                                msg = dr.sub('', option["content"])
                            except:
                                msg = option["content"]
                            title.append("%s-%s" % (order + 1, msg))
                else:
                    if test_type == Survey.TEST_TYPE_BY_QUESTION:
                        question_info_obj = question_info_qs.filter(block_id=0)[0]
                        question_info = json.loads(question_info_obj.question_info)
                        question_count = len(question_info)
                    else:
                        for question_info_obj in question_info_qs:
                            if question_info_obj.block_id == 0:
                                continue
                            if question_info_obj.block_id not in block_question_map:
                                temp_question_info = json.loads(question_info_obj.question_info)
                                if temp_question_info:
                                    question_info += temp_question_info
                                    question_count += len(question_info)
                                    block_question_map[question_info_obj.block_id] = question_info
                    if question_count != 0:
                        for order, question in enumerate(question_info):
                            question_type_map[order] = {"question_type": question["question_type"], "order": order}
                            if question["question_type"] in [Question.QUESTION_TYPE_SINGLE,
                                                             Question.QUESTION_TYPE_SINGLE_FILLIN]:
                                title.append(order + 1)
                            elif question["question_type"] in [Question.QUESTION_TYPE_MULTI,
                                                               Question.QUESTION_TYPE_MULTI_FILLIN]:
                                for option in question["options"]["option_data"]:
                                    title.append(order + 1)
                            # 滑块题 与 九点题
                            elif question["question_type"] in [Question.QUESTION_TYPE_SLIDE, Question.QUESTION_TYPE_NINE_SLIDE]:
                                title.append(order + 1)
                            #  互斥题
                            elif question["question_type"] == Question.QUESTION_TYPE_MUTEXT:
                                for option in question["options"]["options_titles"]:
                                    title.append(order + 1)
                            #   迫选排序题
                            elif question["question_type"] == Question.QUESTION_TYPE_FORCE_ORDER_QUESTION:
                                # 普通问卷迫选排序题导出  title 栏
                                dr = re.compile(r'<[^>]+>', re.S)
                                msg = dr.sub('', question['title'])
                                title.append(msg)
                                for option in question["options"]["options"]:
                                    # 此处选项顺序是按照id的
                                    try:
                                        msg = dr.sub('', option["content"])
                                    except:
                                        msg = option["content"]
                                    title.append("%s-%s" % (order + 1, msg))
        for index_p, people in enumerate(peoples):
            if index_p % 500 == 1:
                logger.info('survey_id %s, people_id %s' % (survey_id, people.id))
            # 每个人的信息
            if people.id not in people_info_same_get_one_dict:
                # 账户名
                au_qs = AuthUser.objects.filter(id=people.user_id)
                account_name = u"" if not au_qs.exists() else au_qs[0].account_name
                stand_dict = renyuan_xinxi(people.more_info, stand_title)
                people_info_same_get_one_l = [people.username, account_name, people.phone, people.email]
                if assess_id in settings.dingzhi_assess_ids:
                    type_account = []
                    dingzhi_type_account = DINGZHI_4_TYPE_ACCOUNT
                    for x in dingzhi_type_account:
                        pa_qs = PeopleAccount.objects.filter_active(people_id=people.id, account_type=int(x)).values_list("account_value", flat=True)
                        if pa_qs.count() == 1:
                            type_account.append(pa_qs[0])
                        else:
                            type_account.append(u"")
                    people_info_same_get_one_l.extend(type_account)
                else:
                    # 定制项目取消组织
                    org_name = all_org(project_obj.id, people.org_codes)
                    people_info_same_get_one_l.extend(org_name)
                people_info_same_get_one_dict[people.id] = {"info_list": people_info_same_get_one_l, "info_stand": stand_dict}
                people_info_same_get_one = people_info_same_get_one_dict[people.id]
                #
            else:
                people_info_same_get_one = people_info_same_get_one_dict[people.id]
            people_survey_rels = PeopleSurveyRelation.objects.filter_active(
                people_id=people.id, project_id=assess_id, survey_id=survey_id)
            if not people_survey_rels.exists():
                one_data_list = []
                # 人员信息,组织信息
                one_data_list.extend(people_info_same_get_one["info_list"])
                # 问卷状态信息
                one_data_list.extend([survey_name, u"未分发", u''])
                # 自由属性信息
                one_data_list.extend(people_info_same_get_one["info_stand"])
                # 模型分
                one_data_list.append(0)
                data.append(one_data_list)
            else:
                for rel_obj in people_survey_rels:
                    status = rel_obj.status_name
                    if rel_obj.begin_answer_time and not rel_obj.finish_time:
                        status = u'答卷中'
                    if rel_obj.finish_time:
                        status = u'已完成'
                    if status == u"进行中":
                        status = u"已分发"
                    people_data = []
                    # 人员组织信息
                    people_data.extend(people_info_same_get_one["info_list"])
                    # 问卷状态信息
                    people_data.extend([rel_obj.survey_name, status, rel_obj.finish_time])
                    # 自由属性信息
                    people_data.extend(people_info_same_get_one["info_stand"])
                    # 模型分
                    people_data.append(round(rel_obj.model_score, 2))
                    # 以下小分
                    if rel_obj.status == PeopleSurveyRelation.STATUS_FINISH:  # and question_count > 0:
                        if model.algorithm_id == ResearchModel.ALGORITHM_DISC:
                            map_keys = ['D', "I", "S", "C"]
                            map_dismension = ["like", 'not_like', 'difference']
                            substandard_score_map = rel_obj.substandard_score_map
                            for dismension in map_dismension:
                                if dismension in substandard_score_map:
                                    for key in map_keys:
                                        if key in substandard_score_map[dismension]:
                                            people_data.append(substandard_score_map[dismension][key])
                                        else:
                                            people_data.append(0)
                                else:
                                    people_data += [0, 0, 0, 0]
                        else:
                            if model.algorithm_id == ResearchModel.ALGORITHM_XFZS:
                                if rel_obj.uniformity_score:
                                    uniformity_score = json.loads(rel_obj.uniformity_score)
                                else:
                                    uniformity_score = {}
                                people_data += [
                                    round(rel_obj.happy_score, 2),
                                    round(rel_obj.happy_ability_score, 2),
                                    round(rel_obj.happy_efficacy_score, 2),
                                    round(uniformity_score.get("A", 0), 2),
                                    round(uniformity_score.get("B", 0), 2),
                                    round(uniformity_score.get("K", 0), 2),
                                ]
                            dismension_score_map = rel_obj.dimension_score_map
                            substandard_score_map = rel_obj.all_substandard_score_map()

                            for dismension_id in dismension_ids:
                                if str(dismension_id) in dismension_score_map:
                                    people_data.append(round(dismension_score_map[str(dismension_id)]["score"], 2))
                                else:
                                    people_data.append(0)
                            if not is_XFXQ:
                                for substandard_id in substandard_ids:
                                    if str(substandard_id) in substandard_score_map:
                                        people_data.append(round(substandard_score_map[str(substandard_id)]["score"], 2))
                                    else:
                                        people_data.append(0)
                            else:
                                xfqs_substandard_ids = xfxq_weidu_substandard_ids + xfxq_zhibiao_zhengti_substandard_ids + xfxq_zhibiao_substandard_ids
                                for substandard_id in xfqs_substandard_ids:
                                    score_key = "score"
                                    if substandard_id.find("_whole") > -1:
                                        score_key = "whole_score"
                                    substandard_id = substandard_id.split("_")[0]
                                    if str(substandard_id) in substandard_score_map:
                                        people_data.append(round(substandard_score_map[str(substandard_id)][score_key], 2))
                                    else:
                                        people_data.append(0)
                        if not is_simple:
                            if form_type == Survey.FORM_TYPE_FORCE:
                                # 迫选组卷
                                for question in question_info:
                                #     答题情况
                                    qs = UserQuestionAnswerInfo.objects.filter_active(
                                        people_id=people.id,
                                        survey_id=survey_id,
                                        project_id=assess_id,
                                        role_type=rel_obj.role_type,
                                        evaluated_people_id=rel_obj.evaluated_people_id,
                                        question_id=question["id"]
                                    )
                                    answer_id_list = qs.values_list("answer_id", flat=True)
                                #     每个选项
                                    for option in question["options"]:
                                        if option["id"] in answer_id_list:
                                    #  判断符合或不符合
                                            a_s = qs.filter(answer_id=option["id"]).values_list("answer_score", flat=True)
                                            if a_s[0] == 1:
                                                people_data.append(1)
                                            else:
                                                people_data.append(-1)
                                        else:
                                            people_data.append(u"")
                            else:
                                for question in question_info:
                                    qs = UserQuestionAnswerInfo.objects.filter_active(
                                        people_id=people.id,
                                        survey_id=survey_id,
                                        project_id=assess_id,
                                        role_type=rel_obj.role_type,
                                        evaluated_people_id=rel_obj.evaluated_people_id,
                                        question_id=question["id"]
                                    )
                                    if question["question_type"] == Question.QUESTION_TYPE_SINGLE:
                                        if qs.exists():
                                            answer_info = qs[0]
                                            people_data.append(answer_info.answer_score)

                                            if qs.count() > 1:
                                                qs.exclude(id=answer_info.id).update(is_active=False)
                                        else:
                                            people_data.append(0)
                                    elif question["question_type"] == Question.QUESTION_TYPE_SINGLE_FILLIN:
                                        if qs.exists():
                                            answer_info = qs[0]
                                            if qs.count() > 1:
                                                qs.exclude(id=answer_info.id).update(is_active=False)

                                            if answer_info.answer_content and len(answer_info.answer_content) > 0:
                                                result = answer_info.answer_content
                                            else:
                                                result = answer_info.answer_score
                                            people_data.append(result)
                                        else:
                                            people_data.append(0)
                                    elif question["question_type"] == Question.QUESTION_TYPE_MULTI:
                                        for option in question["options"]["option_data"]:
                                            option_qs = qs.filter(answer_id=option["id"])
                                            if option_qs.exists():
                                                people_data.append(1)
                                            else:
                                                people_data.append(0)
                                    elif question["question_type"] == Question.QUESTION_TYPE_MULTI_FILLIN:
                                        for option in question["options"]["option_data"]:
                                            option_qs = qs.filter(answer_id=option["id"])
                                            if option_qs.exists():
                                                if option["is_blank"]:
                                                    people_data.append(option_qs[0].answer_content)
                                                else:
                                                    people_data.append(1)
                                            else:
                                                people_data.append(0)
                                    elif question["question_type"] in [Question.QUESTION_TYPE_SLIDE, Question.QUESTION_TYPE_NINE_SLIDE]:
                                        if qs.exists():
                                            people_data.append(qs[0].answer_score)
                                        else:
                                            people_data.append(0)
                                    elif question["question_type"] == Question.QUESTION_TYPE_MUTEXT:
                                        if not qs.exists():
                                            for option in question["options"]["options_titles"]:
                                                people_data.append(0)
                                        else:

                                            if qs.count() > 2:
                                                try:
                                                    qs = answer_distinct(qs)
                                                    if qs.count() > 2:
                                                        qs_ids = qs.order_by('-id')[0:2].values_list('id', flat=True)
                                                        qs.exclude(id__in=list(qs_ids)).update(is_active=False)
                                                        qs = qs.filter(is_active=True)
                                                except:
                                                    logger.error('%s answer_distinct error' % people.id)

                                            for q in qs:
                                                people_data.append(q.answer_score)
                                    elif question["question_type"] == Question.QUESTION_TYPE_FORCE_ORDER_QUESTION:
                                        people_data.append(u'')    #  题干
                                         # 迫选排序题答案
                                        if not qs.exists():
                                            for option in question["options"]["options"]:
                                                people_data.append(u'')
                                        else:
                                            default_scores_list = [u'' for x in range(5)]

                                            if qs.count() > 5:
                                                try:
                                                    qs = answer_distinct(qs.order_by("answer_id"))
                                                except:
                                                    logger.error('%s answer_distinct error' % people.id)

                                            answer_scores_list = [int(x) for x in qs.order_by("answer_id").values_list('answer_score', flat=True)]
                                            # 迫排题 有5个选项，每个选项都有值， 如果需要显示关联，则在title中加标志位
                                            if len(answer_scores_list) == len(default_scores_list):
                                                default_scores_list = answer_scores_list
                                            for x in default_scores_list:
                                                people_data.append(x)
                    data.append(people_data)
        logger.info("try_write")
        if survey_index < len(survey_ids) - 1:
            file_path = excel_util.create_excel(default_export_file_name, title, data,
                sheet_name=u"%s,%s" % (survey_index, survey_name), force_save=False,
                sheet_index=survey_index
            )
        else:
            file_path = excel_util.create_excel(default_export_file_name, title, data,
                sheet_name=u"%s,%s" % (survey_index, survey_name), force_save=True,
                sheet_index=survey_index
            )
        survey_index += 1
    logger.info("finish")
    return file_path, default_export_file_name


def all_org(assess_id, codes):
    # 获得一串组织树
    org_qs = Organization.objects.filter_active(assess_id=assess_id, identification_code__in=codes).order_by("-parent_id")
    org_name = [u'' for x in range(11)]
    if org_qs.exists():
        parent_id = org_qs[0].parent_id
        org_names = [org_qs[0].name]
        while parent_id > 0:
            pa_org = Organization.objects.get(id=parent_id)
            org_names.append(pa_org.name)
            parent_id = pa_org.parent_id
            if len(org_names) > 10:
                break
        for i, name in enumerate(org_names[::-1]):
            org_name[i] = name
        org_name[10] = org_qs[0].identification_code
    return org_name


def renyuan_xinxi(more_info, stand_title):
    try:
        ret = []
        info = {x["key_name"]: x["key_value"] for x in json.loads(more_info)}
        for title in stand_title:
            ret.append(info[title] if title in info else u'')
    except:
        ret = [u'' for x in range(len(stand_title))]
    return ret


@shared_task
def get_people_list_task(assess_id, org_codes, email, user_id, num_p=0, is_simple=False):
    # 一共哪些人
    if org_codes is None:
        people_ids = list(AssessUser.objects.filter_active(assess_id=assess_id).values_list("people_id", flat=True).distinct())
    else:
        org_codes = org_codes.split(",")
        people_ids = list(PeopleOrganization.objects.filter_active(org_code__in=org_codes).values_list(
            "people_id", flat=True).distinct().order_by("people_id"))
    PEOPLE_NUM = 5000 if num_p == 0 else num_p
    num = (len(people_ids) // PEOPLE_NUM) + 1
    all_files_path = []
    for x in range(num):
        file_path, default_export_file_name = get_file(assess_id, people_ids[x * PEOPLE_NUM:(x + 1) * PEOPLE_NUM], x, is_simple=is_simple)
        all_files_path.append(file_path)
    zip_path, zip_name = zip_excel(all_files_path, assess_id)
    oss_keys = AliyunOss().upload_file(user_id, zip_name, zip_path, prefix='wdadmin')
    EmailUtils().send_oss_people_list(oss_keys, email)


# 尝试将多个excel打包
def zip_excel(path_list, assess_id):
    WIN_SPLIT = "\\"
    LINUX_SPLIT = "/"
    row_path_example = LINUX_SPLIT.join(path_list[0].split(LINUX_SPLIT)[:-1])
    parent_dir = os.path.join(row_path_example, "total")
    if not os.path.exists(parent_dir):
        os.mkdir(parent_dir)
    parent_path = "assess_%s_survey_user_total_%s" % (assess_id, str(int(time.time()*100)))
    zip_path = os.path.join(parent_dir, parent_path)
    if not os.path.exists(zip_path):
        os.mkdir(zip_path)
    for x in path_list:
        excel_name = x.split(LINUX_SPLIT)[-1]
        file_full_path = os.path.join(zip_path, excel_name).encode("utf-8")
        shutil.copyfile(x, file_full_path)
    zip_file_path = "%s.zip" % zip_path
    zip_folder(zip_path, zip_file_path)
    logger.info("assess_id %s zip survey_user" % assess_id)
    return zip_file_path, zip_file_path.split(LINUX_SPLIT)[-1]


@shared_task
def assess_people_create_in_sql_task(old_authusers, new_authusers, assess_id):
    ret = do_old_authuser(old_authusers)
    if not ret[0]:
        finish_old_authuser_list = ret[1]
    else:
        return ret
    ret = do_new_authusers(new_authusers)
    if not ret[0]:
        finish_new_authuser_list = ret[1]
    else:
        return ret
    finish_authusers = finish_new_authuser_list + finish_old_authuser_list
    ret = do_people(finish_authusers)
    if not ret[0]:
        finish_peoples = au_id_to_po_obj(ret[1])
    else:
        return ret
    ret = do_enterprise(finish_peoples, assess_id)
    if ret[0]:
        return ret
    if assess_id in settings.dingzhi_assess_ids:
        ret = do_people_account(finish_peoples, assess_id)
        if ret[0]:
            return ret
    ret = do_assessuser(finish_peoples, assess_id)
    if ret[0]:
        return ret
    ret = do_org(finish_peoples)
    if ret[0]:
        return ret
    ret = do_dedicated_link(finish_authusers)
    if ret[0]:
        return ret
    return ErrorCode.SUCCESS, None, u"SUCCESS"


def check_people_account(people_account_value, ep_id):
    dingzhi_list = [y for x, y in PeopleAccount.ACCOUNT_TYPE]
    p_id = None
    use_name = None
    for index, value in enumerate(people_account_value):
        if value:
            y = PeopleAccount.objects.filter_active(account_value=value, account_type=int(DINGZHI_4_TYPE_ACCOUNT[index]), enterprise_id=ep_id).values_list(
                "people_id", flat=True)
            if y.count() > 1:
                return ErrorCode.FAILURE, u"%s已有人多人使用" % value, None, dingzhi_list[index]
            if y.exists() and p_id:
                if p_id != y[0]:
                    return ErrorCode.FAILURE, u"%s已有人使用" % value, None, dingzhi_list[index]
            elif y.exists() and (not p_id):
                p_id = y[0]
                use_name = dingzhi_list[index]
    # 找到一个人或没有人
    if p_id:
        p_id = People.objects.filter_active(id=p_id)[0].user_id
    return ErrorCode.SUCCESS, None, p_id, use_name


def check_input_useful(info_dict, assess_id, enterprise_id, new_user, old_user, new_input):
    old_people_id = None
    if assess_id in settings.dingzhi_assess_ids:
        people_account = [info_dict["type1"], info_dict["type2"], info_dict["type3"], info_dict["type4"]]
        for index, value in enumerate(people_account):
            new_type = "type%s" % str(index+1)
            if value:
                if value in new_input[new_type]:
                    return u"输入的四账号%s列重复" % str(index)
                else:
                    new_input[new_type].append(value)
        ret, msg, old_people_id, use_name = check_people_account(people_account, enterprise_id)
        if ret != ErrorCode.SUCCESS:
            return msg
    if len(info_dict['free_infos_name']) < len(info_dict['free_infos']):
        return u"自由增加的信息没有名字"
    if not (info_dict['phone'] or info_dict["account"] or info_dict["email"]):
        return u"手机，邮箱，账户必填一个"
    if info_dict["phone"]:
        if info_dict["phone"] in new_input["phone"]:
            return u"输入的手机重复"
        else:
            new_input["phone"].append(info_dict["phone"])
    if info_dict["account"]:
        if info_dict["account"] in new_input["account"]:
            return u"输入的账号重复"
        else:
            new_input["account"].append(info_dict["account"])
    if info_dict["email"]:
        if info_dict["email"] in new_input["email"]:
            return u"输入的邮箱重复"
        else:
            new_input['email'].append(info_dict["email"])
    if info_dict["birthday"]:
        if check_birthday(info_dict["birthday"]) != ErrorCode.SUCCESS:
            return u"生日格式有误"
    if info_dict["ops"] == u'修改' or info_dict["ops"] == u"删除":
        p_obj = None
        e_obj = None
        a_obj = None
        p_obj_id = 0
        e_obj_id = 0
        a_obj_id = 0
        # 以上6 个参数用于定位唯一的user_obj
        old_user_obj = None
        if info_dict["account"]:
            a_qs = EnterpriseAccount.objects.filter_active(account_name=info_dict["account"], enterprise_id=enterprise_id)
            if a_qs.count() == 0:
                a_obj = None
            if a_qs.count() == 1:
                try:
                    a_obj = AuthUser.objects.get(id=a_qs[0].user_id)
                    a_obj_id = a_obj.id
                except:
                    logger.error(u"企业账户 %s 没有对应的AuthUser用户 %s" % (str(a_qs[0].id), str(a_qs[0].user_id)))
                    return u"非法账户",
            if a_qs.count() > 1:
                return u"账户已经在企业中存在"
        if info_dict["phone"]:
            if not RegularUtils.phone_check(info_dict["phone"]):
                return u"手机格式有误"
            p_qs = AuthUser.objects.filter(phone=info_dict["phone"], is_active=True)
            if p_qs.count() == 0:
                p_obj = None
            if p_qs.count() == 1:
                p_obj = p_qs[0]
                p_obj_id = p_obj.id
            if p_qs.count() > 1:
                return u"手机绑定多个账户"
        if info_dict["email"]:
            if not RegularUtils.email_check(info_dict["email"]):
                return u"邮箱格式有误"
            e_qs = AuthUser.objects.filter(email=info_dict["email"], is_active=True)
            if e_qs.count() == 0:
                e_obj = None
            if e_qs.count() == 1:
                e_obj = e_qs[0]
                e_obj_id = e_obj.id
            if e_qs.count() > 1:
                return u"邮箱绑定多个账户"
        # 由 e_obj p_obj a_obj 找到唯一的Authuser:
        id_set = list(set([e_obj_id, p_obj_id, a_obj_id]))
        # 定制者
        if old_people_id:
            id_set = list(set([e_obj_id, p_obj_id, a_obj_id, old_people_id]))
        if len(id_set) > 2:
            return u'修改的手机邮箱账户中有信息多人使用'
        if len(id_set) == 2:
            if id_set[0] != 0:
                return u'修改的手机邮箱账户中有信息多人使用'
            id = id_set[1]
        if len(id_set) == 1:
            if id_set[0] == 0:
                return u"不存在此需要修改的用户"
            id = id_set[0]
        old_user_obj = AuthUser.objects.get(id=id)
        if not info_dict["org_names"]:
            return u"组织必填"
        elif info_dict["org_names"]:
            org_names = []
            for name in info_dict["org_names"]:
                if name:
                    org_names.append(str_check(name))
            orgs = get_orgs(org_names, assess_id)
            if len(orgs) != len(info_dict['org_names']):
                return u'组织名有误'
            if not orgs:
                return u"组织有误"
            info_dict["orgs_codes"] = [x.identification_code for x in orgs]
        if info_dict["birthday"]:
            if check_birthday(info_dict["birthday"]) != ErrorCode.SUCCESS:
                return u"生日格式有误"
        if info_dict["ops"] == "删除":
            delete_obj(old_user_obj, assess_id, info_dict["orgs_codes"])
        else:
            old_user.append((old_user_obj.id, info_dict))
    else:  # ops == u"新增" or ops == None:
        if old_people_id:
            return u"定制账号%s有被使用" % use_name
        if info_dict["account"]:
            if EnterpriseAccount.objects.filter_active(account_name=info_dict["account"], enterprise_id=enterprise_id).count() != 0:
                return u"账户已经在企业中存在"
        if info_dict["phone"]:
            if not RegularUtils.phone_check(info_dict["phone"]):
                return u"手机格式有误"
            if AuthUser.objects.filter(phone=info_dict["phone"], is_active=True).count() != 0:
                return u"手机已经被使用"
        if info_dict["email"]:
            if not RegularUtils.email_check(info_dict["email"]):
                return u"邮箱格式有误"
            if AuthUser.objects.filter(email=info_dict["email"], is_active=True).count() != 0:
                return u"邮箱已经被使用"
        if not info_dict["org_names"]:
            return u"组织必填"
        elif info_dict["org_names"]:
            org_names = []
            for name in info_dict["org_names"]:
                if name:
                    org_names.append(str_check(name))
            orgs = get_orgs(org_names, assess_id)
            if len(orgs) != len(info_dict['org_names']):
                return u'组织名有误'
            if not orgs:
                return u"组织有误"
            info_dict["orgs_codes"] = [x.identification_code for x in orgs]
        if info_dict["birthday"]:
            if check_birthday(info_dict["birthday"]) != ErrorCode.SUCCESS:
                return u"生日格式有误"
        new_user.append(info_dict)
    return ErrorCode.SUCCESS


@shared_task
def import_assess_user_task_0916(assess_id, file_path):
    project = AssessProject.objects.get(id=assess_id)
    enterprise_id = project.enterprise_id
    data = ExcelUtils().read_rows(file_path)
    new_user = []   # new_user.append({"infos":input_info})
    old_user = []   # old_user.append((user_obj_id,"infos":input_info))
    new_input = {"phone": [], "email": [], "account": []}
    if assess_id in settings.dingzhi_assess_ids:
        new_input = {"phone": [], "email": [], "account": [], "type1": [], "type2": [], "type3": [], "type4": []}
        for index, infos in enumerate(data):
            try:
                infos = [x if not x else RegularUtils.remove_illegal_char(str_check(x)) for x in infos]
            except:
                return ErrorCode.FAILURE, '有非法字符', index, new_user, old_user
            try:
                if index == 0:
                    free_infos_name = []
                    free_infos_name_row = infos[46:]
                    if infos[4] == u"密码(默认123456)":
                        return ErrorCode.FAILURE, u"定制项目,模板错误", 0, new_user, old_user
                    for name in free_infos_name_row:
                        if name:
                            free_infos_name.append(name)
                    continue
                info_dict = {
                    "nickname": str_check(infos[0]),
                    "account": str_check(infos[1]),
                    "phone": str_check(infos[2]),
                    "email": str_check(infos[3]),
                    "type1": str_check(infos[4]),
                    "type2": str_check(infos[5]),
                    "type3": str_check(infos[6]),
                    "type4": str_check(infos[7]),
                    "mima_row": infos[8],
                    "ops": infos[9],
                    "birthday": str_check(infos[10]),
                    "moreinfo_row": infos[10:36],
                    "org_names": get_orgs_info(infos[36:46]),
                    "index": index,
                    "free_infos_name": free_infos_name,
                    "free_infos": infos[46:]
                             }
                msg = check_input_useful(info_dict, assess_id, enterprise_id, new_user, old_user, new_input)
                if msg != ErrorCode.SUCCESS:
                    if msg.find("定制账号") > -1 and msg.find("有被使用") > -1:
                        info_dict["ops"] = u'修改'
                        msg = check_input_useful(info_dict, assess_id, enterprise_id, new_user, old_user, new_input)
                        if msg != ErrorCode.SUCCESS:
                            print msg, index
                            # return ErrorCode.FAILURE, msg, index, new_user, old_user
                    else:
                        print msg, index
                        #return ErrorCode.FAILURE, msg, index, new_user, old_user
            except Exception, e:
                logger.error(u"check_input_people_data_error %s" % e)
                return ErrorCode.FAILURE, u"异常", index, new_user, old_user
        return ErrorCode.SUCCESS, None, index, new_user, old_user
    for index, infos in enumerate(data):
        try:
            infos = [x if not x else RegularUtils.remove_illegal_char(str_check(x)) for x in infos]
        except:
            return ErrorCode.FAILURE, '有非法字符', index, new_user, old_user
        try:
            if index == 0:
                free_infos_name = []
                free_infos_name_row = infos[43:]
                if infos[4] != u"密码(默认123456)" and assess_id not in settings.dingzhi_assess_ids:
                    return ErrorCode.FAILURE, u"非定制项目", 0, new_user, old_user
                for name in free_infos_name_row:
                    if name:
                        free_infos_name.append(name)
                continue
            info_dict = {"nickname": str_check(infos[0]),
                         "account": str_check(infos[1]),
                         "phone": str_check(infos[2]),
                         "email": str_check(infos[3]),
                         "mima_row": infos[4],
                         "moreinfo_row": infos[6:32],       # 注意这里的 6 要改的话,还有get_moreinfos 中也要改
                         "org_names": get_orgs_info(infos[32:42]),
                         "ops": infos[5],
                         "birthday": str_check(infos[6]),
                         "index": index,
                         "free_infos_name": free_infos_name,
                         "free_infos": infos[43:]     # [41，为空]
                         }
            msg = check_input_useful(info_dict, assess_id, enterprise_id, new_user, old_user, new_input)
            if msg != ErrorCode.SUCCESS:
                return ErrorCode.FAILURE, msg, index, new_user, old_user
        except Exception, e:
            logger.error(u"check_input_people_data_error %s" % e)
            return ErrorCode.FAILURE, u"异常", index, new_user, old_user
    return ErrorCode.SUCCESS, None, index, new_user, old_user


# 数据判断完毕后发送
@shared_task
def distribute_all_survey_task_1025(people_ids, assess_id, status):

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

    # 随机问卷已经决定完毕
    def distribute_one_people_survey(survey_ids, people_id, assess_id, new_distribute_ids):
        people_survey_list = []
        for survey_id in survey_ids:
            survey_qs = Survey.objects.filter_active(id=survey_id)
            if survey_qs.count() == 1:
                survey = survey_qs[0]
            else:
                logger.error("survey_id %d filter ERROR" % survey_id)
                continue
            asr_qs = AssessSurveyRelation.objects.filter_active(assess_id=assess_id, survey_id=survey_id)
            asud_qs = AssessSurveyUserDistribute.objects.filter_active(assess_id=assess_id, survey_id=survey_id)
            if asud_qs.exists():
                asud_obj = asud_qs[0]
                distribute_users = json.loads(asud_obj.people_ids)
            else:
                asud_obj = AssessSurveyUserDistribute.objects.create(assess_id=assess_id, survey_id=survey_id,
                                                                     people_ids=json.dumps([]))
                distribute_users = json.loads(asud_obj.people_ids)
            if asr_qs[0].survey_been_random == True:
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
            elif asr_qs[0].survey_been_random == False:
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
        if people_survey_list:
            if people_id not in new_distribute_ids:
                new_distribute_ids.append(people_id)
        return new_distribute_ids

    def get_random_survey_info(random_num, random_survey_qs, random_index, assess_id, people_id):
        # 从全部的问卷中选取他被随机到的问卷
        if len(random_survey_qs) < random_num:
            random_num = len(random_survey_qs)
        survey_ids = random_survey_qs.values_list('survey_id', flat=True)
        # 获得随机问卷的加起来的分发list
        random_distribute_people_info = get_random_survey_distribute_info(assess_id, survey_ids)
        if people_id not in random_distribute_people_info:
            polling_list = list(survey_ids)
            has_random_survey_ids, random_index = polling_survey(random_num, random_index, polling_list)
            return has_random_survey_ids, random_index
        else:
            return [], random_index

    new_distribute_ids = []
    all_survey_qs = AssessSurveyRelation.objects.filter_active(assess_id=assess_id).distinct().order_by("-order_number")
    random_survey_qs = all_survey_qs.filter(survey_been_random=True)
    normal_survey_qs = all_survey_qs.filter(survey_been_random=False)
    assessment_obj = AssessProject.objects.get(id=assess_id)
    random_num = assessment_obj.survey_random_number
    random_index = assessment_obj.survey_random_index  # 随机标志位
    for people_id in people_ids:
        if random_num and random_survey_qs.exists():
            random_survey_ids, random_index = get_random_survey_info(random_num, random_survey_qs, random_index,assess_id, people_id)
        else:
            random_survey_ids, random_index = [], random_index
        if normal_survey_qs:
            normal_survey_ids = normal_survey_qs.values_list('survey_id', flat=True)
        else:
            normal_survey_ids = []
        all_survey_ids = all_survey_qs.values_list("survey_id", flat=True)
        person_survey_ids_list = []
        for i in all_survey_ids:
            if (i in random_survey_ids) or (i in normal_survey_ids):
                person_survey_ids_list.append(i)
        new_distribute_ids = distribute_one_people_survey(person_survey_ids_list, people_id, assess_id,
                                                          new_distribute_ids)
        if new_distribute_ids:
            send_survey_active_codes.delay(new_distribute_ids)
    assessment_obj.survey_random_index = random_index  # 随机标志位
    assessment_obj.save()


@shared_task
def get_people_list_task_back(assess_id, org_codes, email, user_id, num_p=0):
    # 一共哪些人
    if org_codes is None:
        people_ids = list(AssessUser.objects.filter_active(assess_id=assess_id).values_list("people_id", flat=True).distinct())
    else:
        org_codes = org_codes.split(",")
        people_ids = list(PeopleOrganization.objects.filter_active(org_code__in=org_codes).values_list(
            "people_id", flat=True).distinct().order_by("people_id"))
    PEOPLE_NUM = 5000 if num_p == 0 else num_p
    num = (len(people_ids) // PEOPLE_NUM) + 1
    all_files_path = []
    for x in range(num):
        file_path, default_export_file_name = get_file_back(assess_id, people_ids[x * PEOPLE_NUM:(x + 1) * PEOPLE_NUM], x)
        all_files_path.append(file_path)
    zip_path, zip_name = zip_excel_back(all_files_path, assess_id)
    oss_keys = AliyunOss().upload_file(user_id, zip_name, zip_path, prefix='wdadmin')
    EmailUtils().send_oss_people_list(oss_keys, email)

# 尝试将多个excel打包
def zip_excel_back(path_list, assess_id):
    WIN_SPLIT = "\\"
    LINUX_SPLIT = "/"
    row_path_example = LINUX_SPLIT.join(path_list[0].split(LINUX_SPLIT)[:-1])
    parent_dir = os.path.join(row_path_example, "total")
    if not os.path.exists(parent_dir):
        os.mkdir(parent_dir)
    parent_path = "assess_%s_survey_user_total_%s" % (assess_id, str(int(time.time()*100)))
    zip_path = os.path.join(parent_dir, parent_path)
    if not os.path.exists(zip_path):
        os.mkdir(zip_path)
    for x in path_list:
        excel_name = x.split(LINUX_SPLIT)[-1]
        file_full_path = os.path.join(zip_path, excel_name).encode("utf-8")
        shutil.copyfile(x, file_full_path)
    zip_file_path = "%s.zip" % zip_path
    zip_folder(zip_path, zip_file_path)
    logger.info("assess_id %s zip survey_user" % assess_id)
    return zip_file_path, zip_file_path.split(LINUX_SPLIT)[-1]

def get_title_task_back(stand_title, assess_id=None):
    a = [
            u"姓名",
            u"账户",
            u"手机",
            u"邮箱",
    ]
    b = [
            u"一级组织",
            u"二级组织",    #  5
            u"三级组织",
            u"四级组织",
            u"五级组织",
            u"六级组织",
            u"七级组织",     # 10
            u"八级组织",
            u"九级组织",
            u"十级组织",
            u"组织码",
            u"问卷名称",
            u"问卷状态",     # 15
            u"交卷时间",
    ]
    c = stand_title
    d = [
        u"模型分",
    ]
    a.extend(b)
    a.extend(c)
    a.extend(d)
    return a

def get_stand_dict_back(peoples_more_info):
    row_stand_dict = [
        u"年龄",
        u"身份证",
        u"面试场地",
        u"性别",
        u"婚姻状况",
        u"生育情况",
        u"子女成长情况",
        u"父母健康状况",
        u"个人健康状况",
        u"配偶工作情况",
        u"是否独生子女",
        u"学历",
        u"政治面貌",
        u"司龄",
        u"工龄",
        u"用工方式",
        u"薪酬模式",
        u"职级",
        u"层级",
        u"岗位类别",
        u"内外勤",
        u"岗位序列",
    ]
    for x in peoples_more_info:
        try:
            b = json.loads(x)
            c = [x['key_name'] for x in b]
            d = list(set(c).difference(set(row_stand_dict)))
            row_stand_dict.extend(d)
        except:
            print(x)
    return row_stand_dict

def zibiao_back(s_name, s_id, sub_ds, n, is_XFXQ):
    sub_sub = []
    for k, y in enumerate(sub_ds):
        for j, x in enumerate(y):
            # info = "%s%s%s%s%s%s" % (str(n), u'级', str(k+1), u'父列', str(j+1), u'个')
            info = u""
            if is_XFXQ:
                s_name.append("%s\r\n(%s)\r\n%s" % (u'整体指标', x["name"], info))
            s_name.append("%s\r\n(%s)\r\n%s" % (u'指标', x["name"], info))
            s_id.append(x["id"])
            if x["substandards"]:
                sub_sub.append(x["substandards"])
    if sub_sub:
        zibiao_back(s_name, s_id, sub_sub, n+1, is_XFXQ)
    else:
        return None

def get_file_back(assess_id, people_ids, x):
    timestamp = str(int(time.time() * 1000))
    default_export_file_name = "assess_%s_part_%s_survey_user_%s_download.xlsx" % (assess_id, str(x), timestamp)
    survey_ids = list(AssessSurveyRelation.objects.filter_active(assess_id=assess_id).values_list("survey_id", flat=True).distinct())
    peoples = People.objects.filter_active(id__in=people_ids)
    peoples_more_info = peoples.values_list("more_info", flat=True)
    stand_title = get_stand_dict_back(peoples_more_info)
    survey_index = 0
    file_path = None
    excel_util = ExcelUtils()
    # 本次已经找到的问卷问卷
    process_survey_ids = []
    project_obj = AssessProject.objects.get(id=assess_id)
    # 每一张问卷
    people_info_same_get_one_dict = {}
    for survey_id in survey_ids:
        logger.info("survey_id %s" % survey_id)
        # 避免一张问卷出2个表格
        if survey_id in process_survey_ids:
            continue
        #  记录这次问卷
        process_survey_ids.append(survey_id)
        #  excel 标题栏人员信息
        title = get_title_task_back(stand_title, assess_id)
        data = []
        # 找到问卷的obj, 名字 组卷方式 ， 测试类型 模型id
        try:
            survey_info = SurveyInfo.objects.get(survey_id=survey_id, project_id=assess_id)
            survey_name = survey_info.survey_name
            form_type = survey_info.form_type
            test_type = survey_info.test_type
            survey = Survey.objects.get(id=survey_id)
            model_id = survey.model_id
        except:
            survey = Survey.objects.get(id=survey_id)
            survey_name = survey.title
            form_type = survey.form_type
            test_type = survey.test_type
            model_id = survey.model_id

        model = ResearchModel.objects.get(id=model_id)
        dismension_titles = []
        dismension_ids = []
        substandard_titles = []
        substandard_ids = []
        if model.algorithm_id == ResearchModel.ALGORITHM_DISC:
            substandard_titles = [
                u'最像我—D', u'最像我—I', u'最像我—S', u'最像我—C',
                u'最不像我—D', u'最不像我—I', u'最不像我—S', u'最不像我—C',
                u'差值—D', u'差值—I', u'差值—S', u'差值—C',
            ]
            title += substandard_titles
        else:
            if model.algorithm_id == ResearchModel.ALGORITHM_XFZS:
                happy_titles = [
                    "幸福维度总分",
                    "幸福能力总分",
                    "幸福效能总分",
                    "测谎A",
                    "测谎B",
                    "靠谱度",
                ]
                title += happy_titles
            model_data = ResearchModelDetailSerializer(instance=model).data
            sub_o = []
            is_XFXQ = True if model.algorithm_id == ResearchModel.ALGORITHM_XFXQ else False
            for dismension in model_data["dimension"]:
                # 维度
                dismension_titles.append("(%s)\r\n%s" % (u"维度", dismension["name"]))
                dismension_ids.append(dismension["id"])
                one_d_s = dismension["substandards"]
                sub_o.append(one_d_s)
            zibiao_back(substandard_titles, substandard_ids, sub_o, 1, is_XFXQ)
            title += dismension_titles
            title += substandard_titles
        #  以上根据模型的维度和子标给 excel 加上相应的 title
        # 题目信息
        question_info_qs = SurveyQuestionInfo.objects.filter_active(
            survey_id=survey_id, project_id=assess_id)
        question_count = 0
        block_question_map = {}
        question_type_map = {}
        question_info = []
        timestamp = int(time.time() * 100)
        if not question_info_qs.exists():
            logger.info("surveyId %s is no question" % survey_id)
        else:
            if form_type == Survey.FORM_TYPE_FORCE:
                # 迫选组卷 title 栏字段
                question_info_obj = question_info_qs.filter(block_id=0)[0]
                question_info = json.loads(question_info_obj.question_info)
                question_count = len(question_info)
                for order, x in enumerate(question_info):
                    for option in x["options"]:
                        try:
                            dr = re.compile(r'<[^>]+>', re.S)
                            msg = dr.sub('', option["content"])
                        except:
                            msg = option["content"]
                        title.append("%s-%s" % (order + 1, msg))
            else:
                if test_type == Survey.TEST_TYPE_BY_QUESTION:
                    question_info_obj = question_info_qs.filter(block_id=0)[0]
                    question_info = json.loads(question_info_obj.question_info)
                    question_count = len(question_info)
                else:
                    for question_info_obj in question_info_qs:
                        if question_info_obj.block_id == 0:
                            continue
                        if question_info_obj.block_id not in block_question_map:
                            temp_question_info = json.loads(question_info_obj.question_info)
                            if temp_question_info:
                                question_info += temp_question_info
                                question_count += len(question_info)
                                block_question_map[question_info_obj.block_id] = question_info
                if question_count != 0:
                    for order, question in enumerate(question_info):
                        question_type_map[order] = {"question_type": question["question_type"], "order": order}
                        if question["question_type"] in [Question.QUESTION_TYPE_SINGLE,
                                                         Question.QUESTION_TYPE_SINGLE_FILLIN]:
                            title.append(order + 1)
                        elif question["question_type"] in [Question.QUESTION_TYPE_MULTI,
                                                           Question.QUESTION_TYPE_MULTI_FILLIN]:
                            for option in question["options"]["option_data"]:
                                title.append(order + 1)
                        # 滑块题 与 九点题
                        elif question["question_type"] in [Question.QUESTION_TYPE_SLIDE, Question.QUESTION_TYPE_NINE_SLIDE]:
                            title.append(order + 1)
                        #  互斥题
                        elif question["question_type"] == Question.QUESTION_TYPE_MUTEXT:
                            for option in question["options"]["options_titles"]:
                                title.append(order + 1)
                        #   迫选排序题
                        elif question["question_type"] == Question.QUESTION_TYPE_FORCE_ORDER_QUESTION:
                            # 普通问卷迫选排序题导出  title 栏
                            dr = re.compile(r'<[^>]+>', re.S)
                            msg = dr.sub('', question['title'])
                            title.append(msg)
                            for option in question["options"]["options"]:
                                # 此处选项顺序是按照id的
                                try:
                                    msg = dr.sub('', option["content"])
                                except:
                                    msg = option["content"]
                                title.append("%s-%s" % (order + 1, msg))
        for index_p, people in enumerate(peoples):
            if index_p % 2000 == 1:
                logger.info('survey_id %s, people_id %s' % (survey_id, people.id))
            # 每个人的信息
            if people.id not in people_info_same_get_one_dict:
                # 账户名
                au_qs = AuthUser.objects.filter(id=people.user_id)
                account_name = u"" if not au_qs.exists() else au_qs[0].account_name
                # 人员自由信息
                try:
                    info_dict = json.loads(people.more_info)
                    if type(info_dict) != list:
                        info_dict = []
                except:
                    info_dict = []
                # [{"key_name":1, "key_value":'a'}]
                stand_dict = [dict([(x, u" "), ]) for x in stand_title]   # 每次赋值前都清空
                try:
                    # 列表里面的字典的键值对匹配
                    for key_value in info_dict:
                        for stand_dict_item in stand_dict:
                            if stand_dict_item.keys()[0] == key_value[u'key_name']:
                                stand_dict_item[stand_dict_item.keys()[0]] = str_check(key_value[u'key_value'])
                except Exception, e:
                    logger.error("用户信息格式有误 %s" % e)
                stand_dict = [x.values()[0] for x in stand_dict]
                # 找到所有组织名
                people_org_qs = Organization.objects.filter_active(assess_id=project_obj.id, identification_code__in=people.org_codes).order_by("parent_id")
                org_names = people_org_qs.values_list("name", flat=True).distinct()
                pa_org_qs = people_org_qs.order_by("-parent_id")
                if pa_org_qs.exists():
                    parent_id = pa_org_qs[0].parent_id
                    parent_id_name = pa_org_qs[0].name
                    if parent_id > 0:
                        def get_all_org_with_last_parent_id(old_org_names, parent_id, parent_id_name):
                            org_name = [parent_id_name]
                            try:
                                while True:
                                    if parent_id != 0:
                                        org_obj_for_pa = Organization.objects.get(id=parent_id)
                                        org_name.append(org_obj_for_pa.name)
                                        if org_obj_for_pa.parent_id != 0:
                                            parent_id = org_obj_for_pa.parent_id
                                        else:
                                            return org_name[::-1]
                            except:
                                return old_org_names
                        org_names = get_all_org_with_last_parent_id(org_names, parent_id, parent_id_name)
                org_name = [u'' for x in range(10)]
                for i, name in enumerate(org_names):
                    if i < 10:
                        org_name[i] = name
                if pa_org_qs.exists():
                    org_name.append(pa_org_qs[0].identification_code)
                else:
                    org_name.append(u'')
                #
                people_info_same_get_one_l = [people.username, account_name, people.phone, people.email]
                people_info_same_get_one_l.extend(org_name)
                people_info_same_get_one_dict[people.id] = {"info_list": people_info_same_get_one_l, "info_stand": stand_dict}
                people_info_same_get_one = people_info_same_get_one_dict[people.id]
                #
            else:
                people_info_same_get_one = people_info_same_get_one_dict[people.id]
            people_survey_rels = PeopleSurveyRelation.objects.filter_active(
                people_id=people.id, project_id=assess_id, survey_id=survey_id)
            if not people_survey_rels.exists():
                one_data_list = []
                # 人员信息,组织信息
                one_data_list.extend(people_info_same_get_one["info_list"])
                # 问卷状态信息
                one_data_list.extend([survey_name, u"未分发", u''])
                # 自由属性信息
                one_data_list.extend(people_info_same_get_one["info_stand"])
                # 模型分
                one_data_list.append(0)
                data.append(one_data_list)
            else:
                for rel_obj in people_survey_rels:
                    status = rel_obj.status_name
                    if rel_obj.begin_answer_time and not rel_obj.finish_time:
                        status = u'答卷中'
                    if rel_obj.finish_time:
                        status = u'已完成'
                    if status == u"进行中":
                        status = u"已分发"
                    people_data = []
                    # 人员组织信息
                    people_data.extend(people_info_same_get_one["info_list"])
                    # 问卷状态信息
                    people_data.extend([rel_obj.survey_name, status, rel_obj.finish_time])
                    # 自由属性信息
                    people_data.extend(people_info_same_get_one["info_stand"])
                    # 模型分
                    people_data.append(rel_obj.model_score)
                    # 以下小分
                    if rel_obj.status == PeopleSurveyRelation.STATUS_FINISH:  # and question_count > 0:
                        if model.algorithm_id == ResearchModel.ALGORITHM_DISC:
                            map_keys = ['D', "I", "S", "C"]
                            map_dismension = ["like", 'not_like', 'difference']
                            substandard_score_map = rel_obj.substandard_score_map
                            for dismension in map_dismension:
                                if dismension in substandard_score_map:
                                    for key in map_keys:
                                        if key in substandard_score_map[dismension]:
                                            people_data.append(substandard_score_map[dismension][key])
                                        else:
                                            people_data.append(0)
                                else:
                                    people_data += [0, 0, 0, 0]
                        else:
                            if model.algorithm_id == ResearchModel.ALGORITHM_XFZS:
                                if rel_obj.uniformity_score:
                                    uniformity_score = json.loads(rel_obj.uniformity_score)
                                else:
                                    uniformity_score = {}
                                people_data += [
                                    rel_obj.happy_score,
                                    rel_obj.happy_ability_score,
                                    rel_obj.happy_efficacy_score,
                                    uniformity_score.get("A", 0),
                                    uniformity_score.get("B", 0),
                                    uniformity_score.get("K", 0),
                                ]
                            dismension_score_map = rel_obj.dimension_score_map
                            substandard_score_map = rel_obj.substandard_score_map
                            for dismension_id in dismension_ids:
                                if str(dismension_id) in dismension_score_map:
                                    people_data.append(dismension_score_map[str(dismension_id)]["score"])
                                else:
                                    people_data.append(0)
                            for substandard_id in substandard_ids:
                                if str(substandard_id) in substandard_score_map:
                                    if model.algorithm_id == ResearchModel.ALGORITHM_XFXQ:
                                        people_data.append(substandard_score_map[str(substandard_id)]["whole_score"])
                                    people_data.append(substandard_score_map[str(substandard_id)]["score"])
                                else:
                                    if model.algorithm_id == ResearchModel.ALGORITHM_XFXQ:
                                        people_data.append(0)
                                    people_data.append(0)
                        if form_type == Survey.FORM_TYPE_FORCE:
                            # 迫选组卷
                            for question in question_info:
                            #     答题情况
                                qs = UserQuestionAnswerInfo.objects.filter_active(
                                    people_id=people.id,
                                    survey_id=survey_id,
                                    project_id=assess_id,
                                    role_type=rel_obj.role_type,
                                    evaluated_people_id=rel_obj.evaluated_people_id,
                                    question_id=question["id"]
                                )
                                answer_id_list = qs.values_list("answer_id", flat=True)
                            #     每个选项
                                for option in question["options"]:
                                    if option["id"] in answer_id_list:
                                #  判断符合或不符合
                                        a_s = qs.filter(answer_id=option["id"]).values_list("answer_score", flat=True)
                                        if a_s[0] == 1:
                                            people_data.append(1)
                                        else:
                                            people_data.append(-1)
                                    else:
                                        people_data.append(u"")
                        else:
                            for question in question_info:
                                qs = UserQuestionAnswerInfo.objects.filter_active(
                                    people_id=people.id,
                                    survey_id=survey_id,
                                    project_id=assess_id,
                                    role_type=rel_obj.role_type,
                                    evaluated_people_id=rel_obj.evaluated_people_id,
                                    question_id=question["id"]
                                )
                                if question["question_type"] == Question.QUESTION_TYPE_SINGLE:
                                    if qs.exists():
                                        answer_info = qs[0]
                                        people_data.append(answer_info.answer_score)
                                    else:
                                        people_data.append(0)
                                elif question["question_type"] == Question.QUESTION_TYPE_SINGLE_FILLIN:
                                    if qs.exists():
                                        answer_info = qs[0]
                                        if answer_info.answer_content and len(answer_info.answer_content) > 0:
                                            result = answer_info.answer_content
                                        else:
                                            result = answer_info.answer_score
                                        people_data.append(result)
                                    else:
                                        people_data.append(0)
                                elif question["question_type"] == Question.QUESTION_TYPE_MULTI:
                                    for option in question["options"]["option_data"]:
                                        option_qs = qs.filter(answer_id=option["id"])
                                        if option_qs.exists():
                                            people_data.append(1)
                                        else:
                                            people_data.append(0)
                                elif question["question_type"] == Question.QUESTION_TYPE_MULTI_FILLIN:
                                    for option in question["options"]["option_data"]:
                                        option_qs = qs.filter(answer_id=option["id"])
                                        if option_qs.exists():
                                            if option["is_blank"]:
                                                people_data.append(option_qs[0].answer_content)
                                            else:
                                                people_data.append(1)
                                        else:
                                            people_data.append(0)
                                elif question["question_type"] in [Question.QUESTION_TYPE_SLIDE, Question.QUESTION_TYPE_NINE_SLIDE]:
                                    if qs.exists():
                                        people_data.append(qs[0].answer_score)
                                    else:
                                        people_data.append(0)
                                elif question["question_type"] == Question.QUESTION_TYPE_MUTEXT:
                                    if not qs.exists():
                                        for option in question["options"]["options_titles"]:
                                            people_data.append(0)
                                    else:
                                        for q in qs:
                                            people_data.append(q.answer_score)
                                elif question["question_type"] == Question.QUESTION_TYPE_FORCE_ORDER_QUESTION:
                                    people_data.append(u'')    #  题干
                                     # 迫选排序题答案
                                    if not qs.exists():
                                        for option in question["options"]["options"]:
                                            people_data.append(u'')
                                    else:
                                        default_scores_list = [u'' for x in range(5)]
                                        answer_scores_list = [int(x) for x in qs.order_by("answer_id").values_list('answer_score', flat=True)]
                                        # 迫排题 有5个选项，每个选项都有值， 如果需要显示关联，则在title中加标志位
                                        if len(answer_scores_list) == len(default_scores_list):
                                            default_scores_list = answer_scores_list
                                        for x in default_scores_list:
                                            people_data.append(x)
                    data.append(people_data)
        logger.info("try_write")
        if survey_index < len(survey_ids) - 1:
            file_path = excel_util.create_excel(default_export_file_name, title, data,
                sheet_name=u"%s,%s" % (survey_index, survey_name), force_save=False,
                sheet_index=survey_index
            )
        else:
            file_path = excel_util.create_excel(default_export_file_name, title, data,
                sheet_name=u"%s,%s" % (survey_index, survey_name), force_save=True,
                sheet_index=survey_index
            )
        survey_index += 1
    logger.info("finish")
    return file_path, default_export_file_name