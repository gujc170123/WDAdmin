# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import copy
import inspect
import os

import time

import datetime
from django.contrib.auth import authenticate, login, _get_backends
from django.contrib.auth.hashers import make_password

from WeiDuAdmin.settings import BASE_DIR
from utils import get_random_char, get_random_int
from utils.excel import ExcelUtils
from utils.logger import get_logger
from utils.pyfirstchar import get_first_char
from utils.regular import RegularUtils
from utils.response import ErrorCode
from wduser.models import AuthUser, Organization

logger = get_logger('user')


class UserAccountUtils(object):

    @classmethod
    def authenticate_without_pwd(cls, user, **credentials):
        """
        If the given credentials are valid, return a User object.
        """
        for backend, backend_path in _get_backends(return_tuples=True):
            # try:
            #     inspect.getcallargs(backend.authenticate, **credentials)
            # except:
            #     # This backend doesn't accept these credentials as arguments. Try the next one.
            #     continue
            user.backend = backend_path
            return user

    @classmethod
    def user_auth_pwd(cls, user, pwd):
        u"""通过密码对用户鉴权
        @:param: 密码，用户"""
        user = authenticate(username=user.username, password=pwd)
        return user

    @classmethod
    def user_auth_pwd_without_pwd(cls, user):
        u"""通过密码对用户鉴权
        @:param: 密码，用户"""
        user = cls.authenticate_without_pwd(user, username=user.username, password=None)
        return user

    def user_change_pwd(self):
        pass

    @classmethod
    def account_check(cls, account, check_active_code=False, active_code=None):
        u"""这边的激活码检查，是管理员的激活码检查"""
        if RegularUtils.phone_check(account):
            # 手机号激活码校验
            user_qs = AuthUser.objects.filter(is_active=True, phone=account)
        elif RegularUtils.email_check(account):
            # email 登录
            user_qs = AuthUser.objects.filter(is_active=True, email=account)
        else:
            user_qs = AuthUser.objects.filter(is_active=True, account_name=account)
            if user_qs.count() > 1:
                return None, ErrorCode.USER_ACCOUNT_DOUBLE_ERROR
            if user_qs.count() == 0:
                user_qs = AuthUser.objects.filter(is_active=True, username=account)
            # user_qs = AuthUser.objects.filter(is_active=True, account_name=account)
            # if user_qs.count() > 1:
            #     return None, ErrorCode. USER_ACCOUNT_DOUBLE_ERROR
        if not user_qs.exists():
            return None, ErrorCode.USER_ACCOUNT_NOT_FOUND
        user = user_qs.order_by('id')[0]
        if check_active_code:
            if not active_code:
                return None, ErrorCode.USER_ACTIVE_CODE_INVALID
            if user.active_code != active_code:
                return None, ErrorCode.USER_ACTIVE_CODE_INVALID
            if not user.active_code_valid:
                return None, ErrorCode.USER_ACTIVE_CODE_EXPIRED
        return user, ErrorCode.SUCCESS

    @classmethod
    def user_login_web(cls, request, user, pwd):
        u"""用户登录
        @:request:
        """
        user = cls.user_auth_pwd(user, pwd)
        if not user:
            return None, ErrorCode.USER_PWD_ERROR
        login(request, user)
        return user, ErrorCode.SUCCESS

    @classmethod
    def user_login_web_without_pwd(cls, request, user):
        u"""用户登录
        @:request:
        """
        user = cls.user_auth_pwd_without_pwd(user)
        if not user:
            return None, ErrorCode.USER_PWD_ERROR
        login(request, user)
        return user, ErrorCode.SUCCESS

    @classmethod
    def user_register(cls, pwd, username=None, phone=None, email=None, role_type=AuthUser.ROLE_NORMAL, nickname=None):
        u"""直接注册
        @:param: 密码，用户名， 手机， 邮箱"""
        random_username = get_random_char(6)
        if username is None and phone is None and email is None:
            return None, ErrorCode.INVALID_INPUT
        if username is None and phone is not None:
            username = "%s%s" % (phone, random_username)
        elif username is None and email is not None:
            username = "%s%s" % (email, random_username)
        pwd = make_password(pwd)
        try:
            user = AuthUser.objects.create(
                username=username, password=pwd, phone=phone, email=email, role_type=role_type, nickname=nickname)
        except Exception, e:
            logger.error("user register error(%s, %s, %s), msg(%s)" % (username, phone, email, e))
            return None, ErrorCode.INTERNAL_ERROR
        return user, ErrorCode.SUCCESS


