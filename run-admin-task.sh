#! /bin/bash
pid=./admin-task.pid
if [ -f $pid ]; then
    if kill -0 `cat $pid` > /dev/null 2>&1; then
        echo running as process `cat $pid`.  Stop it first.
        exit 1
    fi
fi
#! source /home/xd/xd-dev/server/xiaode-env/bin/activate
#source /usr/bin/virtualenvwrapper.sh
#workon py2admin
#cd /home/wd/production/project/admin/uwsgi
nohup nice -n 0 celery -B -A WeiDuAdmin worker -l INFO > celery.log & echo $! > $pid
