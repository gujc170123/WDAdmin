import redis
from redis.client import BasePipeline

from WeiDuAdmin import settings

connection_pool = None


def get_redis_connection(server_name='default'):
    '''
    Gets the specified redis connection
    '''
    global connection_pool

    if connection_pool is None:
        connection_pool = setup_redis()

    pool = connection_pool[server_name]

    return redis.StrictRedis(connection_pool=pool)


def setup_redis():
    '''
    Starts the connection pool for all configured redis servers
    '''
    pools = {}
    for name, config in settings.CACHE['redis'].items():
        pool = redis.ConnectionPool(
            host=config['host'],
            port=config['port'],
            password=config.get('password'),
            db=config['db'],
            decode_responses=True
        )
        pools[name] = pool
    return pools


class RedisStorage(object):

    '''
    The base for all redis data structures
    '''
    key_format = 'redis:cache:%s'

    def __init__(self, key, redis=None, redis_server='default'):
        # write the key
        self.key = key
        # handy when using fallback to other data sources
        self.source = 'redis'
        # the redis connection, self.redis is lazy loading the connection
        self._redis = redis
        # the redis server (see get_redis_connection)
        self.redis_server = redis_server

    def get_redis(self):
        '''
        Only load the redis connection if we use it
        '''
        if self._redis is None:
            self._redis = get_redis_connection(
                server_name=self.redis_server
            )
        return self._redis

    def set_redis(self, value):
        '''
        Sets the redis connection
        '''
        self._redis = value

    redis = property(get_redis, set_redis)

    def get_key(self):
        return self.key

    def delete(self):
        key = self.get_key()
        self.redis.delete(key)

    def _pipeline_if_needed(self, operation, *args, **kwargs):
        '''
        If the redis connection is already in distributed state use it
        Otherwise spawn a new distributed connection using .map
        '''
        pipe_needed = not isinstance(self.redis, BasePipeline)
        if pipe_needed:
            pipe = self.redis.pipeline(transaction=False)
            operation(pipe, *args, **kwargs)
            results = pipe.execute()
        else:
            results = operation(self.redis, *args, **kwargs)
        return results