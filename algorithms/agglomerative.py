__author__ = 'ggdhines'
import clustering
import pandas as pd
import numpy as np
from scipy.spatial.distance import pdist,squareform
from scipy.cluster.hierarchy import linkage
import time
import automatic_optics
from scipy.stats import beta
import math
import numpy

class Agglomerative(clustering.Cluster):
    def __init__(self,project_api,min_cluster_size=1,mapping =None):
        clustering.Cluster.__init__(self,project_api,min_cluster_size,mapping)
        self.algorithm_name = "agglomerative"
        self.all_distances = []
        self.max = 0

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

    def __results_to_json__(self,node):
        results = {}
        results["center"] = [np.median(axis) for axis in zip(*node.pts)]
        results["points"] = node.pts
        results["users"] = node.users

        return results

    def __inner_fit__(self,markings,user_ids,jpeg_file=None,debug=False,gold_standard=False,subject_id=None):
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
        assert isinstance(user_ids,tuple)
        user_ids = list(user_ids)
        start = time.time()

        if self.mapping is not None:
            mapped_markings = []
            for i,m in enumerate(markings):
                try:
                    mapped_markings.append(self.mapping(m))
                except ZeroDivisionError:
                    user_ids.pop(i)
            # mapped_markings = [self.mapping(m) for m in markings]
        else:
            mapped_markings = markings
        assert len(mapped_markings) == len(user_ids)


        # cluster_centers = []
        # end_clusters = []
        # end_users = []
        results = []
        # this converts stuff into panda format - probably a better way to do this but the labels do seem
        # necessary
        labels = [str(i) for i in mapped_markings]
        param_labels = [str(i) for i in range(len(mapped_markings[0]))]
        df = pd.DataFrame(np.array(mapped_markings), columns=param_labels, index=labels)
        row_dist = pd.DataFrame(squareform(pdist(df, metric='euclidean')), columns=labels, index=labels)
        # use ward metric to do the actual clustering
        row_clusters = linkage(row_dist, method='ward')


        # use the results to build a tree representation
        nodes = [automatic_optics.LeafNode(pt,ii,user=user) for ii,(user,pt) in enumerate(zip(user_ids,markings))]

        max_height = 0

        # read through the results
        # each row give a cluster/node to merge
        # one any two cluters have a user in common - don't merge them - and represent this by a None cluster
        # if trying to merge with a None cluster - this gives a None cluster as well
        for merge in row_clusters:
            rchild_index = int(merge[0])
            lchild_index = int(merge[1])

            rnode = nodes[rchild_index]
            lnode = nodes[lchild_index]

            # if either node/cluster is None, we have already encountered overlapping users
            if (rnode is None) or (lnode is None):
                # if any of these nodes are not None, add them to the end cluster list
                if rnode is not None:
                    # cluster_centers,end_clusters,end_users = self.__add_cluster(cluster_centers,end_clusters,end_users,rnode)
                    results.append(self.__results_to_json__(rnode))
                elif lnode is not None:
                    # cluster_centers,end_clusters,end_users = self.__add_cluster(cluster_centers,end_clusters,end_users,lnode)
                    results.append(self.__results_to_json__(lnode))
                nodes.append(None)
            else:
                # check for intersection
                intersection = [u for u in rnode.users if u in lnode.users]

                # if there are users in common, add to the end clusters list (which consists of cluster centers
                # the points in each cluster and the list of users)
                if intersection != []:
                    # cluster_centers,end_clusters,end_users = self.__add_cluster(cluster_centers,end_clusters,end_users,rnode)
                    # cluster_centers,end_clusters,end_users = self.__add_cluster(cluster_centers,end_clusters,end_users,lnode)
                    results.append(self.__results_to_json__(rnode))
                    results.append(self.__results_to_json__(lnode))

                    nodes.append(None)
                else:
                    # else just merge
                    nodes.append(automatic_optics.InnerNode(rnode,lnode))

        # in the rare case where the root node is not None, add it to the end clusters
        if nodes[-1] is not None:
            # self.__add_cluster(cluster_centers,end_clusters,end_users,nodes[-1])
            results.append(self.__results_to_json__(nodes[-1]))

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