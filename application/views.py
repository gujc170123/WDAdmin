from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import GenericAPIView
from utils.views import CustomModelViewSet
from utils.response import general_json_response, ErrorCode
from application import models,serializers

class ChoiceView(GenericAPIView):

    available_dicts = {
        "status": models.Event.STATUS_CHOICES,
        "progress": models.Application.PROGRESS_CHOICES,
        "industry": models.Applier.INDUSTRY_CHOICES,
        "size": models.Applier.SIZE_CHOICES,
        "source": models.Applier.SOURCE_CHOICES,
    }

    def get(self, request):
        option = request.GET.get("option", None)
        if option is not None and option in self.available_dicts:
            result_list = []
            chosen_dict = available_dicts[option]
            for i in chosen_dict:
                key, value = i
                tmp = {"key": key, "value": value}
                result_list.append(tmp)
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, result_list)            
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, {"Error": "Empty or invalid option given"})              

class ApplicationModelViewset(CustomModelViewSet):

    queryset = models.Application.objects.all()
    serializer_class = serializers.ApplicationSerializer

class ApplierModelViewset(CustomModelViewSet):

    queryset = models.Applier.objects.all()
    serializer_class = serializers.ApplierSerializer

class EventModelViewset(CustomModelViewSet):

    queryset = models.Event.objects.all()
    serializer_class = serializers.EventSerializer