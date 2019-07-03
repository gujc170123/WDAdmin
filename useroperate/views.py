# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from urllib import quote,base64
from django.core.exceptions import ObjectDoesNotExist
from django.http import QueryDict
from utils.views import CustomModelViewSet
from WeiDuAdmin import settings
from useroperate import models, serializers
from assessment.models import AssessProject,AssessSurveyRelation,AssessProjectSurveyConfig,AssessJoinedOrganization
from assessment.serializers import AssessmentBasicSerializer
from sales.models import Balance,Product_Specification,Schema,OrderDetail
from wduser.models import BaseOrganization,BaseOrganizationPaths
from workspace.serializers import BaseOrganizationSerializer
from sales.serializers import Product_SpecificationSerializer
from utils.response import general_json_response, ErrorCode
from rest_framework import mixins,status,views
from datetime import date,datetime

class MenuListView(views.APIView):

    def get(self, request, *args, **kwargs):
        
        enterprise_id = self.kwargs['enterprise_id']
        skulist = Balance.objects.filter(enterprise_id=enterprise_id,
                                        validto__gte=date.today(),
                                        sku__gte=3).values_list("sku",flat=True)

        queryset = Product_Specification.objects.filter(id__in=skulist)

        serializer = Product_SpecificationSerializer(queryset, many=True)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

class SPUView(views.APIView):

    def get(self, request, *args, **kwargs):
        
        spu_id = self.kwargs['key']
        try:
            spu = Product_Specification.objects.get(id=spu_id)
            data = QueryDict(mutable=True)
            field_names = [f.name for f in spu._meta.fields]
            for field_name in field_names:
                data[field_name] = spu.__getattribute__(field_name)
            attrs = Schema.objects.filter(category_id=spu.category_id).values_list('name', flat=True)
            for field_name in attrs:
                data[field_name] = spu.__getattr__(field_name)
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,data )
        except ObjectDoesNotExist:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, {"Error": u'商品不存在'})                                    

class TrialMessageView(views.APIView):

    def get(self, request, *args, **kwargs):

        enterprise_id = self.kwargs['enterprise_id']
        spu_id = self.kwargs['key']
        order = OrderDetail.objects.get(sku_id=spu_id,order__enterprise_id=enterprise_id)
        
        message = '本次评估每次只能做一次，评估人数上限为%(n1)d人，开启评估后，周期最长为一个月。请合理安排时间，完成测评，如一个月未完成测试，可联系工作人员。' % {"n1":order.number}
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"message": message})

class MessageViewset(CustomModelViewSet):

    queryset = models.Message.objects.filter(cancel=False)
    serializer_class = serializers.MessageSerializer

class MessagePushViewset(CustomModelViewSet):

    queryset = models.MessagePush.objects.all()
    serializer_class = serializers.MessagePushSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def list(self, request, *args, **kwargs):
        
        enterprise_id = self.kwargs['enterprise_id']
        queryset = models.MessagePush.objects.filter(enterprise_id=enterprise_id,is_read=False)

        serializer =  self.get_serializer(queryset,many=True)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data['enterprise_id'] = self.kwargs['enterprise_id']
        serializer = self.get_serializer(data=data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)
        self.perform_create(serializer)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

class TrialOrganizationViewset(CustomModelViewSet):

    queryset = BaseOrganization.objects.all()
    serializer_class = BaseOrganizationSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def list(self, request, *args, **kwargs):
        assess_id = self.kwargs['assess_id']
        data = AssessJoinedOrganization.objects.filter(assess_id=assess_id,snapchildorg__level=1).values('organization_id','organization__name')
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,data)

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        enterprise_id = self.kwargs['enterprise_id']
        data['enterprise_id'] = enterprise_id
        top = BaseOrganization.objects.get(parent_id=0,is_active=True,enterprise_id=enterprise_id)
        data['parent_id'] = top.id
        serializer = self.get_serializer(data=data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)
        self.perform_create(serializer)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)           
        self.perform_update(serializer)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        BaseOrganization.objects.filter(pk=instance.id).update(is_active=False)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class AssessViewset(CustomModelViewSet):

    queryset = AssessProject.objects.all()    

    def get_share_url(self,assess_id):
        project_id_bs64 = quote(base64.b64encode(str(assess_id)))
        return settings.CLIENT_HOST + '/people/join-project/?ba=%s&bs=0' % (project_id_bs64)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            if hasattr(self, 'detail_serializer_class'):
                return self.detail_serializer_class

        return super(CustomModelViewSet, self).get_serializer_class()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = serializers.TrialAssessDetailSerializer(instance)
        data = serializer.data.copy()
        data['url'] = self.get_share_url(instance.id)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)

    def list(self, request, *args, **kwargs):
        
        enterprise_id = self.kwargs['enterprise_id']
        queryset = AssessProject.objects.filter(enterprise_id=enterprise_id,is_active=True).order_by('-id')        

        serializer = serializers.TrialAssessListSerializer(queryset, many=True)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def create(self, request, *args, **kwargs):

        #create assessproject
        data = request.data.copy()
        data['enterprise_id'] = self.kwargs['enterprise_id']
        data['distribute_type'] = AssessProject.DISTRIBUTE_OPEN
        data['assess_type'] = AssessProject.TYPE_ORGANIZATION
        data['has_distributed'] = True
        data['finish_choices'] = AssessProject.FINISH_TXT
        data['finish_txt'] = u'<p>感谢您参与此次调研！<br></p>'
        serializer = AssessmentBasicSerializer(data=data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)
        begin_time = datetime.strptime(data['begin_time'], "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(data['end_time'], "%Y-%m-%d %H:%M:%S")
        if end_time.__le__(begin_time):
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, u'结束时间必须晚于开始时间')
        if (end_time-begin_time).days>30:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, u'此次调研须在30天内完成')
        organizations = data['organizations'].split('|')
        if len(organizations)<1:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, u'请添加机构')
        self.perform_create(serializer)

        surveys = data['survey_id'].split(',')
        assess_id = serializer.data['id']

        for survey in surveys:
            #create assess-survey relation
            AssessSurveyRelation.objects.create(assess_id=assess_id,survey_id=survey)
            qs = AssessProjectSurveyConfig.objects.filter_active(survey_id=survey,
                                                                assess_id=0).all()
            for x in qs:
                x.id = None
                x.assess_id=assess_id
            AssessProjectSurveyConfig.objects.bulk_create(qs)

        top = BaseOrganization.objects.get(parent_id=0,is_active=True,enterprise_id=data['enterprise_id'])
        AssessJoinedOrganization.objects.create(assess_id=assess_id,organization_id=top.id)
                
        for org in organizations:
            toaddorg = BaseOrganization.objects.create(name=org,parent_id=top.id,enterprise_id=data['enterprise_id'])
            AssessJoinedOrganization.objects.create(assess_id=assess_id,organization_id=toaddorg.id)

        data = serializer.data.copy()
        data['url'] = self.get_share_url(assess_id)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)