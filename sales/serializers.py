# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import serializers
from sales import models

class ProductSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = models.Product
        fields = '__all__'

class SpecificationSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = models.Product_Specification
        fields = '__all__'

class OrderDetailSerializer(serializers.ModelSerializer):   

    class Meta:
        model = models.OrderDetail
        fields = '__all__'

class OrderSerializer(serializers.ModelSerializer):

    children = OrderDetailSerializer(many=True, read_only=True)

    class Meta:
        model = models.Order
        fields = '__all__'