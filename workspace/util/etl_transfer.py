# -*- coding:utf-8 -*-
import re
import os
import sys
import time
import pandas as pd
import pymysql
import functools
from utils.logger import get_logger
from celery import shared_task
from collections import OrderedDict
from wduser.models import AuthUser
from workspace.models import FactOEI
from workspace.util.redispool import redis_pool
from wduser.models import BaseOrganization, BaseOrganizationPaths
from django.db import connection, connections

reload(sys)
sys.setdefaultencoding('utf8')

logger = get_logger("etl")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
etl_data_dir = os.path.join(os.path.dirname(BASE_DIR), 'etl_data')
if not os.path.exists(etl_data_dir):
    os.mkdir(etl_data_dir)


def try_catch(func):
    @functools.wraps(func)
    def inner(*args, **kwargs):
        name = kwargs.get("name")
        try:
            logger.info(u"%s开始" % name)
            ret = func(*args, **kwargs)
            logger.info(u"%s结束" % name)
            return ret
        except Exception, e:
            logger.error(u"执行%s出错" % name)
            redis_pool.rpush(redis_key, time.time(), 2)
            raise e

    return inner


def get_data(conn, sql, *args):
    cursor = conn.cursor()
    cursor.execute(sql, args)
    return cursor.fetchall()


# class MySqlConn:
#     def __init__(self, host, port, db, user, pwd):
#         self.conn = pymysql.connect(host=host, port=port, database=db, user=user, password=pwd)
#         self.cursor = self.conn.cursor()
#
#     def get_data(self, sql, *args):
#         rows = self.cursor.execute(sql, args)
#         return self.cursor.fetchall()
#
#     def close(self):
#         self.cursor.close()
#         self.conn.close()


# 人员列表
@try_catch
def list_people(conn, pro_id, sur_id, name):
    sql = """
        SELECT
        people_id
        FROM front_peoplesurveyrelation
        where
        is_active=true 
        and project_id=%s
        and survey_id=%s
        order by people_id
        """
    res = ['people_id'], get_data(conn, sql, pro_id, sur_id)
    return res


# 问卷答案
@try_catch
def get_answer(conn, pro_id, sur_id, name):
    sql = """
            SELECT
            people_id, question_id, sum(answer_score) as answer_score
            FROM front_userquestionanswerinfo a,
            (select max(id) id FROM front_userquestionanswerinfo 
            where project_id=%s and survey_id=%s and is_active=true
            group by people_id,question_id,answer_id
            ) b
            where a.id=b.id
            group by people_id,question_id
            order by people_id,question_id
        """
    res = get_data(conn, sql, pro_id, sur_id)
    # ((people_id, question_id, sum(answer_score)), (people_id, question_id, sum(answer_score)), ...)
    return ['people_id', 'question_id', 'answer_score'], res


# 题目编号
@try_catch
def question_tag(conn, t_id, name):
    sql = """
        SELECT
        object_id
        , tag_value
        FROM research_questiontagrelation
        where is_active=true 
        and tag_id=%s
        order by object_id
        """
    res = get_data(conn, sql, t_id)
    return ['object_id', 'tag_value'], res  # ((object_id, tag_value), )


