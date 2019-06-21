from rest_framework.response import Response
from rest_framework import status
from application import models,serializers

class ChoiceView(GenericAPIView):

    available_dicts = {
        "status": models.Application.STATUS_CHOICES,
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
            return Response(result_list,status=status.HTTP_200_OK)
        else:
            return Response({"Error": "Empty or invalid option given"}, status=status.HTTP_400_BAD_REQUEST)

class ApplicationModelViewset(ModelViewSet):

    queryset = models.Application
    serializer_class = serializers.ApplicationSerializer

class ApplierModelViewset(ModelViewSet):

    queryset = models.Applier
    serializer_class = serializers.ApplierSerializer

class EventModelViewset(ModelViewSet):

    queryset = models.Event.objects.all()
    serializer_class = serializers.EventSerializer