#!/usr/bin/env python
__author__ = 'greg'
import cPickle as pickle

f1 = open("/home/greg/2015-3-19_0_7.csv")
l1 = list(f1.readlines())

f2 = open("/home/greg/2015-3-18_22_13.csv")
l2 = list(f2.readlines())



aggregations,timestamp = pickle.load(open("/home/greg/aggregations.pickle","rb"))

metadata = pickle.load(open("/home/greg/metadata.pickle","rb"))

scores = []

# id = metadata[12036]["candidateID"]
# print metadata[12306]
# for d in l1[1:]:
#     words = d.split(",")
#     ii = words[0]
#
#     if id == ii:
#         print words

for ii,d in enumerate(l1):
    if ii == 0:
        continue

    words = d.split(",")
    #print words
    # print words[-1][:-1]
    # print words[-2]
    # print words[-3]

    total = int(words[-1][:-1])+int(words[-3])+int(words[-2])

    id = d.split(",")[0]
    #print id
    score = d.split(",")[5]
    #print score



    for subject_id,m in enumerate(metadata):
        if m is None:
            #print "None"
            continue


        if m["candidateID"] == id:
            #print m["ThumbName"]
            try:
                example = not("sub201503" in m["ThumbName"])
            except KeyError:
                example = False

            break


    if subject_id == 12036:
        print "total is " + str(total)
        print words
    if score != "3.0":
        break
    if not(example):
        scores.append((id,total,"https://stargazing2015.zooniverse.org/#/projects/zooniverse/Snapshot%20Supernova/subjects/"+str(subject_id)))



for id,total,url in  sorted(scores,key = lambda x:x[1],reverse=True):
    print id, url