import numpy as np
import cv2
from matplotlib import pyplot as plt
import matplotlib.cbook as cbook
import scipy
import math
fname = "/home/greg/Databases/images/01a10f4b-e03a-4dee-9a2c-62bcc3da3c09.jpeg"

img = cv2.imread(fname)
gray = cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
ret, thresh = cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)



# noise removal
kernel = np.ones((3,3),np.uint8)
opening = cv2.morphologyEx(thresh,cv2.MORPH_OPEN,kernel, iterations = 2)

# sure background area
sure_bg = cv2.dilate(opening,kernel,iterations=3)

# Finding sure foreground area
dist_transform = cv2.distanceTransform(opening,cv2.DIST_L2,3)
ret, sure_fg = cv2.threshold(dist_transform,0.7*dist_transform.max(),255,0)

# Finding unknown region
sure_fg = np.uint8(sure_fg)
unknown = cv2.subtract(sure_bg,sure_fg)
cv2.imwrite("image_processed.png",thresh)

import numpy
import PIL
img = PIL.Image.open("image_processed.png").convert("L")
arr = numpy.array(img)

from sklearn.cluster import DBSCAN


from sklearn.datasets.samples_generator import make_blobs
import matplotlib.pyplot as plt

v = []
for i,r in enumerate(arr):
    for j,c in enumerate(r):
      if c != 0:
          v.append((i,j))



print len(v)
import numpy as np
X = np.asarray(v)

db = DBSCAN(eps=3.5, min_samples=10).fit(X)
core_samples_mask = np.zeros_like(db.labels_, dtype=bool)
core_samples_mask[db.core_sample_indices_] = True
labels = db.labels_
n_clusters_ = len(set(labels)) - (1 if -1 in labels else 0)

from scipy.spatial import ConvexHull

# Black removed and is used for noise instead.
unique_labels = set(labels)
colors = plt.cm.Spectral(np.linspace(0, 1, len(unique_labels)))

image_file = cbook.get_sample_data(fname)
image = plt.imread(image_file)
fig, ax = plt.subplots()
im = ax.imshow(image)

Y = []
X = []
for k, col in zip(unique_labels, colors):
    if k == -1:
        continue

    class_member_mask = (labels == k)

    # xy = X[class_member_mask & core_samples_mask]
    #
    # if len(xy) > 100:
    #     continue
    #
    # plt.plot(xy[:, 1], -xy[:, 0], 'o', markerfacecolor=col,
    #          markeredgecolor='k', markersize=2)
    #
    # xy = X[class_member_mask & ~core_samples_mask]
    # if len(xy) > 100:
    #     continue
    #
    # plt.plot(xy[:, 1], -xy[:, 0], 'o', markerfacecolor=col,
    #          markeredgecolor='k', markersize=2)


    xy = X[class_member_mask]

    if len(xy) > 2000:
        continue

    x,y = zip(*xy)

    # if not math.isnan(np.median(y)):
    Y.append([np.median(y),])
    X.append([np.median(x),])
    # else:
    #     print

    # xy = zip(y,x)
    # xy = np.asarray(xy)
    # print xy
    # try:
    #     hull = ConvexHull(xy)
    # except scipy.spatial.qhull.QhullError:
    #     print x
    #     print y
    #     print
    #     continue
    # X_l,Y_l= xy[hull.vertices,0], xy[hull.vertices,1]
    # X_l = list(X_l)
    # Y_l = list(Y_l)
    # X_l.append(X_l[0])
    # Y_l.append(Y_l[0])
    #
    # plt.plot(X_l,Y_l, lw=1)

# from sklearn.cluster import KMeans
# kmeans = KMeans(init='k-means++', n_clusters=20, n_init=10)
# Y = np.asarray(Y)
# kmeans.fit(Y)

XY = np.asarray(zip(X,Y))
db = DBSCAN(eps=3.5, min_samples=1).fit(XY)

core_samples_mask = np.zeros_like(db.labels_, dtype=bool)
core_samples_mask[db.core_sample_indices_] = True
labels = db.labels_
n_clusters_ = len(set(labels)) - (1 if -1 in labels else 0)

from scipy.spatial import ConvexHull

# Black removed and is used for noise instead.
unique_labels = set(labels)


# plt.title('Estimated number of clusters: %d' % n_clusters_)
# plt.show()