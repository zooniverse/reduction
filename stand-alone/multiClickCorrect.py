import math
import numpy as np

class MultiClickCorrect:
    def __init__(self,dist_threshold=float("inf"),overlap_threshold=float("inf"),min_cluster_size=0):
        self.dist_threshold = dist_threshold
        self.overlap_threshold = overlap_threshold
        self.min_cluster_size = min_cluster_size

    def __find_closest__(self, clusters):
        # note this property is not symmetric - just because A is closest B, does not mean that B is closest to A
        # this means that for each cluster, we must read through ALL of the other cluster
        # however, this does mean that we will have some doubles which will need to be filtered out -
        # hence, closest_neighbours is a set
        # find the closest neighbours which satisfy an optional set of constraints
        closest_neighbours = set([])
        if len(clusters) == 1:
            return []
        print len(clusters)
        for c1_index,c1 in enumerate(clusters):
            closest = None
            min_dist = float("inf")
            current_overlap = None
            min_size = None

            center_1 = c1["center"]

            # todo - generalize this
            assert len(center_1) == 2

            for c2_index,c2 in enumerate(clusters):
                if c1_index == c2_index:
                    continue

                center_2 = c2["center"]

                dist = math.sqrt((center_1[0]-center_2[0])**2+(center_1[1]-center_2[1])**2)
                users_1 = c1["users"]
                users_2 = c2["users"]
                assert users_1 != []
                assert users_2 != []
                overlap = [u for u in users_1 if u in users_2]

                # have we found a closer cluster?
                # if so, update the necessary values
                if min_dist>dist:
                    min_dist = dist
                    closest = c2_index
                    current_overlap = overlap[:]
                    # min size is the size of the smaller of the two clusters
                    min_size = min(len(users_1),len(users_2))

            # if two really close clusters have a lot of users in common, then we can be pretty sure that despite being
            # so close they actually represent different things
            # if the minimum distance is large enough then again we can be pretty sure we can dealing with different clusters
            # if the minimum size is not big enough: for example if there is only one user in common and the smaller
            # cluster contains only that user, then it is a toss up between if that user made a mistake or saw something
            # that everyone missed
            if (len(current_overlap) <= self.overlap_threshold) and (min_dist <= self.dist_threshold) and (min_size >= self.min_cluster_size):
                closest_neighbours.add((min_dist,min(c1_index,closest),max(c1_index,closest)))


        return sorted(list(closest_neighbours), key = lambda x:x[0])

    def __fix__(self,cluster_results):
        # print cluster_results
        # print len(cluster_results)
        # cluster_centers,cluster_pts,users_per_cluster = zip(*cluster_results)
        # find nearby clusters which have no users in common and merge them
        # mostly just to be on the results of dk-means
        k = 0
        while True:
            k += 1
            if k > 100:
                break
            # compare every pair of clusters - returns only those clusters with 0 users in common
            # within the threshold
            closest_neighbours = self.__find_closest__(cluster_results)
            if closest_neighbours == []:
                break

            # do this one at a time just to be careful
            distance,c1_index, c2_index = closest_neighbours[0]
            assert c2_index > c1_index

            # retrieve the two clusters to be merged - pop the higher one first to maintain the index
            # for the lower one
            # I guess we don't have to technically pop both - we could just merge one into the other
            # but there is enough going on here that I just wanted to be clear
            cluster2 = cluster_results.pop(c2_index)
            cluster1 = cluster_results.pop(c1_index)

            # start by dealing with the users (and their corresponding points) which only occur in one cluster
            # for now - those users who appear in both cluster - I'm going to just take there first point
            # todo - check to make sure that this reasonable
            from_cluster1 = [(u,p,t) for u,p,t in zip(cluster1["users"],cluster1["cluster members"],cluster1["tools"])]
            from_cluster2 = [(u,p,t) for u,p,t in zip(cluster2["users"],cluster2["cluster members"],cluster2["tools"]) if u not in cluster1["users"]]

            # now combine those points
            users,points,tools = zip(*from_cluster1)
            users2,points2,tools2 = zip(*from_cluster2)
            users = list(users)
            points = list(points)
            tools = list(tools)
            users.extend(users2)
            points.extend(points2)
            tools.extend(tools2)

            # take the median along each dimension
            center = [np.median(dim) for dim in zip(*points)]
            cluster_results.append({"center":center,"cluster members":points,"users":users,"tools":tools})

        return cluster_results