# Row denormaliser
@try_catch
def row_denormaliser(value_lists, name):
    res = OrderedDict()
    for lst in value_lists:  # lst = ['people_id', 'answer_score', 'tag_value']
        key = lst[0]
        tag = lst[2]
        # tagValue合法性
        re_rule = r"G\d|S\d|C\d{1,2}|R\d|L\d{1,2}|Z\d{1,2}|X\d{1,2}|BENM\d|MASK\d|N\d{1,2}"

        if re.match(re_rule, tag):
            if key not in res:
                res[key] = {"score": [], "tag_value": []}
                res[key]["score"].append(lst[1])
                res[key]["tag_value"].append(lst[2])
            else:
                res[key]["score"].append(lst[1])
                res[key]["tag_value"].append(lst[2])
    ret = []
    # len(target_tag_value) == 126
    origin_tag_value = [
        'G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8',
        'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9',
        'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'C9', 'C10',
        'R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7', 'R8',
        'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8', 'L9', 'L10', 'L11', 'L12', 'L13', 'L14', 'L15', 'L16', 'L17',
        'L18', 'L19', 'L20',
        'Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6', 'Z7', 'Z8', 'Z9', 'Z10', 'Z11', 'Z12', 'Z13', 'Z14', 'Z15', 'Z16', 'Z17',
        'Z18', 'Z19', 'Z20', 'Z21', 'Z22', 'Z23',
        'X1', 'X2', 'X3', 'X4', 'X5', 'X6', 'X7', 'X8', 'X9', 'X10', 'X11', 'X12', 'X13', 'X14', 'X15', 'X16', 'X17',
        'X18',
        'BENM1', 'BENM2',
        'MASK1', 'MASK2', 'MASK3', 'MASK4',
        'N1', 'N2', 'N3', 'N4', 'N5', 'N6', 'N7', 'N8', 'N9', 'N10', 'N11', 'N12', 'N13', 'N14', 'N15', 'N16', 'N17',
        'N18', 'N19', 'N20', 'N21', 'N22', 'N23', 'N24',
    ]
    for pid in res:
        line = [pid]
        scores = res[pid]["score"]
        tags = res[pid]["tag_value"]
        order_score = [0 for j in xrange(126)]
        for idx, tag in enumerate(tags):
            origin_tag_index = origin_tag_value.index(tag)
            order_score[origin_tag_index] = scores[idx]
        line.extend(order_score)
        ret.append(line)
    colIndex = ['people_id'] + origin_tag_value
    return colIndex, ret


# ***************人员列表、问卷答案************
def line3(conn, pro_id, sur_id, t_id, *args):
    admin_conn = args[0]
    # 人员列表 ((people_id, ), (people_id, ), ...)
    column_index_pit, people_id_tuples = list_people(conn, pro_id, sur_id, name=u"查询人员列表")
    column_index_at, answer_tuples = get_answer(conn, pro_id, sur_id, name=u"查询问卷答案")

    column_index_mj2, merge_join_2 = merge(answer_tuples, people_id_tuples, column_index_at, column_index_pit,
                                           how='left', on=['people_id'], name="merge_join_2")
    merge_join_2.sort(key=lambda x: x[1])
    column_index_qt, question_tag_tuples = question_tag(admin_conn, t_id, name=u"查询题目编号")
    column_index_mj, merge_join = merge(merge_join_2, question_tag_tuples, column_index_mj2, column_index_qt,
                                        left_on=['question_id'], right_on=['object_id'],
                                        del_column=['question_id', 'object_id'], name="merge_join")
    select_value = merge_join
    column_index_sv = ['people_id', 'answer_score', 'tag_value']
    select_value.sort(key=lambda x: (x[0], x[2]))
    column_index_rd, RowDenormaliser = row_denormaliser(select_value, name=u"列转行")
    # Sort rows 4
    RowDenormaliser.sort(key=lambda x: x[0])
    sort_rows_4 = RowDenormaliser
    return column_index_rd, sort_rows_4


@try_catch
def merge(left, right, lindex, rindex, how='inner', on=None, left_on=None, right_on=None, del_column=None, axis=1,
          **kwargs):
    # 转DataFrame对象，设置列索引
    if not isinstance(left, list):
        left = list(left)
    if not isinstance(right, list):
        right = list(right)
    pd_left = pd.DataFrame(left)
    pd_left.columns = lindex

    pd_right = pd.DataFrame(right)
    pd_right.columns = rindex
    # merge
    result = pd.merge(pd_left, pd_right, how=how, on=on, left_on=left_on, right_on=right_on)
    result = result.drop_duplicates()  # 去重
    if del_column:  # 删除列
        result = result.drop(del_column, axis=axis)
    # 处理NaN
    result = result.where(result.notnull(), None)

    return result.columns.tolist(), result.values.tolist()


@try_catch
def query_user_id(conn, aid, name):
    sql = """
    SELECT
        user_id, id people_id
        FROM wduser_people a,
        (SELECT c.people_id FROM 
        assessment_assessproject a,
        assessment_assessuser c
        where c.is_active=true
        and a.id=%s
        and c.assess_id=a.id) b
        where a.is_active=true and a.id=b.people_id
        """
    res = get_data(conn, sql, aid)
    user_id = [i[0] for i in res]
    user_people_index = ['user_id', 'people_id']
    return user_id, res, user_people_index


def cal_year(date):
    if not date:
        return None
    ts = time.mktime(date.timetuple())  # timestamp
    s = time.time() - ts
    return int(s / (365 * 24 * 60 * 60))


