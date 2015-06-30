#!/usr/bin/env python
__author__ = 'greg'
import pymongo
import random
import os
import time
from time import mktime
from datetime import datetime,timedelta
import numpy as np
from scipy.stats import ks_2samp
import cPickle as pickle
from scipy.stats import beta
import matplotlib.pyplot as plt
from scipy.special import gamma as gammaf
from scipy.optimize import fmin
from scipy.stats import ks_2samp
project = "serengeti"
date = "2015-02-22"

# for Greg - which computer am I on?
if os.path.exists("/home/ggdhines"):
    base_directory = "/home/ggdhines"
    code_directory = base_directory + "/github"
elif os.path.exists("/Users/greg"):
    base_directory = "/Users/greg"
    code_directory = base_directory + "/Code"

else:
    base_directory = "/home/greg"
    code_directory = base_directory + "/github"

client = pymongo.MongoClient()
db = client[project+"_"+date]
classification_collection = db[project+"_classifications"]
subject_collection = db[project+"_subjects"]
user_collection = db[project+"_users"]

# user_names = []
# for user in user_collection.find({"classification_count":{"$gt":100}}):
#     name = user["name"]
#
#     if not(name in ["brian-c"]):
#         user_names.append(name)
#
# sample_users = random.sample(list(user_names),min(2,len(list(user_names))))



# for classification in classification_collection.find({"tutorial":{"$ne":True},"user_name":{"$nin":["brian-c","parrish","arfon","kosmala"]}}):
#     zooniverse_id = classification["subjects"][0]["zooniverse_id"]
#     subject = subject_collection.find_one({"zooniverse_id":zooniverse_id})
#
#     print classification
#     break

# for jj,user in enumerate(sample_users):
#     print user
#     times = []
#     correct_blanks = []
#     false_blanks = []
#     u = user_collection.find_one({"name":user})
names_to_skip = ["brian-c","parrish","arfon","kosmala","aliburchard","davidmill","laurawhyte","mschwamb","kellinora","ttfnrob"]

def classifications_to_retirement(zooniverse_id):
    num_votes = 0
    for num_votes, classification in enumerate(classification_collection.find({"subjects.0.zooniverse_id":zooniverse_id}).limit(25)):
        classified = []
        for ann in classification["annotations"]:
            if "species" in ann:
                classified.append(ann["species"])

        classified.sort()
        classified = tuple(classified)

        if not(classified in all_classifications):
            all_classifications[classified] = 1
        else:
            all_classifications[classified] += 1

        #print all_classifications
        if max(all_classifications.values()) == 10:
            break

    return num_votes+1


times = {}
baseline_votes = []
# for subject_count,subject in enumerate(subject_collection.find({"tutorial":{"$ne":True},"state":"complete","metadata.retire_reason":{"$nin":["blank"]}}).limit(100)):
#     print subject_count
#     zooniverse_id = subject["zooniverse_id"]
#     #print zooniverse_id
#
#     all_classifications = {}
#     num_votes = classifications_to_retirement(zooniverse_id)
#
#     baseline_votes.append(num_votes+1)
#print np.mean(baseline_votes),np.median(baseline_votes),np.std(votes)
#assert False
print "now reading in classifications"

for ii,classification in enumerate(classification_collection.find({"tutorial":{"$ne":True},"user_name":{"$nin":names_to_skip}}).limit(600000)):
    try:
        name = classification["user_name"]
    except KeyError:
        continue
    print classification["annotations"]
    zooniverse_id = classification["subjects"][0]["zooniverse_id"]

    annotations = classification["annotations"]
    keys = [ann.keys() for ann in annotations]
    timing_index = keys.index([u'started'])
    timing = annotations[timing_index]
    started_at = timing["started"]

    # u'Tue, 16 Sep 2014 16:11:58 GMT'
    classify_time = time.strptime(started_at,"%a, %d %b %Y %H:%M:%S %Z")
    user_nothing = ["nothing"] in keys

    if not(name in times):
        times[name] = [(datetime.fromtimestamp(mktime(classify_time)),user_nothing,zooniverse_id)]
    else:
        times[name].append((datetime.fromtimestamp(mktime(classify_time)),user_nothing,zooniverse_id))

