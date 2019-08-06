# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import serializers
from application import models



class ApplierSerializer(serializers.ModelSerializer):

    size_text = serializers.CharField(source='get_size_display')
    industry = serializers.CharField(source='get_industry_display')
    source = serializers.CharField(source='get_source_display')
    
    class Meta:
        model = models.Applier
        fields = '__all__'

class EventSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = models.Event
        fields = '__all__'

class ApplicationSerializer(serializers.ModelSerializer):
    
    progress_text = serializers.CharField(source='get_progress_display')
    applier =  ApplierSerializer()

    class Meta:
        model = models.Application
        fields = '__all__'
        depth = 1