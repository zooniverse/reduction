__author__ = 'greg'
import pymongo
import bisect
import sys
import os
import csv
import matplotlib.pyplot as plt
import urllib
import matplotlib.cbook as cbook
from collections import Iterator
import math
from scipy.stats.stats import pearsonr
import cPickle as pickle
from scipy.stats.mstats import normaltest
import warnings
import time

from pylab import meshgrid,cm,imshow,contour,clabel,colorbar,axis,title,show

import numpy as np
from mpl_toolkits.mplot3d import Axes3D
# for Greg - which computer am I on?
if os.path.exists("/home/ggdhines"):
    base_directory = "/home/ggdhines"
    github_directory = base_directory + "/github"
    code_directory = base_directory + "/PycharmProjects"
elif os.path.exists("/Users/greg"):
    base_directory = "/Users/greg"
    code_directory = base_directory + "/Code"
    github_directory = base_directory +"/github"
    print github_directory
else:
    base_directory = "/home/greg"
    code_directory = base_directory + "/github"
    github_directory = base_directory + "/github"

sys.path.append(github_directory+"/pyIBCC/python")
sys.path.append(code_directory+"/reduction/experimental/clusteringAlg")
import ibcc
import multiClickCorrect



def index(a, x):
    'Locate the leftmost value exactly equal to x'
    i = bisect.bisect_left(a, x)
    if i != len(a) and a[i] == x:
        return i
    raise ValueError


class ClassificationTools():
    def __init__(self,scale=1):
        self.scale = scale

    def __classification_to_markings__(self,classification):
        assert False

    def __list_markings__(self, classification):
        print "hello"
        return False
        # yield 1
        # return
        # print classification
        # marks_list = self.__classification_to_markings__(classification)
        # print marks_list
        # assert False
        #
        # for mark in marks_list:
        #     x = float(mark["x"])*self.scale
        #     y = float(mark["y"])*self.scale
        #
        #     if not("animal" in mark):
        #         animal_type = None
        #     else:
        #         animal_type = mark["animal"]
        #
        #     yield (x,y),animal_type

class ROIClassificationTools(ClassificationTools):
    def __init__(self,scale=1):
        # roi is the region of interest - if a point lies outside of this region, we will ignore it
        # such cases should probably all be errors - a marking lies outside of the image
        # or, somehow, just outside of the ROI - see penguin watch for an example
        # because Penguin Watch started it, and the images for penguin watch are flipped (grrrr)
        # the roi is the region ABOVE the line segments
        ClassificationTools.__init__(self,scale)

        self.roi_dict = {}

    def __load_roi__(self,classification):
        assert False

    def __list_markings__(self,classification):
        marks_list = self.__classification_to_markings__(classification)
        roi = self.__load_roi__(classification)

        for mark in marks_list:
            x = float(mark["x"])*self.scale
            y = float(mark["y"])*self.scale

            if not("animal" in mark):
                animal_type = None
            else:
                animal_type = mark["animal"]

            #find which line segment on the roi the point lies on (x-axis wise)
            for segment_index in range(len(roi)-1):
                if (roi[segment_index][0] <= x) and (roi[segment_index+1][0] >= x):
                    rX1,rY1 = roi[segment_index]
                    rX2,rY2 = roi[segment_index+1]

                    m = (rY2-rY1)/float(rX2-rX1)
                    rY = m*(x-rX1)+rY1

                    if y >= rY:
                        # we have found a valid marking
                        # create a special type of animal None that is used when the animal type is missing
                        # thus, the marking will count towards not being noise but will not be used when determining the type

                        yield (x,y),animal_type
                        break
                    else:
                        break




