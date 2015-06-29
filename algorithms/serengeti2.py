#!/usr/bin/env python
__author__ = 'greg'
import pymongo
import matplotlib.pyplot as plt
import numpy
import math
import random

# connect to the mongo server
client = pymongo.MongoClient()
db = client['serengeti_2015-02-22']
classification_collection = db["serengeti_classifications"]
subject_collection = db["serengeti_subjects"]
user_collection = db["serengeti_users"]

# for storing the time stamp of the last classification made by each user
current_sessions = {}
# how many subjects each user has classified during the current session
session_length = {}
# how many blank each user has classified during the current session
num_blanks = {}

# X - percentage of blanks per session
X = []
# Y - session length
Y = []

for ii,classification in enumerate(classification_collection.find().skip(0).limit(1000000)):
    print ii
    # use the ip address to identify the user - that way we track non-logged in users as well
    id =  classification["user_ip"]
    # what time was the classification made at?
    time = classification["updated_at"]

    # skip tutorial classifications
    if "tutorial" in classification:
        continue

    # get the id for the subject and find out whether it was retired as a blank
    zoonvierse_id= classification["subjects"][0]["zooniverse_id"]
    # you can include blank consensus as well but I found those to be pretty error prone
    subject = subject_collection.find_one({"zooniverse_id":zoonvierse_id})
    if subject["metadata"]["retire_reason"] in ["blank"]:
        try:
            num_blanks[id] += 1
        except KeyError:
            num_blanks[id] = 1

    # increment the session length
    try:
        session_length[id] += 1
    except KeyError:
        session_length[id] = 1

    # how long has it been since that person made their previous classification
    # if it has been 10 minutes or more, count as a new session
    try:
        time_delta = time - current_sessions[id]
        if time_delta.seconds >= 60*10:
            # store data and reset counters
            X.append(num_blanks[id]/float(session_length[id]))
            Y.append(session_length[id])
            session_length[id] = 0
            num_blanks[id] = 0

    except KeyError:
        pass

    current_sessions[id] = time

# basic plot of results
plt.plot(X,Y,'.')
plt.xlabel("percentage of images per session which are blank")
plt.ylabel("session length - blank + non-blank")
plt.show()

XY = zip(X,Y)
XY.sort(key = lambda x:x[0])

# create bins for a range of different X values between 0 and 1 - incrementing by 0.025
# assume that within bin, the distribution of values is independent of X
bins_endpts = numpy.arange(0,1.01,0.025)
bins = {(bins_endpts[i],bins_endpts[i+1]):[] for i in range(len(bins_endpts)-1)}
exp_lambda = []
X2 = []
error = []

# store y values in appropriate bins
for x,y in XY:
    if x == 1:
        bins[(bins_endpts[-2],bins_endpts[-1])].append(y)
    else:
        for lb,ub in bins.keys():
            if (lb <= x) and (x < ub):
                bins[(lb,ub)].append(y)
                break

v = {}

# use an exponential distribution to approximate the values in each bin
# estimate lambda - the one param for an exponential distribution
for i in range(len(bins_endpts)-1):
    lb = bins_endpts[i]
    ub = bins_endpts[i+1]

    if len(bins[(lb,ub)]) >= 10:
        values = bins[(lb,ub)]
        mean=numpy.mean(values)
        var=numpy.var(values,ddof=1)

        print len(values), var >= (mean*(1-mean))

        exp_lambda.append(1/mean)
        v[lb] = mean

        X2.append((ub+lb)/2.)
        error.append((1/mean)*1.96/math.sqrt(len(values)))

# plot out the lambda values - with confidence regions - for each bin
plt.errorbar(X2,exp_lambda,yerr=error)
plt.xlabel("percentage of images per session which are blank")
plt.ylabel("estimate of lambda param for exponential distribution")
plt.xscale("log")
plt.show()
plt.close()


# plot a cumulative distribution of values as well
plt.hist(X, 50, normed=1,histtype='step', cumulative=True)
plt.xlabel("percentage of images per session which are blank")
plt.ylabel("cumulative distribution")
plt.show()

X = []
Y = []

for i in range(len(bins_endpts)-1):
    lb = bins_endpts[i]
    ub = bins_endpts[i+1]

    if lb in v:

        for j in range(200):
            X.append(random.uniform(lb,ub))

            Y.append(numpy.random.exponential(v[lb]))

plt.plot(X,Y,'.')
plt.show()
