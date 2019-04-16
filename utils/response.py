# -*- coding:utf-8 -*-
from __future__ import unicode_literals
import json
from rest_framework.response import Response
from django.http.response import HttpResponse
from rest_framework.renderers import JSONRenderer


class ErrorCode(object):
    SUCCESS = 0

    FAILURE = 40000
    SENSITIVE_WORDS = FAILURE + 1

    INVALID_INPUT = 40400
    AUTHENTICATION_FAIL = 40401
    PERMISSION_FAIL = 40403
    INTERNAL_ERROR = 40500
    NOT_EXISTED = 40404
    METHOD_NOT_ALLOWED = 40405

    # user
    USER_CODE = 41000
    USER_ACCOUNT_NOT_FOUND = USER_CODE + 1
    USER_PWD_ERROR = USER_CODE + 2
    USER_ACTIVE_CODE_INVALID = USER_CODE + 3
    USER_ACTIVE_CODE_EXPIRED = USER_CODE + 4
    USER_PIC_CODE_INVALID = USER_CODE + 5
    USER_VERIFY_CODE_INVALID = USER_CODE + 6
    USER_ADMIN_PERMISSION_INVALID = USER_CODE + 7
    USER_ADMIN_ROLE_NAME_FORBID = USER_CODE + 8
    USER_ACCOUNT_EXISTS = USER_CODE + 9
    USER_ORG_CODE_VALID = USER_CODE + 10
    USER_ACCOUNT_NOT_EXISTS = USER_CODE + 11
    USER_PWD_MODIFY_OLD_PWD_ERROR = USER_CODE + 12
    USER_ANSWER_SURVEY_ORDER_ERROR = USER_CODE + 13
    USER_ACCOUNT_NAME_ERROR = USER_CODE + 14
    USER_INFO_ERROR = USER_CODE + 15
    USER_NICK_ACCOUNT_ERROR = USER_CODE + 16
    USER_PHONE_USED_ERROR = USER_CODE + 17
    USER_PHONE_REGUL_ERROR = USER_CODE + 18
    USER_EMAIL_USED_ERROR = USER_CODE + 19
    USER_EMAIL_REGUL_ERROR = USER_CODE + 20
    USER_UPDATE_ERROR = USER_CODE + 21
    USER_EMAIL_HAS_ERROR = USER_CODE + 22   # 您没有邮箱,请检查,修改邮箱
    USER_ACCOUNT_DOUBLE_ERROR = USER_CODE + 23
    USER_HAS_LOGIN_ERROR = USER_CODE + 24  # 用户已经登陆
    USER_HAS_LOGIN_OTHER_PLACE_ERROR = USER_CODE + 25  # 用户在另地登陆，或已过期
    USER_HAS_IN_ROLETYPE_ERROR = USER_CODE + 26  # 账号已存在 41026


    # enterprise
    ENTERPRISE = 42000
    ENTERPRISE_CNNAME_EXISTS = ENTERPRISE + 1
    ENTERPRISE_SHORT_NAME_EXISTS = ENTERPRISE + 2
    ENTERPRISE_DELETE_FAILED_WITH_ASSESS_PROJECT = ENTERPRISE + 3
    ENTERPRISE_LINK_ERROR = ENTERPRISE + 4
    ENTERPRISE_USER_ERROR = ENTERPRISE + 5
    ENTERPRISE_ASSESS_NONE_ERROR = ENTERPRISE + 6
    ENTERPRISE_LINK_LOGIN_ERROR = ENTERPRISE + 7

    # # org, project
    ORG_USED_IN_PROJECT_CAN_NOT_DELETE = ENTERPRISE + 100
    ORG_IMPORT_DATA_ERROR = ENTERPRISE + 101
    ORG_NAME_DOUBLE_ERROR = ENTERPRISE + 102
    ORG_PEOPLE_IN_ASSESS_ERROR = ENTERPRISE + 103
    PROJECT_BEGIN_CAN_NOT_DELETE = ENTERPRISE + 200
    PROJECT_SURVEY_USED_FORBID_DELETE = ENTERPRISE + 201
    PROJECT_SURVEY_USER_IMPORT_ERROR = ENTERPRISE + 202
    PROJECT_SURVEY_RELATION_VALID = ENTERPRISE + 203
    PROJECT_SURVEY_RELATION_REPEAT = ENTERPRISE + 204
    PROJECT_SURVEY_USER_IMPORT_ORG_ERROR = ENTERPRISE + 205
    PROJECT_ORG_EMPTY_ERROR = ENTERPRISE + 206
    PROJECT_ORG_INPUT_ERROR = ENTERPRISE + 207
    PROJECT_PEOPLE_ERROR = ENTERPRISE + 208
    PROJECT_ORG_CODE_EMPTY_ERROR = ENTERPRISE + 209  # 组织码不存在
    PROJECT_ORG_CODE_DOUBLE_ERROR = ENTERPRISE + 210  # 组织码重复
    PROJECT_NOT_OPEN_ERROR = ENTERPRISE + 211  # 项目非开放,
    ASSESSUSER_360_ROLE_TYPE_UP_DOWN_ERROR = ENTERPRISE + 212   # 该用户已有上级，不能设置下级

    # research
    RESEARCH = 43000
    RESEARCH_MODEL_NAME_REPEAT = RESEARCH + 1
    RESEARCH_MODEL_USED_MODIFY_ALGO_ERROR = RESEARCH + 2
    RESEARCH_MODEL_USED_DEL_ERROR = RESEARCH + 3
    RESEARCH_DIMENSION_MODIFY_FORBID = RESEARCH + 4
    RESEARCH_DIMENSION_DELETE_FORBID = RESEARCH + 5
    RESEARCH_MODEL_RELEASE_DATA_INVALID = RESEARCH + 6
    RESEARCH_MODEL_INHERIT_DATA_INVALID = RESEARCH + 7
    RESEARCH_COPY_SELF_FORBID = RESEARCH + 8
    RESEARCH_TAG_USED_MODIFY_DELETE_FORBID = RESEARCH + 9

    RESEARCH_REPORT_DELETE_FORBID = RESEARCH + 10
    RESEARCH_REPORT_NAME_FORBID = RESEARCH + 11
    RESEARCH_TAG_NAME_FORBID = RESEARCH + 12

    # survey
    SURVEY = 44000
    SURVEY_USED_DELETE_MODIFY_FORBID = SURVEY + 1
    SURVEY_RELEASE_FORBID_WITHOUT_MODEL = SURVEY + 2
    SURVEY_RELEASE_FORBID_MODEL_QUESTION_RELATED_ERROR = SURVEY + 3
    SURVEY_MODEL_SUBSTANDARD_NOT_RELATED_QUESTION = SURVEY + 4
    SURVEY_MODEL_RELATION_ERROR = SURVEY + 5
    SURVEY_FORCE_OPTION_RELATED_ERROR = SURVEY + 6
    SURVEY_QUESTION_AUTO_EMPTY = SURVEY + 7
    SURVEY_RAMDOM_NUM_ERROR = SURVEY + 8
    SURVEY_FORCE_OPTION_DIMENSION_ERROR = SURVEY + 9   # 问卷选项迫选个数大于维度个数  44009
    SURVEY_REALTION_OPTION_REPEAT_ERROR = SURVEY + 10  # 一个选项不能关联2个指标
    SURVEY_QUESTION_OPTION_DOUBLE_ERROR = SURVEY + 11   # 问卷不能同时关联选项与题目
    SURVEY_OPTION_QUESTION_TYPE_ERROR = SURVEY + 12   # 选项的题目类型不是迫选排序题
    SURVEY_OPTION_QUESTION_OF_DIMENSION_ERROR = SURVEY + 13   # 迫选排序题的不同选项不能关联在不同维度下
    SURVEY_FINISH_PART_ERROR = SURVEY + 14   # 您已提交不可重复提交 44014

    # question
    QUESTION = 45000
    QUESTION_USED_DELETE_FORBID = QUESTION + 1
    QUESTION_USED_MODIFIED_FORBID = QUESTION + 2
    QUESTION_OBJECT_NAME_REPEAT = QUESTION + 3
    QUESTION_OPTION_NUMBER_ERROR = QUESTION + 4  # 迫选排序题选项个数应为5个  45004
    # permission
    PERMISSION = 46000
    PERMISSION_USER_EXISTS = 46001
    PERMISSION_ROLE_USER_EXISTS = 46002
    PERMISSION_PHONE_EMAIL_NOT_SAME_USER = 46003
    ROLE_USER_NOT_EXISTS = 46004  # 角色不存在

    MSG = {
        SUCCESS: 'Success',
        FAILURE: 'General failure',
        SENSITIVE_WORDS: "sensitive words not permission",

        AUTHENTICATION_FAIL: 'Authenication failure',
        PERMISSION_FAIL: 'not have permission to perform this action.',
        INVALID_INPUT: 'Invalid input',
        INTERNAL_ERROR: 'Internal Error',
        NOT_EXISTED: "Not existed",
        METHOD_NOT_ALLOWED: "method not allowed",

        # user
        USER_ACCOUNT_NOT_FOUND: "user account not found",
        USER_PWD_ERROR: "user password error",
        USER_ACTIVE_CODE_INVALID: u"无效激活码，请重新输入",
        USER_ACTIVE_CODE_EXPIRED: u"激活码已被使用",
        USER_PIC_CODE_INVALID: u"图片验证码失效",
        USER_VERIFY_CODE_INVALID: u"验证码无效，请重新获取",
        USER_ADMIN_PERMISSION_INVALID: u"非管理员用户，不能登录",
        USER_ADMIN_ROLE_NAME_FORBID: "role name already exists",
        USER_ACCOUNT_EXISTS: u"帐号已经存在",
        USER_ORG_CODE_VALID: u"组织码非法，您没有权限加入改组织",
        USER_ACCOUNT_NOT_EXISTS: u"该账户暂未绑定此手机号或邮箱号",
        USER_PWD_MODIFY_OLD_PWD_ERROR: u"旧密码输入错误，请重新输入",
        USER_ANSWER_SURVEY_ORDER_ERROR: u"请按顺序作答，完成该项目里前面的问卷",
        # enterprise
        ENTERPRISE_CNNAME_EXISTS: "enterprise name already exists",
        ENTERPRISE_SHORT_NAME_EXISTS: "enterprise short name already exists",
        ENTERPRISE_DELETE_FAILED_WITH_ASSESS_PROJECT: "delete enterprise failed with assess project exists",
        ENTERPRISE_LINK_ERROR: "your enterprise link not exists",
        ENTERPRISE_USER_ERROR: "your account not in enterprise",
        ORG_USED_IN_PROJECT_CAN_NOT_DELETE: "org already used in project, can not delete",
        ORG_IMPORT_DATA_ERROR: "org data import error, please chec import data",
        PROJECT_BEGIN_CAN_NOT_DELETE: "project already begin, can not delete",
        PROJECT_SURVEY_USED_FORBID_DELETE: u"项目问卷已经被使用，禁止删除",
        PROJECT_SURVEY_USER_IMPORT_ERROR: u"测评项目人员导入失败",
        PROJECT_SURVEY_RELATION_VALID: u"项目问卷未关联，不能发布",
        PROJECT_SURVEY_RELATION_REPEAT: u"项目不能关联重复问卷",
        PROJECT_SURVEY_USER_IMPORT_ORG_ERROR: u"组织代码错误，请检查后重新提交",
        # research
        RESEARCH_MODEL_NAME_REPEAT: "model name already exists",
        RESEARCH_MODEL_USED_MODIFY_ALGO_ERROR: "model already used, can not modify algorithm_id",
        RESEARCH_MODEL_USED_DEL_ERROR: "model already used, can not deleted",
        RESEARCH_DIMENSION_MODIFY_FORBID: "model released, dimension can not modified",
        RESEARCH_DIMENSION_DELETE_FORBID: "model released, dimension can not deleted",
        RESEARCH_MODEL_RELEASE_DATA_INVALID: "model data invalid, can not released",
        RESEARCH_MODEL_INHERIT_DATA_INVALID: "model not release, can not inherit",
        RESEARCH_COPY_SELF_FORBID: "can not copy self",
        RESEARCH_TAG_USED_MODIFY_DELETE_FORBID: "标签被使用，禁止修改或删除",
        RESEARCH_REPORT_DELETE_FORBID: "报告已被关联禁止删除",
        RESEARCH_REPORT_NAME_FORBID: "report name already exists",
        RESEARCH_TAG_NAME_FORBID: "tag name already exists",
        # survey
        SURVEY_USED_DELETE_MODIFY_FORBID: "survey used, delete forbid",
        SURVEY_RELEASE_FORBID_WITHOUT_MODEL: "survey without model, release forbid",
        SURVEY_RELEASE_FORBID_MODEL_QUESTION_RELATED_ERROR: "请预览问卷题目， 确认问卷题目后方可发布",
        SURVEY_MODEL_SUBSTANDARD_NOT_RELATED_QUESTION: "survey model substandard/dimension not relate question",
        SURVEY_MODEL_RELATION_ERROR: u"问卷模型关联题目异常，请重新关联",
        SURVEY_FORCE_OPTION_RELATED_ERROR: u"指标（能力）迫选组卷，设置迫选项个数错误（无法除尽）",
        SURVEY_QUESTION_AUTO_EMPTY: u"因重复选题太多或其他原因，无法自动选出题目",
        SURVEY_RAMDOM_NUM_ERROR:u"项目随机问卷数有误",
        #
        QUESTION_USED_DELETE_FORBID: "question used, delete forbid",
        QUESTION_USED_MODIFIED_FORBID: "question used, modified forbid",
        QUESTION_OBJECT_NAME_REPEAT: u"名称重复，请重新输入",
        # permission
        PERMISSION_USER_EXISTS: u"管理员用户已经存在，请不要重复添加",
        PERMISSION_ROLE_USER_EXISTS: u"用户已经再该角色，请务重新添加",
        PERMISSION_PHONE_EMAIL_NOT_SAME_USER: u"手机和邮箱对应两个不同帐号，请更换手机或邮箱",
        USER_HAS_IN_ROLETYPE_ERROR: u"账号已存在",

    }


