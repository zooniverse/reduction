__author__ = 'greg'
import bisect
import math
import ouroboros_api
import abc
import numpy as np
import os
import re
import ibcc
import csv
import matplotlib.pyplot as plt
import random
import socket
import warnings
import scipy
from shapely.geometry import Polygon
# import panoptes_api

cnames = {
'aliceblue':            '#F0F8FF',
'antiquewhite':         '#FAEBD7',
'aqua':                 '#00FFFF',
'aquamarine':           '#7FFFD4',
'azure':                '#F0FFFF',
'beige':                '#F5F5DC',
'bisque':               '#FFE4C4',
'black':                '#000000',
'blanchedalmond':       '#FFEBCD',
'blue':                 '#0000FF',
'blueviolet':           '#8A2BE2',
'brown':                '#A52A2A',
'burlywood':            '#DEB887',
'cadetblue':            '#5F9EA0',
'chartreuse':           '#7FFF00',
'chocolate':            '#D2691E',
'coral':                '#FF7F50',
'cornflowerblue':       '#6495ED',
'cornsilk':             '#FFF8DC',
'crimson':              '#DC143C',
'cyan':                 '#00FFFF',
'darkblue':             '#00008B',
'darkcyan':             '#008B8B',
'darkgoldenrod':        '#B8860B',
'darkgray':             '#A9A9A9',
'darkgreen':            '#006400',
'darkkhaki':            '#BDB76B',
'darkmagenta':          '#8B008B',
'darkolivegreen':       '#556B2F',
'darkorange':           '#FF8C00',
'darkorchid':           '#9932CC',
'darkred':              '#8B0000',
'darksalmon':           '#E9967A',
'darkseagreen':         '#8FBC8F',
'darkslateblue':        '#483D8B',
'darkslategray':        '#2F4F4F',
'darkturquoise':        '#00CED1',
'darkviolet':           '#9400D3',
'deeppink':             '#FF1493',
'deepskyblue':          '#00BFFF',
'dimgray':              '#696969',
'dodgerblue':           '#1E90FF',
'firebrick':            '#B22222',
'floralwhite':          '#FFFAF0',
'forestgreen':          '#228B22',
'fuchsia':              '#FF00FF',
'gainsboro':            '#DCDCDC',
'ghostwhite':           '#F8F8FF',
'gold':                 '#FFD700',
'goldenrod':            '#DAA520',
'gray':                 '#808080',
'green':                '#008000',
'greenyellow':          '#ADFF2F',
'honeydew':             '#F0FFF0',
'hotpink':              '#FF69B4',
'indianred':            '#CD5C5C',
'indigo':               '#4B0082',
'ivory':                '#FFFFF0',
'khaki':                '#F0E68C',
'lavender':             '#E6E6FA',
'lavenderblush':        '#FFF0F5',
'lawngreen':            '#7CFC00',
'lemonchiffon':         '#FFFACD',
'lightblue':            '#ADD8E6',
'lightcoral':           '#F08080',
'lightcyan':            '#E0FFFF',
'lightgoldenrodyellow': '#FAFAD2',
'lightgreen':           '#90EE90',
'lightgray':            '#D3D3D3',
'lightpink':            '#FFB6C1',
'lightsalmon':          '#FFA07A',
'lightseagreen':        '#20B2AA',
'lightskyblue':         '#87CEFA',
'lightslategray':       '#778899',
'lightsteelblue':       '#B0C4DE',
'lightyellow':          '#FFFFE0',
'lime':                 '#00FF00',
'limegreen':            '#32CD32',
'linen':                '#FAF0E6',
'magenta':              '#FF00FF',
'maroon':               '#800000',
'mediumaquamarine':     '#66CDAA',
'mediumblue':           '#0000CD',
'mediumorchid':         '#BA55D3',
'mediumpurple':         '#9370DB',
'mediumseagreen':       '#3CB371',
'mediumslateblue':      '#7B68EE',
'mediumspringgreen':    '#00FA9A',
'mediumturquoise':      '#48D1CC',
'mediumvioletred':      '#C71585',
'midnightblue':         '#191970',
'mintcream':            '#F5FFFA',
'mistyrose':            '#FFE4E1',
'moccasin':             '#FFE4B5',
'navajowhite':          '#FFDEAD',
'navy':                 '#000080',
'oldlace':              '#FDF5E6',
'olive':                '#808000',
'olivedrab':            '#6B8E23',
'orange':               '#FFA500',
'orangered':            '#FF4500',
'orchid':               '#DA70D6',
'palegoldenrod':        '#EEE8AA',
'palegreen':            '#98FB98',
'paleturquoise':        '#AFEEEE',
'palevioletred':        '#DB7093',
'papayawhip':           '#FFEFD5',
'peachpuff':            '#FFDAB9',
'peru':                 '#CD853F',
'pink':                 '#FFC0CB',
'plum':                 '#DDA0DD',
'powderblue':           '#B0E0E6',
'purple':               '#800080',
'red':                  '#FF0000',
'rosybrown':            '#BC8F8F',
'royalblue':            '#4169E1',
'saddlebrown':          '#8B4513',
'salmon':               '#FA8072',
'sandybrown':           '#FAA460',
'seagreen':             '#2E8B57',
'seashell':             '#FFF5EE',
'sienna':               '#A0522D',
'silver':               '#C0C0C0',
'skyblue':              '#87CEEB',
'slateblue':            '#6A5ACD',
'slategray':            '#708090',
'snow':                 '#FFFAFA',
'springgreen':          '#00FF7F',
'steelblue':            '#4682B4',
'tan':                  '#D2B48C',
'teal':                 '#008080',
'thistle':              '#D8BFD8',
'tomato':               '#FF6347',
'turquoise':            '#40E0D0',
'violet':               '#EE82EE',
'wheat':                '#F5DEB3',
'white':                '#FFFFFF',
'whitesmoke':           '#F5F5F5',
'yellow':               '#FFFF00',
'yellowgreen':          '#9ACD32'}
colour_list = cnames.keys()

