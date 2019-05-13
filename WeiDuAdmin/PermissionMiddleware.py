# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from django.utils.deprecation import MiddlewareMixin
from wduser.models import AuthUser,  BusinessPermission


class PermissionMiddleware(MiddlewareMixin):
    u"""权限检验"""
    PERMISSION_MAP = {
        "user": [
            BusinessPermission.PERMISSION_ENTERPRISE_ALL,
            BusinessPermission.PERMISSION_ENTERPRISE_PART,    # 12
            BusinessPermission.PERMISSION_ENTERPRISE_ALL_SEE,
            BusinessPermission.PERMISSION_ENTERPRISE_BUSINESS,
            BusinessPermission.PERMISSION_ENTERPRISE_MASTER,
            BusinessPermission.PERMISSION_ENTERPRISE_PROJECT,
            BusinessPermission.PERMISSION_ORG_ALL,
            BusinessPermission.PERMISSION_PROJECT_ALL,
            BusinessPermission.PERMISSION_PROJECT_PART,    # 41
            BusinessPermission.PERMISSION_PERMISSION_ALL,
            BusinessPermission.PERMISSION_PERMISSION_ROLE,
            BusinessPermission.PERMISSION_PERMISSION_ROLE_USER,
            BusinessPermission.PERMISSION_PERMISSION_PROJECT_ASSIGNED
        ],
        "assessment": [
            BusinessPermission.PERMISSION_ENTERPRISE_ALL,
            BusinessPermission.PERMISSION_ENTERPRISE_PART,
            BusinessPermission.PERMISSION_ENTERPRISE_ALL_SEE,
            BusinessPermission.PERMISSION_PROJECT_ALL,
            BusinessPermission.PERMISSION_PROJECT_PART,
            # 企业管理 会访问项目
            BusinessPermission.PERMISSION_ENTERPRISE_ALL,
            BusinessPermission.PERMISSION_ENTERPRISE_PART,
            # 权限管理
            BusinessPermission.PERMISSION_PERMISSION_ALL
        ],
        "research": [
            BusinessPermission.PERMISSION_MODEL_ORG_ALL,
            BusinessPermission.PERMISSION_MODEL_PERSONAL_ALL,
            BusinessPermission.PERMISSION_TAG_ALL,
            # 问卷管理需要访问模型
            BusinessPermission.PERMISSION_SURVEY_ORG_ALL,
            BusinessPermission.PERMISSION_SURVEY_ORG_USE,
            BusinessPermission.PERMISSION_SURVEY_PERSONAL_ALL,
            BusinessPermission.PERMISSION_SURVEY_PERSONAL_USE,
            BusinessPermission.PERMISSION_SURVEY_360_ALL,
            BusinessPermission.PERMISSION_SURVEY_360_USE,
            # 企业管理 会访问模型
            BusinessPermission.PERMISSION_ENTERPRISE_ALL,
            BusinessPermission.PERMISSION_ENTERPRISE_PART,
            BusinessPermission.PERMISSION_ENTERPRISE_ALL_SEE

        ],
        "survey": [
            # 企业管理会访问问卷
            BusinessPermission.PERMISSION_ENTERPRISE_ALL,
            BusinessPermission.PERMISSION_ENTERPRISE_PART,
            BusinessPermission.PERMISSION_ENTERPRISE_ALL_SEE,
            #
            BusinessPermission.PERMISSION_SURVEY_ORG_ALL,
            BusinessPermission.PERMISSION_SURVEY_ORG_USE,
            BusinessPermission.PERMISSION_SURVEY_PERSONAL_ALL,
            BusinessPermission.PERMISSION_SURVEY_PERSONAL_USE,
            BusinessPermission.PERMISSION_SURVEY_360_ALL,
            BusinessPermission.PERMISSION_SURVEY_360_USE,
            # 权限管理
            BusinessPermission.PERMISSION_PERMISSION_ALL,
            # 项目管理权限 9.15
            # BusinessPermission.PERMISSION_PROJECT_PART
        ],
        "question": [
            #
            BusinessPermission.PERMISSION_SURVEY_ORG_ALL,
            BusinessPermission.PERMISSION_SURVEY_ORG_USE,
            BusinessPermission.PERMISSION_SURVEY_PERSONAL_ALL,
            BusinessPermission.PERMISSION_SURVEY_PERSONAL_USE,
            BusinessPermission.PERMISSION_SURVEY_360_ALL,
            BusinessPermission.PERMISSION_SURVEY_360_USE,
            #
            BusinessPermission.PERMISSION_QUESTION_ALL,
            #
            BusinessPermission.PERMISSION_ENTERPRISE_ALL,
            BusinessPermission.PERMISSION_ENTERPRISE_PART,
            BusinessPermission.PERMISSION_ENTERPRISE_ALL_SEE,
            BusinessPermission.PERMISSION_PROJECT_ALL,
            BusinessPermission.PERMISSION_PROJECT_PART

        ]

    }
    PERMISSION_EXCEPT_URL = [
        '/api/v1/user/login/',
        '/api/v1/user/logout/',
        '/api/v1/research/tag/',
        '/people/join-project/',
    ]
    PERMISSION_EXCEPT_URL_PREFIX = [
        '/api/client/v1/front/',
        '/people/',
        '/api/ws/v1/',
    ]

    def process_request(self, request):
        url_path = request.path
        setattr(request, 'has_permission', True)
        # logger.debug("permission request path is: %s" % url_path)
        if url_path in PermissionMiddleware.PERMISSION_EXCEPT_URL:
            return
        for url_prefix in PermissionMiddleware.PERMISSION_EXCEPT_URL_PREFIX:
            if url_path.find(url_prefix) > -1:
                return
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return
        user = request.user
        if user.role_type == AuthUser.ROLE_NORMAL:
            # 普通用户
            # raise exceptions.PermissionDenied()
            setattr(request, 'has_permission', False)
            return
        elif user.role_type == AuthUser.ROLE_SUPER_ADMIN:
            # 超级用户
            return

        business_model = url_path.split("/")[3]
        # role_ids = RoleUser.objects.filter_active(user_id=user.id).values_list("role_id", flat=True)
        # permission_ids = list(RoleBusinessPermission.objects.filter_active(role_id__in=role_ids).values_list(
        #     "permission_id", flat=True
        # ))
        # 是不是 app
        if business_model not in PermissionMiddleware.PERMISSION_MAP:
            return
        if not hasattr(request, "session") or "wdp" not in request.session:
            # raise exceptions.PermissionDenied()
            setattr(request, 'has_permission', False)
            return
        permission_ids = []
        for p_id in request.session["wdp"].split(","):
            if p_id:
                permission_ids.append(int(p_id))
                if (int(p_id)) == BusinessPermission.PERMISSION_ALL:
                    return
        need_permissions = PermissionMiddleware.PERMISSION_MAP[business_model]
        # 找到MAP中的app对应的权限list()
        # 找你的pid就是几号权限，在不再这个允许的list中。
        has_permissions = list(set(permission_ids).intersection(set(need_permissions)))
        if not has_permissions:
            # raise exceptions.PermissionDenied()
            setattr(request, 'has_permission', False)
        return