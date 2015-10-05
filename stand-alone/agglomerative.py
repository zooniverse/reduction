__author__ = 'ggdhines'
import clustering
import pandas as pd
import numpy as np
from scipy.spatial.distance import pdist,squareform
from scipy.cluster.hierarchy import linkage
import time
import abc
from scipy.stats import beta
import math
import numpy
import multiClickCorrect
import json
import random


def text_line_mappings(line_segments):
    """
    use if we want to cluster based on Hesse normal form - but want to retain the original values
    :param line_segment:
    :return:
    """
    reduced_markings = []

    for line_seg in line_segments:
        x1,y1,x2,y2,text = line_seg

        x2 += random.uniform(-0.0001,0.0001)
        x1 += random.uniform(-0.0001,0.0001)

        dist = (x2*y1-y2*x1)/math.sqrt((y2-y1)**2+(x2-x1)**2)

        try:
            tan_theta = math.fabs(y1-y2)/math.fabs(x1-x2)
            theta = math.atan(tan_theta)
        except ZeroDivisionError:
            theta = math.pi/2.

        reduced_markings.append((dist,theta,text))

    return reduced_markings


class Agglomerative(clustering.Cluster):
    def __init__(self,shape,**kwargs):
        clustering.Cluster.__init__(self,shape,kwargs)
        self.all_distances = []
        self.max = 0

        self.correction_alg = multiClickCorrect.MultiClickCorrect(overlap_threshold=1,min_cluster_size=2,dist_threshold=20)

    def __add_cluster(self,cluster_centers,end_clusters,end_users,node):
        # if len(node.pts) < 4:
        #     cluster_centers.append(None)
        #     end_clusters.append(None)
        #     end_users.append(None)
        # else:
        cluster_centers.append([np.median(axis) for axis in zip(*node.pts)])
        end_clusters.append(node.pts)
        end_users.append(node.users)

        return cluster_centers,end_clusters,end_users

    # def __results_to_json__(self,node):
    #     results = {}
    #     results["center"] = [np.median(axis) for axis in zip(*node.pts)]
    #     results["points"] = node.pts
    #     results["users"] = node.users
    #
    #     return results

    def __cluster__(self,markings,user_ids,tools,reduced_markings,image_dimensions):
        """
        the actual clustering algorithm
        markings and user_ids should be the same length - a one to one mapping
        :param markings:
        :param user_ids:
        :param jpeg_file:
        :param debug:
        :param gold_standard:
        :param subject_id:
        :return:
        """
        assert len(markings) == len(user_ids)
        assert len(markings) == len(reduced_markings)
        assert isinstance(user_ids,tuple)
        user_ids = list(user_ids)
        start = time.time()

        if len(user_ids) == len(set(user_ids)):
            # all of the markings are from different users => so only one cluster
            # todo implement
            result = {"users":user_ids,"cluster members":markings,"tools":tools,"num users":len(user_ids)}
            result["center"] = [np.median(axis) for axis in zip(*markings)]
            return [result],0

        all_users = set()

        # cluster based n the reduced markings, but list the clusters based on their original values

        # this converts stuff into panda format - probably a better way to do this but the labels do seem
        # necessary
        labels = [str(i) for i in reduced_markings]
        param_labels = [str(i) for i in range(len(reduced_markings[0]))]

        df = pd.DataFrame(np.array(reduced_markings), columns=param_labels, index=labels)
        row_dist = pd.DataFrame(squareform(pdist(df, metric='euclidean')), columns=labels, index=labels)
        # use ward metric to do the actual clustering
        row_clusters = linkage(row_dist, method='ward')

        # use the results to build a tree representation
        # nodes = [LeafNode(pt,ii,user=user) for ii,(user,pt) in enumerate(zip(user_ids,markings))]
        results = [{"users":[u],"cluster members":[p],"tools":[t],"num users":1} for u,p,t in zip(user_ids,markings,tools)]

        # read through the results
        # each row gives a cluster/node to merge
        # if one any two clusters have a user in common - don't merge them - and represent this by a None cluster
        # if trying to merge with a None cluster - this gives a None cluster as well
        for merge in row_clusters:
            rchild_index = int(merge[0])
            lchild_index = int(merge[1])

            rnode = results[rchild_index]
            lnode = results[lchild_index]

            # use "center" being in a dict to indicate that a node shouldn't be merged any more
            # use None to indicate that a "child" of the current node was a "terminal" node
            # if either node/cluster is None, we have already encountered overlapping users
            # if both are already terminal - just append None
            if ((rnode is None) or ("center" in rnode)) and ((lnode is None) or ("center" in lnode)):
                results.append(None)
            # maybe just the rnode was is already done - in which case "finish" the lnode
            elif (rnode is None) or ("center" in rnode):
                lnode["center"] = [np.median(axis) for axis in zip(*lnode["cluster members"])]
                results.append(None)
            # maybe just the lnode is done:
            elif (lnode is None) or ("center" in lnode):
                rnode["center"] = [np.median(axis) for axis in zip(*rnode["cluster members"])]
                results.append(None)
            else:
                # check if we should merge - only if there is no overlap
                # otherwise "cap" or terminate both nodes
                intersection = [u for u in rnode["users"] if u in lnode["users"]]

                # if there are users in common, add to the end clusters list (which consists of cluster centers
                # the points in each cluster and the list of users)
                if intersection != []:
                    rnode["center"] = [np.median(axis) for axis in zip(*rnode["cluster members"])]
                    lnode["center"] = [np.median(axis) for axis in zip(*lnode["cluster members"])]
                    results.append(None)
                else:
                    # else just merge
                    merged_users = rnode["users"]
                    merged_points = rnode["cluster members"]
                    merged_tools = rnode["tools"]
                    # add in the values from the second node
                    merged_users.extend(lnode["users"])
                    merged_points.extend(lnode["cluster members"])
                    merged_tools.extend(lnode["tools"])
                    num_users = rnode["num users"] + lnode["num users"]
                    results.append({"users":merged_users,"cluster members":merged_points,"tools":merged_tools,"num users":num_users})

        # go and remove all non terminal nodes from the results
        for i in range(len(results)-1,-1,-1):
            # if None => corresponds to being above a terminal node
            # or center not in results => corresponds to being beneath a terminal node
            # in both cases does not mean immediately above or below
            if (results[i] is None) or ("center" not in results[i]):
                results.pop(i)

        # todo - this is just for debugging
        for j in results:
            assert "num users" in j

        end = time.time()
        return results,end-start

    def __check__(self):
        self.all_distances = [d/max(self.all_distances) for d in self.all_distances]
        mean=numpy.mean(self.all_distances)
        var=numpy.var(self.all_distances,ddof=1)

        ii = len(self.all_distances)
        while var >= (mean*(1-mean)):
            ii -= 1
            mean=numpy.mean(self.all_distances[:ii])
            var=numpy.var(self.all_distances[:ii],ddof=1)

        alpha1=mean*(mean*(1-mean)/var-1)
        beta1=alpha1*(1-mean)/mean
        for d in sorted(self.all_distances):
            print d,beta.cdf(d,alpha1,beta1)