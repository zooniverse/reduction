#!/usr/bin/env python
import numpy as np
import cv2
from matplotlib import pyplot as plt
import matplotlib.cbook as cbook
import scipy
import math
fname = "/home/greg/Databases/serengeti/images/50c212438a607540b901d4b6_0.jpg"

img = cv2.imread(fname)
edges = cv2.Canny(img,100,200)

count = 0
for c in edges:
    for cell in c:
        if cell  > 0:
            count += 1
print count

plt.subplot(121),plt.imshow(img,cmap = 'gray')
plt.title('Original Image'), plt.xticks([]), plt.yticks([])
plt.subplot(122),plt.imshow(edges,cmap = 'gray')
plt.title('Edge Image'), plt.xticks([]), plt.yticks([])

plt.show()