def get_error_detail(error_code):
    try:
        return {"msg": ErrorCode.MSG[error_code]}
    except KeyError:
        return {"msg": "Unknown error code(%s)" % error_code}


# class GeneralResponse(object):
#     def __init__(self, code, detail):
#         self.code = code
#         self.detail = detail


# class GeneralResponseSerializer(serializers.Serializer):
#    code = serializers.IntegerField()
#    detail = serializers.CharField(max_length=200)


def general_response_data(code, detail=None):
    if detail is None:
        detail = get_error_detail(code)
    # serializer = GeneralResponseSerializer(GeneralResponse(code, detail))
    # return serializer.data
    data = {'code': code, 'detail': detail}
    return data


def general_response(status, code, detail=None):
    return Response(data=general_response_data(code, detail), status=status)


def general_json_response(status, code, detail=None):
    # type: (object, object, object) -> object
    return HttpResponse(JSONRenderer().render(general_response_data(code, detail)),
                        content_type="application/json;charset=utf-8", status=status)


def general_data_json_response(status, detail):
    return HttpResponse(JSONRenderer().render(detail), content_type="application/json;charset=utf-8", status=status)


def general_extend_response(response, data):
    content = json.loads(response.content)
    content["detail"].update(data)
    response.content = JSONRenderer().render(content)
    return response
