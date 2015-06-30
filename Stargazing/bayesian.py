#!/usr/bin/env python
__author__ = 'greg'
import os
import psycopg2
import sys
from postgres_aggregation import PanoptesAPI
import csv
import matplotlib.pyplot as plt
import numpy as np
import datetime

if os.path.isdir("/home/greg"):
    baseDir = "/home/greg/"
else:
    baseDir = "/home/ggdhines/"


select = "SELECT user_id,user_ip,subject_ids,annotations,Created_at from classifications order by subject_ids"