def get_user_info(user_ids):
    res = []
    people_info = AuthUser.objects.filter(id__in=user_ids).values_list(
        "id", "username", "birthday", "gender__value", "sequence__value", "hiredate", "rank__value", "organization_id"
    )
    for personal in people_info:
        info = [personal[0], personal[1], cal_year(personal[2]), personal[3],
                personal[4], cal_year(personal[5]), personal[6], personal[7]]
        res.append(info)
    res.sort(key=lambda x: x[0])
    index = ['user_id', 'username', u"年龄", u"性别", u"岗位序列", u"司龄", u"层级", 'org_id']
    return index, res


def line1(conn, aid):
    user_ids, user_people_id, user_people_index = query_user_id(conn, aid, name=u"查询参加人员")
    column_index_sv3, select_values_3 = get_user_info(user_ids)
    column_index, select_values = merge(user_people_id, select_values_3, user_people_index, column_index_sv3,
                                        on='user_id', del_column='user_id', name="merge user_id people_id")
    return column_index, select_values


def get_org_siblings(org_id):
    redis_org_key = 'org_%s' % org_id
    org = redis_pool.get(redis_org_key)
    if not org:
        parents = BaseOrganizationPaths.objects.filter(child_id=org_id).values_list('parent_id').order_by("-depth")
        parent_id = [i[0] for i in parents]
        orgs = BaseOrganization.objects.filter(id__in=parent_id).values_list("name")
        org = '.'.join([j[0] for j in orgs])
        redis_pool.set(redis_org_key, org)
    return org


# ***************机构一览表************
# 机构一览表
@try_catch
def list_org(conn, aid, name):  # orgname, orgcode
    sql = """
            select baseorganization_id
            from wduser_organization
            where is_active=true and assess_id=%s
            """
    res = get_data(conn, sql, aid)  # res = (('org_id'), ('org_id'), )
    org_name_id = []
    for i in res:
        orgname = get_org_siblings(i[0])
        org_name_id.append([orgname, i[0]])
    return ['orgname', 'org_id'], org_name_id


# Split fields 2
@try_catch
def split_field_2(orgs, name):
    res = []
    for org in orgs:
        org_list = org[0].split(".")
        if len(org_list) < 9:
            length = 9 - len(org_list)
            org_list.extend([None] * length)
        org_list.append(org[1])
        res.append(org_list)
    return res


def line2(conn, aid):  # [org1,org2,...org9, org_code]
    column_index_orgs, orgs = list_org(conn, aid, name=u"机构一览表")
    split_field = split_field_2(orgs, name="split field 2")
    orgs_index = [u'一级机构',
                  u'二级机构',
                  u'三级机构',
                  u'四级机构',
                  u'五级机构',
                  u'六级机构',
                  u'七级机构',
                  u'八级机构',
                  u'九级机构',
                  'org_id'
                  ]
    split_field.sort(key=lambda x: x[-1])
    return orgs_index, split_field


# 计算所有分数
@try_catch
def compute_all(all_score, assessID, hidden_people_id, reference, **kwargs):
    fact_list = []
    for person_score_list in all_score:
        if None not in person_score_list[16:]:
            # 计算mask1-4
            mask_score = person_score_list[114: 118]
            mask = filter_mask(mask_score, reference)
            x_dict = get_X(person_score_list)
            fact_obj = model_obj_create(person_score_list, assessID, x_dict, hidden_people_id, mask)
            fact_list.append(fact_obj)
    FactOEI.objects.bulk_create(fact_list)


def filter_mask(mask_score, reference):
    if sum(mask_score) >= reference * 4:
        return True
    return False


def get_X(person_score_list):
    x = ['X1', 'X2', 'X3', 'X4', 'X5', 'X6', 'X7', 'X8', 'X9', 'X10',
         'X11', 'X12', 'X13', 'X14', 'X15', 'X16', 'X17', 'X18']
    x_value = person_score_list[94: 112]
    return dict(zip(x, x_value))


