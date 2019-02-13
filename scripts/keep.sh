#!/bin/sh

ps auxw | grep nginx | grep -v grep > /dev/null

if [ $? != 0 ]
then
      systemctl restart nginx > /dev/null
fi

ps auxw | grep docker | grep -v grep > /dev/null

if [ $? != 0 ]
then
      systemctl restart docker > /dev/null
fi

ps auxw | grep postgresql | grep -v grep > /dev/null

if [ $? != 0 ]
then
      systemctl restart postgresql > /dev/null
fi

CONTAINERS=$(docker ps -qa --no-trunc --filter "status=exited" --filter "name=trustcode-odoo*")

for dock in $CONTAINERS; do
    docker start $dock
done
