# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import hashlib
import os

import time

import datetime

from WeiDuAdmin import settings
from WeiDuAdmin.env import CLIENT_HOST
from WeiDuAdmin.settings import BASE_DIR
from assessment.models import AssessUser, AssessSurveyRelation
from utils import str_check
from utils.excel import ExcelUtils
from wduser.models import AuthUser, People, PeopleOrganization, PeopleAccount

class AssessImportExport(ExcelUtils):
    download_path = os.path.join(BASE_DIR, "download")
    assess_path = os.path.join(download_path, "assess")
    template_dir = os.path.join(download_path, "template")
    link_dir = os.path.join(download_path, "link")

    if not os.path.exists(assess_path):
        os.mkdir(assess_path)

    if not os.path.exists(template_dir):
        os.mkdir(template_dir)

    @staticmethod
    def get_title(assess_id=None):
        title_people = [
            u"姓名(必填)",
            u"帐号(帐号/手机/邮箱三选一必填)",
            u"手机号(帐号/手机/邮箱三选一必填)",
            u"邮箱(帐号/手机/邮箱三选一必填)",
        ]
        if assess_id in settings.dingzhi_assess_ids:
            title_type_account = [y for x, y in PeopleAccount.ACCOUNT_TYPE]
            title_people.extend(title_type_account)
        title_ops = [
            u"密码(默认123456)",
            u"操作（增加/修改/删除）",
        ]
        title_info = [
            u"出生日期(如:20010101)",  # 注 用户信息从6开始,前面如若增加,需谨慎
            u"身份证",
            u"面试场地",
            u"岗位",
            u"职务名称",
            u"用工方式(劳务制员工/合同制员工/其他用工方式)",
            u"入职时间",
            u"年龄(25岁以下/26-30岁/31-35岁/36-40岁/41-45岁/46岁-50岁/51岁以上)",
            u"性别(男/女)",
            u"婚姻状况(未婚/已婚/离异)",
            u"生育情况(已育一个孩子/已育两个孩子/正在孕育/未育)",
            u"子女成长情况(小学/初中/高中/大学及研究生以上/已工作/幼儿园及以下/其他)",
            u"父母健康状况(让我担心/健康良好)",
            u"个人健康状况(让自己担心/健康良好)",
            u"配偶工作情况(在职工作且繁忙/在职工作且可以顾家/全职在家)",
            u"是否独生子女(独生子女/有弟弟或妹妹/有姐姐或哥哥/有兄弟姐妹)",
            u"学历(大专以下/大专/本科/硕士研究生/博士研究生)",
            u"政治面貌(群众/共青团员/中共预备党员/中共党员/其他)",
            u"司龄(在当前公司工作的时长，1年以下/1-2年/3-5年/5-7年/8-10年/10-14年/15年以上)",
            u"工龄(第一份全日制工作到现在的时间，1年以下/1-3年/4-6年/7-9年/10-14年/15年以上)",
            u"薪酬模式(年薪制/岗位绩效工资制/项目工资制/计件（时）工资制/业绩提成制)",
            u"职级(客户公司详细/定制)",
            u"层级(高层管理人员/中层管理人员/基层管理人员/员工)",
            u"岗位类别(管理族/技术族/专业族/营销族/操作族/基础服务族)",
            u"内外勤(中后台，内勤/外勤（前台/中台/后台）)",
            u"岗位序列()",
        ]
        title_org = [
            u"一级组织(必填)",
            u"二级组织(必填)",
            u"三级组织(必填)",
            u"四级组织(必填)",
            u"五级组织(必填)",
            u"六级组织(必填)",
            u"七级组织(必填)",
            u"八级组织(必填)",
            u"九级组织(必填)",
            u"十级组织(必填)",
        ]
        title_free = [
            u'此列空，后续列可自由属性'
        ]
        title = []
        title.extend(title_people)
        title.extend(title_ops)
        title.extend(title_info)
        title.extend(title_org)
        title.extend(title_free)
        return title

    @staticmethod
    def get_link_title():
        return [
            u"帐号",
            u"姓名",
            u"手机号",
            u"邮箱",
            u"专属链接"
        ]

    @classmethod
    def export_template(cls, assess_id=None):
        u"""
        :return: 项目导入模版文件路径 文件名
        """
        file_name = u"wd-assess-import-template-v17.xlsx"
        assess_id = settings.dingzhi_DEBUG
        if assess_id:
            file_name = u"wd-assess-import-template-v16-%s.xlsx" % assess_id
        titles = cls.get_title(assess_id)
        file_full_path = os.path.join(cls.template_dir, file_name)
        if os.path.exists(file_full_path):
            return file_full_path, file_name
        file_full_path = ExcelUtils().create_excel(file_name, titles, [], parent_dir=cls.template_dir, sheet_index=0)
        return file_full_path, file_name

    @classmethod
    def export_dedicated_link(cls, assess_id):
        u"""

        :return: 项目导入模版文件路径 文件名  df
        """
        file_name = u"wd-assess" + str(assess_id) + u"-export_dedicated_link-v7.xlsx"
        titles = cls.get_link_title()
        # 项目的所有用户
        people_obj_user_ids = AssessUser.objects.filter_active(assess_id=assess_id).values_list("people_id", flat=True).distinct()
        people_authuser_ids = People.objects.filter_active(id__in=people_obj_user_ids).values_list('user_id', flat=True).distinct()
        # 找到people
        data = []
        authuser_objs = AuthUser.objects.filter(id__in=people_authuser_ids)
        for authuser_obj in authuser_objs:
            if not authuser_obj.dedicated_link:
                id_str = "%10d" % authuser_obj.id
                sha1 = hashlib.sha1()
                sha1.update(id_str)
                dedicated_link = sha1.hexdigest()
                authuser_obj.dedicated_link = dedicated_link
                authuser_obj.save()
            link = CLIENT_HOST + '/people/'+str(authuser_obj.dedicated_link)+'/'
            # people.username
            # 参与人员列表里面的是people.username 就是nickname
            data.append([str_check(authuser_obj.account_name), authuser_obj.nickname, authuser_obj.phone, authuser_obj.email, link])
        file_full_path = ExcelUtils().create_excel(file_name, titles, data, sheet_name="link", parent_dir=cls.link_dir, sheet_index=0)
        return file_full_path, file_name

    @classmethod
    def export_org_data(cls, enterprise_id):
        u"""
        导出企业组织数据
        :param enterprise_id: 企业ID
        :return: 组织数据文件路径  文件名
        """
        pass

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


class AssessPeopleExport(object):
    u"""项目人员导出"""

    def __init__(self, assess_id, org_codes):
        # 默认名字
        timestamp = time.time() * 1000
        default_export_file_name = "survey_user_download_v3_%s_%s.xlsx" % (assess_id, timestamp)
        # 没有项目则空
        self.assess_id = assess_id
        # 抓取该项目下问卷所有问卷
        self.survey_ids = list(AssessSurveyRelation.objects.filter_active(
            assess_id=assess_id).values_list("survey_id", flat=True))
        # 没有填组织的则找到项目下所有人
        if org_codes is None:
            self.people_ids = AssessUser.objects.filter_active(
                assess_id=assess_id).values_list("people_id", flat=True).distinct()
        else:
            # 否则找到组织下所有人
            org_codes = org_codes.split(",")
            self.people_ids = PeopleOrganization.objects.filter_active(
                org_code__in=org_codes).values_list("people_id", flat=True).distinct()