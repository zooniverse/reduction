#!/usr/bin/env python
__author__ = 'greg'
from panoptes_api import PanoptesAPI
import agglomerative
import clustering
import math
import pandas as pd
import numpy as np
from scipy.spatial.distance import pdist,squareform
from scipy.cluster.hierarchy import linkage
import abc
import re
import random
import unicodedata
import os
from copy import deepcopy

if os.path.exists("/home/ggdhines"):
    base_directory = "/home/ggdhines"
else:
    base_directory = "/home/greg"

class AbstractNode:
    def __init__(self):
        self.value = None
        self.rchild = None
        self.lchild = None

        self.parent = None
        self.depth = None
        self.height = None

        self.users = None

    def __set_parent__(self,node):
        assert isinstance(node,InnerNode)
        self.parent = node

    @abc.abstractmethod
    def __traversal__(self):
        return []

    def __set_depth__(self,depth):
        self.depth = depth


class LeafNode(AbstractNode):
    def __init__(self,value,index,user=None):
        AbstractNode.__init__(self)
        self.value = value
        self.index = index
        self.users = [user,]
        self.height = 0
        self.pts = [value,]

    def __traversal__(self):
        return [(self.value,self.index),]

class InnerNode(AbstractNode):
    def __init__(self,rchild,lchild,dist=None):
        AbstractNode.__init__(self)
        assert isinstance(rchild,(LeafNode,InnerNode))
        assert isinstance(lchild,(LeafNode,InnerNode))

        self.rchild = rchild
        self.lchild = lchild

        rchild.__set_parent__(self)
        lchild.__set_parent__(self)

        self.dist = dist

        assert (self.lchild.users is None) == (self.rchild.users is None)
        if self.lchild.users is not None:
            self.users = self.lchild.users[:]
            self.users.extend(self.rchild.users)

        self.pts = self.lchild.pts[:]
        self.pts.extend(self.rchild.pts[:])

        self.height = max(rchild.height,lchild.height)+1

    def __traversal__(self):
        retval = self.rchild.__traversal__()
        retval.extend(self.lchild.__traversal__())

        return retval


def set_depth(node,depth=0):
    assert isinstance(node,AbstractNode)
    node.__set_depth__(depth)

    if node.rchild is not None:
        set_depth(node.rchild,depth+1)
    if node.lchild is not None:
        set_depth(node.lchild,depth+1)


def lowest_common_ancestor(node1,node2):
    assert isinstance(node1,LeafNode)
    assert isinstance(node2,LeafNode)

    depth1 = node1.depth
    depth2 = node2.depth

    # make sure that the first node is the "shallower" node
    if depth1 > depth2:
        temp = node2
        node2 = node1
        node1 = temp

        depth1 = node1.depth
        depth2 = node2.depth
    while depth2 > depth1:
        node2 = node2.parent
        depth2 = node2.depth

    while node1 != node2:
        node1 = node1.parent
        node2 = node2.parent

    return node1.height

def create_clusters(ordering,maxima):
    if maxima == []:
        return [ordering,]

    next_maxima = max(maxima,key=lambda x:x[1])

    split = next_maxima[0]
    left_split = ordering[:split]
    right_split = ordering[split:]

    maxima_index = maxima.index(next_maxima)
    left_maximia = maxima[:maxima_index]
    right_maximia = maxima[maxima_index+1:]
    # print right_maximia
    # need to adjust the indices for the right hand values
    right_maximia = [(i-split,j) for (i,j) in right_maximia]
    # print right_maximia

    retval = create_clusters(left_split,left_maximia)
    retval.extend(create_clusters(right_split,right_maximia))

    return retval

def Levenshtein(a,b):
    "Calculates the Levenshtein distance between a and b."
    n, m = len(a), len(b)
    if n > m:
        # Make sure n <= m, to use O(min(n,m)) space
        a,b = b,a
        n,m = m,n

    current = range(n+1)
    for i in range(1,m+1):
        previous, current = current, [i]+[0]*n
        for j in range(1,n+1):
            add, delete = previous[j]+1, current[j-1]+1
            change = previous[j-1]
            if a[j-1] != b[i-1]:
                change = change + 1
            current[j] = min(add, delete, change)

    return current[n]