def get_scale_and_dimension(person_score_list):
    scale1 = (sum(person_score_list[94: 98]) * 20 / 4 +
              sum(person_score_list[98: 103]) * 20 / 5 +
              sum(person_score_list[103: 106]) * 20 / 3 +
              sum(person_score_list[106: 109]) * 20 / 3 +
              sum(person_score_list[109: 112]) * 20 / 3) / 5
    scale2 = 0  # 目前没有该项
    scale3 = 0  # 目前没有该项
    dimension1 = ((person_score_list[16] + person_score_list[17]) * 20 / 2 +
                  person_score_list[18] * 20 +
                  person_score_list[19] * 20 +
                  person_score_list[20] * 20 +
                  (person_score_list[21] + person_score_list[22]) * 20 / 2 +
                  person_score_list[23] * 20) / 6
    dimension2 = (person_score_list[24] * 20 +
                  (person_score_list[25] + person_score_list[26]) * 20 / 2 +
                  (person_score_list[27] + person_score_list[28]) * 20 / 2 +
                  person_score_list[29] * 20 +
                  (person_score_list[30] + person_score_list[31] + person_score_list[32]) * 20 / 3) / 5
    dimension3 = (sum(person_score_list[33: 37]) * 20 / 4 +
                  (person_score_list[37] + person_score_list[38] + person_score_list[39]) * 20 / 3 +
                  (person_score_list[40] + person_score_list[41] + person_score_list[42]) * 20 / 3) / 3
    dimension4 = ((person_score_list[43] + person_score_list[44]) * 20 / 2 +
                  (person_score_list[45] + person_score_list[46]) * 20 / 2 +
                  (person_score_list[47] + person_score_list[48]) * 20 / 2 +
                  person_score_list[49] * 20 +
                  person_score_list[50] * 20) / 5
    dimension5 = ((person_score_list[51] + person_score_list[52] + person_score_list[53]) * 20 / 3 +
                  (person_score_list[54] + person_score_list[55]) * 20 / 2 +
                  sum(person_score_list[56: 64]) * 20 / 8 +
                  (person_score_list[64] + person_score_list[65]) * 20 / 2 +
                  (person_score_list[66] + person_score_list[67] + person_score_list[68]) * 20 / 3 +
                  (person_score_list[69] + person_score_list[70]) * 20 / 2) / 6
    dimension6 = (person_score_list[71] * 20 +
                  (person_score_list[72] + person_score_list[73]) * 20 / 2 +
                  (person_score_list[74] + person_score_list[75]) * 20 / 2 +
                  (person_score_list[76] + person_score_list[77]) * 20 / 2 +
                  (person_score_list[78] + person_score_list[79]) * 20 / 2 +
                  (person_score_list[80] + person_score_list[81]) * 20 / 2 +
                  sum(person_score_list[82: 86]) * 20 / 4 +
                  (person_score_list[86] + person_score_list[87]) * 20 / 2 +
                  (person_score_list[88] + person_score_list[89]) * 20 / 2 +
                  sum(person_score_list[90: 94]) * 20 / 4) / 10
    dimension7 = sum(person_score_list[118:]) * 25 / 24
    return scale1, scale2, scale3, dimension1, dimension2, dimension3, dimension4, dimension5, dimension6, dimension7


def merge_quota(person_score_list):
    quota55 = (sum(person_score_list[118: 122]) + sum(person_score_list[124: 126]) +
               sum(person_score_list[128: 130])) * 25 / 2 / 4
    quota56 = (sum(person_score_list[126: 128]) + sum(person_score_list[134: 140])) * 25 / 2 / 4
    quota57 = (sum(person_score_list[122: 124]) + sum(person_score_list[130: 134]) +
               sum(person_score_list[140:])) * 25 / 2 / 4
    return quota55, quota56, quota57


