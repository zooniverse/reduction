#!/usr/bin/env python
__author__ = 'ggdhines'
from penguinAggregation import PenguinAggregation
import random
import os
import sys
import cPickle as pickle
import aggregation
import matplotlib.pyplot as plt
import numpy as np

# add the paths necessary for clustering algorithm and ibcc - currently only works on Greg's computer
if os.path.exists("/home/ggdhines"):
    sys.path.append("/home/ggdhines/PycharmProjects/reduction/experimental/clusteringAlg")
else:
    sys.path.append("/home/greg/github/reduction/experimental/clusteringAlg")

from agglomerativeClustering import Ward
from divisiveKmeans import DivisiveKmeans

clusterAlg2 = DivisiveKmeans().__fit__

dkmeans = PenguinAggregation(clustering_alg= DivisiveKmeans().__fit__)
agglomerative = PenguinAggregation(clustering_alg = Ward().__fit__)
subject_ids = pickle.load(open(aggregation.base_directory+"/Databases/penguin_gold.pickle","rb"))


X1 = []
Y1 = []
X2 = []
Y2 = []
Z1 = []
Z2 = []
nonEmpty = 0
index = -1
random.shuffle(subject_ids)
while True:
    index += 1
#for i,subject in enumerate(random.sample(subject_ids,50)):
    #subject = "APZ000173v"
    subject = subject_ids[index]
    #print nonEmpty,index

    agglomerative.__readin_subject__(subject,read_in_gold=True)#,users_to_skip=["caitlin.black"])
    dkmeans.__readin_subject__(subject,read_in_gold=True)
    numClusters,time_to_cluster = agglomerative.__cluster_subject__(subject)


    if numClusters == 0:
        continue

    print nonEmpty

    nonEmpty += 1
    if nonEmpty == 20:
        break
    accuracy1 = agglomerative.__accuracy__(subject)

    X1.append(numClusters)
    Y1.append(time_to_cluster)
    Z1.append(accuracy1)

    numClusters2,time_to_cluster = dkmeans.__cluster_subject__(subject, clusterAlg2,fix_distinct_clusters=True)
    accuracy2 = dkmeans.__accuracy__(subject)
    X2.append(numClusters2)
    Y2.append(time_to_cluster)
    Z2.append(accuracy2)

    #dkmeans.__outliers__(subject)

    print accuracy1,accuracy2,dkmeans.__num_gold_clusters__(subject)
    #print numMarkings,numMarkings2


print len([z1 for (z1,z2) in zip(Z1,Z2) if z1 > z2])/float(len(Z1))
print len([z1 for (z1,z2) in zip(Z1,Z2) if z1 < z2])/float(len(Z1))
print len([z1 for (z1,z2) in zip(Z1,Z2) if z1 == z2])/float(len(Z1))

plt.plot(Z2,Z1,'.',color="black")
plt.xlabel("Number of Clusters Found by Divisive K-Means")
plt.ylabel("Number of Clusters Found by Agglomerative Clustering")
plt.plot([0,max(max(Z1),max(Z2))+10],[0,max(max(Z1),max(Z2))+10],"--",color="black")
plt.xlim((0,max(max(Z1),max(Z2))+10))
plt.ylim((0,max(max(Z1),max(Z2))+10))
plt.show()

agglomerative.__signal_ibcc__()
X,Y = agglomerative.__roc__()
plt.plot(X,Y,color="red")

dkmeans.__signal_ibcc__()
X,Y = dkmeans.__roc__()
plt.plot(X,Y,color="green")

plt.show()

#
# plt.plot(X1,Y1,"+",color="black",label="Agglomerative")
# plt.plot(X2,Y2,"o",color="black",label = "Divisive k-means")
# plt.xlabel("Number of Clusters")
# plt.ylabel("Runtime of Clustering Algorithm")
# plt.legend(loc="upper left")
# print len(X1),len(X2)
# print np.mean(Y1)
# print np.mean(Y2)
#
# plt.show()