#!/usr/bin/env python
__author__ = 'alex'
import pymongo
import matplotlib.pyplot as plt
import numpy
import math
import random
import csv
import pickle

print "\nLoading data..."

X = pickle.load( open( "X.p", "rb" ) )
Y = pickle.load( open( "Y.p", "rb" ) )

# print tasks for debugging
#
#import pprint
#pp = pprint.PrettyPrinter(indent=2)
#pp.pprint(X)
#pp.pprint(Y)

points =[]
for idx, val in enumerate(X):
  if Y[idx]>3:
    newDataPoint = { "X" : val, "Y" : Y[idx]}
    points.append(newDataPoint)

bucketedPoints = {}
for i in range(0,101):
  bucketedPoints[str(i)] = []

for idx,point in enumerate(points):
  bucket = str(int(round(point["X"]*100)))
  bucketedPoints[bucket].append(point.copy())

#now everything is arranged in buckets by percentile, need to reduce to a finite number for each.
# but first, how many do we have for each?
for i in sorted(bucketedPoints):
  #print "enumerating %s as %s " % (i, bucketedPoints[i])
  print "Original bucket [%s] has %s datapoints" % (i, len(bucketedPoints[i]))

# print tasks for debugging
#import pprint
#pp = pprint.PrettyPrinter(indent=2)
#pp.pprint(bucketedPoints)

finiteBucketedPoints = {}
for i in range(0,101):
  finiteBucketedPoints[str(i)] = []

N=2000

# for each bucket, add N samples from real bucket to corresponding finite bucket
for b in bucketedPoints:
  for i in range(0,N):
    if finiteBucketedPoints.has_key(str(b)):
      if len(bucketedPoints[b])>0:
        finiteBucketedPoints[str(b)].append(random.choice(bucketedPoints[b]))

noOfBuckets = 101
print "After normalization, all 101 fixed size buckets had %s datapoints, except for:" % N
for i in sorted(finiteBucketedPoints):
  #print "enumerating %s as %s " % (i, bucketedPoints[i])
  if (len(finiteBucketedPoints[i])<N):
    print "[%s] bucket has %s datapoints" % (i, len(finiteBucketedPoints[i]))
    noOfBuckets -= 1
     
simplePointsX = []
simplePointsY = []

for i in finiteBucketedPoints:
  bucket = finiteBucketedPoints[str(i)]
  for point in bucket:
    simplePointsX.append(point["X"])
    simplePointsY.append(point["Y"])

# basic plot of results
plt.plot(simplePointsX,simplePointsY,'.')
plt.hist(simplePointsX, noOfBuckets,weights=[0.75 for i in simplePointsX],histtype='step') # was 0.75
plt.xlabel("percentage of images per session which are blank")
plt.ylabel("session length - blank + non-blank")
plt.show()
plt.close()

#XY = zip(X,Y)
#XY.sort(key = lambda x:x[0])

# create bins for a range of different X values between 0 and 1 - incrementing by 0.025
# assume that within bin, the distribution of values is independent of X
#bins_endpts = numpy.arange(0,1.01,0.025)
#bins = {(bins_endpts[i],bins_endpts[i+1]):[] for i in range(len(bins_endpts)-1)}
#exp_lambda = []
#X2 = []
#error = []

# store y values in appropriate bins
#for x,y in XY:
#    if x == 1:
#        bins[(bins_endpts[-2],bins_endpts[-1])].append(y)
#    else:
#        for lb,ub in bins.keys():
#            if (lb <= x) and (x < ub):
#                bins[(lb,ub)].append(y)
#                break

# use an exponential distribution to approximate the values in each bin
# estimate lambda - the one param for an exponential distribution
#for i in range(len(bins_endpts)-1):
#    lb = bins_endpts[i]
#    ub = bins_endpts[i+1]
#
#    if len(bins[(lb,ub)]) >= 10:
#        values = bins[(lb,ub)]
#        mean=numpy.mean(values)
#        var=numpy.var(values,ddof=1)
#
#        print len(values), var >= (mean*(1-mean))
#
#        exp_lambda.append(1/mean)
#        X2.append((ub+lb)/2.)
#        error.append((1/mean)*1.96/math.sqrt(len(values)))

# plot out the lambda values - with confidence regions - for each bin
#plt.errorbar(X2,exp_lambda,yerr=error)
#plt.xlabel("percentage of images per session which are blank")
#plt.ylabel("estimate of lambda param for exponential distribution")
#plt.show()


# plot a cumulative distribution of values as well
#plt.hist(X, 50, normed=1,histtype='step', cumulative=True)
#plt.xlabel("percentage of images per session which are blank")
#plt.ylabel("cumulative distribution")
#plt.show()