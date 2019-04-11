from rest_framework import status
from utils.views import AuthenticationExceptView, WdCreateAPIView, WdRetrieveUpdateAPIView ,\
                        WdDestroyAPIView
from utils.response import general_json_response, ErrorCode
from wduser.user_utils import UserAccountUtils
from utils.logger import get_logger
from workspace.helper import OrganizationHelper
from workspace.serializers import UserInfoSerializer,BaseOrganizationSerializer
from workspace.models import BaseOrganization,BasePersonOrganization

#retrieve logger entry for workspace app
logger = get_logger("workspace")

class PeopleLoginView(AuthenticationExceptView, WdCreateAPIView):
    """Login API for Workspace"""

    def people_login(request, user, context):
        u"""initialize model'user' serializer within current context"""
        return UserInfoSerializer(instance=user, context=context).data

    def post(self, request, *args, **kwargs):
        u"""get account,pwd field from request's data"""
        account = request.data.get('account', None)
        pwd = request.data.get("pwd", None)
        #assure account and pwd be not empty
        if account is None or pwd is None:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)
        #continue unless account exists
        user, err_code = UserAccountUtils.account_check(account)
        if err_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, err_code)
        #continue unless account/pwd is correct
        user, err_code = UserAccountUtils.user_login_web(request, user, pwd)
        if err_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, err_code)
        #return UserInfo Serialization
        user_info = people_login(request, user, self.get_serializer_context())
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, user_info)


class OrganizationListCreateView(AuthenticationExceptView, WdCreateAPIView):
    """organization tree view"""
    model = BaseOrganization
    serializer_class = BaseOrganizationSerializer
    GET_CHECK_REQUEST_PARAMETER = {"organization_id"}

    def get(self, request, *args, **kwargs):
        """get organization tree of current user"""
        tree_orgs = OrganizationHelper.get_tree_orgs(self.organization_id)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": tree_orgs})


class OrganizationlRetrieveUpdateDestroyView(AuthenticationExceptView, WdRetrieveUpdateAPIView, WdDestroyAPIView):
    """organization management"""
    model = BaseOrganization
    serializer_class = BaseOrganizationSerializer

    def delete(self, request, *args, **kwargs):
        
        org = self.get_id()
        org_ids = [org] + OrganizationHelper.get_child_ids(org)
        #delete all organizations only when no active member exists
        if BasePersonOrganization.objects.filter_active(organization_id__in=org_ids).exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.WORKSPACE_ORG_MEMBEREXISTS)
        else:
            BaseOrganization.objects.filter(id__in=org_ids).update(is_active=False)
            logger.info('user_id %s want delete orgs %s' % (self.request.user.id,org_ids))
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class OrganizationImportExportView(AuthenticationExceptView):
    """organization template import/export"""
    def get_template(self):
        #todo
        """get template file"""

    def post(self, request, *args, **kwargs):
        #todo
        """import organization file"""
    