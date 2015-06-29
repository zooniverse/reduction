#!/usr/bin/env python
__author__ = 'greg'
import cPickle as pickle

f1 = open("/home/greg/2015-3-18_22_11.csv")
l1 = list(f1.readlines())

f2 = open("/home/greg/2015-3-18_22_13.csv")
l2 = list(f2.readlines())

differences = list(set(l1)-set(l2))


aggregations,timestamp = pickle.load(open("/home/greg/aggregations.pickle","rb"))

metadata = pickle.load(open("/tmp/metadata.pickle","rb"))

missed_ids = []

for ii,d in enumerate(differences):
    id = d.split(",")[0]

    for subject_id,m in enumerate(metadata[1:]):
        if m["candidateID"] == id:
            break

    print aggregations[subject_id+1]
    missed_ids.append(subject_id+1)

print len(missed_ids)