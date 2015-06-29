#!/usr/bin/env python
__author__ = 'greghines'
import numpy as np
import os
import pymongo
import urllib
import matplotlib.pyplot as plt
import cv2
from skimage.measure import structural_similarity as ssim

def mse(imageA, imageB):
    # taken from
    # http://www.pyimagesearch.com/2014/09/15/python-compare-two-images/
    # the 'Mean Squared Error' between the two images is the
    # sum of the squared difference between the two images;
    # NOTE: the two images must have the same dimension
    err = np.sum((imageA.astype("float") - imageB.astype("float")) ** 2)
    err /= float(imageA.shape[0] * imageA.shape[1])

    # return the MSE, the lower the error, the more "similar"
    # the two images are
    return err

# the directory to store the movie preview clips in
image_directory = "/home/greg/Databases/serengeti/images/"

# connect to the mongodb server
client = pymongo.MongoClient()
db = client['serengeti_2015-02-22']
subjects = db["serengeti_subjects"]

false_positives = []
true_positives = []

for ii,s in enumerate(subjects.find({"tutorial":{"$ne":True},"coords":[-2.4672743413359295, 34.75278520232197]}).limit(100)):
    # print s["coords"],s["created_at"]
    reason = s["metadata"]["retire_reason"]
    coords = s["metadata"]["timestamps"][0]

    # print coords

    urls = s["location"]["standard"]
    slash_indices = [i.rfind("/") for i in urls]
    fnames = [str(i[j+1:]) for i,j in zip(urls,slash_indices)]

    if len(fnames) == 1:
        continue

    for url,fname in zip(urls,fnames):
        if not(os.path.isfile(image_directory+fname)):
                urllib.urlretrieve(url, image_directory+fname)

    differences = []
    for i,fname1 in enumerate(fnames):
        for fname2 in fnames[i+1:]:
            f1 = cv2.imread(image_directory+fname1)
            f2 = cv2.imread(image_directory+fname2)

            f1 = cv2.cvtColor(f1,cv2.COLOR_BGR2GRAY)
            f2 = cv2.cvtColor(f2,cv2.COLOR_BGR2GRAY)
            differences.append(-ssim(f1,f2))

    # add the threshold value to either the false positive (if the movie was
    # classified as blank by users) or true positive
    if reason == "blank":
        false_positives.append(max(differences))
    else:
        true_positives.append(max(differences))

# create the ROC curve
alphas = true_positives[:]
alphas.extend(false_positives)
alphas.sort()
X = []
Y = []
for a in alphas:
    X.append(len([x for x in false_positives if x >= a])/float(len(false_positives)))
    Y.append(len([y for y in true_positives if y >= a])/float(len(true_positives)))

print len(false_positives)
print len(true_positives)
plt.plot(X,Y)
plt.plot([0,1],[0,1],"--",color="green")
plt.xlabel("False Positive Count")
plt.ylabel("True Positive Count")
plt.show()