class OrganizationUtils(object):

    @classmethod
    def get_child_orgs(cls, assess_id, parent_id, max_depth=None, depth_time=1):
    # def get_child_orgs(cls, enterprise_id, parent_id, max_depth=None, depth_time=1):
        from wduser.serializers import OrganizationBasicSerializer
        if parent_id == 0:
            level = 1
        else:
            level = depth_time
        orgs = Organization.objects.filter_active(assess_id=assess_id, parent_id=parent_id)
        org_data = []
        child_org_ids = []
        for org in orgs:
            org_info = OrganizationBasicSerializer(instance=org).data
            org_info["level"] = level
            # org_info = dict({
            #     "id": org.id,
            #     "name": org.name,
            #     "identification_code": org.identification_code,
            #     "parent_id": parent_id,
            #     "level": level,
            #     "list_custom_attrs": [u"自定义标签1", u"自定义标签2", u"自定义标签3"]
            # })
            child_org_ids.append(org.id)
            if max_depth is None or depth_time < max_depth:
                child_org_data, ids = OrganizationUtils.get_child_orgs(assess_id, org.id, max_depth, depth_time + 1)
                org_info["child_orgs"] = child_org_data
                child_org_ids += ids
            else:
                org_info["child_orgs"] = []
            org_data.append(org_info)
        return org_data, child_org_ids

    @classmethod
    def get_parent_org_names(cls, org_codes):
        org_names = []

        def get_org_name(org_code=None, org_id=None):
            try:
                if org_code:
                    org = Organization.objects.get(identification_code=org_code, is_active=True)
                elif org_id:
                    org = Organization.objects.get(id=org_id)
                else:
                    return
                org_names.append(org.name)
                if not org.parent_id:
                    return
                else:
                    get_org_name(org_id=org.parent_id)
            except:
                pass
        for org_code in org_codes:
            get_org_name(org_code=org_code)
        return org_names

    @classmethod
    def get_tree_organization(cls, assess_id, parent_id=0, max_depth=None):
        from wduser.serializers import OrganizationBasicSerializer
        level = 1
        if parent_id != 0:
            porg = Organization.objects.get(id=parent_id)
            porg_info = OrganizationBasicSerializer(instance=porg).data
            porg_info["level"] = level
            porg_info["child_orgs"] = OrganizationUtils.get_child_orgs(assess_id, parent_id, max_depth)[0]
            # porg_info = dict({
            #     "id": porg.id,
            #     "name": porg.name,
            #     "identification_code": porg.identification_code,
            #     "parent_id": porg.parent_id,
            #     "list_custom_attrs": [u"自定义标签1", u"自定义标签2", u"自定义标签3"],
            #     "level": level,
            #     "child_orgs": OrganizationUtils.get_child_orgs(enterprise_id, parent_id, max_depth)[0]
            # })
            return porg_info
        return OrganizationUtils.get_child_orgs(assess_id, parent_id, max_depth)[0]

    @classmethod
    def generate_org_code(cls, assess_id, org_name):
        if type(org_name) == str:
            try:
                org_name = org_name.encode("utf-8")
            except Exception, e:
                logger.error("org name encode utf8 error, msg: %s" % e)
        code = '%s%s%s' % (get_first_char(org_name, 4), assess_id, get_random_int(4))
        return code


