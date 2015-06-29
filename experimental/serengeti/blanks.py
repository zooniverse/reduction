#!/usr/bin/env python
__author__ = 'greghines'
import numpy as np
import os
import pymongo
import urllib
import matplotlib.pyplot as plt
import cv2

# the directory to store the movie preview clips in
image_directory = "/home/greg/Databases/chimp/images/"

# connect to the mongodb server
client = pymongo.MongoClient()
db = client['serengeti_2015-02-22']
subjects = db["serengeti_subjects"]
classifications = db["serengeti_classifications"]


for ii,s in enumerate(classifications.find({"tutorial":{"$ne":True}}).limit(100)):
    if not("started" in s["annotations"][-1]):
        continue

    print s["metadata"]
    print s["user_ip"],s["annotations"]
    print subjects.find_one()
# for ii,s in enumerate(subjects.find({"tutorial":{"$ne":True}}).limit(10)):
#     # print s["coords"],s["created_at"]
#     print s["coords"]
#     print s["metadata"]["timestamps"][0]
#     images = s["location"]["standard"]
#     slash_indices =
#     print