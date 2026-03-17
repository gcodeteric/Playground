#!/bin/bash
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt --user
python3 main.py