class TextCluster(clustering.Cluster):
    def __init__(self,project_api,min_cluster_size=1,mapping=None):
        clustering.Cluster.__init__(self,project_api,min_cluster_size)

    def __get_aggregation_lines__(self,lines):
        rep = {" ":"@","-":"#","(":"{",">":"^"}
        rep = dict((re.escape(k), v) for k, v in rep.iteritems())
        pattern = re.compile("|".join(rep.keys()))

        id_ = str(random.uniform(0,1))



        with open(base_directory+"/Databases/transcribe"+id_+".fasta","wb") as f:
           for line in lines:

                # line = unicodedata.normalize('NFKD', line).encode('ascii','ignore')
                assert isinstance(line,str)
                fasta_line = pattern.sub(lambda m: rep[re.escape(m.group(0))], line)
                # for i in range(max_length-len(line)):
                #     fasta_line += "-"

                try:
                    f.write(">\n"+fasta_line+"\n")
                except UnicodeEncodeError:
                    print fasta_line
                    print unicodedata.normalize('NFKD', fasta_line).encode('ascii','ignore')
                    raise

        t = "mafft --anysymbol " + base_directory+"/Databases/transcribe"+id_+".fasta>"+base_directory+"/Databases/transcribe"+id_+".out 2> /dev/null"
        os.system(t)

        aligned_text = []
        with open(base_directory+"/Databases/transcribe"+id_+".out","rb") as f:
            cumulative_line = ""
            # print "here here"
            for line in f.readlines():
                # print line[:-1]
                if (line == ">\n"):
                    if (cumulative_line != ""):
                        aligned_text.append(cumulative_line)
                        cumulative_line = ""
                else:
                    cumulative_line += line[:-1]

            aligned_text.append(cumulative_line)

        # for a in aligned_text:
        #     assert isinstance(a,str)
        #     leftmost_char = -1
        #     rightmost_char = -1
        #     for i,c in enumerate(a):
        #         if c != "-":
        #             leftmost_char = i
        #             break
        #     for i,c in reversed(list(enumerate(a))):
        #         if c != "-":
        #             rightmost_char = i
        #             break
        #     print leftmost_char,rightmost_char
        #     print a
        # print

        os.remove(base_directory+"/Databases/transcribe"+id_+".fasta")
        os.remove(base_directory+"/Databases/transcribe"+id_+".out")

        return aligned_text

    def __accuracy__(self,s):
        assert isinstance(s,str)
        assert len(s) > 0
        return sum([1 for c in s if c != "-"])/float(len(s))

    def __agreement__(self,text):
        assert isinstance(text,list)
        assert len(text) > 1
        assert isinstance(text[0],str)
        assert min([len(t) for t in text]) == max([len(t) for t in text])

        retval = []

        for t in text:
            leftmost_char = -1
            rightmost_char = -1
            for i,c in enumerate(t):
                if c != "-":
                    leftmost_char = i
                    break
            for i,c in reversed(list(enumerate(t))):
                if c != "-":
                    rightmost_char = i
                    break

            agreement = 0

            for i in range(leftmost_char,rightmost_char+1):
                c = [t2[i].lower() for t2 in text]
                if min(c) == max(c):
                    assert c[0] != "-"
                    agreement += 1

            retval.append(agreement/float(rightmost_char-leftmost_char+1))
        return retval

    def __complete_agreement__(self,text):
        assert isinstance(text,list)
        assert len(text) > 1
        assert isinstance(text[0],str)
        assert min([len(t) for t in text]) == max([len(t) for t in text])

        agreement = 0
        # print text
        for i in range(len(text[0])):

            c = [t[i].lower() for t in text if t[i] != "-"]
            if min(c) == max(c):
                assert c[0] != "-"
                agreement += 1

        return agreement/float(len(text[0]))

    def __inner_fit__(self,markings,user_ids,jpeg_file=None,debug=False,gold_standard=False,subject_id=None):


        M = []
        texts = []

        for x1,x2,y1,y2,text in markings:
            dist = (x2*y1-y2*x1)/math.sqrt((y2-y1)**2+(x2-x1)**2)
            texts.append(text)
            try:
                tan_theta = math.fabs(y1-y2)/math.fabs(x1-x2)
                theta = math.atan(tan_theta)
            except ZeroDivisionError:
                theta = math.pi/2.

            M.append((dist,theta))
            # print str(dist) + "\t" + str(theta) + "\t" + text

        ordering  = self.__fit2__(M,user_ids)

        current_lines = {}
        current_direction = {}
        current_indices = {}

        clusters = []

        for a,b in ordering:
            i = M.index(a)
            user = user_ids[i]
            # print a,user
            # print current_lines.keys()
            text = texts[i]
            # print text
            assert isinstance(text,unicode)
            text = text.encode('ascii','ignore')
            # text = unicodedata.normalize('NFKD', text).encode('ascii','ignore')
            # print user
            # print type(text)
            # print text
            if user in current_lines:
                print "%%"
                print user
                print current_lines[user]
                print text
                # print a,b
                current_direction[user].append(a[1])
                current_indices[user].append(i)
                # 45 degrees

                # what happens if we went with the new text instead of the old
                if len(current_lines) > 1:
                    aligned_text = self.__get_aggregation_lines__(current_lines.values())
                    current_accuracy = self.__agreement__(aligned_text)

                    new_lines = deepcopy(current_lines)
                    new_lines[user] = text
                    aligned_text = self.__get_aggregation_lines__(new_lines.values())
                    new_accuracy = self.__agreement__(aligned_text)
                    print current_accuracy
                    print new_accuracy
                    assert False
                else:
                    assert False

                # if math.fabs(np.mean(current_direction[user])) <= 0.785:
                #     s = sorted(current_indices[user],key=lambda x:markings[x][0])
                #     new_str = ""
                #     for i in s:
                #         new_str += markings[i][4]
                #     new_str = text.encode('ascii','ignore')
                #     if len(current_lines) > 1:
                #         # print "*****"
                #         # print [markings[i][4] for i in s]
                #         assert "" not in current_lines.values()
                #         aligned_text = self.__get_aggregation_lines__(current_lines.values())
                #         assert len(aligned_text) == len(current_lines)
                #         # print aligned_text
                #         assert "" not in aligned_text
                #         old_accuracy =  np.mean([self.__accuracy__(s) for s in aligned_text])
                #
                #         new_lines = deepcopy(current_lines)
                #         new_lines[user] = new_str
                #         aligned_text = self.__get_aggregation_lines__(new_lines.values())
                #         new_accuracy = np.mean([self.__accuracy__(s) for s in aligned_text])
                #
                #         print "$$"
                #         for t in aligned_text:
                #             print t
                #
                #         agreement = self.__agreement__(aligned_text)
                #         print
                #         # print old_accuracy,new_accuracy,agreement
                #         # print
                #         if new_accuracy < old_accuracy:
                #             print "===---"
                #             # for user,l in current_lines.items():
                #             #     # print list(markings)[current_indices[user]]
                #             #     print list(list(markings)[current_indices[user][0]])[:-1]
                #             #     print M[current_indices[user][0]]
                #             #     print user,l
                #             #
                #             # print
                #             clusters.append(current_lines.values())
                #
                #             current_lines = {user:text}
                #             current_direction = {user:[a[1]]}
                #             current_indices = {user:[i]}
                #         else:
                #             # print current_lines
                #             # print new_lines
                #             assert False
                #     else:
                #         current_lines[user] = new_str
                #         current_direction[user].append(a[1])
                #         current_indices[user].append(i)
                #
                # else:
                #     assert False
                # print
                # print current_direction[user],a[1]
                # assert False
            else:
                # print len(text)
                # print "==---"
                # for l in current_lines.values():
                #     print Levenshtein(text,l)
                # print

                current_lines[user] = text

                if user not in current_direction:
                    current_direction[user] = [a[1]]
                else:
                    current_direction[user].append(a[1])

                if user not in current_indices:
                    current_indices[user] = [i]
                else:
                    current_indices[user].append(i)

                if len(current_lines) > 1:
                    # print current_lines.items()
                    temp_users,temp_lines = zip(*current_lines.items())
                    # print temp_user,temp_lines
                    # print temp_lines
                    aligned_text = self.__get_aggregation_lines__(temp_lines)
                    print "$$"
                    for t in aligned_text:
                        print t

                    agreement = self.__agreement__(aligned_text)
                    print
                    if min(agreement) <= 0.3:
                        print "^^^"
                        clusters.append(current_lines.values())
                        current_lines = {user:text}
                        current_direction = {user:[a[1]]}
                        current_indices = {user:[i]}

                    # print [self.__accuracy__(s) for s in aligned_text][temp_users.index(user)]
                    # print accuracy
                    # assert False
        for c in clusters:
            for l in c:
                print l
            print

    def __fit2__(self,markings,user_ids,jpeg_file=None,debug=False):
        # l = [[(u,m[0]) for m in marking] for u,marking in zip(user_ids,markings)]
        user_list,pts_list = user_ids,markings
        # assert len(pts_list) == len(list(set(pts_list)))
        labels = range(len(pts_list))
        variables = ["X","Y"]
        # X = np.random.random_sample([5,3])*10
        df = pd.DataFrame(list(pts_list),columns=variables, index=labels)

        row_dist = pd.DataFrame(squareform(pdist(df, metric='euclidean')), columns=labels, index=labels)

        row_clusters = linkage(row_dist, method='single')

        nodes = [LeafNode(pt,ii) for ii,pt in enumerate(pts_list)]

        for merge in row_clusters:
            rchild_index = int(merge[0])
            lchild_index = int(merge[1])
            dist = float(merge[2])

            rnode = nodes[rchild_index]
            lnode = nodes[lchild_index]

            # if both nodes are leaf nodes, just merge them
            if isinstance(rnode,LeafNode) and isinstance(lnode,LeafNode):
                nodes.append(InnerNode(rnode,lnode,dist))
            # if rnode is an inner node - we might need to merge into it
            elif isinstance(lnode,LeafNode):
                r_dist = rnode.dist

                if r_dist == dist:
                    # merge
                    pass
                else:
                    # create a new parent node
                    nodes.append(InnerNode(rnode,lnode,dist))
            elif isinstance(rnode,LeafNode):
                l_dist = lnode.dist

                if l_dist == dist:
                    # merge
                    pass
                else:
                    # create a new parent node
                    nodes.append(InnerNode(rnode,lnode,dist))
            else:
                # we have two inner nodes
                l_dist = lnode.dist
                r_dist = rnode.dist

                if dist == l_dist:
                    assert dist == r_dist
                    assert False
                else:
                    nodes.append(InnerNode(rnode,lnode,dist))

        # set the depths of all of the nodes
        set_depth(nodes[-1])

        reachability_ordering = nodes[-1].__traversal__()
        return reachability_ordering
        # assert False
        # reachability_distance = [float("inf"),]
        # for ii, leaf in enumerate(reachability_ordering[1:]):
        #     # print reachability_ordering[ii]
        #     # print reachability_ordering[ii+1]
        #     node1 = nodes[reachability_ordering[ii][1]]
        #     node2 = nodes[reachability_ordering[ii+1][1]]
        #
        #     reachability_distance.append(lowest_common_ancestor(node1,node2))
        #
        #
        #
        # # find the "important" local maxima
        # important_local_maxima = []
        # for i in range(1,len(reachability_distance)-1):
        #     dist = reachability_distance[i]
        #     other_distances = []
        #     if i > 0:
        #         other_distances.append(reachability_distance[i-1])
        #     if i < (len(reachability_distance)-1):
        #         other_distances.append(reachability_distance[i+1])
        #     if dist > max(other_distances):
        #         if np.mean(other_distances) < 0.8*dist:
        #             important_local_maxima.append((i,dist))
        #
        # clusters = create_clusters(zip(*reachability_ordering)[0],important_local_maxima)
        # users_per_cluster = [[user_list[pts_list.index(p)] for p in c] for c in clusters]
        # cluster_centers = [[np.mean(axis) for axis in zip(*c)] for c in clusters]
        # return (cluster_centers,clusters,users_per_cluster),0

def line_mapping(marking):
    # want to extract the params x1,x2,y1,y2 but
    # ALSO make sure that x1 <= x2 and flip if necessary
    x1 = marking["x1"]
    x2 = marking["x2"]
    y1 = marking["y1"]
    y2 = marking["y2"]

    try:
        text = marking["text"]
    except KeyError:
        print marking
        raise

    if x1 <= x2:
        return x1,x2,y1,y2,text
    else:
        return x2,x1,y2,y1,text

class Tate(PanoptesAPI):
    def __init__(self):
        PanoptesAPI.__init__(self,"tate")

        self.marking_params_per_shape = dict()
        self.marking_params_per_shape["text"] = line_mapping

    def __task_setup__(self):
        self.classification_tasks = {}
        self.task_type["init"] = "drawing"
        self.task_type["T1"] = None
        self.shapes_per_tool["init"] = []
        self.shapes_per_tool["init"].append("text")

bentham = [4150,4151,4152,4153,4154]
tate = [4127,4129,4130,4131,4132,4133,4136]
project = Tate()
# project.__migrate__()
project.__set_subjects__([4150])
project.__set_clustering_alg__(TextCluster)
project.__cluster__()
