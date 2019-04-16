# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import math
try:
    import numpy as np
    from scipy.integrate import quad, dblquad, nquad
except Exception, e:
    print u"algorithm error, maybe need install: numpy and scipy"


def normsdist(z):
    u"""excel normsdist函数
    参数excal帮助说明，内附公式
    1/根号下2派*微积分（-无穷到z）e（-t^2/2）
    """
    quzd_value = quad(lambda x: math.exp(-math.pow(x, 2)/2), -np.inf, z)[0]
    return round((1/math.sqrt(2*math.pi)) * quzd_value, 6)
