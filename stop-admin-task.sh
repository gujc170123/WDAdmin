#! /bin/bash

file=admin-task.pid
if [ -f $file ]; then
    kill -9 `cat $file`
    rm $file
    echo "Stop $file"
fi
