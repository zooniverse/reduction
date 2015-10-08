__author__ = 'greg'
import clustering
import os
import re
import matplotlib.pyplot as plt
import networkx as nx
import itertools
from copy import deepcopy
import abc
import json
import csv
import math

def findsubsets(S,m):
    return set(itertools.combinations(S, m))

class Classification:
    def __init__(self):
        # ,clustering_alg=None
        # assert isinstance(project,ouroboros_api.OuroborosAPI)

        # if clustering_alg is not None:
        #     assert isinstance(clustering_alg,clustering.Cluster)
        # self.cluster_alg = clustering_alg

        current_directory = os.getcwd()
        slash_indices = [m.start() for m in re.finditer('/', current_directory)]

        self.species = {"lobate":0,"larvaceanhouse":0,"salp":0,"thalasso":0,"doliolidwithouttail":0,"rocketthimble":1,"rockettriangle":1,"siphocorncob":1,"siphotwocups":1,"doliolidwithtail":1,"cydippid":2,"solmaris":2,"medusafourtentacles":2,"medusamorethanfourtentacles":2,"medusagoblet":2,"beroida":3,"cestida":3,"radiolariancolonies":3,"larvacean":3,"arrowworm":3,"shrimp":4,"polychaeteworm":4,"copepod":4}
        self.candidates = self.species.keys()

    @abc.abstractmethod
    def __task_aggregation__(self,classifications,task_id,aggregations):
        return []

    def __subtask_classification__(self,task_id,classification_tasks,marking_tasks,raw_classifications,aggregations):
        """
        call this when at least one of the tools associated with task_id has a follow up question
        :param task_id:
        :param classification_tasks:
        :param raw_classifications:
        :param clustering_results:
        :param aggregations:
        :return:
        """


        # go through the tools which actually have the followup questions
        for tool in classification_tasks[task_id]:

            # now go through the individual followup questions
            # range(len()) - since individual values will be either "single" or "multiple"

            for followup_question_index in range(len(classification_tasks[task_id][tool])):
                global_index = str(task_id)+"_" +str(tool)+"_"+str(followup_question_index)


                followup_classification = {}
                # this is used for inserting the results back into our running aggregation - which are based
                # on shapes, not tools
                shapes_per_cluster = {}

                # go through each cluster and find the corresponding raw classifications
                for subject_id in aggregations:
                    if subject_id == "param":
                        continue

                    # has anyone done this task for this subject?
                    if task_id in aggregations[subject_id]:
                        # find the clusters which we have determined to be of the correct type
                        # only consider those users who made the correct type marking
                        # what shape did this particular tool make?
                        shape =  marking_tasks[task_id][tool]
                        for cluster_index,cluster in aggregations[subject_id][task_id][shape + " clusters"].items():
                            if cluster_index in ["param","all_users"]:
                                continue

                            # what is the most likely tool for this cluster?
                            most_likely_tool,_ = max(cluster["tool_classification"][0].items(),key = lambda x:x[1])
                            if int(most_likely_tool) != int(tool):
                                continue


                            # polygons and rectangles will pass cluster membership back as indices
                            # ints => we can't case tuples
                            if isinstance(cluster["cluster members"][0],int):
                                user_identifiers = zip(cluster["cluster members"],cluster["users"])
                            else:
                                user_identifiers = zip([tuple(x) for x in cluster["cluster members"]],cluster["users"])
                            ballots = []

                            for user_identifiers,tool_used in zip(user_identifiers,cluster["tools"]):
                                # did the user use the relevant tool - doesn't matter if most people
                                # used another tool
                                if tool_used == tool:

                                    followup_answer = raw_classifications[global_index][subject_id][user_identifiers]
                                    u = user_identifiers[1]
                                    ballots.append((u,followup_answer))

                            followup_classification[(subject_id,cluster_index)] = deepcopy(ballots)
                            shapes_per_cluster[(subject_id,cluster_index)] = shape


                followup_results = self.__task_aggregation__(followup_classification,global_index,{})
                assert isinstance(followup_results,dict)

                for subject_id,cluster_index in followup_results:
                    shape =  shapes_per_cluster[(subject_id,cluster_index)]
                    # keyword_list = [subject_id,task_id,shape+ " clusters",cluster_index,"followup_questions"]
                    new_results = followup_results[(subject_id,cluster_index)]
                    # if this is the first question - insert
                    # otherwise append

                    if followup_question_index == 0:
                        aggregations[subject_id][task_id][shape + " clusters"] [cluster_index]["followup_question"] = {}


                    aggregations[subject_id][task_id][shape + " clusters"] [cluster_index]["followup_question"][followup_question_index] = new_results.values()[0]

        return aggregations

    def __existence_classification__(self,task_id,shape,aggregations):
        """
        classify whether clusters are true or false positives
        i.e. whether each cluster corresponds to something which actually exists

        return in json format so we can merge with other results
        :return:
        """

        # aggregations = {}

        # raw_classifications and clustering_results have different hierarchy orderings- raw_classifications
        # is better for processing data and clustering_results is better for showing the end result
        # technically we only need to look at the data from clustering_results right now but its
        # hierarchy is really inefficient so use raw_classifications to help

        # each shape is done independently

        # set - so if multiple tools create the same shape - we only do that shape once
        # for shape in set(marking_tasks[task_id]):


        # pretentious name but basically whether each person who has seen a subject thinks it is a true
        # positive or not
        existence_classification = {"param":"subject_id"}

        global_cluster_index = 0
        # clusters_per_subject = []

        # look at the individual points in the cluster
        for subject_id in aggregations.keys():
            if subject_id == "param":
                continue

            # gold standard pts may not match up perfectly with the given clusters -
            # for example, we could have a gold penguin at 10,10 but the users' cluster
            # is centered at 10.1,9.8 - same penguin though
            # so as we go through the clusters, we need to see which ones match up more closely
            # with the gold standard
            # if subject_id in gold_standard_clustering[0]:
            #     # closest cluster and distance
            #     gold_to_cluster = {pt:(None,float("inf")) for pt in gold_standard_clustering[0][subject_id]}
            # else:
            #     gold_to_cluster = None


            # clusters_per_subject.append([])

            # # in either case probably an empty image
            # if subject_id not in clustering_results:
            #     continue
            # if task_id not in clustering_results[subject_id]:
            #     continue

            if (shape+ " clusters") not in aggregations[subject_id][task_id]:
                # if none of the relevant markings were made on this subject, skip it
                continue

            all_users = aggregations[subject_id][task_id][shape+ " clusters"]["all_users"]

            for local_cluster_index in aggregations[subject_id][task_id][shape+ " clusters"]:
                if local_cluster_index == "all_users":
                    continue

                # extract the users who marked this cluster
                cluster = aggregations[subject_id][task_id][shape+ " clusters"][local_cluster_index]

                # todo - put this back when we support gold standard clustering
                # # is this user cluster close to any gold standard pt?
                # if subject_id in gold_standard_clustering[0]:
                #     x,y = cluster["center"]
                #     for (gold_x,gold_y) in gold_to_cluster:
                #         dist = math.sqrt((x-gold_x)**2+(y-gold_y)**2)
                #         if dist < gold_to_cluster[(gold_x,gold_y)][1]:
                #             gold_to_cluster[(gold_x,gold_y)] = local_cluster_index,dist
                #
                # # now repeat for negative gold standards
                # if subject_id in gold_standard_clustering[1]:
                #     x,y = cluster["center"]
                #     min_dist = float("inf")
                #     closest= None
                #     for x2,y2 in gold_standard_clustering[1][subject_id]:
                #         dist = math.sqrt((x-x2)**2+(y-y2)**2)
                #         if dist < min_dist:
                #             min_dist = min(dist,min_dist)
                #             closest = (x2,y2)
                #     if min_dist == 0.:
                #         assert (x,y) == closest
                #         mapped_gold_standard[(subject_id,local_cluster_index)] = 0

                users = cluster["users"]

                ballots = []

                # todo - the 15 hard coded value - might want to change that at some point
                for u in all_users:
                    if u in users:
                        ballots.append((u,1))
                    else:
                        ballots.append((u,0))

                existence_classification[(subject_id,local_cluster_index)] = ballots
                # clusters_per_subject[-1].append(global_cluster_index)
                # global_cluster_index += 1

            # # note we don't care about why a cluster corresponds to a gold standard pt - that is
            # # it could be really close to given gold standards - the point is that it is close
            # # to at least one of them
            # if gold_to_cluster is not None:
            #     for (local_cluster_index,dist) in gold_to_cluster.values():
            #         # arbitrary threshold but seems reasonable
            #         if dist < 1:
            #             mapped_gold_standard[(subject_id,local_cluster_index)] = 1

        existence_results = self.__task_aggregation__(existence_classification,task_id,{})#,mapped_gold_standard)
        assert isinstance(existence_results,dict)

        for subject_id,cluster_index in existence_results:
            new_results = existence_results[(subject_id,cluster_index)][task_id]
            # new_agg = {subject_id: {task_id: {shape + " clusters": {cluster_index: {"existence": new_results}}}}}
            # aggregations = self.__merge_results__(aggregations,new_agg)
            aggregations[subject_id][task_id][shape + " clusters"][cluster_index]["existence"] = new_results
            # if subject_id not in aggregations:
            #     aggregations[subject_id] = {}
            # if task_id not in aggregations[subject_id]:
            #     aggregations[subject_id][task_id] = {}
            # if (shape + " clusters") not in aggregations[subject_id][task_id]:
            #     aggregations[subject_id][task_id][shape+ " clusters"] = {}
            # # this part is probably redundant
            # if cluster_index not in aggregations[subject_id][task_id][shape+ " clusters"]:
            #     aggregations[subject_id][task_id][shape+ " clusters"][cluster_index] = {}
            #
            # aggregations[subject_id][task_id][shape+ " clusters"][cluster_index]["existence"] = existence_results[(subject_id,cluster_index)]

        return aggregations

    def __tool_classification__(self,task_id,shape,aggregations):
        """
        if multiple tools can make the same shape - we need to decide which tool actually corresponds to this cluster
        for example if both the adult penguin and chick penguin make a pt - then for a given point we need to decide
        if it corresponds to an adult or chick
        :param task_id:
        :param classification_tasks:
        :param raw_classifications:
        :param clustering_results:
        :return:
        """
        print "tool classification - more than one tool could create " +str(shape) + "s in task " + str(task_id)

        if aggregations == {}:
            print "warning - empty classifications"
            return {}

        # only go through the "uncertain" shapes
        tool_classifications = {}

        for subject_id in aggregations:
            # look at the individual points in the cluster

            for cluster_index,cluster in aggregations[subject_id][task_id][shape+ " clusters"].items():
                # all_users just gives us a list of all of the users who have seen this subject
                # not relevant here
                if cluster_index == "all_users":
                    continue

                # which users marked this cluster
                users = cluster["users"]
                # which tool each individual user used
                tools = cluster["tools"]
                assert len(tools) == len(users)

                # in this case, we want to "vote" on the tools
                ballots = zip(users,tools)

                tool_classifications[(subject_id,cluster_index)] = ballots

        # classify
        print "tool results classification"
        tool_results = self.__task_aggregation__(tool_classifications,task_id,{})
        assert isinstance(tool_results,dict)

        for subject_id,cluster_index in tool_results:

            new_results = tool_results[(subject_id,cluster_index)][task_id]
            # the clustering results already exist so we are just adding more data to it
            aggregations[subject_id][task_id][shape + " clusters"][cluster_index]["tool_classification"] = new_results

        return aggregations

    def __separate_tasks__(self,workflow):
        """
        workflow should be a dict object representing the workflow JSON
        """

        classifications = {}
        marking = {}

        for key,value in workflow.iteritems():
            if value["type"]=="marking":
                marking[key] = value
            else:
                classifications[key] = value

        return [classifications,marking]

    def __aggregate__(self,raw_classifications,workflow,aggregations):
        # use the first subject_id to find out which tasks we are aggregating the classifications for
        # aggregations = {}
        #classification_tasks,marking_tasks = workflow
        classification_tasks,marking_tasks = self.__separate_tasks__(workflow)
    

        # start by doing existence classifications for markings
        # i.e. determining whether a cluster is a true positive or false positive
        # also do tool type classification for tasks where more than one tool
        # can create the same shape
        # followup questions will be dealt as classification tasks
        # note that polygons and rectangles (since they are basically a type of polygon)
        # handle some of this themselves
        for task_id in marking_tasks:
            for shape in set(marking_tasks[task_id]):
                # these shapes are dealt with else where
                # if shape not in ["polygon","text"]:
                aggregations = self.__existence_classification__(task_id,shape,aggregations)

                # tool classification for rectangles/polygon is handled by the actual clustering algorithm
                # technically, that clustering algorithm could also take care of existence as well
                # but that would really mess up the code
                if shape not in ["rectangle","polygon"]:
                    # can more than one tool create this shape?
                    # if only one tool could create this shape, this is slightly silly to do but
                    # it does mean that the aggregation json is correctly structured
                    aggregations = self.__tool_classification__(task_id,shape,aggregations)


                    # for subject_id in aggregations:
                    #     for cluster_index in aggregations[subject_id][task_id][shape + " clusters"]:
                    #         if cluster_index != "all_users":
                    #             assert "tool_classification" in aggregations[subject_id][task_id][shape + " clusters"][cluster_index]

        # now go through the normal classification aggregation stuff
        # which can include follow up questions
        for task_id in classification_tasks:
            #print "classifying task " + str(task_id)

            # task_results = {}
            # just a normal classification question
            #print classification_tasks[task_id]["type"]

            if classification_tasks[task_id]["type"] in ["single","multiple"]:
                # did anyone actually do this classification?
                if task_id in raw_classifications:

                    aggregations = self.__task_aggregation__(raw_classifications[task_id],task_id,aggregations)

            else:
                # we have a follow up classification
                aggregations = self.__subtask_classification__(task_id,classification_tasks,marking_tasks,raw_classifications,aggregations)

        return aggregations


