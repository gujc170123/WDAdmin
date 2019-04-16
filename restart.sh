#! /bin/bash
#source /usr/bin/virtualenvwrapper.sh
#workon py2admin

cd /home/wd/production/project/admin/WeiDuAdmin
#./stop-admin.sh
#sleep 3
#cd ../WeiDuAdmin/
#python manage.py makemigrations 
#python manage.py migrate --database default
#python manage.py migrate --database front
cd ../uwsgi/
./run-admin.sh