class OrgImportExport(ExcelUtils):
    ORG_LEVEL = ['零级组织', '一级组织', '二级组织', '三级组织', '四级组织', '五级组织', '六级组织',
                 '七级组织', '八级组织', '九级组织', '十级组织']
    ORG_OPS_EXISTS = [u"现有", '1']
    ORG_OPS_CREATED = [u"新增", '2']
    ORG_OPS_UPDATE = [u"更新", '3']
    ORG_OPS_DELETE = [u"删除", '4']
    download_path = os.path.join(BASE_DIR, "download")
    # enterprise_path = os.path.join(download_path, "enterprise")
    assess_path = os.path.join(download_path, "assess")
    template_dir = os.path.join(download_path, "template")

    if not os.path.exists(assess_path):
        os.mkdir(assess_path)

    if not os.path.exists(template_dir):
        os.mkdir(template_dir)

    @staticmethod
    def get_title():
        # return [u"组织级别(可填：一级组织/二级组织/三级组织...)", u"组织名称", u"组织代码（系统生成，不可修改）", u"父组织名称", u"父组织代码(系统生成，不可修改)", u"状态（可填：现有/新增/更新/删除，也可以用1/2/3/4代替）"]
        return [u"一级组织", u"二级组织", u"三级组织", u"四级组织",
                u"五级组织", u"六级组织", u"七级组织", u"八级组织",
                u"九级组织", u"十级组织",]

    @classmethod
    def export_template(cls):
        u"""

        :return: 组织模版文件路径 文件名
        """
        file_name = u"wd-org-import-template-v4.xlsx"
        titles = cls.get_title()
        file_full_path = os.path.join(cls.template_dir, file_name)
        if os.path.exists(file_full_path):
            return file_full_path, file_name
        file_full_path = ExcelUtils().create_excel(file_name, titles, [], parent_dir=cls.template_dir, sheet_index=0)
        return file_full_path, file_name

    @classmethod
    def export_org_data_old(cls, assess_id):
        u"""
        导出企业组织数据
        :param assess_id: 项目ID
        :return: 组织数据文件路径  文件名
        """
        def get_org_list(org_tree, porg_name=u"", porg_code=u""):
            for org in org_tree:
                try:
                    level_name = cls.ORG_LEVEL[org["level"]]
                except:
                    level_name = u"子组织"
                org_list.append([
                    level_name,
                    org["name"],
                    org["identification_code"],
                    porg_name,
                    porg_code,
                    u"现有"
                ])
                if org["child_orgs"]:
                    get_org_list(org["child_orgs"], org["name"], org["identification_code"])

        org_tree = OrganizationUtils.get_tree_organization(assess_id)
        org_list = []
        get_org_list(org_tree)

        timestamp = int(time.time())
        file_name = "wd-org-data-export-%s.xlsx" % timestamp
        file_path = ExcelUtils().create_excel(file_name, cls.get_title(), org_list, parent_dir=cls.assess_path)
        return file_path, file_name

    @classmethod
    def export_org_data(cls, assess_id):
        u"""
        导出企业组织数据
        :param enterprise_id: 企业ID
        :return: 组织数据文件路径  文件名
        """
        def get_org_list(org_tree, porg_names=[]):
            for org in org_tree:
                # try:
                #     level_name = cls.ORG_LEVEL[org["level"]]
                # except:
                #     level_name = u"子组织"
                # org_names = porg_names.append(org["name"])
                # org_list.append(org_names)
                # if org["child_orgs"]:
                #     get_org_list(org["child_orgs"], org_names)
                org_names = copy.deepcopy(porg_names)
                org_names.append(org["name"])
                if org["child_orgs"]:
                    get_org_list(org["child_orgs"], org_names)
                else:
                    org_list.append(org_names)

        org_tree = OrganizationUtils.get_tree_organization(assess_id)
        org_list = []
        get_org_list(org_tree)
        timestamp = int(time.time())
        title = cls.get_title()
        title.append(u'组织码')
        for x in org_list:
            end_org_name = x[-1]
            b = len(x)
            if b < 10:
                x.extend([u'' for i in range(10-b)])
            org_qs = Organization.objects.filter(name=end_org_name, assess_id=assess_id).order_by('-parent_id')
            if org_qs.exists():
                org_code = org_qs[0].identification_code
                x.append(org_code)
        file_name = "wd-org-data-export-%s.xlsx" % timestamp
        file_path = ExcelUtils().create_excel(file_name, title, org_list, parent_dir=cls.assess_path, sheet_index=0)
        return file_path, file_name

    @classmethod
    def import_data(cls, file_data, file_name, assess_id=0):
        now = datetime.datetime.now()
        str_today = now.strftime("%Y-%m-%d")
        file_path = os.path.join(cls.assess_path, assess_id, str_today)
        if not os.path.exists(file_path):
            os.makedirs(file_path)
        file_full_path = os.path.join(file_path, file_name)
        f = open(file_full_path, "wb")
        for chunk in file_data.chunks():
            f.write(chunk)
        f.close()
        return file_full_path

