# -*- coding:utf-8 -*-
from rest_framework import status
from utils.views import CustomModelViewSet
from django_filters import rest_framework as filters
from sales import models,serializers
from datetime import date, datetime
import datetime
from wduser.models import EnterpriseInfo
from utils.response import general_json_response, ErrorCode
from django.contrib.contenttypes.models import ContentType

class CategoryModelViewset(CustomModelViewSet):

    queryset = models.Category.objects.all()
    serializer_class = serializers.CategorySerializer

class ProductFilter(filters.FilterSet):

    class Meta:
        model = models.Product_Specification
        fields = ('category_id',)

class ProductModelViewset(CustomModelViewSet):

    queryset = models.Product_Specification.objects.all()
    serializer_class = serializers.Product_SpecificationSerializer
    filter_backend = filters.DjangoFilterBackend
    filter_class = ProductFilter

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        spu = models.Product_Specification.objects.create(
            price = data['price'],
            title = data['title'],
            menu = data['menu'],
            category = models.Category.objects.get(pk=data['category_id']),
            is_platform = data['is_platform']
        )
        for attr in data['attrs']:
            spu._schemata_cache_dict[attr['name']]._save_single_attr(spu,attr['value'])      
        serializer = self.get_serializer(spu)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def update(self, request, *args, **kwargs):
        data = request.data.copy()
        instance = self.get_object()
        models.Attr.objects.filter(entity_id=instance.id).delete()                      
        instance.price = float(data['price'])
        instance.title = data['title']
        instance.menu = data['menu']
        instance.category_id = instance.category_id
        instance.is_platform = data['is_platform']
        instance.save()
        for attr in data['attrs']:
            instance._schemata_cache_dict[attr['name']]._save_single_attr(instance,attr['value'])      
        serializer = self.get_serializer(instance)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)       

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        models.Attr.objects.filter(entity_id=instance.id).delete()  
        self.perform_destroy(instance)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)
    

class SchemaFilter(filters.FilterSet):

    class Meta:
        model = models.Schema
        fields = ('category_id',)

class SchemaModelViewset(CustomModelViewSet):

    queryset = models.Schema.objects.all()
    serializer_class = serializers.SchemaSerializer
    filter_backend = filters.DjangoFilterBackend
    filter_class = SchemaFilter    

class OrderModelViewset(CustomModelViewSet):

    queryset = models.Order.objects.all()
    serializer_class = serializers.OrderSerializer

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data['enterprise'] = self.kwargs['enterprise_id']    
        serializer = self.get_serializer(data=data)
        is_valid = serializer.is_valid(raise_exception=False)
        if not is_valid:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, serializer.errors)            
        self.perform_create(serializer)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def list(self, request, *args, **kwargs):
        enterprise_id = self.kwargs['enterprise_id']    
        self.queryset = models.Order.objects.filter(enterprise_id=enterprise_id)
        return super(OrderModelViewset, self).list(request, *args, **kwargs)

class OrderCRMModelViewset(CustomModelViewSet):

    queryset = models.Order.objects.all()
    serializer_class = serializers.OrderSerializer

    def create(self, request, *args, **kwargs):

        data = request.data.copy()

        order = models.Order.objects.create(
            product_amount = data['product_amount'],
            order_amount = data['product_amount'],
            order_date = data['order_date'],
            paid_date = data['paid_date'],
            delivered_date = data['delivered_date'],
            enterprise = EnterpriseInfo.objects.get(pk=data['enterprise_id']),
        )

        period = 0
        skudict = {}
        orderdict = {}
        for detail in data['products']:
            orderdetail = models.OrderDetail.objects.create(
                sku_name = detail['sku_name'],
                price = detail['price'],
                discount_rate = detail['discount_rate'],
                discount_amount = detail['discount_amount'],
                number = detail['number'],
                subtotal = detail['subtotal'],
                order = order,
                sku = models.Product_Specification.objects.get(pk=detail['sku'])
            )
            skudict[orderdetail.sku.id] = orderdetail.sku
            orderdict[orderdetail.sku.id] = orderdetail.number
            if orderdetail.sku.is_platform:
                period = orderdetail.sku.platform_period

        
        balances = models.Balance.objects.filter(enterprise_id=order.enterprise_id,sku__in=skudict.keys())
        for balance in balances:
            balance.number = balance.number + skudict[balance.sku.id].number
            balance.validto = balance.validto + datetime.timedelta(days=period)
            balance.save()
            skudict.pop(balance.sku.id)

        for sku in skudict.keys():
            models.Balance.objects.create(
                enterprise = order.enterprise,
                sku = skudict[sku],
                number = orderdict[sku],
                validfrom = datetime.datetime.strptime(order.order_date, '%Y-%m-%d'),
                validto= datetime.datetime.strptime(order.order_date, '%Y-%m-%d') + datetime.timedelta(days=period))

        serializer = self.get_serializer(order)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)

    def update(self, request, *args, **kwargs):
        data = request.data.copy()
        instance = self.get_object()
        models.OrderDetail.objects.filter(order_id=instance.id).delete()
        instance.product_amount = data['product_amount']
        instance.order_amount = data['product_amount']
        instance.order_date = data['order_date']
        instance.paid_date = data['paid_date']
        instance.delivered_date = data['delivered_date']
        instance.enterprise = EnterpriseInfo.objects.get(pk=data['enterprise_id'])
        instance.save()

        for detail in data['products']:
            orderdetail = models.OrderDetail.objects.create(
                sku_name = detail['sku_name'],
                price = float(detail['price']),
                discount_rate = float(detail['discount_rate']),
                discount_amount = float(detail['discount_amount']),
                number = float(detail['number']),
                subtotal = float(detail['subtotal']),
                order = instance,
                sku = models.Product_Specification.objects.get(pk=detail['sku'])
            )
        serializer = self.get_serializer(instance)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, serializer.data)       

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        models.OrderDetail.objects.filter(order_id=instance.id).delete() 
        self.perform_destroy(instance)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


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
        self.queryset = models.OrderDetail.objects.filter(enterprise_id=enterprise_id)
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
        self.queryset = models.Balance.objects.filter(enterprise_id=enterprise_id)
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
        self.queryset = models.Consume.objects.filter(enterprise_id=enterprise_id)
        return super(ConsumeModelViewset, self).list(request, *args, **kwargs)
