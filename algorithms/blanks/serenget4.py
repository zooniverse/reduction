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

all_files = []
reasons = []

for ii,s in enumerate(subjects.find({"tutorial":{"$ne":True},"coords":[-2.4672743413359295, 34.75278520232197]}).limit(100)):
    # print s["coords"],s["created_at"]
    reason = s["metadata"]["retire_reason"]
    coords = s["coords"]

    # print s["created_at"]
    # print coords
    # print s["metadata"]["timestamps"]

    urls = s["location"]["standard"]
    slash_indices = [i.rfind("/") for i in urls]
    fnames = [str(i[j+1:]) for i,j in zip(urls,slash_indices)]

    if len(fnames) == 1:
        continue

    for url,fname in zip(urls,fnames):
        if not(os.path.isfile(image_directory+fname)):
                urllib.urlretrieve(url, image_directory+fname)

    all_files.append(fnames)
    reasons.append(reason)


for subject_index in range(min(50,len(all_files))):
    similarity = []
    non_similarity = []
    print subject_index
    # print reasons[subject_index]
    # print "---"
    similarities = []
    for subject_index2 in (subject_index+1,min(len(all_files),subject_index+7)):
        per_image_sim = []
        for fname1 in all_files[subject_index]:
            for fname2 in all_files[subject_index2]:
                # print image_directory+fname1
                # print image_directory+fname2
                command = "matlab -nodisplay -nosplash -nodesktop -r \"serengeti '"+image_directory+fname1+ "' '"+image_directory+fname2+"'\" > /dev/null"
                # print command
                os.system(command)

                with open("/home/greg/Databases/serengeti.out","rb") as f:
                    per_image_sim.append(int(f.readline()[:-1]))

        similarities.append(np.mean(per_image_sim))


        # if reasons[subject_index] == reasons[subject_index2]:
        #     similarity.append(max(differences))
        # else:
        #     non_similarity.append(max(differences))




    # print min(similarity),max(similarity),np.mean(similarity)
    # print min(non_similarity),max(non_similarity),np.mean(non_similarity)

    if reasons[subject_index] == "blank":
        false_positives.append(max(similarities))
    else:
        true_positives.append(max(similarities))

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