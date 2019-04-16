# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.conf.urls import url

from wduser.views import LoginView, EnterpriseListCreateView, OrganizationListCreateView, \
    EnterpriseRetrieveUpdateDestroyAPIView, OrganizationlRetrieveUpdateDestroyView, LogoutView, \
    OrganizationImportExportView, EnterpriseOpsView, UserAdminRoleListCreateView, PermissionListView, \
    UserAdminRoleDetailView, RolePermissionAPIView, RoleUserListCreateView, RoleUserDetailView, UserRoleListCreateView, \
    RoleUserBusinessListCreateView, ActiveCodeCheckView, ActiveCodePwdSetView, UserPwdForgetView, \
    ForgetVerifyCodeCheckView, RoleUserPartListCreateView

urlpatterns = [
    # 登录接口
    url(r"^login/$", LoginView.as_view(), name="user-login"),
    # 登录校验激活码
    url(r"^check/active-code/$", ActiveCodeCheckView.as_view(), name="user-active-code-check"),
    # 激活码设置密码
    url(r"^active-code/pwd/$", ActiveCodePwdSetView.as_view(), name="user-active-code-pwd"),
    # 忘记密码
    url(r"^forget/pwd/$", UserPwdForgetView.as_view(), name="user-active-code-pwd"),
    # # 忘记密码 校验验证码
    url(r"^forget/verify-code-check/$", ForgetVerifyCodeCheckView.as_view(), name="user-check-verify-code"),
    # 登出接口
    url(r"^logout/$", LogoutView.as_view(), name="user-logout"),
    # 企业新建 企业列表
    url(r"^enterprise/$", EnterpriseListCreateView.as_view(), name="enterprise-view"),
    # 企业详情 企业修改  企业删除
    url(r"^enterprise/(?P<pk>\d+)/$", EnterpriseRetrieveUpdateDestroyAPIView.as_view(), name="enterprise-view-detail"),
    # 企业操作
    url(r"^enterprise/ops/$", EnterpriseOpsView.as_view(), name="enterprise-ops-view"),
    # 组织新建 组织列表
    url(r"^organization/$", OrganizationListCreateView.as_view(), name="organization-view"),
    # 组织详情 组织修改  组织删除
    url(r"^organization/(?P<pk>\d+)/$", OrganizationlRetrieveUpdateDestroyView.as_view(), name="organization-view-detail"),
    # 组织导出
    url(r"^organization/export/$", OrganizationImportExportView.as_view(), name="organization-export"),
    # 角色管理
    url(r"^role/$", UserAdminRoleListCreateView.as_view(), name="user-admin-role-view"),
    url(r"^role/(?P<pk>\d+)/$", UserAdminRoleDetailView.as_view(), name="user-admin-role-detail-view"),
    # 角色权限关联
    url(r"^role/permission/$", RolePermissionAPIView.as_view(), name="role-permission-view"),
    # 角色成员列表 新建
    url(r"^role/user/$", RoleUserListCreateView.as_view(), name="role-user-view"),
    # 新增关理关联授权model
    url(r"^role/user/part/$", RoleUserPartListCreateView.as_view(), name="role-user-part-view"),
    # 全部成员列表
    # url(r"^$", AdminUserListCreateView.as_view(), name="role-user-view"),
    # 角色成员编辑 删除
    url(r"^role/user/(?P<pk>\d+)/$", RoleUserDetailView.as_view(), name="role-user-detail-view"),
    # 权限列表
    url(r"^permission/$", PermissionListView.as_view(), name="permission-list-view"),
    # 人员关联角色
    url(r"^userrole/$", UserRoleListCreateView.as_view(), name="user-role-view"),
    # 授权对象 列表，新建 删除
    url(r"^permission/model/$", RoleUserBusinessListCreateView.as_view(), name="user-permission-model-view")



]