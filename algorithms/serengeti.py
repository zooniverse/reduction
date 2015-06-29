#!/usr/bin/env python
__author__ = 'greg'
import pymongo
import matplotlib.pyplot as plt
import numpy
import math
import random
import csv
import scipy.stats as stats
# import numpy as np
import pylab as pl
import scipy.special as ss
from scipy.stats import beta as beta_func

# load subject data from CSV
subjects_index = {}
with open('/home/greg/Documents/subject_species_all.csv', 'rb') as csvfile:
    reader = csv.reader(csvfile, delimiter=',', quotechar='"')
    for row in reader:
        subjects_index[row[1]] = row[2]

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

max_classifications = 0

# scan through *ALL* classifications (add a .skip or .limit to look at subset)
for ii, classification in enumerate(classification_collection.find().skip(0).limit(1000000)):
    if ii % 10000 == 0:
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
    #subject = subject_collection.find_one({"zooniverse_id":zoonvierse_id})
    #if subject["metadata"]["retire_reason"] in ["blank"]:
    if subjects_index[zoonvierse_id]=="blank":
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
        if time_delta.seconds >= 60*30: # note, session length currently set to 60 minutes. Change second number to 10 for a 10 min session
            # store data and reset counters

            if session_length[id] >= 3:
                max_classifications = max(max_classifications,session_length[id])
                X.append(num_blanks[id]/float(session_length[id]))
                Y.append(session_length[id])
            session_length[id] = 0
            num_blanks[id] = 0



    except KeyError:
        pass

    current_sessions[id] = time

# basic plot of results
plt.plot(X,Y,'.')
plt.hist(X, 50,weights=[0.75 for i in X],histtype='step')
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
v = {}
confidence = {}
# store y values in appropriate bins
for x,y in XY:
    if x == 1:
        bins[(bins_endpts[-2],bins_endpts[-1])].append(y)
    else:
        for lb,ub in bins.keys():
            if (lb <= x) and (x < ub):
                bins[(lb,ub)].append(y/float(max_classifications))
                break



def beta_(a, b, mew):
    e1 = ss.gamma(a + b)
    e2 = ss.gamma(a)
    e3 = ss.gamma(b)
    e4 = mew ** (a - 1)
    e5 = (1 - mew) ** (b - 1)
    return (e1/(e2*e3)) * e4 * e5

def plot_beta(a, b):
    Ly = []
    Lx = []
    mews = numpy.mgrid[0:1:100j]
    for mew in mews:
        Lx.append(mew)
        Ly.append(beta_(a, b, mew))
    pl.plot(Lx, Ly, label="a=%f, b=%f" %(a,b))

Y2 = [y/float(max_classifications) for y in Y]
mean=numpy.mean(Y2)
var=numpy.var(Y2,ddof=1)
print var < (mean*(1-mean))
alpha = mean*(mean*(1-mean)/var-1)
beta = (1-mean)*(mean*(1-mean)/var-1)
# plot_beta(alpha,beta)
# pl.show()

for i in range(len(bins_endpts)-1):
    lb = bins_endpts[i]
    ub = bins_endpts[i+1]

    t= len(bins[(lb,ub)])
    if t > 0:
    # print t
        v = sorted(bins[(lb,ub)])
        mid = len(v)/2.-0.5
        lc = int(mid-3.6)
        uc = int(mid+3.6)
        #lc = int(round(len(v)/2.-1.96*math.sqrt(len(v))/2.)-1)
        #uc = int(round(1+len(v)/2.+1.96*math.sqrt(len(v))/2.)-1)
        #print numpy.median(bins[(lb,ub)])
        print v[lc],v[uc]
    # r = beta_func.rvs(alpha, beta, size=t)
    # print numpy.median(r)
    # print

assert False
# def main():
#     plot_beta(0.1, 0.1)
#     plot_beta(1, 1)
#     plot_beta(2, 3)
#     plot_beta(8, 4)
#     pl.xlim(0.0, 1.0)
#     pl.ylim(0.0, 3.0)
#     pl.legend()
#     pl.show()

# use an exponential distribution to approximate the values in each bin
# estimate lambda - the one param for an exponential distribution
for i in range(len(bins_endpts)-1):
    lb = bins_endpts[i]
    ub = bins_endpts[i+1]

    if len(bins[(lb,ub)]) >= 5:
        values = bins[(lb,ub)]
        mean=numpy.mean(values)
        var=numpy.var(values,ddof=1)

        # print len(values), var >= (mean*(1-mean))

        exp_lambda.append(1/mean)
        v[lb] = mean
        lambd = 1/mean

        confidence[lb] = (lambd * (1-1.96/math.sqrt(len(values))), lambd * (1+1.96/math.sqrt(len(values))))
        alpha = mean*(mean*(1-mean)/var-1)
        beta = (1-mean)*(mean*(1-mean)/var-1)

        if var < (mean*(1-mean)):
            print alpha,beta
            plot_beta(alpha,beta)

        X2.append((ub+lb)/2.)
        error.append((1/mean)*1.96/math.sqrt(len(values)))

pl.show()
assert False
print "variance is " + str(numpy.var(v.values()))

# plot out the lambda values - with confidence regions - for each bin
plt.errorbar(X2,exp_lambda,yerr=error)
plt.xlabel("percentage of images per session which are blank")
plt.ylabel("estimate of lambda param for exponential distribution")
plt.yscale("log")
plt.show()
plt.close()


# plot a cumulative distribution of values as well
plt.hist(X, 50, normed=1,histtype='step', cumulative=True)
plt.xlabel("percentage of images per session which are blank")
plt.ylabel("cumulative distribution")
plt.yscale("log")
plt.show()

X = []
Y = []

v2 = {}

for i in range(len(bins_endpts)-1):
    lb = bins_endpts[i]
    ub = bins_endpts[i+1]

    if lb in v:

        for j in range(200):
            X.append(random.uniform(lb,ub))
            Y.append(random.expovariate(random.uniform(confidence[lb][0],confidence[lb][1])))

            # Y.append(numpy.random.exponential(v[lb]))

plt.plot(X,Y,'.')

XY = zip(X,Y)
bins2 = {(bins_endpts[i],bins_endpts[i+1]):[] for i in range(len(bins_endpts)-1)}

# store y values in appropriate bins
for x,y in XY:
    if x == 1:
        bins2[(bins_endpts[-2],bins_endpts[-1])].append(y)
    else:
        for lb,ub in bins2.keys():
            if (lb <= x) and (x < ub):
                bins2[(lb,ub)].append(y)
                break

for i in range(len(bins_endpts)-1):
    lb = bins_endpts[i]
    ub = bins_endpts[i+1]

    if len(bins2[(lb,ub)]) >= 5:
        values = bins2[(lb,ub)]
        mean=numpy.mean(values)

        v2[lb] = mean
print "variance is now " + str(numpy.var(v2.values()))
plt.show()