def model_obj_create(person_score_list, assessID, x_dict, hidden_people_id, mask):
    scale1, scale2, scale3, dimension1, dimension2, dimension3, dimension4, dimension5, dimension6, dimension7 = get_scale_and_dimension(person_score_list)
    quota55, quota56, quota57 = merge_quota(person_score_list)
    score_dict = {
        'AssessKey': assessID,
        'DW_Person_ID': person_score_list[0],
        'profile1': person_score_list[2],
        'profile2': person_score_list[3],
        'profile3': person_score_list[4],
        'profile4': person_score_list[5],
        'profile5': person_score_list[6],
        'organization1': person_score_list[7],
        'organization2': person_score_list[8],
        'organization3': person_score_list[9],
        'organization4': person_score_list[10],
        'organization5': person_score_list[11],
        'organization6': person_score_list[12],

        'scale1': scale1,  # 幸福效能
        'scale2': scale2,  # 岗位压力  目前没有该项
        'scale3': scale3,  # 幸福度  目前没有该项
        'dimension1': dimension1,  # 工作投入
        'dimension2': dimension2,  # 生活愉悦
        'dimension3': dimension3,  # 成长有力
        'dimension4': dimension4,  # 人际和谐
        'dimension5': dimension5,  # 领导激发
        'dimension6': dimension6,  # 组织卓越
        'dimension7': dimension7,  # 个人幸福能力

        # 幸福总分
        'model': (dimension1 + dimension2 + dimension3 + dimension4 + dimension5 + dimension6) / 6 * 0.8 + dimension7 * 0.2,

        'quota1': (person_score_list[16] + person_score_list[17]) * 20 / 2,  # G1-2 安全健康
        'quota2': person_score_list[18] * 20,  # G3 环境舒适
        'quota3': person_score_list[19] * 20,  # G4 条件支持
        'quota4': person_score_list[20] * 20,  # G5 角色清晰
        'quota5': (person_score_list[21] + person_score_list[22]) * 20 / 2,  # G6 G7 任务安排
        'quota6': person_score_list[23] * 20,  # G8 工作成就

        'quota7': person_score_list[24] * 20,  # S1 薪酬保障
        'quota8': (person_score_list[25] + person_score_list[26]) * 20 / 2,  # S2 S3 生活平衡
        'quota9': (person_score_list[27] + person_score_list[28]) * 20 / 2,  # S4 S5 福利关爱
        'quota10': person_score_list[29] * 20,  # S6 家庭关爱
        'quota11': (person_score_list[30] + person_score_list[31] + person_score_list[32]) * 20 / 3,  # S7 - 9 身心关爱

        'quota12': sum(person_score_list[33: 37]) * 20 / 4,  # C1-4 成长路径
        'quota13': (person_score_list[37] + person_score_list[38] + person_score_list[39]) * 20 / 3,  # C5 - 7 系统培养
        'quota14': (person_score_list[40] + person_score_list[41] + person_score_list[42]) * 20 / 3,  # C8 - 10 成长机制

        'quota15': (person_score_list[43] + person_score_list[44]) * 20 / 2,  # R1 - 2 共同担当
        'quota16': (person_score_list[45] + person_score_list[46]) * 20 / 2,  # R3 - 4 跨界协作
        'quota17': (person_score_list[47] + person_score_list[48]) * 20 / 2,  # R5 - 6 开放包容
        'quota18': person_score_list[49] * 20,  # R7 人际吸引
        'quota19': person_score_list[50] * 20,  # R8 相互促进

        'quota20': (person_score_list[51] + person_score_list[52] + person_score_list[53]) * 20 / 3,  # L1 - 3 目标引领
        'quota21': (person_score_list[54] + person_score_list[55]) * 20 / 2,  # L4 - 5 系统把握
        'quota22': sum(person_score_list[56: 64]) * 20 / 8,  # L6 - 13 激发信任
        'quota23': (person_score_list[64] + person_score_list[65]) * 20 / 2,  # L14 - 15 读懂他人
        'quota24': (person_score_list[66] + person_score_list[67] + person_score_list[68]) * 20 / 3,  # L16 - 18 释放潜能
        'quota25': (person_score_list[69] + person_score_list[70]) * 20 / 2,  # L19 - 20 促进成长

        'quota26': person_score_list[71] * 20,  # Z1 愿景激发
        'quota27': (person_score_list[72] + person_score_list[73]) * 20 / 2,  # Z2 - 3 组织配置
        'quota28': (person_score_list[74] + person_score_list[75]) * 20 / 2,  # Z4 - 5 流程高效
        'quota29': (person_score_list[76] + person_score_list[77]) * 20 / 2,  # Z6 - 7 授权赋能
        'quota30': (person_score_list[78] + person_score_list[79]) * 20 / 2,  # Z8 - 9 纵向支持
        'quota31': (person_score_list[80] + person_score_list[81]) * 20 / 2,  # Z10 - 11 信息透明
        'quota32': sum(person_score_list[82: 86]) * 20 / 4,  # Z12 - 15 价值激励
        'quota33': (person_score_list[86] + person_score_list[87]) * 20 / 2,  # Z16 - 17 鼓励创新
        'quota34': (person_score_list[88] + person_score_list[89]) * 20 / 2,  # Z18 - 19 文化优秀
        'quota35': sum(person_score_list[90: 94]) * 20 / 4,  # Z20 - 23 品牌影响

        'quota36': sum(person_score_list[94: 98]) * 20 / 4,  # X1 - 4 工作状态
        'quota37': sum(person_score_list[98: 103]) * 20 / 5,  # X5 - 9 留任倾向
        'quota38': sum(person_score_list[103: 106]) * 20 / 3,  # X10 - 12 组织认同
        'quota39': sum(person_score_list[106: 109]) * 20 / 3,  # X13 - 15 敬业投入
        'quota40': sum(person_score_list[109: 112]) * 20 / 3,  # X16 - 18 团队活力

        'quota41': person_score_list[112] * 20,  # BENM1 岗位压力
        'quota42': person_score_list[113] * 10,  # BENM2 幸福度

        'quota43': (person_score_list[118] + person_score_list[119]) * 25 / 2,  # N1 - 2 自主定向
        'quota44': (person_score_list[120] + person_score_list[121]) * 25 / 2,  # N3 - 4 意义寻求
        'quota45': (person_score_list[122] + person_score_list[123]) * 25 / 2,  # N5 - 6 自我悦纳
        'quota46': (person_score_list[124] + person_score_list[125]) * 25 / 2,  # N7 - 8 自我拓展
        'quota47': (person_score_list[126] + person_score_list[127]) * 25 / 2,  # N9 - 10 情绪调节
        'quota48': (person_score_list[128] + person_score_list[129]) * 25 / 2,  # N11 - 12 专注投入
        'quota49': (person_score_list[130] + person_score_list[131]) * 25 / 2,  # N13 - 14 亲和利他
        'quota50': (person_score_list[132] + person_score_list[133]) * 25 / 2,  # N15 - 16 包容差异
        'quota51': (person_score_list[134] + person_score_list[135]) * 25 / 2,  # N 17 - 18 乐观积极
        'quota52': (person_score_list[136] + person_score_list[137]) * 25 / 2,  # N19 - 20 自信坚韧
        'quota53': (person_score_list[138] + person_score_list[139]) * 25 / 2,  # N21 - 22 合理归因
        'quota54': (person_score_list[140] + person_score_list[141]) * 25 / 2,  # N23 - 24 灵活变通
        'quota55': quota55,
        'quota56': quota56,
        'quota57': quota57,
        'hidden': mask,
    }
    score_dict.update(x_dict)
    if person_score_list[0] in hidden_people_id:  # person_score_list[0] == people_id
        score_dict['hidden'] = True
    return FactOEI(**score_dict)