def betaNLL(param,*args):
    '''Negative log likelihood function for beta
    <param>: list for parameters to be fitted.
    <args>: 1-element array containing the sample data.

    Return <nll>: negative log-likelihood to be minimized.
    '''

    a,b=param
    data=args[0]
    pdf=beta.pdf(data,a,b,loc=0,scale=1)
    lg=np.log(pdf)
    #-----Replace -inf with 0s------
    lg=np.where(lg==-np.inf,0,lg)
    nll=-1*np.sum(lg)
    return nll

total = 0
totalError = 0
overall_errors = set()
print "now looking for false positives"
for name in times.keys()[:250]:
    times[name].sort(key = lambda x:x[0])
    correct = 0
    incorrect = 0
    correct_times = []
    incorrect_list = []
    for classification_index,(t,nothing,zooniverse_id) in enumerate(times[name][:-1]):
        subject = subject_collection.find_one({"zooniverse_id":zooniverse_id})

        if nothing:
            #how long did it take them to classify?
            next_t = times[name][classification_index+1][0]

            time_to_classify = next_t - t

            assert time_to_classify.total_seconds() >= 0
            if time_to_classify.total_seconds() == 0:
                #print "weird"
                continue

            if time_to_classify.total_seconds() > 45:
                continue

            true_nothing = subject["metadata"]["retire_reason"]
            if true_nothing in ["blank","blank_consensus"]:
                correct += 1
                correct_times.append(time_to_classify.total_seconds())
            else:
                incorrect += 1
                incorrect_list.append((time_to_classify.total_seconds(),zooniverse_id))

    if (incorrect > 0) and (correct > 0):
        # print name,len(times[name])
        # print correct,incorrect
        # print np.mean(correct_times),np.mean(incorrect_times)
        incorrect_list.sort(key = lambda x:x[0])
        incorrect_times = zip(*incorrect_list)[0]
        ids = zip(*incorrect_list)[1]

        # is this any overall difference?
        s,starting_p = ks_2samp(correct_times,incorrect_times)
        if starting_p < 0.01:
            for ii in range(len(incorrect_times)-1,-1,-1):
                s,p = ks_2samp(correct_times,incorrect_times[:ii])
                if p > 0.01:
                    break
            totalError+= len(incorrect_times)-ii
            print (len(incorrect_times)-ii,len(incorrect_times))
            errors = incorrect_times[ii:]
            zooniverse_errors = [ids[incorrect_times.index(t)] for t in errors]
            for id in zooniverse_errors:
                overall_errors.add(id)
            #for id in zooniverse_errors:
            #    print subject_collection.find_one({"zooniverse_id":id})
            #    print
        else:
            print 0,len(incorrect_times)

        total += len(incorrect_times)
        # #print sum([1 for c in correct_times if c >= min(incorrect_times)])/float(len(correct_times))
        # #print
        # max_time = max(max(correct_times),max(incorrect_times))
        # min_time = min(min(correct_times),min(incorrect_times))
        # data = correct_times
        # data = [(t-min_time)/float(max_time-min_time) for t in data]
        # #print data
        # a,b,lower,scale = beta.fit(data)
        # #print a,b,lower,scale
        # #print
        # #print beta.cdf(0.8,a,b)
        # #----------------Fit using moments----------------
        # mean=np.mean(data)
        # var=np.var(data,ddof=1)
        # alpha1=mean**2*(1-mean)/var-mean
        # beta1=alpha1*(1-mean)/mean
        #
        #
        # print beta.cdf((incorrect_times[-1]-min_time)/(max_time-min_time),alpha1,beta1)
        #print
        #break

        #print correct_times
        #print incorrect_times

print totalError,total
error_votes = []
for zooniverse_id in list(overall_errors):
    num_votes = classifications_to_retirement(zooniverse_id)
    error_votes.append(num_votes)


#print times.keys()
#print user_collection.find_one({"name":"kellinora"})
print np.mean(baseline_votes),np.median(baseline_votes)
print np.mean(error_votes),np.median(error_votes)

print ks_2samp(baseline_votes,error_votes)