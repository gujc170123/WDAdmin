#! /bin/bash
pid=./admin-task.pid
if [ -f $pid ]; then
    if kill -0 `cat $pid` > /dev/null 2>&1; then
        echo running as process `cat $pid`.  Stop it first.
        exit 1
    fi
fi
source /home/xd/xd-dev/server/xiaode-env/bin/activate
nohup nice -n 0 celery -A WeiDuAdmin worker -l INFO > celery.log & echo $! > $pid