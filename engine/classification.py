from __future__ import print_function
import itertools
import abc
__author__ = 'greg'

def findsubsets(S,m):
    return set(itertools.combinations(S, m))

class Classification:
    def __init__(self,environment):
        self.environment = environment

    @abc.abstractmethod
    def __task_aggregation__(self,classifications,task_id,aggregations):
        return []

    def __most_likely_tool__(self,cluster):
        """
        given a cluster of markings - all corresponding to the same shape, but not necessarily the same tool
        return the most likely tool associated with this cluster
        :param cluster:
        :return:
        """
        tools = cluster["tools"]
        # count how many times each tool is used
        try:
            tool_count = {t:len([t_ for t_ in tools if (t == t_)]) for t in set(tools)}
        except TypeError:
            print(cluster)
            print(tools)
            raise
        # sort by how many times each tool was used
        sorted_tools = sorted(tool_count.items(), key = lambda x:x[1])

        # get the most likely tool and how many voted for this tool
        most_likely_tool,max_count = sorted_tools[-1]
        # how many people voted in total?
        total_count = sum(tool_count.values())
        percentage = max_count/float(total_count)

        assert percentage > 0
        return most_likely_tool,percentage,sorted_tools

    def __get_relevant_identifiers__(self,most_likely_tool,cluster):
        """
        given a cluster of markings (each user is identified by a combination of their markings' coordinates
        and their user ids) - return only those markings where the tool used matches the most likely tool for this
        cluster
        :param most_likely_tool:
        :return:
        """
        relevant_identifiers = []

        # rectangles and polygons seem to have different structures
        # todo - refactor so that all shapes have the same structure - or be really sure that different shapes need different structures
        if isinstance(cluster["cluster members"][0],int):
            user_identifiers = zip(cluster["cluster members"],cluster["users"])
        else:
            user_identifiers = zip([tuple(x) for x in cluster["cluster members"]],cluster["users"])

        for user_identifiers,tool_used in zip(user_identifiers,cluster["tools"]):
            if tool_used == most_likely_tool:
                relevant_identifiers.append(user_identifiers)

        return relevant_identifiers

    def __subtask_classification__(self,task_id,classification_tasks,marking_tasks,raw_classifications,aggregations):
        """
        call this when at least one of the tools associated with task_id has a follow up question
        :param task_id:
        :param classification_tasks:
        :param raw_classifications:
        :param aggregations:
        :return:
        """

        # the global index contains the task id, tool id and the follow up question id
        for global_index in raw_classifications.keys():
            task_id,most_likely_tool,followup_question_index = global_index.split("_")

            # since clusters are stored by shape not tool - convert the tool to its shape
            # and get all of the clusters with the that shape. Then for each of those clusters, look
            # for only those people who used the right tool and extract their classifications
            shape = marking_tasks[task_id][int(most_likely_tool)]

            # go through each subject that has classifications for the given
            # task, tool and follow up question
            for subject_id in raw_classifications[global_index]:
                # go through each individual cluster
                for cluster_index,cluster in aggregations[subject_id][task_id][shape + " clusters"].items():
                    # skip keys which don't actually point to clusters (e.g. misc. extra info)
                    if cluster_index == "all_users":
                        continue
                    # create a new dictionary element to store the results
                    aggregations[subject_id][task_id][shape + " clusters"][cluster_index]["followup_question"] = {}

                    relevant_identifiers = self.__get_relevant_identifiers__(most_likely_tool,cluster)

                    # extract all of the answers for this particular followup question
                    followup_answers = []
                    # id_ will be a combination of the user's id (either zooniverse login name or ip address)
                    # and the coordinates of their marking
                    # so even though raw_classifications doesn't record clusters, we can use ids + coordinates
                    # to find the markings
                    for id_ in relevant_identifiers:
                        # extract this person's follow up answers
                        answer = raw_classifications[global_index][subject_id][id_]
                        # id_[1] is the user id (marking coordinates are [0] and don't matter any more)
                        u = id_[1]
                        followup_answers.append((u,answer))

                    # task_aggregation can work over multiple subjects at once (which is what happens if we call
                    # it for a simple classification task, i.e. one that is not a following task) so
                    # task_aggregation is actually expecting a dictionary which maps from subject_id to individual
                    # classifications. Hence the dummy_wrapper
                    dummy_wrapper = {subject_id:followup_answers}
                    followup_results = self.__task_aggregation__(dummy_wrapper,global_index,{})

                    # extract the result and add it to the overall set of aggregations
                    aggregations[subject_id][task_id][shape + " clusters"][cluster_index]["followup_question"][followup_question_index] = followup_results[subject_id][global_index]

        return aggregations

    def __existence_classification__(self,task_id,shape,aggregations):
        """
        classify whether clusters are true or false positives
        i.e. whether each cluster corresponds to something which actually exists

        return in json format so we can merge with other results
        :return:
        """
        # pretentious name but basically whether each person who has seen a subject thinks it is a true
        # positive or not
        existence_classification = {"param":"subject_id"}

        global_cluster_index = 0
        # clusters_per_subject = []

        # look at the individual points in the cluster
        for subject_id in aggregations.keys():
            if subject_id == "param":
                continue

            # if no one did this task for this subject
            if task_id not in aggregations[subject_id]:
                continue

            if (shape+ " clusters") not in aggregations[subject_id][task_id]:
                # if none of the relevant markings were made on this subject, skip it
                continue

            all_users = aggregations[subject_id][task_id][shape+ " clusters"]["all_users"]

            for local_cluster_index in aggregations[subject_id][task_id][shape+ " clusters"]:
                if local_cluster_index == "all_users":
                    continue

                # extract the users who marked this cluster
                cluster = aggregations[subject_id][task_id][shape+ " clusters"][local_cluster_index]

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


        existence_results = self.__task_aggregation__(existence_classification,task_id,{})#,mapped_gold_standard)
        assert isinstance(existence_results,dict)

        for subject_id,cluster_index in existence_results:
            new_results = existence_results[(subject_id,cluster_index)][task_id]

            aggregations[subject_id][task_id][shape + " clusters"][cluster_index]["existence"] = new_results


        return aggregations

    def __tool_classification__(self,task_id,shape,aggregations):
        """
        for a given task/shape figure out the most likely tool to have created each cluster
        """

        for subject_id in aggregations:
            if task_id not in aggregations[subject_id]:
                continue

            for cluster_index,cluster in aggregations[subject_id][task_id][shape+ " clusters"].items():
                # all_users just gives us a list of all of the users who have seen this subject
                # not relevant here
                if cluster_index == "all_users":
                    continue

                most_likely_tool,percentage,sorted_tools = self.__most_likely_tool__(cluster)
                aggregations[subject_id][task_id][shape + " clusters"][cluster_index]["most_likely_tool"] = most_likely_tool
                aggregations[subject_id][task_id][shape + " clusters"][cluster_index]["percentage"] = percentage
                # aggregations[subject_id][task_id][shape + " clusters"][cluster_index]["sorted_tools"] = sorted_tools

        return aggregations

    def __aggregate__(self,raw_classifications,workflow,aggregations,workflow_id):
        # use the first subject_id to find out which tasks we are aggregating the classifications for
        # aggregations = {}
        classification_tasks,marking_tasks,_ = workflow

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

                # figure out the most likely tool to have created this cluster (since up until now we've only cared
                # about shape, not tool). Polygons are handled differently - will be in the blob clustering code
                # since polygon aggregation isn't really clustering
                if shape != "polygon":
                    aggregations = self.__tool_classification__(task_id,shape,aggregations)

        # now go through the normal classification aggregation stuff
        # which can include follow up questions
        for task_id in classification_tasks:
            # just a normal classification question
            if classification_tasks[task_id] in ["single","multiple"]:
                # did anyone actually do this classification?
                if task_id in raw_classifications:

                    aggregations = self.__task_aggregation__(raw_classifications[task_id],task_id,aggregations)

            else:
                # we have a follow up classification
                aggregations = self.__subtask_classification__(task_id,classification_tasks,marking_tasks,raw_classifications,aggregations)

        return aggregations


class VoteCount(Classification):
    def __init__(self,environment,param_dict):
        Classification.__init__(self,environment)

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

        for subject_id in raw_classifications:
            vote_counts = {}
            if subject_id == "param":
                continue

            for user,ballot in raw_classifications[subject_id]:
                if ballot is None:
                    continue
                # in which case only one vote is allowed
                if isinstance(ballot,int):
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