def index(a, x):
    'Locate the leftmost value exactly equal to x'
    i = bisect.bisect_left(a, x)
    if i != len(a) and a[i] == x:
        return i
    raise ValueError


# code from
# http://stackoverflow.com/questions/2130016/splitting-a-list-of-arbitrary-size-into-only-roughly-n-equal-parts
def chunk_it(seq, num):
    avg = len(seq) / float(num)
    out = []
    last = 0.0

    while last < len(seq):
        out.append(dict(seq[int(last):int(last + avg)]))
        last += avg

    return out


def line_picker(line, mouseevent):
    """
    code copied from
    http://matplotlib.org/examples/event_handling/pick_event_demo.html
    find the points within a certain distance from the mouseclick in
    data coords and attach some extra attributes, pickx and picky
    which are the data points that were picked
    """
    if mouseevent.xdata is None: return False, dict()
    xdata = line.get_xdata()
    ydata = line.get_ydata()
    maxd = 0.05
    d = np.sqrt((xdata-mouseevent.xdata)**2. + (ydata-mouseevent.ydata)**2.)

    ind = np.nonzero(np.less_equal(d, maxd))
    if len(ind):
        pickx = np.take(xdata, ind)
        picky = np.take(ydata, ind)
        props = dict(ind=ind, pickx=pickx, picky=picky)
        return True, props
    else:
        return False, dict()

def onpick(clustering_alg):
    assert isinstance(clustering_alg,Cluster)
    def onpick2(event):
        """
        again - copied from
        http://matplotlib.org/examples/event_handling/pick_event_demo.html
        :param event:
        :return:
        """

        artist = event.artist
        x, y = artist.get_xdata(), artist.get_ydata()
        ind = event.ind
        clustering_alg.x_roc = float(x[ind[0]])
        clustering_alg.y_roc = float(y[ind[0]])

        plt.close()

    return onpick2

