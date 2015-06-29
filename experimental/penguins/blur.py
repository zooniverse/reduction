#!/usr/bin/env python
__author__ = 'greghines'
import numpy as np
import os
import pymongo



# connect to the mongodb server
client = pymongo.MongoClient()
db = client['penguin_2015-05-06']
subjects = db["penguin_subjects"]
classifications = db["penguin_classifications"]

false_blanks = 0
non_blanks = 0

for ii,s in enumerate(subjects.find({"state":"complete","metadata.retire_reason":{"$ne":"blank"}}).limit(200)):
    zooniverse_id = s["zooniverse_id"]
    image_blank = s["metadata"]["retire_reason"]
    # print s

    has_animals = []
    for c in classifications.find({"subjects.0.zooniverse_id":zooniverse_id}):
        has_animals.append(c["annotations"][0]["value"] == "yes")
        # print c["annotations"][0]["value"]

    # print has_animals

    percent = sum([1 for b in has_animals if b == True])/float(len(has_animals))
    if percent < 0.6:
        print s["metadata"]["retire_reason"]
        print s["location"]["standard"]
    # print (sum([1 for b in has_animals if b == True]) <= 1)

    # if (sum([1 for b in has_animals if b == True]) <= 1) and (image_blank != "blank"):
    #     print "***"
    #     # print image_blank
    #     # print s
    #     false_blanks += 1
    #
    # if image_blank != "blank":
    #     non_blanks +=1

print false_blanks,non_blanks