class Aggregation:
    def __init__(self, project, date, tools=None, to_skip=[],clustering_alg=None):
        self.project = project

        client = pymongo.MongoClient()
        db = client[project+"_"+date]
        self.classification_collection = db[project+"_classifications"]
        self.subject_collection = db[project+"_subjects"]
        self.user_collection = db[project+"_users"]

        # we a global list of logged in users so we use the index for the same user over multiple images
        self.all_users = []

        # we need a list of of users per subject (and a separate one for just those users who were not logged in
        # those ones will just have ip addresses
        self.users_per_subject = {}
        self.ips_per_subject = {}

        # dictionaries for the raw markings per image
        self.markings_list = {}
        #who made what marking
        self.markings_to_user = {}
        #self.users_per_ = {}
        # what did the user think they saw these coordinates?
        # for example, in penguin watch, it could be a penguin
        self.what_list = {}
        self.subjects_per_user = {}

        self.correct_clusters = {}

        # the clustering results per image
        self.clusterResults = {}
        self.signal_probability = []

        # this is the iteration class that goes through all of the markings associated with each classification
        # for at least some of the projects the above code will work just fine
        self.tools = tools

        self.to_skip = to_skip

        # image dimensions - used to throw silly markings not actually on the image
        self.dimensions = {}
        self.num_clusters = None
        self.closest_neighbours = {}

        self.ibcc_confusion = None

        self.gold_data = {}

        self.correction = multiClickCorrect.MultiClickCorrect(overlap_threshold=0)


        self.expert = None
        self.clustering_alg = clustering_alg

    def __get_users__(self,zooniverse_id):
        return self.users_per_subject[zooniverse_id]

    def __readin_users__(self):
        for user_record in self.user_collection.find():
            if "name" in user_record:
                user = user_record["name"]
                bisect.insort(self.all_users,user)

    def __get_completed_subjects__(self):
        id_list = []
        for subject in self.subject_collection.find({"state": "complete"}):
            zooniverse_id = subject["zooniverse_id"]
            id_list.append(zooniverse_id)

            self.dimensions[zooniverse_id] = subject["metadata"]["original_size"]

        return id_list

    def __cluster_overlap__(self, c1, c2):
        return [c for c in c1 if c in c2]



    # def __find_closest_neighbour__(self,zooniverse_id,to_skip=[]):
    #     cluster_results = self.clusterResults[zooniverse_id]
    #     # if there is only one cluster NN doesn't make sense
    #     if len(cluster_results[0]) == 1:
    #         return
    #
    #     assert zooniverse_id in self.clusterResults
    #     self.closest_neighbours[zooniverse_id] = []
    #
    #
    #
    #     assert len(cluster_results[0]) == len(cluster_results[1])
    #     assert len(cluster_results[1]) == len(cluster_results[2])
    #
    #
    #
    #     for i1 in range(len(cluster_results[0])):
    #         if i1 in to_skip:
    #             self.closest_neighbours[zooniverse_id].append((None,None, None, None))
    #             continue
    #         center1,pts1,users1 = cluster_results[0][i1],cluster_results[1][i1],cluster_results[2][i1]
    #
    #         minimum_distance = float("inf")
    #         overlap = None
    #         closest_neighbour = None
    #         closest_index = None
    #         for i2 in range(len(cluster_results[0])):
    #             if (i1 != i2) and not(i2 in to_skip):
    #                 try:
    #                     center2,pts2,users2 = cluster_results[0][i2],cluster_results[1][i2],cluster_results[2][i2]
    #                 except IndexError:
    #                     print i2
    #                     print len(cluster_results[0])
    #                     print len(cluster_results[1])
    #                     print len(cluster_results[2])
    #                     raise
    #
    #                 dist = math.sqrt((center1[0]-center2[0])**2+(center1[1]-center2[1])**2)
    #                 if dist < minimum_distance:
    #                     minimum_distance = dist
    #                     overlap = self.__cluster_overlap__(users1, users2)
    #                     closest_neighbour = center2[:]
    #                     closest_index = i2
    #
    #         assert overlap is not None
    #         assert closest_neighbour is not None
    #
    #         self.closest_neighbours[zooniverse_id].append((closest_index,closest_neighbour, minimum_distance, overlap))

    def __plot_closest_neighbours__(self,zooniverse_id_list):
        totalY = []
        totalDist = []

        for zooniverse_id in zooniverse_id_list:
            if zooniverse_id in self.closet_neighbours:
                pt_l,dist_l = zip(*self.closet_neighbours[zooniverse_id])
                X_pts,Y_pts = zip(*pt_l)

                # find to flip the image
                Y_pts = [-p for p in Y_pts]

                plt.plot(dist_l,Y_pts,'.',color="red")

                totalDist.extend(dist_l)
                totalY.extend(Y_pts)

        print pearsonr(dist_l,Y_pts)
        plt.show()

    def __find_one__(self,zooniverse_id_list):
        # for zooniverse_id in zooniverse_id_list:
        #     if zooniverse_id in self.closet_neighbours:
        #         self.__display_image__(zooniverse_id)
        #         for cluster_index in range(len(self.clusterResults[zooniverse_id][0])):
        #             center = self.clusterResults[zooniverse_id][0][cluster_index]
        #             nearest_neigbhour = self.closet_neighbours[zooniverse_id][cluster_index][0]
        #             overlap = self.closet_neighbours[zooniverse_id][cluster_index][2]
        #
        #             plt.plot([center[0],], [center[1],],'o',color="blue")
        #             if overlap == 1:
        #                 plt.plot([center[0],nearest_neigbhour[0]],[center[1],nearest_neigbhour[1]],color="red")
        #
        #         plt.show()
        # return


        #  sort of barnes interpolation
        totalY = []
        totalDist = []

        scale = 1

        Ypixel_range = np.arange(0,1,0.005)
        dist_range = np.arange(0,scale,0.01)
        X,Y = np.meshgrid(Ypixel_range,dist_range)

        Z = []

        #convert into one big list
        for zooniverse_id in zooniverse_id_list:
            if zooniverse_id in self.closet_neighbours:
                cluster_centers = self.clusterResults[zooniverse_id][0]
                X_pts,Y_pts = zip(*cluster_centers)

                distance_to_nn = zip(*self.closet_neighbours[zooniverse_id])[1]

                totalDist.extend(distance_to_nn)
                totalY.extend(Y_pts)

        #scale
        minY,maxY = min(totalY),max(totalY)
        minD,maxD = min(totalDist),max(totalDist)

        totalY = [scale*(y-minY)/(maxY-minY) for y in totalY]
        totalDist = [scale*(d-minD)/(maxD-minD) for d in totalDist]

        # now search for all of the clusters whose neighbour has one or zero users in common
        # convert into one big list
        to_show = []
        for zooniverse_id in zooniverse_id_list:
            if zooniverse_id in self.closet_neighbours:
                for cluster_index,center in enumerate(self.clusterResults[zooniverse_id][0]):


                    y_pixel = center[1]

                    # find out about the nearest neighbour
                    neighbour,dist,overlap_l = self.closet_neighbours[zooniverse_id][cluster_index]

                    if len(overlap_l) == 1:
                        #normalize the y pixel height
                        y_pixel = scale*(y_pixel-minY)/(maxY-minY)
                        #normalize the distance
                        dist = scale*(dist-minD)/(maxD-minD)
                        z = sum([math.exp(-(Y-y_pixel)**2) for Y,d in zip(totalY,totalDist) if d <= dist])

                        z_max = sum([math.exp(-(Y-y_pixel)**2) for Y,d in zip(totalY,totalDist) if d <= scale])
                        to_show.append((z/z_max,zooniverse_id,center[:],neighbour[:],overlap_l[:]))

        to_show.sort(key = lambda x:x[0])
        shownPts = []
        for p,zooniverse_id,pt1,pt2,overlap in to_show:
            if (pt1 in shownPts) or (pt2 in shownPts):
                continue

            print overlap

            shownPts.append(pt1)
            shownPts.append(pt2)
            self.__display_image__(zooniverse_id)
            #plt.plot([pt1[0],pt2[0]],[pt1[1],pt2[1]],"o-",color="blue")
            #plt.plot([pt1[0],],[pt1[1],],"o",color="red")
            plt.plot([0,pt1[0]],[0,pt1[1]])
            plt.plot([1000,pt2[0]],[0,pt2[1]])
            plt.show()

    def __get_image_fname__(self,zooniverse_id):
        """
        get the path to JPG for this image - also download the image if necessary
        :param zooniverse_id:
        :return:
        """
        subject = self.subject_collection.find_one({"zooniverse_id": zooniverse_id})
        url = subject["location"]["standard"]

        slash_index = url.rfind("/")
        object_id = url[slash_index+1:]

        #print object_id

        if not(os.path.isfile(base_directory+"/Databases/"+self.project+"/images/"+object_id)):
            urllib.urlretrieve(url, base_directory+"/Databases/"+self.project+"/images/"+object_id)

        fname = base_directory+"/Databases/"+self.project+"/images/"+object_id

        return fname




    def __display_image__(self,zooniverse_id):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fname = self.__get_image_fname__(zooniverse_id)

            image_file = cbook.get_sample_data(fname)
            image = plt.imread(image_file)

            fig, ax = plt.subplots()
            im = ax.imshow(image)

    def __barnes_interpolation__(self,zooniverse_id_list):
        # sort of barnes interpolation
        totalY = []
        totalDist = []

        scale = 1

        Ypixel_range = np.arange(0,1,0.005)
        dist_range = np.arange(0,scale,0.01)
        X,Y = np.meshgrid(Ypixel_range,dist_range)

        Z = []

        # convert into one big list
        for zooniverse_id in zooniverse_id_list:
            if zooniverse_id in self.closet_neighbours:
                closest_neighbours = self.closet_neighbours[zooniverse_id]
                pt_l,pt_2,dist_l,overlap_size_l = zip(*closest_neighbours)
                X_pts,Y_pts = zip(*pt_l)

                totalDist.extend(dist_l)
                totalY.extend(Y_pts)

        #scale
        minY,maxY = min(totalY),max(totalY)
        minD,maxD = min(totalDist),max(totalDist)

        totalY = [scale*(y-minY)/(maxY-minY) for y in totalY]
        totalDist = [scale*(d-minD)/(maxD-minD) for d in totalDist]


        # now search for all of the clusters whose neighebour has one or zero users in common
        # convert into one big list
        P = []
        for zooniverse_id in zooniverse_id_list:
            if zooniverse_id in self.closet_neighbours:
                closest_neighbours = self.closet_neighbours[zooniverse_id]
                pt_l,pt_2,dist_l,overlap_size_l = zip(*closest_neighbours)
                for pts,dist,overlap_size in zip(pt_l,dist_l,overlap_size_l):
                    if overlap_size == 1:
                        y_pixel = scale*(pts[1]-minY)/(maxY-minY)
                        dist = scale*(dist-minD)/(maxD-minD)
                        z = sum([math.exp(-(Y-y_pixel)**2) for Y,d in zip(totalY,totalDist) if d <= dist])

                        z_max = sum([math.exp(-(Y-y_pixel)**2) for Y,d in zip(totalY,totalDist) if d <= 1])
                        P.append(z/z_max)
        print len(P)
        plt.hist(P,bins=20,normed=1,cumulative=True)
        plt.xlabel("Percentile for Clusters with |NN|=1")
        plt.show()



        # y_pixel = 0.1
        # Z = []
        # for dist in dist_range:
        #     Z.append(sum([math.exp(-(Y-y_pixel)**2) for Y,d in zip(totalY,totalDist) if d <= dist]))
        #
        # Z = [z/max(Z) for z in Z]
        # plt.plot(dist_range,Z)
        #
        # y_pixel = 0.9
        # Z = []
        # for dist in dist_range:
        #     Z.append(sum([math.exp(-(Y-y_pixel)**2) for Y,d in zip(totalY,totalDist) if d <= dist]))
        #
        # Z = [z/max(Z) for z in Z]
        # plt.plot(dist_range,Z)
        # plt.xlim((0,0.2))
        # plt.title("CDF of Nearest Neighbour Distance")
        # plt.legend(("Upper row", "Lower row"), "lower right")
        # plt.show()


    def __plot_cluster_size__(self,zooniverse_id_list):
        data = {}

        for zooniverse_id in zooniverse_id_list:
            if self.clusterResults[zooniverse_id] is not None:
                centers,pts,users = self.clusterResults[zooniverse_id]

                Y = [700-c[1] for c in centers]
                X = [len(p) for p in pts]

                plt.plot(X,Y,'.',color="blue")

                for x,y in zip(X,Y):
                    if not(x in data):
                        data[x] = [y]
                    else:
                        data[x].append(y)

        print pearsonr(X,Y)

        X = sorted(data.keys())
        Y = [np.mean(data[x]) for x in X]
        plt.plot(X,Y,'o-')
        plt.xlabel("Cluster Size")
        plt.ylabel("Height in Y-Pixels")
        plt.show()

    def __cluster_subject__(self,zooniverse_id,clustering_alg=None,correction_alg=None,fix_distinct_clusters = False):
        if clustering_alg is None:
            clustering_alg = self.clustering_alg
        assert clustering_alg is not None
        assert zooniverse_id in self.markings_list

        if self.markings_list[zooniverse_id] != []:
            # cluster results will be a 3-tuple containing a list of the cluster centers, a list of the points in each
            # cluster and a list of the users who marked each point

            fname = self.__get_image_fname__(zooniverse_id)

            self.clusterResults[zooniverse_id],time_to_cluster = clustering_alg(self.markings_list[zooniverse_id],self.markings_to_user[zooniverse_id])
            self.num_clusters = len(zip(*self.clusterResults[zooniverse_id]))
            assert type(self.num_clusters) == int

            # make sure we got a 3 tuple and since there was a least one marking, we should have at least one cluster
            # pruning will come later
            if not(len(self.clusterResults[zooniverse_id]) == 3):

                print self.clusterResults[zooniverse_id]
            assert len(self.clusterResults[zooniverse_id]) == 3
            assert self.clusterResults[zooniverse_id][0] != []
            # for cluster in self.clusterResults[zooniverse_id][1]:
            #     if len(cluster) >= 10:
            #         X,Y = zip(*cluster)
            #         print "**"
            #         print normaltest(X)
            #         print normaltest(Y)

            # print "-"

            # fix the cluster if desired
            if fix_distinct_clusters:
                self.clusterResults[zooniverse_id] = self.correction.__fix__(self.clusterResults[zooniverse_id])
                self.num_clusters = len(self.clusterResults[zooniverse_id][0])
                assert type(self.num_clusters) == int

            if correction_alg is not None:
                self.clusterResults[zooniverse_id] = correction_alg(self.clusterResults[zooniverse_id])
                self.num_clusters = len(self.clusterResults[zooniverse_id][0])
                assert type(self.num_clusters) == int
        else:
            self.clusterResults[zooniverse_id] = [],[],[]
            self.num_clusters = 0
            time_to_cluster = 0

        #print self.clusterResults
        return len(self.clusterResults[zooniverse_id][0]),time_to_cluster

    def __signal_ibcc__(self):
        self.__readin_users__()

        # run ibcc on each cluster to determine if it is a signal (an actual animal) or just noise
        # run ibcc on all of the subjects that have been processed (read in and clustered) so far
        # each cluster needs to have a universal index
        cluster_count = -1

        # need to give the ip addresses unique indices, so update ip_index after every subject
        ip_index = 0

        # needed for determining priors for IBCC
        real_animals = 0
        fake_animals = 0
        true_pos = 0
        false_neg = 0
        false_pos = 0
        true_neg = 0

        # intermediate holder variable
        # because ibcc needs indices to be nice and ordered with no gaps, we have to make two passes through the data
        to_ibcc = []

        self.global_index_list = {}

        for zooniverse_id in self.clusterResults:
            self.global_index_list[zooniverse_id] = []
            if self.clusterResults[zooniverse_id] is None:
                continue

            for cluster_center,cluster_markings,user_per_cluster in zip(*self.clusterResults[zooniverse_id]):
                # moving on to the next animal so increase counter
                # universal counter over all images
                cluster_count += 1

                # needed for determining priors for IBCC
                pos = 0
                neg = 0

                self.global_index_list[zooniverse_id].append(cluster_count) #(cluster_count,cluster_center[:]))

                # check whether or not each user marked this cluster
                for u in self.users_per_subject[zooniverse_id]:
                    # was this user logged in or not?
                    # if not, their user name will be an ip address
                    try:
                        i = self.ips_per_subject[zooniverse_id].index(u) + ip_index


                        if u in user_per_cluster:
                            to_ibcc.append((u,-i,cluster_count,1))
                            pos += 1
                        else:
                            to_ibcc.append((u,-i,cluster_count,0))
                            neg += 1
                    # ifNone a ValueError was thrown, the user name was not in the list of ip addresses
                    # and therefore, the user name was not an ip address, which means the user was logged in
                    except ValueError as e:

                        if u in user_per_cluster:
                            to_ibcc.append((u,index(self.all_users,u),cluster_count,1))
                            pos += 1
                        else:
                            to_ibcc.append((u,index(self.all_users,u),cluster_count,0))
                            neg += 1

                if pos > neg:
                    real_animals += 1

                    true_pos += pos/float(pos+neg)
                    false_neg += neg/float(pos+neg)
                else:
                    fake_animals += 1

                    false_pos += pos/float(pos+neg)
                    true_neg += neg/float(pos+neg)

            ip_index += len(self.ips_per_subject[zooniverse_id])

        # now run through again - this will make sure that all of the indices are ordered with no gaps
        # since the user list is created by reading through all the users, even those which haven't annotated
        # of the specific images we are currently looking at
        ibcc_user_list = []
        self.ibcc_users = {}

        for user,user_index,animal_index,found in to_ibcc:
            # can't use bisect or the indices will be out of order
            if not(user_index in ibcc_user_list):
                ibcc_user_list.append(user_index)
                self.ibcc_users[user] = len(ibcc_user_list)-1

        # write out the input file for IBCC
        with open(base_directory+"/Databases/"+self.project+"_ibcc.csv","wb") as f:
            f.write("a,b,c\n")
            for user,user_index,animal_index,found in to_ibcc:
                i = ibcc_user_list.index(user_index)
                f.write(str(i)+","+str(animal_index)+","+str(found)+"\n")

        # create the prior estimate and the default confusion matrix
        prior = real_animals/float(real_animals + fake_animals)
        confusion = [[max(int(true_neg),1),max(int(false_pos),1)],[max(int(false_neg),1),max(int(true_pos),1)]]

        # create the config file
        print "this is here"
        print base_directory+"/Databases/"+self.project+"_ibcc.py"
        with open(base_directory+"/Databases/"+self.project+"_ibcc.py","wb") as f:
            f.write("import numpy as np\n")
            f.write("scores = np.array([0,1])\n")
            f.write("nScores = len(scores)\n")
            f.write("nClasses = 2\n")
            f.write("inputFile = \""+base_directory+"/Databases/"+self.project+"_ibcc.csv\"\n")
            f.write("outputFile = \""+base_directory+"/Databases/"+self.project+"_signal.out\"\n")
            f.write("confMatFile = \""+base_directory+"/Databases/"+self.project+"_ibcc.mat\"\n")
            f.write("nu0 = np.array(["+str(max(int((1-prior)*100),1))+","+str(max(int(prior*100),1))+"])\n")
            f.write("alpha0 = np.array("+str(confusion)+")\n")

        # start by removing all temp files
        try:
            os.remove(base_directory+"/Databases/"+self.project+"_signal.out")
        except OSError:
            pass

        try:
            os.remove(base_directory+"/Databases/"+self.project+"_ibcc.mat")
        except OSError:
            pass

        try:
            os.remove(base_directory+"/Databases/"+self.project+"_ibcc.csv.dat")
        except OSError:
            pass

        # pickle.dump((big_subjectList,big_userList),open(base_directory+"/Databases/tempOut.pickle","wb"))
        ibcc.runIbcc(base_directory+"/Databases/"+self.project+"_ibcc.py")

    def __calc_correct_markings__(self,zooniverse_id):
        # return the local indices of the correct markings
        correct_pts = []
        cluster_centers = self.clusterResults[zooniverse_id][0]
        gold_pts = self.gold_data[zooniverse_id]

        # if either of these sets are empty, then by def'n we can't have any correct WRT this image
        if (cluster_centers == []) or (gold_pts == []):
            return correct_pts

        userToGold = [[] for i in range(len(gold_pts))]
        goldToUser = [[] for i in range(len(cluster_centers))]

        # find which gold standard pts, the user cluster pts are closest to
        for local_index, (x,y) in enumerate(cluster_centers):
            dist = [math.sqrt((float(pt["x"])-x)**2+(float(pt["y"])-y)**2) for pt in gold_pts]
            userToGold[dist.index(min(dist))].append(local_index)



        # find out which user pts each gold standard pt is closest to
        for gold_index, pt in enumerate(gold_pts):
            dist = [math.sqrt((float(pt["x"])-x)**2+(float(pt["y"])-y)**2) for (x,y) in cluster_centers]
            goldToUser[dist.index(min(dist))].append(gold_index)

        for local_index in range(len(cluster_centers)):
            if len(goldToUser[local_index]) >= 1:
                    correct_pts.append(local_index)

        return correct_pts

    def __display_false_positives__(self):
        for zooniverse_id in self.clusterResults:
            if self.clusterResults[zooniverse_id] is None:
                continue

            correct_pts = self.__calc_correct_markings__(zooniverse_id)

            cluster_centers = self.clusterResults[zooniverse_id][0]
            cluster_pts = self.clusterResults[zooniverse_id][1]

            if len(correct_pts) != len(cluster_centers):
                self.__display_image__(zooniverse_id)



                for index,(x,y) in enumerate(cluster_centers):
                    if index in correct_pts:
                        plt.plot(x,y,'o',color="red")
                    else:
                        plt.plot(x,y,'o',color="blue")

                for pts in cluster_pts:
                    for (x,y) in pts:
                        plt.plot(x,y,'.',color="yellow")

                plt.show()



    def __roc__(self,plot=False):
        correct_pts = []
        #print self.global_index_list

        # use the gold standard data to determine which of our points is correct
        for zooniverse_id, global_indices in self.global_index_list.items():

            gold_pts = self.gold_data[zooniverse_id]
            #print gold_pts
            # if either of these sets are empty, then by def'n we can't have any correct WRT this image
            if (global_indices == []) or (gold_pts == []):
                continue

            userToGold = [[] for i in range(len(gold_pts))]
            goldToUser = [[] for i in range(len(global_indices))]

            #global_cluster_indices,cluster_centers = zip(*user_pts)
            cluster_centers = self.clusterResults[zooniverse_id][0]


            # find which gold standard pts, the user cluster pts are closest to
            for local_index, (x,y) in enumerate(cluster_centers):
                dist = [math.sqrt((float(pt["x"])-x)**2+(float(pt["y"])-y)**2) for pt in gold_pts]
                userToGold[dist.index(min(dist))].append(local_index)



            # find out which user pts each gold standard pt is closest to
            for gold_index, pt in enumerate(gold_pts):
                dist = [math.sqrt((float(pt["x"])-x)**2+(float(pt["y"])-y)**2) for (x,y) in cluster_centers]
                goldToUser[dist.index(min(dist))].append(gold_index)



            for local_index,global_index in zip(range(len(cluster_centers)),global_indices):
                # which gold pt did this user pt map to?
                # gold_index = [i for i,pts in enumerate(userToGold) if local_index in pts][0]
                # print [i for i,pts in enumerate(userToGold) if local_index in pts]
                # did this gold pt also map to the user pt?
                # look at all of the
                # for g in gold:
                #    if g in goldToUser[local_index]:
                #        correct_pts.append(global_index)
                #        break
                if len(goldToUser[local_index]) >= 1:
                    correct_pts.append(global_index)

        truePos = []
        falsePos = []
        with open(base_directory+"/Databases/"+self.project+"_signal.out","rb") as f:
            for ii,l in enumerate(f.readlines()):
                a,b,prob = l[:-1].split(" ")

                if ii in correct_pts:
                    truePos.append(float(prob))
                else:
                    falsePos.append(float(prob))

        alphas = truePos[:]
        alphas.extend(falsePos)
        alphas.sort()
        X = []
        Y = []
        for a in alphas:
            X.append(len([x for x in falsePos if x >= a]))
            Y.append(len([y for y in truePos if y >= a]))

        if plot:
            plt.plot(X,Y)
            plt.xlabel("False Positive Count")
            plt.ylabel("True Positive Count")
            plt.show()

        return X,Y

    def __outliers__(self,zooniverse_id):
        for (Cx,Cy), markings in zip(self.clusterResults[zooniverse_id][0],self.clusterResults[zooniverse_id][1]):
            distances = []
            if len(markings) == 1:
                continue
            for (x,y) in markings:
                dist = math.sqrt((x-Cx)**2+(y-Cy)**2)
                distances.append(dist)

            ratio =  max(distances)/np.mean(distances)



            if ratio > 4:
                print ratio
                self.__display_image__(zooniverse_id)
                X,Y = zip(*markings)

                plt.plot(X,Y,'.')

                plt.show()


    def __process_signal__(self):
        self.signal_probability = []

        with open(base_directory+"/Databases/"+self.project+"_signal.out","rb") as f:
            results = csv.reader(f, delimiter=' ')

            for row in results:
                self.signal_probability.append(float(row[2]))

    def __get_subjects_per_site__(self,zooniverse_id):
        pass

    def __display__markings__(self, zooniverse_id):
        assert zooniverse_id in self.clusterResults
        subject = self.subject_collection.find_one({"zooniverse_id": zooniverse_id})
        zooniverse_id = subject["zooniverse_id"]
        print zooniverse_id
        url = subject["location"]["standard"]

        slash_index = url.rfind("/")
        object_id = url[slash_index+1:]

        if not(os.path.isfile(base_directory+"/Databases/"+self.project+"/images/"+object_id)):
            urllib.urlretrieve(url, base_directory+"/Databases/"+self.project+"/images/"+object_id)

        image_file = cbook.get_sample_data(base_directory+"/Databases/"+self.project+"/images/"+object_id)
        image = plt.imread(image_file)

        fig, ax = plt.subplots()
        im = ax.imshow(image)

        for (x, y), pts, users in zip(*self.clusterResults[zooniverse_id]):
            plt.plot([x, ], [y, ], 'o', color="red")


        plt.show()
        plt.close()

    def __display_raw_markings__(self,zooniverse_id):
        self.__display_image__(zooniverse_id)
        print "Num users: " + str(len(self.users_per_subject[zooniverse_id]))
        X,Y = zip(*self.markings_list[zooniverse_id])
        plt.plot(X,Y,'.')
        plt.xlim((0,1000))
        plt.ylim((563,0))


        plt.show()
        plt.close()



    def __save_raw_markings__(self,zooniverse_id):
        self.__display_image__(zooniverse_id)
        print "Num users: " + str(len(self.users_per_subject[zooniverse_id]))
        X,Y = zip(*self.markings_list[zooniverse_id])
        plt.plot(X,Y,'.')
        plt.xlim((0,1000))
        plt.ylim((563,0))
        plt.xticks([])
        plt.yticks([])
        plt.savefig(base_directory+"/Databases/"+self.project+"/examples/"+zooniverse_id+".pdf",bbox_inches='tight')
        plt.close()

    # def __display_image__(self,zooniverse_id):
    #     #assert zooniverse_id in self.clusterResults
    #     subject = self.subject_collection.find_one({"zooniverse_id": zooniverse_id})
    #     zooniverse_id = subject["zooniverse_id"]
    #     #print zooniverse_id
    #     url = subject["location"]["standard"]
    #
    #     slash_index = url.rfind("/")
    #     object_id = url[slash_index+1:]
    #
    #     if not(os.path.isfile(base_directory+"/Databases/"+self.project+"/images/"+object_id)):
    #         urllib.urlretrieve(url, base_directory+"/Databases/"+self.project+"/images/"+object_id)
    #
    #     image_file = cbook.get_sample_data(base_directory+"/Databases/"+self.project+"/images/"+object_id)
    #     image = plt.imread(image_file)
    #
    #     fig, ax = plt.subplots()
    #     im = ax.imshow(image)
    #     plt.xlim((0,1000))
    #     plt.ylim((563,0))

    def __soy_it__(self,zooniverse_id):
        self.__display_image__(zooniverse_id)
        gold_markings = self.gold_data[zooniverse_id]
        # start by matching each of the user output images to the gold standard
        userToGold = [[] for i in range(len(gold_markings))]
        goldToUser = [[] for i in range(len(zip(*self.clusterResults[zooniverse_id])))]
        #print len(gold_markings)
        #print len(zip(*self.clusterResults[zooniverse_id]))
        for marking_index,((x, y), pts, users) in enumerate(zip(*self.clusterResults[zooniverse_id])):
            dist = [math.sqrt((pt["x"]-x)**2+(pt["y"]-y)**2) for pt in gold_markings]
            userToGold[dist.index(min(dist))].append(marking_index)

        for gold_index, pt in enumerate(gold_markings):
            dist = [math.sqrt((pt["x"]-x)**2+(pt["y"]-y)**2) for (x,y),pts,users in zip(*self.clusterResults[zooniverse_id])]
            goldToUser[dist.index(min(dist))].append(gold_index)

        for marking_index, pt in enumerate(gold_markings):
            if len(userToGold[marking_index]) == 0:
                plt.plot(pt["x"], pt["y"], 'o', color="red")
            elif len(userToGold[marking_index]) > 1:
                plt.plot(pt["x"], pt["y"], 'o', color="blue")


        for marking_index,((x, y), pts, users) in enumerate(zip(*self.clusterResults[zooniverse_id])):
            if len(goldToUser[marking_index]) == 1:
                plt.plot([x, ], [y, ], 'o', color="yellow")
            elif len(goldToUser[marking_index]) == 0:
                plt.plot([x, ], [y, ], 'o', color="grey")
            else:
                plt.plot([x, ], [y, ], 'o', color="green")
                # print "===---"
                # for index in goldToUser[marking_index]:
                #     print gold_markings[index]


        # for marking_index,((x, y), pts, users) in enumerate(zip(*self.clusterResults[zooniverse_id])):
        #     #find the match
        #     for gold_index, (x2,y2) in enumerate(gold_markings):
        #         if (marking_index in userToGold[gold_index]) and (gold_index in goldToUser[marking_index]):
        #             plt.plot((x,x2),(y,y2),"-",color="blue")
        #         elif marking_index in userToGold[gold_index]:
        #             plt.plot((x,x2),(y,y2),"-",color="green")
        #         elif gold_index in goldToUser[marking_index]:
        #             plt.plot((x,x2),(y,y2),"-",color="red")

        #for (x, y) in gold_markings:
        #    plt.plot([x, ], [y, ], 'o', color="red")

        #ROI = [(0, 1050),(0, 370),(1920, 370),(1920, 1050)]
        #print zip(*ROI)
        #X = [x/1.92 for x,y in ROI]
        #Y = [y/1.92 for x,y in ROI]
        #print X,Y
        #plt.plot(X,Y,"o-",color="red")

        plt.show()


    def __display_signal_noise(self):
        for ii,zooniverse_id in enumerate(self.clusterResults):
            print zooniverse_id
            subject = self.subject_collection.find_one({"zooniverse_id":zooniverse_id})
            zooniverse_id = subject["zooniverse_id"]
            url = subject["location"]["standard"]

            slash_index = url.rfind("/")
            object_id = url[slash_index+1:]

            if not(os.path.isfile(base_directory+"/Databases/condors/images/"+object_id)):
                urllib.urlretrieve (url, base_directory+"/Databases/condors/images/"+object_id)

            image_file = cbook.get_sample_data(base_directory+"/Databases/condors/images/"+object_id)
            image = plt.imread(image_file)

            fig, ax = plt.subplots()
            im = ax.imshow(image)

            for center,animal_index,users_l,user_count in results_dict[zooniverse_id]:
                if ibcc_v[animal_index] >= 0.5:
                    print center[0],center[1],1
                    plt.plot([center[0],],[center[1],],'o',color="green")
                else:
                    print center[0],center[1],0
                    plt.plot([center[0],],[center[1],],'o',color="red")

            plt.show()
            plt.close()

    def __load_dimensions__(self,zooniverse_id,subject=None):
        pass

    def __get_status__(self,zooniverse_id):
        return self.subject_collection.find_one({"zooniverse_id":zooniverse_id})["state"]

    def __load_roi__(self,zooniverse_id):
        assert False

    def __load_gold_standard__(self,zooniverse_id):
        # have we already encountered this subject?
        if os.path.isfile(base_directory+"/Databases/"+self.project+"/"+zooniverse_id+"_gold.pickle"):
            self.gold_data[zooniverse_id] = pickle.load(open(base_directory+"/Databases/"+self.project+"/"+zooniverse_id+"_gold.pickle","rb"))
        else:
            self.gold_data[zooniverse_id] = []
            classification = self.classification_collection.find_one({"subjects.zooniverse_id":zooniverse_id,"user_name":self.expert})

            for pt, animal_type in self.tools.__list_markings__(classification):
                marking = {"x":pt[0],"y":pt[1]}
                self.gold_data[zooniverse_id].append(marking)

            pickle.dump(self.gold_data[zooniverse_id],open(base_directory+"/Databases/"+self.project+"/"+zooniverse_id+"_gold.pickle","wb"))

    def __accuracy__(self,zooniverse_id):
        """
        Calculate the accuracy for the given zooniverse_id, clustering needs to have already been done
        and gold standard data needs to have already been read in
        :param zooniverse_id:
        :return:
        """
        gold_markings = self.gold_data[zooniverse_id]
        userToGold = [[] for i in range(len(gold_markings))]
        goldToUser = [[] for i in range(len(zip(*self.clusterResults[zooniverse_id])))]

        for marking_index,((x, y), pts, users) in enumerate(zip(*self.clusterResults[zooniverse_id])):
            try:
                dist = [math.sqrt((gold["x"]-x)**2+(gold["y"]-y)**2) for gold in gold_markings]
                userToGold[dist.index(min(dist))].append(marking_index)
            except ValueError:
                #print zooniverse_id
                #print gold_markings
                #print self.clusterResults[zooniverse_id]
                print "Empty gold standard: " + zooniverse_id
                return 0

        for gold_index, gold in enumerate(gold_markings):
            try:
                dist = [math.sqrt((gold["x"]-x)**2+(gold["y"]-y)**2) for (x,y),pts,users in zip(*self.clusterResults[zooniverse_id])]
                goldToUser[dist.index(min(dist))].append(gold_index)
            except ValueError:
                print "Empty user clusters: " + zooniverse_id
                return 0

        num_match = len([x for x in userToGold if len(x) > 0])
        return num_match
        #print userToGold
        lower_bound = num_match/float(len(userToGold))
        additional = len([x for x in goldToUser if len(x) == 0])

        could_have_found = 0
        missed = 0

        #which penguins have we missed?
        missedPenguins = [i for i in range(len(gold_markings)) if userToGold[i] == []]
        # find which are the closest penguins we found which correspond to these penguins
        for i in missedPenguins:
            for j in range(len(goldToUser)):
                try:
                    goldToUser[j].index(i)
                    break
                except ValueError:
                    pass

            goldToUser[j].index(i)
            #which gold penguin did j map to?
            for ii in range(len(gold_markings)):
                try:
                    userToGold[ii].index(j)
                    break
                except ValueError:
                    pass

            userToGold[ii].index(j)
            x_i,y_i = gold_markings[i]
            x_ii,y_ii = gold_markings[ii]
            pts = zip(*self.clusterResults[zooniverse_id])[j][1]
            # are these points closer to i or ii?
            dist_i = [math.sqrt((x-x_i)**2+(y-y_i)**2) for (x,y) in pts]
            dist_ii = [math.sqrt((x-x_ii)**2+(y-y_ii)**2) for (x,y) in pts]

            close_to_i = sum([1 for (di,dii) in zip(dist_i,dist_ii) if di < dii])
            missed += 1
            if close_to_i > 0:
                could_have_found += 1
            #print "** " +str((close_to_ii,len(pts)))
        #print (additional,len(userToGold))
        #print "\t"+str((lower_bound,(num_match+additional)/float(len(userToGold)+additional)))

        return lower_bound,could_have_found,missed

    def __find_correct__(self,zooniverse_id,gold_markings):
        # find all one to one mappings, in the case where we have multiple markings, take the closest to the
        # gold standard
        goldToUser = [[] for i in range(len(zip(*self.clusterResults[zooniverse_id])))]

        for gold_index, (Gx,Gy) in enumerate(gold_markings):
            dist = [math.sqrt((Gx-x)**2+(Gy-y)**2) for (x,y),pts,users in zip(*self.clusterResults[zooniverse_id])]
            goldToUser[dist.index(min(dist))].append(gold_index)

        self.correct_clusters[zooniverse_id] =  [i for i in range(len(zip(*self.clusterResults[zooniverse_id]))) if goldToUser[i] != []]
        return [i for i in range(len(zip(*self.clusterResults[zooniverse_id]))) if goldToUser[i] != []]

    def __user_accuracy__(self,user_id):
        r = []

        for zooniverse_id,clusters_index_list in self.correct_clusters.items():
            if not(user_id in self.users_per_subject[zooniverse_id]):
                continue

            clusters = zip(*self.clusterResults[zooniverse_id])
            #how many of these clusters did this user mark?
            accuracy_count = 0
            for i in clusters_index_list:
                if user_id in clusters[i][2]:
                    accuracy_count += 1

            r.append(accuracy_count/float(len(clusters_index_list)))

        return np.mean(r)

    def __relative_sizes__(self,zooniverse_id,gold_markings):
        correct = self.__find_correct__(zooniverse_id,gold_markings)
        not_correct = [i for i in range(len(zip(*self.clusterResults[zooniverse_id]))) if not(i in correct)]

        X = []
        Y = []

        self.__find_closest_neighbour__(zooniverse_id)
        for i in range(self.num_clusters):
            if i in not_correct:
                if len(self.closest_neighbours[zooniverse_id][i][3]) == 1:
                    j = self.closest_neighbours[zooniverse_id][i][0]

                    size_i = len(zip(*self.clusterResults[zooniverse_id])[i][1])
                    size_j = len(zip(*self.clusterResults[zooniverse_id])[j][1])

                    X.append(max(size_i,size_j))
                    Y.append(min(size_i,size_j))
        return X,Y

    def __overlap__(self,zooniverse_id,gold_markings):
        correct = self.__find_correct__(zooniverse_id,gold_markings)
        not_correct = [i for i in range(len(zip(*self.clusterResults[zooniverse_id]))) if not(i in correct)]

        to_return = []
        to_return2 = []


        self.__find_closest_neighbour__(zooniverse_id)
        for i in range(self.num_clusters):
            if (i in not_correct) and (len(self.closest_neighbours[zooniverse_id][i][3]) == 1):
                to_return2.extend(self.closest_neighbours[zooniverse_id][i][3])
        return to_return2





    def __off_by_one__(self,display=False):
        # return the global indices of all clusters which have only one user in common (obviously from the same image)
        # and the image ID and the local indices - so we can tell which users saw
        one_overlap = []
        for zooniverse_id in self.clusterResults:
            one = self.__find_closest__(zooniverse_id,user_threshold=1)
            # convert from local to global indices
            global_indices = self.global_index_list[zooniverse_id]
            for (i,j,overlap) in one:
                # we should have already dealt with clusters where the overlap is zero
                assert len(overlap) == 1
                global_i = global_indices[i]
                global_j = global_indices[j]
                one_overlap.append((zooniverse_id,global_i,global_j,i,j))

                if display:
                    self.__display_image__(zooniverse_id)
                    x1,y1 = self.clusterResults[zooniverse_id][0][i]
                    plt.plot([x1],[y1],"o",color="red")
                    x2,y2 = self.clusterResults[zooniverse_id][0][j]
                    plt.plot([x2],[y2],".",color="blue")
                    print len(self.clusterResults[zooniverse_id][1][i]),len(self.clusterResults[zooniverse_id][1][j])
                    plt.show()

        return one_overlap

    def __relative_confusion__(self,t):
        # what is the relative probability that we have two distinct clusters as opposed to one?
        if self.ibcc_confusion is None:
            self.ibcc_confusion = []
            with open("/Users/greg/Databases/penguin_ibcc.mat","rb") as f:
                for l in f.readlines():
                    probs = l[:-1].split(" ")
                    probs = [float(p) for p in probs]
                    self.ibcc_confusion.append(probs[:])

        zooniverse_id = t[0]
        i = t[3]
        j = t[4]
        all_users = self.users_per_subject[zooniverse_id]
        users_i = self.clusterResults[zooniverse_id][2][i]
        users_j = self.clusterResults[zooniverse_id][2][j]

        ibcc_user_indices = [self.ibcc_users[u] for u in all_users]

        # 0 or 1 for whether or not each user tagged the first cluster
        annotated_i = [1 if u in users_i else 0 for u in all_users]
        annotated_j = [1 if u in users_j else 0 for u in all_users]

        # what is "probability"
        prob_i = 1

        for index, annotated in zip(ibcc_user_indices,annotated_i):
            prob_i = prob_i * self.ibcc_confusion[index][2+annotated]

        prob_j = 1
        for index, annotated in zip(ibcc_user_indices,annotated_j):
            prob_j = prob_j * self.ibcc_confusion[index][2+annotated]

        prob_ij = 1
        for index, a1,a2 in zip(ibcc_user_indices,annotated_i,annotated_j):
            prob_ij = prob_ij * self.ibcc_confusion[index][2+max(a1,a2)]

        print sum(annotated_i),sum(annotated_j)
        print prob_ij/(prob_i*prob_j)


    # def __off_by_one__(self,zooniverse_id,gold_markings):
    #     correct = self.__find_correct__(zooniverse_id,gold_markings)
    #     not_correct = [i for i in range(len(zip(*self.clusterResults[zooniverse_id]))) if not(i in correct)]
    #
    #     to_return = []
    #     to_return2 = []
    #
    #     self.__find_closest_neighbour__(zooniverse_id,to_skip=not_correct)
    #     for i in range(self.num_clusters):
    #         if i in not_correct:
    #             continue
    #
    #         to_return.append((len(self.closest_neighbours[zooniverse_id][i][3])))
    #
    #
    #     self.__find_closest_neighbour__(zooniverse_id)
    #     for i in range(self.num_clusters):
    #         if i in not_correct:
    #             to_return2.append((len(self.closest_neighbours[zooniverse_id][i][3])))
    #     return to_return,to_return2



        # userToGold = [[] for i in range(len(gold_markings))]
        # goldToUser = [[] for i in range(len(zip(*self.clusterResults[zooniverse_id])))]
        # #print len(goldToUser)
        # #print len(userToGold)
        # for marking_index,((x, y), pts, users) in enumerate(zip(*self.clusterResults[zooniverse_id])):
        #     dist = [math.sqrt((Gx-x)**2+(Gy-y)**2) for (Gx,Gy) in gold_markings]
        #     userToGold[dist.index(min(dist))].append(marking_index)
        #
        # for gold_index, (Gx,Gy) in enumerate(gold_markings):
        #     dist = [math.sqrt((Gx-x)**2+(Gy-y)**2) for (x,y),pts,users in zip(*self.clusterResults[zooniverse_id])]
        #     goldToUser[dist.index(min(dist))].append(gold_index)
        #
        # # which user penguins do not have a corresponding gold standard penguin - i.e., a false positive
        # false_positive = [j for j,closest in enumerate(goldToUser) if closest == []]
        # if false_positive == []:
        #     return 0
        # print "^^^^^"
        # for j in false_positive:
        #     for ii in range(len(gold_markings)):
        #         try:
        #             userToGold[ii].index(j)
        #             break
        #         except ValueError:
        #             pass
        #     if len(userToGold[ii]) ==   2:
        #         print "***"
        #         print userToGold[ii]
        #         print self.closest_neighbours[zooniverse_id][userToGold[ii][0]][0],len(self.closest_neighbours[zooniverse_id][userToGold[ii][0]][3])
        #         print self.closest_neighbours[zooniverse_id][userToGold[ii][1]][0],len(self.closest_neighbours[zooniverse_id][userToGold[ii][1]][3])
        #         print "--/"

        # return len(false_positive)




    def __precision__(self,zooniverse_id,gold_markings):
        # start by matching each of the user output images to the gold standard
        userToGold = [[] for i in range(len(gold_markings))]
        goldToUser = [[] for i in range(len(zip(*self.clusterResults[zooniverse_id])))]

        for marking_index,((x, y), pts, users) in enumerate(zip(*self.clusterResults[zooniverse_id])):
            dist = [math.sqrt((Gx-x)**2+(Gy-y)**2) for (Gx,Gy) in gold_markings]
            userToGold[dist.index(min(dist))].append(marking_index)

        for gold_index, (Gx,Gy) in enumerate(gold_markings):
            dist = [math.sqrt((Gx-x)**2+(Gy-y)**2) for (x,y),pts,users in zip(*self.clusterResults[zooniverse_id])]
            goldToUser[dist.index(min(dist))].append(gold_index)

        match1 = len([g for g in goldToUser if len(g) == 1])
        missed2 = len([g for g in userToGold if len(g) == 0])

        for marking_index,((x, y), pts, users) in enumerate(zip(*self.clusterResults[zooniverse_id])):
            for gold_index, (Gx,Gy) in enumerate(gold_markings):
                if (goldToUser[marking_index] == [gold_index]) and (userToGold[gold_index] == [marking_index]) and (len(pts) >= 10):
                    X,Y = zip(*pts)
                    print normaltest(X)[1], normaltest(Y)[1]


        #print missed,missed2
        #print missed,missed2

    def __display_nearest_neighbours__(self,zooniverse_id):
        if self.clusterResults[zooniverse_id] == None:
            return

        self.__display_image__(zooniverse_id)

        centers,pts,users = self.clusterResults[zooniverse_id]
        neighbours = multiClickCorrect.MultiClickCorrect().__find_closest__(centers,users)
        for c1_index,c2_index,users in neighbours:
            x1,y1 = centers[c1_index]
            x2,y2 = centers[c2_index]
            print (x1,y1),(x2,y2),len(users)

            if len(users) == 1:
                plt.plot([x1,x2],[y1,y2],"o-",color="red")
            else:
                plt.plot([x1,x2],[y1,y2],"o-",color="blue")

        plt.show()

    def __num_gold_clusters__(self,zooniverse_id):
        return len(self.gold_data[zooniverse_id])

    def __readin_subject__(self, zooniverse_id,read_in_gold=False):
        subject = self.subject_collection.find_one({"zooniverse_id":zooniverse_id})
        #print subject["location"]["standard"]
        # records relating to the individual annotations
        # first - the actual XY markings, then what species are associated with the annotations,
        # then who made each marking
        self.markings_list[zooniverse_id] = []
        self.subjects_per_user[zooniverse_id] = []
        self.what_list[zooniverse_id] = []
        self.markings_to_user[zooniverse_id] = []
        # keep track of which users annotated this. Users per subject will contain all users - ip_addresses
        # will contain just those users who were not logged in so we only have the ip address to identify them
        # we need to deal with non-logged in users slightly differently
        self.ips_per_subject[zooniverse_id] = []
        self.users_per_subject[zooniverse_id] = []

        if read_in_gold and not(zooniverse_id in self.gold_data):
            self.__load_gold_standard__(zooniverse_id)

        #roi = self.__load_roi__(zooniverse_id)

        if os.path.isfile(base_directory+"/Databases/"+self.project+"/"+zooniverse_id+".pickle"):
            mongo_results = pickle.load(open(base_directory+"/Databases/"+self.project+"/"+zooniverse_id+".pickle","rb"))
        else:
            mongo_results = list(self.classification_collection.find({"subjects.zooniverse_id":zooniverse_id}))
            pickle.dump(mongo_results,open(base_directory+"/Databases/"+self.project+"/"+zooniverse_id+".pickle","wb"))

        for user_index, classification in enumerate(mongo_results):
            # get the name of this user
            if "user_name" in classification:
                user = classification["user_name"]
            else:
                user = classification["user_ip"]

                if not(user == self.expert):
                    self.ips_per_subject[zooniverse_id].append(user)

            if user == self.expert:
                continue

            # check to see if we have already encountered this subject/user pairing
            # due to some double classification errors
            if user in self.users_per_subject[zooniverse_id]:
                continue

            self.users_per_subject[zooniverse_id].append(user)

            if not(user in self.subjects_per_user):
                self.subjects_per_user[user] = [zooniverse_id]
            else:
                self.subjects_per_user[user].extend(zooniverse_id)

            # read in all of the markings this user made - which might be none

            for pt, animal_type in self.tools.__list_markings__(classification):
                if not(animal_type in self.to_skip):
                    self.markings_list[zooniverse_id].append(pt)
                    # print annotation_list
                    self.markings_to_user[zooniverse_id].append(user)
                    self.what_list[zooniverse_id].append(animal_type)


