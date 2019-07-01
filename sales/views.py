# -*- coding:utf-8 -*-
from rest_framework import status
from utils.views import CustomModelViewSet
from sales import models,serializers
from datetime import date
from utils.response import general_json_response, ErrorCode

class OrderModelViewset(CustomModelViewSet):

    queryset = models.Order.objects.all()
    serializer_class = serializers.OrderSerializer

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data['enterprise_id'] = self.kwargs['enterprise_id']    
        serializer = self.get_serializer(data=data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)            
        self.perform_create(serializer)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def list(self, request, *args, **kwargs):
        enterprise_id = self.kwargs['enterprise_id']    
        queryset = models.Order.objects.filter(enterprise_id=enterprise_id)
        return super(OrderModelViewset, self).list(request, *args, **kwargs)

class OrderDetailModelViewset(CustomModelViewSet):

    queryset = models.OrderDetail.objects.all()
    serializer_class = serializers.OrderDetailSerializer

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data['enterprise_id'] = self.kwargs['enterprise_id']
        serializer = self.get_serializer(data=data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)            
        self.perform_create(serializer)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def list(self, request, *args, **kwargs):
        enterprise_id = self.kwargs['enterprise_id']
        queryset = models.OrderDetail.objects.filter(enterprise_id=enterprise_id)
        return super(OrderDetailModelViewset, self).list(request, *args, **kwargs)

class BalanceModelViewset(CustomModelViewSet):

    queryset = models.Balance.objects.all()
    serializer_class = serializers.BalanceSerializer

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data['enterprise_id'] = self.kwargs['enterprise_id']
        serializer = self.get_serializer(data=data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)            
        self.perform_create(serializer)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def list(self, request, *args, **kwargs):
        enterprise_id = self.kwargs['enterprise_id']
        queryset = models.Balance.objects.filter(enterprise_id=enterprise_id)
        return super(BalanceModelViewset, self).list(request, *args, **kwargs)

class ConsumeModelViewset(CustomModelViewSet):

    queryset = models.Consume.objects.all()
    serializer_class = serializers.ConsumeSerializer

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data['enterprise_id'] = self.kwargs['enterprise_id']
        serializer = self.get_serializer(data=data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)            
        self.perform_create(serializer)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def list(self, request, *args, **kwargs):
        enterprise_id = self.kwargs['enterprise_id']
        queryset = models.Consume.objects.filter(enterprise_id=enterprise_id)
        return super(ConsumeModelViewset, self).list(request, *args, **kwargs)