class Cluster:
    __metaclass__ = abc.ABCMeta

    def __init__(self, project_api,min_cluster_size=1,mapping=None):
        """
        :param project_api: how to talk to whatever project we are clustering for (Panoptes/Ouroboros shouldn't matter)
        :param min_cluster_size: minimum number of points in a cluster to not be considered noise
        :return:
        """
        # assert isinstance(project_api,panoptes_api.PanoptesAPI)
        self.project_api = project_api
        self.min_cluster_size = min_cluster_size
        self.clusterResults = {}
        self.goldResults = {}

        self.correct_pts = {}
        # for gold points which we have missed
        self.missed_pts = {}
        # for false positives (according to the gold standard)
        self.false_positives = {}
        # we also need to map between user points and gold points
        self.user_gold_mapping = {}

        # the distance between a user cluster and what we believe to do the corresponding goal standard point
        self.user_gold_distance = {}

        # the list of every subject we have processed so far - a set just in case we accidentally process the same
        # one twice. Probably should never happen but just in case
        self.processed_subjects = set([])

        # needed for when we want use ibcc for stuff
        current_directory = os.getcwd()
        slash_indices = [m.start() for m in re.finditer('/', current_directory)]
        self.base_directory = current_directory[:slash_indices[2]+1]

        # for creating names of ibcc output files
        self.alg = None

        self.x_roc = None
        self.y_roc = None

        self.algorithm_name = None

        self.mapping = mapping

    def __compare_against__(self,other_clustering,subject_id):
        assert isinstance(other_clustering,Cluster)
        assert subject_id in other_clustering.clusterResults

        for ii,our_cluster in enumerate(self.clusterResults[subject_id][1]):
            overlap_count = 0
            args = []
            kwargs = []
            for their_cluster in other_clustering.clusterResults[subject_id][1]:
                overlap = [pt for pt in our_cluster if pt in their_cluster]
                if overlap != []:
                    x,y = zip(*overlap)
                    args.append([x,y,'o'])
                    kwargs.append({"color":colour_list[overlap_count]})

                    # are there any points in their cluster which are not in our cluster?
                    not_in = [pt for pt in their_cluster if not(pt in our_cluster)]
                    if not_in != []:
                        x,y = zip(*not_in)
                        args.append([x,y,'>'])
                        kwargs.append({"color":colour_list[overlap_count]})

                    overlap_count += 1

            if overlap_count > 1:
                self.project_api.__display_image__(subject_id,args,kwargs)

        # for their_cluster in other_clustering.clusterResults[subject_id][1]:
        #     overlap_count = 0
        #     args = []
        #     kwargs = []
        #     for ii,our_cluster in enumerate(self.clusterResults[subject_id][1]):
        #         overlap = [pt for pt in their_cluster if pt in our_cluster]
        #         if overlap != []:
        #             x,y = zip(*overlap)
        #             args.append([x,y,'x'])
        #             kwargs.append({"color":colour_list[overlap_count]})
        #
        #             # are there any points in our cluster which are not in their cluster?
        #             not_in = [pt for pt in our_cluster if not(pt in their_cluster)]
        #             if not_in != []:
        #                 x,y = zip(*not_in)
        #                 args.append([x,y,'<'])
        #                 kwargs.append({"color":colour_list[overlap_count]})
        #
        #             overlap_count += 1
        #
        #     if overlap_count > 1:
        #         self.project_api.__display_image__(subject_id,args,kwargs)

    def __correct__(self,subject_id):
        pass

    def __display__markings__(self, subject_id):
        """
        display the results of clustering algorithm - the image must already have been downloaded
        :param subject_id:
        :param fname: the file name of the downloaded image
        :return:
        """
        try:
            x,y = zip(*self.clusterResults[subject_id][0])
            args = [x,y,'o']
            kwargs = {"color":"red"}
        except ValueError:
            args = []
            kwargs = {}

        ax = self.project_api.__display_image__(subject_id,[args],[kwargs])

    def __get_results__(self,subject_id):
        return self.clusterResults[subject_id]

    def __raw_clusters__(self,subject_id):
        #colours = ["green","red","blue","purple","yellow","coral","tan","steelblue","fuchsia","darksage","peru"]
        args = []
        kwargs = []
        for ii,cluster in enumerate(self.clusterResults[subject_id][1]):
            args_c = []
            kwargs_c = {"color":cnames.keys()[ii]}
            for x,y in cluster:
                args_c.extend([x,y,'o'])

            args.append(args_c)
            kwargs.append(kwargs_c)

        self.project_api.__display_image__(subject_id,args,kwargs)

    def __check_correctness__(self,subject_id):
        """
        display any and all pairs of users/gold standard points which we think are too far apart
        :param subject_id:
        :return:
        """
        args = []
        for u_pt,g_pt,dist in self.user_gold_distance[subject_id]:
            if dist > 5:
                args.extend([[u_pt[0],g_pt[0]],[u_pt[1],g_pt[1]],"o-"])

        if args != []:
            ax = self.project_api.__display_image__(subject_id,[args],[{},])

    def __display_results__(self,subject_id):
        """
        plot found clusters, missed clusters and false positives clusters
        :param subject_id:
        :return:
        """
        args_l = []
        kwargs_l = []
        for cluster in self.clusterResults[subject_id][1]:
            x,y = zip(*cluster)
            args_l.append([x,y,'x'])
            kwargs_l.append({"color":"blue"})

        # green is for correct points
        try:
            x,y = zip(*self.correct_pts[subject_id])
            args_l.append([x,y,'o'])
            kwargs_l.append({"color":"green"})
        except ValueError:
            pass

        # yellow is for missed points
        try:
            x,y = zip(*self.missed_pts[subject_id])
            args_l.append([x,y,'o'])
            kwargs_l.append({"color":"yellow"})
        except ValueError:
            pass

        # red is for false positives
        try:
            x,y = zip(*self.false_positives[subject_id])
            args_l.append([x,y,'o'])
            kwargs_l.append({"color":"red"})
        except ValueError:
            pass



        self.project_api.__display_image__(subject_id,args_l,kwargs_l,title=self.algorithm_name)

    @abc.abstractmethod
    def __inner_fit__(self,markings,user_ids,tools):
        """
        the main function for clustering
        :param user_ids:
        :param markings:
        :param jpeg_file:
        :return cluster_centers: the center of each cluster - probably just take the average along each dimension
        feel free to try something else but the results might not mean as much
        :return markings_per_cluster: the markings in each cluster
        :return users_per_cluster: the user id of each marking per cluster
        :return time_to_cluster: how long it took to cluster
        """
        cluster_centers = []
        markings_per_cluster = []
        users_per_cluster = []
        time_to_cluster = 0

        return (cluster_centers , markings_per_cluster, users_per_cluster), time_to_cluster


    def __get_cluster__(self,subject_id):
        return self.clusterResults[subject_id]

    def __aggregate__(self,raw_markings):
        """
        the function to call from outside to do the clustering
        override but call if you want to add additional functionality
        :param subject_id: what is the subject (in Ouroboros == zooniverse_id)
        :param jpeg_file: for debugging - to show step by step what is happening
        :return:
        """
        self.clusterResults = {}

        # start by calling the api to get the annotations along with the list of who made each marking
        # so for this function, we know that annotations = markings
        # all_markings =  self.project_api.__get_markings__(subject_id,gold_standard)
        # print all_markings
        # self.clusterResults[subject_id] = {"param":"task_id"}
        for task_id in raw_markings:
            print task_id
            for shape in raw_markings[task_id]:
                for subject_id in raw_markings[task_id][shape]:
                    users,markings,tools = zip(*raw_markings[task_id][shape][subject_id])

                    # otherwise, just set to empty
                    if (markings == []) or (markings == [[] for i in users]):
                        cluster_results = [],[],[]
                        time_to_cluster = 0
                    else:
                        cluster_results,time_to_cluster = self.__inner_fit__(markings,users,tools)

                        if task_id not in self.clusterResults:
                            self.clusterResults[task_id] = {}

                        if shape not in self.clusterResults[task_id]:
                            self.clusterResults[task_id][shape] = {}

                        # if subject_id not in self.clusterResults[task_id][shape][subject_id]:
                        #     self.clusterResults[subject_id] = []

                        self.clusterResults[task_id][shape][subject_id] = cluster_results


    def __get_densities__(self,subject_id):
        """
        return the density of all clusters which have at least three points
        (otherwise the convex hull is 1 or 2 D)
        :param subject_id:
        :return:
        """
        densities = []
        for cluster in  self.clusterResults[subject_id][1]:
            if len(cluster) >= 3:
                hull_indices =  scipy.spatial.ConvexHull(cluster).vertices
                hull = [cluster[i] for i in hull_indices]

                area = Polygon(hull).area
                density = len(cluster)/area
                densities.append(density)

        return densities



    def __find_correct_markings__(self,subject_id):
        """
        find which user clusters we think are correct points
        :param subject_id:
        :return:
        """
        # get the markings made by the experts
        gold_markings = self.project_api.__get_markings__(subject_id,expert_markings=True)
        cluster_centers = self.clusterResults[subject_id][0]

        # init the set of correct markings, the missed ones, the false positives and the distance
        # between a correct marking and its corresponding gold standard pt - used for debugging
        self.correct_pts[subject_id] = []
        self.missed_pts[subject_id] = []
        self.user_gold_distance[subject_id] = []
        self.false_positives[subject_id] = []

        # if there are no gold markings, technically everything is a false positive
        if gold_markings == ([],[]):
            self.false_positives[subject_id] = cluster_centers
            return 0

        # so we know that there is at least one gold standard pt - but are there are any user clusters?
        # extract the actual points
        gold_pts = zip(*gold_markings[1][0])[0]

        # if there are no user markings, we have missed everything
        if cluster_centers == []:
            self.missed_pts[subject_id] = gold_pts
            return 0

        # we know that there are both gold standard points and user clusters - we need to match them up
        # user to gold - for a gold point X, what are the user points for which X is the closest gold point?
        users_to_gold = [[] for i in range(len(gold_pts))]

        # find which gold standard pts, the user cluster pts are closest to
        # this will tell us which gold points we have actually found
        for local_index, u_pt in enumerate(cluster_centers):
            # dist = [math.sqrt((float(pt["x"])-x)**2+(float(pt["y"])-y)**2) for g_pt in gold_pts]
            min_dist = float("inf")
            closest_gold_index = None

            # find the nearest gold point to the cluster center
            # doing this in a couple of lines so that things are simpler - need to allow
            # for an arbitrary number of dimensions
            for gold_index,g_pt in enumerate(gold_pts):
                dist = math.sqrt(sum([(u-g)**2 for (u,g) in zip(u_pt,g_pt)]))

                if dist < min_dist:
                    min_dist = dist
                    closest_gold_index = gold_index

            if min_dist < 30:
                users_to_gold[closest_gold_index].append(local_index)

        # and now find out which user clusters are actually correct
        # that will be the user point which is closest to the gold point
        distances_l =[]
        for gold_index,g_pt in enumerate(gold_pts):
            min_dist = float("inf")
            closest_user_index = None

            for u_index in users_to_gold[gold_index]:
                dist = math.sqrt(sum([(u-g)**2 for (u,g) in zip(cluster_centers[u_index],g_pt)]))

                if dist < min_dist:
                    min_dist = dist
                    closest_user_index = u_index

            # if none then we haven't found this point
            if closest_user_index is not None:
                u_pt = cluster_centers[closest_user_index]
                self.correct_pts[subject_id].append(u_pt)
                # todo: probably remove for production - only really useful for papers
                self.user_gold_distance[subject_id].append((u_pt,g_pt,min_dist))
                distances_l.append(min_dist)

                self.user_gold_mapping[(subject_id,tuple(u_pt))] = g_pt
            else:
                try:
                    self.missed_pts[subject_id].append(g_pt)
                except TypeError:
                    print self.missed_pts[subject_id]
                    raise

        # what were the false positives?
        self.false_positives[subject_id] = [pt for pt in cluster_centers if not(pt in self.correct_pts[subject_id])]
        return len(self.correct_pts[subject_id])

    def __analyze_missed_gold_pts__(self,subject_id):
        should_have_found = set([])
        for g_pt in self.missed_pts[subject_id]:
            for cluster_index in range(len(self.clusterResults[subject_id][0])):
                cluster_center = self.clusterResults[subject_id][0][cluster_index]
                cluster_pts = self.clusterResults[subject_id][1][cluster_index]

                for u_pt in cluster_pts:
                    dist_to_center = math.sqrt(sum([(a-b)**2 for (a,b) in zip(u_pt,cluster_center)]))
                    dist_to_gold = math.sqrt(sum([(a-b)**2 for (a,b) in zip(u_pt,g_pt)]))

                    if dist_to_center > dist_to_gold:
                        should_have_found.add(g_pt)
        return len(list(should_have_found)),len(self.missed_pts[subject_id]) - len(list(should_have_found))

    def __setup_global_indices__(self,include_gold=False):
        """
        if we want to use gold standard data for IBCC, we need to know which indices have gold standard data
        and also insert spots for gold standard points which all users missed
        :param include_gold - if we should make sure to include even those gold standard points for which
        there are not corresponding user clusters
        :return global_indices - a list of all of the subjects and clusters within those subjects - you can
        use enumerate on that list to retrieve the global indices. If the cluster is None, this is a cluster which
        none of the users have found but the expert did - only deal with these when they are being provided
        as gold standard data
        :return global_gold_indices: a dictionary where the keys are the indices of all the points where we have gold
        standard data. Maps to True if it is a true positive and False if it is a false positive
        """
        cluster_count = -1
        global_indices = []

        # whether each point is true or positive according to the gold standard
        # minus equals false
        # go with indices to help with IBCC stuff
        global_gold_indices = {}

        # # keep special track of all of the points that were completely missed - they will need to be added in
        # # specially to the IBCC input file
        # missed_gold_indices = []

        # go through each subject and convert local indices into global ones
        if self.user_gold_mapping == {}:
            warnings.warn("Empty set of true positives")
        for zooniverse_id in self.clusterResults:
            if not(self.clusterResults[zooniverse_id] is None):
                for local_index,center in enumerate(self.clusterResults[zooniverse_id][0]):
                    cluster_count += 1

                    # note that the cluster with index cluster_count is from subject zooniverse_id
                    global_indices.append((zooniverse_id,local_index))
                    # does this result have a gold standard counterpart?
                    global_index = len(global_indices)-1
                    if (zooniverse_id,tuple(center)) in self.user_gold_mapping:
                        global_gold_indices[global_index] = True
                    else:
                        global_gold_indices[global_index] = False

            # if we are going this for the indices of true positive gold standard examples then we should make sure
            # to include even those pts which users missed
            if include_gold:
                # include spots for animals which users missed
                for i in self.missed_pts[zooniverse_id]:
                    cluster_count += 1
                    global_indices.append((zooniverse_id,None))

                    # and add to the list
                    global_index = len(global_indices)-1
                    global_gold_indices[global_index] = True

        return global_indices,global_gold_indices

    def __weighted_majority_voting__(self,global_indices,gold_standard_pts,split_ip_address=True):
        user_accuracy = {}
        for gold_index in gold_standard_pts:
            subject_id,local_index = global_indices[gold_index]
            users_per_subject = self.project_api.__users__(subject_id)
            ips_per_subject = self.project_api.__ips__(subject_id)

            if local_index is None:
                user_per_cluster = []
            else:
                user_per_cluster = self.clusterResults[subject_id][2][local_index]

            for user_id in users_per_subject:
                if user_id not in user_accuracy:
                    # TP FP FN TN
                    user_accuracy[user_id] = [0,0,0,0]

                # true positive
                if gold_standard_pts[gold_index] is True:
                    # did the user see this "thing"?
                    if user_id in user_per_cluster:
                        user_accuracy[user_id][0] += 1
                    else:
                        user_accuracy[user_id][2] += 1
                # a false positive
                else:
                    # did the user see this "thing"?
                    if user_id in user_per_cluster:
                        user_accuracy[user_id][1] += 1
                    else:
                        user_accuracy[user_id][3] += 1

    def __signal_ibcc_gold__(self,global_indices,gold_standard_pts,split_ip_address=True):
        """
        uses gold standard from experts instead of priors based on majority voting
        :param global_indices:
        :param split_ip_address:
        :param gold_standard_pts: the list of global indices for which we are going to provide gold standard data
        using a negative index is a way of giving a false positive
        :return:
        """
        # intermediate holder variable
        # because ibcc needs indices to be nice and ordered with no gaps, we have to make two passes through the data
        to_ibcc = []


        # there will be some redundancy reading in the subject list - so keep track of the current subject_id
        # and only update when necessary
        users_per_subject = None
        ips_per_subject = None
        current_subject = None

        # we may skip over some indices if they correspond to gold standard points which no one marked and
        # are not being used as provided gold standard data
        actually_used_clusters = []

        for global_cluster_index,(subject_id,local_index) in enumerate(global_indices):
            # only update when necessary - when we have moved on to a new subject
            if subject_id != current_subject:
                # get the list of all the users who viewed this subject
                # and the ip addresses of every user who was not logged in while viewing the subjects
                users_per_subject = self.project_api.__users__(subject_id)
                # ips_per_subject = self.project_api.__ips__(subject_id)

                current_subject = subject_id

            if local_index is None:
                # in this case, we know that no user marked this animal
                # this is either provided gold standard data, or a test - in which case we should ignore
                # this data
                if not(global_cluster_index in gold_standard_pts):
                    continue
                else:
                    user_per_cluster = []
            else:
                user_per_cluster = self.clusterResults[subject_id][2][local_index]

            actually_used_clusters.append(global_cluster_index)

            for user_id in list(users_per_subject):
                # check to see if this user was logged in - if not, the user_id should be an ip address
                # if not logged in, we just need to decide whether to add the subject_name on to the user_id
                # which as a result treats the same ip address for different subjects as completely different
                # users
                try:
                    socket.inet_aton(user_id)
                    if split_ip_address:
                        user_id += subject_id
                except (socket.error,UnicodeEncodeError) as e:
                    # logged in user, nothing to do
                    pass
                if user_id in user_per_cluster:
                    to_ibcc.append((user_id,global_cluster_index,1))
                else:
                    to_ibcc.append((user_id,global_cluster_index,0))

        # gives each user an index with no gaps in the list
        user_indices = []

        # write out the input file for IBCC
        with open(self.base_directory+"/Databases/"+self.alg+"_ibcc.csv","wb") as f:
            f.write("a,b,c\n")
            for user,cluster_index,found in to_ibcc:
                if not(user in user_indices):
                    user_indices.append(user)

                i = user_indices.index(user)
                j = actually_used_clusters.index(cluster_index)
                f.write(str(i)+","+str(j)+","+str(found)+"\n")

        #return user_indices,actually_used_clusters
        # write out the input file for IBCC

        # create the config file
        with open(self.base_directory+"/Databases/"+self.alg+"_ibcc.py","wb") as f:
            f.write("import numpy as np\n")
            f.write("scores = np.array([0,1])\n")
            f.write("nScores = len(scores)\n")
            f.write("nClasses = 2\n")
            f.write("inputFile = \""+self.base_directory+"/Databases/"+self.alg+"_ibcc.csv\"\n")
            f.write("outputFile = \""+self.base_directory+"/Databases/"+self.alg+"_signal.out\"\n")
            f.write("confMatFile = \""+self.base_directory+"/Databases/"+self.alg+"_ibcc.mat\"\n")
            f.write("goldFile= \""+self.base_directory+"/Databases/"+self.alg+"_gold.csv\"\n")

        # start by removing all temp files
        try:
            os.remove(self.base_directory+"/Databases/"+self.alg+"_signal.out")
        except OSError:
            pass

        try:
            os.remove(self.base_directory+"/Databases/"+self.alg+"_ibcc.mat")
        except OSError:
            pass

        try:
            os.remove(self.base_directory+"/Databases/"+self.alg+"_ibcc.csv.dat")
        except OSError:
            pass

        # pickle.dump((big_subjectList,big_userList),open(base_directory+"/Databases/tempOut.pickle","wb"))
        ibcc.runIbcc(self.base_directory+"/Databases/"+self.alg+"_ibcc.py")

        return self.base_directory+"/Databases/"+self.alg+"_signal.out", user_indices,actually_used_clusters

    def __split_gold_standards__(self,gold_indices,num_splits):
        """
        for when we want to do cross validation with IBCC and provide some of the gold standard data a time
        :param num_splits:
        :return:
        """
        # start by converting into a list
        gold_list = gold_indices.items()
        random.shuffle(gold_list)
        return chunk_it(gold_list,num_splits)

    def __majority_vote__(self):
        global_index = -1
        with open(self.base_directory+"Databases/"+self.alg+"_majority_vote.csv","wb") as f:
            for zooniverse_id in self.clusterResults:
                if self.clusterResults[zooniverse_id] is None:
                    continue

                users_per_subject = self.project_api.__users__(zooniverse_id)
                ips_per_subject = self.project_api.__ips__(zooniverse_id)

                num_users = len(users_per_subject) + len(ips_per_subject)

                for local_index,markings_in_cluster in enumerate(self.clusterResults[zooniverse_id][1]):
                    global_index += 1
                    num_markings = len(markings_in_cluster)

                    probability = num_markings/float(num_users)

                    f.write(str(global_index)+" "+str(1-probability)+" "+str(probability)+"\n")

        return self.base_directory+"Databases/"+self.alg+"_majority_vote.csv"




    def __signal_ibcc_majority__(self,split_ip_address=True):
        """
        run ibcc to determine which clusters are signal or noise

        use majority voting to determine priors

        :param split_ip_address: for user ids which are ip addresses - when people are not logged in - should be
        treat each subject completely separate. That is if ip address X marked subjects A and B should we treat
        X as being two completely different people for those two classifications. There is no guarantee that they
        are the same person but seems like a lot of information to throw away. The param is to allow exploring the
        options and results.
        :return:
        """
        # todo: implement a middle ground for split_ip_address where we treat the same ip address as the same person
        # todo: as long as the classifications are close enough together time wise

        # get all users who have viewed any subjects which are processing - also get the list of those who
        # did so while not logged in
        all_users = list(self.project_api.__all_users__())
        all_ips = list(self.project_api.__all_ips__())

        # global cluster count - across all images/subjects
        cluster_count = -1

        # need to give the ip addresses unique indices, so update ip_offset after every subject
        ip_offset = 0

        # needed for determining priors for IBCC
        real_animals = 0
        fake_animals = 0

        # needed for prior confusion matrix
        true_pos = []
        true_neg = []

        # intermediate holder variable
        # because ibcc needs indices to be nice and ordered with no gaps, we have to make two passes through the data
        to_ibcc = []

        # for each global cluster index, store what image/subject it is from and what its local index is
        # wrt to that subject
        self.global_to_local = []

        # print out the classifications and set up the priors using majority voting
        for zooniverse_id in self.clusterResults:
            if self.clusterResults[zooniverse_id] is None:
                continue

            # get the list of all the users who viewed this subject
            # and the ip addresses of every user who was not logged in while viewing the subjects
            users_per_subject = self.project_api.__users__(zooniverse_id)
            ips_per_subject = self.project_api.__ips__(zooniverse_id)

            # process each cluster (possible animal), one at a time
            # only the names of users who marked this cluster matter - the specific x,y points are irrelevant right now
            for local_index,user_per_cluster in enumerate(self.clusterResults[zooniverse_id][2]):
                # moving on to the next animal so increase counter
                # universal counter over all images
                cluster_count += 1

                # needed for determining priors for IBCC
                pos = 0
                neg = 0

                # note that the cluster with index cluster_count is from subject zooniverse_id
                self.global_to_local.append((zooniverse_id,local_index))

                # for this cluster, go through each user and see if they marked this cluster
                # check whether or not each user marked this cluster
                for user_id in users_per_subject:
                    # if the user was not logged in
                    if user_id in ips_per_subject:
                        # if we are considering the ip addresses of each user (i.e. those that were not logged in)
                        # separately for each image - assign a user index based only this image
                        # use negative indices to differentiate ip addresses and users
                        # +1 assures that we don't have 0 - which is "both" positive and negative
                        if split_ip_address:
                            user_index = -(ips_per_subject.index(user_id)+ip_offset+1)
                        else:
                            # we are treating all occurances of this ip address as being from the same user
                            user_index = -all_ips.index(user_id)-1
                    else:
                        # user was logged in
                        # todo: use bisect to increase speed
                        user_index = all_users.index(user_id)

                    # did the user mark this cluster or not?
                    if user_id in user_per_cluster:
                        to_ibcc.append((user_id,user_index,cluster_count,1))
                        pos += 1
                    else:
                        to_ibcc.append((user_id,user_index,cluster_count,0))
                        neg += 1

                # if a majority of people say that there is an animal - use this for prior values
                if pos > neg:
                    real_animals += 1

                    # for estimating the confusion matrix
                    true_pos.append(pos/float(pos+neg))
                else:
                    fake_animals += 1

                    true_neg.append(neg/float(pos+neg))

            ip_offset += len(ips_per_subject)

        # now run through again - this will make sure that all of the indices are ordered with no gaps
        # since the user list is created by reading through all the users, even those which haven't annotated
        # of the specific images we are currently looking at
        ibcc_user_list = []

        # this is also for other functions to be able to interpret the results
        self.ibcc_users = []

        for user,user_index,animal_index,found in to_ibcc:
            # can't use bisect or the indices will be out of order
            if not(user_index in ibcc_user_list):
                ibcc_user_list.append(user_index)
                self.ibcc_users.append(user)

        # write out the input file for IBCC
        with open(self.base_directory+"/Databases/"+self.alg+"_ibcc.csv","wb") as f:
            f.write("a,b,c\n")
            for marking_count,(user,user_index,animal_index,found) in enumerate(to_ibcc):
                if marking_count == 200:
                    break
                i = ibcc_user_list.index(user_index)
                f.write(str(i)+","+str(animal_index)+","+str(found)+"\n")

        # create the prior estimate and the default confusion matrix
        prior = real_animals/float(real_animals + fake_animals)

        t = np.mean(true_pos)
        f = np.mean(true_neg)
        # what the weight should be
        # todo: should this be hard coded or set as a param?
        weight = 10

        # the confusion matrix cannot have any zero values
        confusion = [[max(int(t*weight),1),max(int((1-t)*weight),1)],[max(int((1-f)*weight),1),max(int(f*weight),1)]]

        # create the config file
        with open(self.base_directory+"/Databases/"+self.alg+"_ibcc.py","wb") as f:
            f.write("import numpy as np\n")
            f.write("scores = np.array([0,1])\n")
            f.write("nScores = len(scores)\n")
            f.write("nClasses = 2\n")
            f.write("inputFile = \""+self.base_directory+"/Databases/"+self.alg+"_ibcc.csv\"\n")
            f.write("outputFile = \""+self.base_directory+"/Databases/"+self.alg+"_signal.out\"\n")
            f.write("confMatFile = \""+self.base_directory+"/Databases/"+self.alg+"_ibcc.mat\"\n")
            f.write("nu0 = np.array(["+str(max(int((1-prior)*100),1))+","+str(max(int(prior*100),1))+"])\n")
            f.write("alpha0 = np.array("+str(confusion)+")\n")

        # start by removing all temp files
        try:
            os.remove(self.base_directory+"/Databases/"+self.alg+"_signal.out")
        except OSError:
            pass

        try:
            os.remove(self.base_directory+"/Databases/"+self.alg+"_ibcc.mat")
        except OSError:
            pass

        try:
            os.remove(self.base_directory+"/Databases/"+self.alg+"_ibcc.csv.dat")
        except OSError:
            pass

        # pickle.dump((big_subjectList,big_userList),open(base_directory+"/Databases/tempOut.pickle","wb"))
        ibcc.runIbcc(self.base_directory+"/Databases/"+self.alg+"_ibcc.py")

    def __review_training_set__(self,global_cluster_list,training_set):
        current_subject = None
        users_to_gold = None
        for ii in training_set:
            # only checking negative results, so skip over the positive ones
            if training_set[ii] is True:
                continue

            subject_id,local_index = global_cluster_list[ii]

            # which subject does this cluster belong to and what is its local index?
            # subject_id, local_index = self.global_to_local[int(float(ii))]
            center = self.clusterResults[subject_id][0][local_index]

            args_l = [[center[0],center[1],'x'],]
            kwargs_l = [{"color":"red"},]

            self.project_api.__display_image__(subject_id,args_l,kwargs_l,block=False)
            f = raw_input("is this a true positive? ") or "n"
            if f[0].lower() == "y":
                training_set[ii] = True
            self.project_api.__close_image__()

        return training_set

    def __review_gold__(self,global_cluster_list,actually_used_clusters,training_clusters):
        """
        do a roc analysis of the ibcc results
        :param plot:
        :param training_clusters: which clusters with gold standard data were used for training
        we will have to ignore these clusters
        :param actually_used_clusters: a mapping from the clusters with ibcc based indices to
        global based indices
        :return:
        """
        current_subject = None
        users_to_gold = None
        with open(self.base_directory+"/Databases/"+self.alg+"_signal.out","rb") as f:
            reader = csv.reader(f,delimiter=" ")
            for r in reader:
                # t is 1-prob, so we can just ignore it t= temp or trash
                ii,t,prob = r
                global_index = actually_used_clusters[int(float(ii))]
                subject_id,local_index = global_cluster_list[global_index]

                if subject_id != current_subject:
                    users_to_gold = self.__find_correct_markings__(subject_id)
                    current_subject = subject_id

                if ii in training_clusters:
                    continue
                if local_index is None:
                    continue
                # which subject does this cluster belong to and what is its local index?
                # subject_id, local_index = self.global_to_local[int(float(ii))]
                center = self.clusterResults[subject_id][0][local_index]

                prob = float(prob)

                if not(center in self.correct_pts[subject_id]):
                    if prob > 0.8:
                        print prob
                        try:
                            gold_pts = zip(*self.project_api.__get_markings__(subject_id,expert_markings=True)[1][0])[0]
                            x,y = zip(*gold_pts)
                            args_l = [[x,y,'o'],]
                            kwargs_l = [{"color":"green"},]

                            for g_index,u_list in enumerate(users_to_gold):
                                gold = gold_pts[g_index]
                                for u_index in u_list:
                                    user = self.clusterResults[subject_id][0][u_index]

                                    args_l.append([[user[0],gold[0]],[user[1],gold[1]],'-'])
                                    kwargs_l.append({"color":"blue"})



                        except IndexError:
                            args_l = []
                            kwargs_l = []

                        try:
                            x,y = zip(*self.correct_pts[subject_id])
                            args_l.append([x,y,'o'],)
                            kwargs_l.append({"color":"yellow"},)
                        except ValueError:
                            pass

                        # red is for false positives
                        x,y = self.clusterResults[subject_id][0][local_index]
                        args_l.append([x,y,'x'])
                        kwargs_l.append({"color":"red"})

                        self.project_api.__display_image__(subject_id,args_l,kwargs_l,block=False)
                        f = raw_input("is this a true positive? ") or "y"
                        if f[0].lower() == "y":
                            self.correct_pts[subject_id].append(center)
                        self.project_api.__close_image__()

    def __roc__(self,fname,global_cluster_list,actually_used_clusters=None,training_clusters=[]):
        """
        do a roc analysis of the ibcc results
        :param plot:
        :param training_clusters: which clusters with gold standard data were used for training
        we will have to ignore these clusters
        :param actually_used_clusters: a mapping from the clusters with ibcc based indices to
        global based indices
        :return:
        """
        # # start by finding the correct markings for all of the images we have done
        # for subject_id in self.clusterResults:
        #     self.__find_correct_markings__(subject_id)

        truePos = []
        falsePos = []

        # if no list is provided - assume that all clusters were used
        if actually_used_clusters is None:
            actually_used_clusters = range(len(global_cluster_list))

        with open(fname,"rb") as f:
            reader = csv.reader(f,delimiter=" ")
            for r in reader:
                # t is 1-prob, so we can just ignore it t= temp or trash
                ii,t,prob = r
                global_index = actually_used_clusters[int(float(ii))]
                subject_id,local_index = global_cluster_list[global_index]
                if ii in training_clusters:
                    continue
                if local_index is None:
                    continue
                # which subject does this cluster belong to and what is its local index?
                # subject_id, local_index = self.global_to_local[int(float(ii))]
                center = self.clusterResults[subject_id][0][local_index]

                if center in self.correct_pts[subject_id]:
                    truePos.append(float(prob))
                else:
                    falsePos.append(float(prob))

        # create the ROC curve
        alphas = truePos[:]
        alphas.extend(falsePos)
        alphas.sort()
        X = []
        Y = []
        for a in alphas:
            X.append(len([x for x in falsePos if x >= a]))
            Y.append(len([y for y in truePos if y >= a]))


        fig, ax = plt.subplots()
        line, = ax.plot(X,Y,picker=10)
        plt.xlabel("False Positive Count")
        plt.ylabel("True Positive Count")
        fig.canvas.mpl_connect('pick_event', onpick(self))
        plt.show()

        print self.x_roc