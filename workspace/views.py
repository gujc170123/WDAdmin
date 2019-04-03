from utils.views import AuthenticationExceptView, WdCreateAPIView
from utils.response import general_json_response, ErrorCode
from rest_framework import status
from .serializers import UserInfoSerializer
from wduser.user_utils import UserAccountUtils
from utils.logger import get_logger

#retrieve logger entry for workspace app
logger = get_logger("workspace")

class PeopleLoginView(AuthenticationExceptView, WdCreateAPIView):
    u"""Login API for Workspace"""

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
