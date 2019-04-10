from utils.views import AuthenticationExceptView, WdListCreateAPIView
from utils.response import general_json_response, ErrorCode
from rest_framework import status
from utils.logger import get_logger
from .models import BaseOrganization
from .helper import OrganizationHelper

logger = get_logger("front")

class Dashboard(AuthenticationExceptView, WdListCreateAPIView):
    """Dashboard"""

    api_mapping = {
        "organtree": 'self.get_organtree',
        "facet": 'self.get_get_facet',
    }

    def get_organtree(self,**kargs):
        """return organization tree list"""

        res = []
        org = kargs["org_id"]
        if not org:
            return res, ErrorCode.INVALID_INPUT
        try:
            organzations = BaseOrganization.objects.filter_active(id=org)
            if organzations.exists():
                res = OrganizationHelper.get_child_orgs(organzations[0].id)
                return res, ErrorCode.SUCCESS
            else:
                return res, ErrorCode.NOT_EXISTED
        except Exception, e:
            logger.error("get report data error, msg: %s " % e)
            return res, ErrorCode.INTERNAL_ERROR

    def get_facet(org):
        """return facet list of eoi"""
        return []

    def get_eoi(org):
        """return current organization's oei"""
        return 0

    def get_eoi_std(org):
        """return oei benchmark"""
        return 65

    def get_oeistress_dist(org):
        """return oei-stress population distribution"""
        return []
    
    def get_oeidevote_dist(org):
        """return oei-devotion population distribution"""
        return 0

    def get_oei_advantage(org):
        """return advantage behaviour of oei"""
        return []

    def get_oei_disadvantage(org):
        """return disadvantage behaviour of oei"""
        return []
    
    def get_oei_ranking(org):
        """return oei ranking of current org"""
        return []

    def get_oei_dimension(org):
        """return oei dimension matrix of current org"""
        return []
    
    def get_oei_profilefacet(org,profile):
        """return oei table of selected profile facet"""
        return []

    def get_oei_dist(org):
        """return oei popluation distribution"""
        return []
    
    def get_oei_pop_dist(org,model,dimension,pop):
        """return population facet distribution of """
        return []

    def post(self, request, *args, **kwargs):
        
        api_id = self.request.data.get("api", None)
        org_id = self.request.data.get("org", None)
        profile_id = self.request.data.get("profile", None)
        dimension_id = self.request.data.get("dimension", None)
        population_id = self.request.data.get("population", None)

        args = {"org_id": org_id,
                "profile_id": profile_id,
                "dimension_id": dimension_id,
                "population_id": population_id}
        
        try:
            #retrieve chart's data
            data, err_code = eval(self.api_mapping[api_id])(org_id=org_id,
                                                            profile_id=profile_id,
                                                            dimension_id=dimension_id,
                                                            population_id=population_id)
            if err_code != ErrorCode.SUCCESS:
                return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT, {"msg": err_code})
            else:
                return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": data})
        except Exception, e:
            logger.error("dashboard error, msg is %s" % e)
            return general_json_response(status.HTTP_200_OK, ErrorCode.INTERNAL_ERROR, {"msg": "%s" %e})