class VoteCount(Classification):
    def __init__(self,param_dict):
        Classification.__init__(self)

    def __task_aggregation__(self,raw_classifications,task_id,aggregations):
        """
        question_id is not None if and only if the classification relates to a marking
        :param subject_ids:
        :param task_id:
        :param question_id:
        :param gold_standard:
        :return:
        """
        # results = {}

	#print "***"
	#print task_id
	#print aggregations
	#print raw_classifications
	
        for subject_id in raw_classifications:

            vote_counts = {}
            if subject_id == "param":
                continue
            for user,ballot in raw_classifications[subject_id]:

                if ballot is None:
                    continue
                # in which case only one vote is allowed

		# differentiate between list of strings and single string
                if isinstance(ballot,(str,unicode)):
                    if ballot in vote_counts:
                        vote_counts[ballot] += 1
                    else:
                        vote_counts[ballot] = 1
                # in which case multiple votes are allowed
                else:
                    for vote in ballot:
                        if vote in vote_counts:
                            vote_counts[vote] += 1
                        else:
                            vote_counts[vote] = 1

            # convert to percentages
            percentages = {}
            for vote in vote_counts:
                percentages[vote] = vote_counts[vote]/float(sum(vote_counts.values()))

            results = percentages,len(raw_classifications[subject_id])

            # merge the new results into the existing one
            # aggregations = self.__merge_results__(aggregations,new_agg)
            if subject_id not in aggregations:
                aggregations[subject_id] = {}
            aggregations[subject_id][task_id] = results

        return aggregations


