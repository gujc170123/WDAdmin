# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import serializers
from application import models

class ApplicationSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = models.Application
        fields = '__all__'
        depth = 1

class ApplierSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = models.Applier
        fields = '__all__'

class EventSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = models.Event
        fields = '__all__'