def get_avg_answer_time(conn, project_id, survey_id, stime):
    sql = """
        select people_id, AVG(answer_time)
        from front_userquestionanswerinfo
        where project_id=%s and survey_id=%s and is_active=true
        group by people_id
    """
    res = get_data(conn, sql, project_id, survey_id)
    hidden_people_id = [i[0] for i in res if i[1] < stime]
    return hidden_people_id


@shared_task
def main(AssessID, SurveyID, stime, reference):
    assess_id = project_id = AssessID  # 191
    survey_id = SurveyID  # 132
    tag_id = 54
    global redis_key
    redis_key = 'etl_%s_%s' % (assess_id, survey_id)
    redis_pool.rpush(redis_key, time.time(), 3)

    admin_conn = connections['default']
    front_conn = connections['front']
    redis_pool.rpush(redis_key, time.time(), 0)

    # Sort rows 3
    column_index_sr3, sort_rows_3 = line1(admin_conn, assess_id)

    column_index_sr2, sort_rows_2 = line2(admin_conn, assess_id)

    column_index_mj3, merge_join_3 = merge(sort_rows_3, sort_rows_2, column_index_sr3, column_index_sr2,
                                           how='left', on='org_id', del_column="org_id", name='merge_join_3')
    sort_select_values_2 = merge_join_3
    column_index_mj3[column_index_mj3.index('username')] = u'姓名'

    column_index_l3, sort_rows_4 = line3(front_conn, project_id, survey_id, tag_id, admin_conn)
    column_index_mj33, merge_join_3_3 = merge(sort_select_values_2, sort_rows_4, column_index_mj3, column_index_l3,
                                              how='left', on=["people_id"], name='merge_join_3_3')

    hidden_pid = get_avg_answer_time(front_conn, project_id, survey_id, stime)
    compute_all(merge_join_3_3, AssessID, hidden_pid, reference, name=u'计算各项维度分')

    with connection.cursor() as cursor:
        ret = cursor.callproc("CalculateFacet", (assess_id, survey_id,))
    redis_pool.rpush(redis_key, time.time(), 1)

