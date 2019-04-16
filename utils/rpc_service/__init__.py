import json
import urllib2


class HttpService():
    HOST = ""

    @classmethod
    def get_host(cls, enterprise_id=0):
        return cls.HOST

    @classmethod
    def do_request(cls, url, data=None, enterprise_id=0):

        headers = {

        }
        if data is not None:
            data = json.dumps(data)
        req = urllib2.Request(cls.get_host(enterprise_id)+url, headers=headers)
        rst = urllib2.urlopen(req, data)
        data = rst.read()
        return json.loads(data)