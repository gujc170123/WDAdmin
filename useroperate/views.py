# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from django.core.exceptions import ObjectDoesNotExist
from django.http import QueryDict
from utils.views import CustomModelViewSet
from useroperate import models, serializers
from assessment.models import AssessProject,AssessSurveyRelation,AssessProjectSurveyConfig
from assessment.serializers import AssessmentSurveyRelationDetailGetSerializer
from sales.models import Balance,Product_Specification,Schema,OrderDetail
from workspace.serializers import AssessListSerializer
from sales.serializers import Product_SpecificationSerializer
from utils.response import general_json_response, ErrorCode
from rest_framework import mixins,status,views
from datetime import date

class MenuListView(views.APIView):

    def get(self, request, *args, **kwargs):
        
        enterprise_id = self.kwargs['enterprise_id']
        skulist = Balance.objects.filter(enterprise_id=enterprise_id,
                                        validto__gte=date.today(),
                                        sku__gte=3).values("sku")

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
        
        message = '您当前使用的是%(n1)s，仅能开设1场调研，调研人数上限为%(n2)d人' % {"n1":order.sku_name,"n2":order.number}
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"message": message})

class MessageViewset(CustomModelViewSet):

    queryset = models.Message.objects.filter(cancel=False)
    serializer_class = serializers.MessageSerializer

class MessagePushViewset(CustomModelViewSet):

    queryset = models.MessagePush.objects.all()
    serializer_class = serializers.MessagePushSerializer

    def get(self, request, *args, **kwargs):
        
        enterprise_id = self.kwargs['enterprise_id']
        queryset = models.Message.objects.filter(enterprise_id=enterprise_id,is_read=False)

        serializer =  self.get_serializer(queryset, many=True)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def create(self, request, *args, **kwargs):
        data = request.data
        data['enterprise_id'] = self.kwargs['enterprise_id']
        serializer = self.get_serializer(data=data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)
        self.perform_create(serializer)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

class AssessViewset(CustomModelViewSet):

    serializer_class = AssessListSerializer
    detail_serializer_class = AssessmentSurveyRelationDetailGetSerializer

    def get_serializer_class(self):
        if self.action == 'retrieve':
            if hasattr(self, 'detail_serializer_class'):
                return self.detail_serializer_class

        return super(CustomModelViewSet, self).get_serializer_class()

    def get(self, request, *args, **kwargs):
        
        enterprise_id = self.kwargs['enterprise_id']
        queryset = models.AssessProject.objects.filter(enterprise_id=enterprise_id,is_active=True).order_by('-id')

        serializer = self.get_serializer(queryset, many=True)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def create(self, request, *args, **kwargs):

        #create assessproject
        data = request.data
        data['enterprise_id'] = self.kwargs['enterprise_id']
        data['distribute_type'] = AssessProject.DISTRIBUTE_OPEN
        data['assess_type'] = AssessProject.TYPE_ORGANIZATION
        data['has_distributed'] = True
        data['finish_choices'] = AssessProject.FINISH_TXT
        data['finish_txt'] = u'<p>感谢您参与此次调研！<br></p>'
        serializer = self.get_serializer(data=data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)
        if data['begin_time']>=data['end_time']:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, u'结束时间必须晚于开始时间')
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

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)