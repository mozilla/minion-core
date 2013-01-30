#!/bin/bash

set -x

# This script expects an active virtualenv

if [ -z "$VIRTUAL_ENV" ]; then
    echo "abort: no virtual environment active"
    exit 1
fi

case $1 in
    develop)
        (cd plugin-service && python setup.py develop)
        (cd task-engine && python setup.py develop)
        ;;
esac
