from __future__ import print_function
import os
import numpy
import tarfile
import math
import sys
# for sphinx documentation, there seems to be trouble with importing shapely
# so for the time being, if we can't import it, since it doesn't actually matter
# for documentation, just have all the imported things wind up being undefined
try:
    import shapely.geometry as geometry
except OSError:
    pass
import helper_functions
import numpy as np
from helper_functions import warning

__author__ = 'greg'


class CsvOut:
    def __init__(self,project):
        # assert isinstance(project,aggregation_api.AggregationAPI)
        self.project = project

        self.project_id = project.project_id
        self.instructions = project.instructions
        self.workflow_names = project.workflow_names
        self.workflows = project.workflows

        print("workflows are " + str(self.workflows))

        self.__yield_aggregations__ = project.__yield_aggregations__
        self.retirement_thresholds = project.retirement_thresholds
        self.versions = project.versions

        self.__count_subjects_classified__ = project.__count_subjects_classified__

        # stores the file names
        self.file_names = {}
        self.workflow_directories = {}

    def __detailed_row__(self,workflow_id,task_id,subject_id,aggregations,followup_id=None,tool_id=None,cluster_index=None):
        """
        given the results for a given workflow/task and subject_id (and possibly shape and follow up id for marking)
        give a detailed results with the probabilities for each class
        """
        # key for accessing the csv output file
        id_ = (task_id,tool_id,followup_id,"detailed")

        # get what percentage of users voted for each classification
        votes,num_users = aggregations[task_id]

        # if a follow up question - the answers did is in a different format
        if followup_id is not None:
            answers_dict = self.instructions[workflow_id][task_id]["tools"][tool_id]["followup_questions"][followup_id]["answers"]
        else:
            # extract the text corresponding to each answer
            answers_dict = self.instructions[workflow_id][task_id]["answers"]

        with open(self.file_names[id_],"a") as csv_file:
            csv_file.write(str(subject_id))

            if cluster_index is not None:
                csv_file.write("," + str(cluster_index))

            # pretty sure that the answers should already be sorted by numerical key value
            # but if someone has been messing around with their tasks that might not be the case
            # so play it safe - extract the answer ids and sort them
            for answer_key in sorted(answers_dict.keys()):
                # todo - double check why the keys in "votes" are strings but in answer_key they are integers
                # not the end of the world, but worth double checking
                # if no one chose this particular answer, the probability was 0
                if str(answer_key) not in votes:
                    percentage = 0
                else:
                    percentage = votes[str(answer_key)]

                csv_file.write(","+str(percentage))

            csv_file.write(","+str(num_users)+"\n")

    def __marking_followup_rows__(self,workflow_id,task_id,subject_id,aggregations):
        """
        for a given task id /subject id, handle all of the marking/cluster related outputs for follow up questions
        I had thought about this function returning the rows to add to the csv (inside of the writing happening inside
        this function) - we wouldn't needed task_id or subject_id. But this function actually writes up to multiple
        csv files (for different follow up questions) and can have an arbitrary number of rows produced
        so it seems easiest if everything happens inside the function
        :param task_id: the id of the task - used to access the relevant csv output file
        :param subject_id: used to write out to the csv file so we know what subjects each line refers to
        :param followup_questions: the list of follow up questions for every marking tool associated with this task
        :return:
        """
        # get the marking_tasks
        tasks = self.workflows[workflow_id]
        # go through each tool

        all_shapes = set(tasks['marking'][task_id])

        # go through each shape separately
        for shape in all_shapes:
            # go through all clusters of this particular shape
            relevant_aggregations=aggregations[task_id][shape + " clusters"]
            for cluster_index,cluster in relevant_aggregations.items():
                # misc. info that should be skipped
                if cluster_index == "all_users":
                    continue

                # get the tool id for this cluster (which is the most likely tool to have created this cluster)
                try:
                    tool_id = cluster["most_likely_tool"]
                except KeyError:
                    print("skipping cluster")
                    continue
                # and the follow up questions
                # first check if there are any follow questions
                if "followup_questions" not in self.instructions[workflow_id][task_id]["tools"][tool_id]:
                    continue

                followup_questions = self.instructions[workflow_id][task_id]["tools"][tool_id]["followup_questions"]

                # go through each of the follow up questions
                for followup_index in followup_questions.keys():
                    # bit of a sanity check but we may have cases where the followup questions were not done
                    if "followup_question" not in relevant_aggregations[cluster_index]:
                        continue

                    # extract the responses to this specific followup question
                    try:
                        followup_aggregations = relevant_aggregations[cluster_index]["followup_question"][str(followup_index)]
                    except KeyError:
                        raise

                    # add both detailed and summary results for this particular follow up question
                    self.__detailed_row__(workflow_id,task_id,subject_id,{task_id:followup_aggregations[:]},followup_index,tool_id,cluster_index)
                    # and repeat with summary row

                    self.__classification_summary_row__(workflow_id,task_id,subject_id,{task_id:followup_aggregations[:]},followup_index,tool_id,cluster_index)

    def __marking_summary_row__(self,workflow_id,task_id,subject_id,aggregations,given_shape):
        """
        for a given shape, print out a summary of the all corresponding clusters  - one line more subject
        each line contains a count of the the number of such clusters which at least half the people marked
        the mean and median % of people to mark each cluster and the mean and median vote % for the
        most likely tool for each cluster. These last 4 values will help determine which subjects are "hard"
        :param workflow_id:
        :param task_id:
        :param subject_id:
        :param aggregations:
        :param shape:
        :return:
        """
        relevant_tools = [tool_id for tool_id,tool_shape in enumerate(self.workflows[workflow_id][1][task_id]) if tool_shape == given_shape]
        counter = {t:{} for t in relevant_tools}
        aggreement = []

        prob_true_positive = []#{t:[] for t in relevant_tools}

        # go through every cluster with this associated shape
        for cluster_index,cluster in aggregations[task_id][given_shape + " clusters"].items():
            if cluster_index == "all_users":
                continue

            # how much agreement was their on the most likely tool?
            try:
                tool_prob = cluster["percentage"]
            except KeyError:
                continue

            aggreement.append(tool_prob)

            prob_true_positive.append(cluster["existence"][0]["1"])

            # count how many people used each marking tool int his cluster
            for u,t in zip(cluster["users"],cluster["tools"]):
                if u in counter[t]:
                    counter[t][u] += 1
                else:
                    counter[t][u] = 1

        # start off with the subject id
        row = str(subject_id) + ","
        # then add how often, on average, each tool marking was used
        for tool_id in sorted(counter.keys()):
            tool_count = counter[tool_id].values()
            if tool_count == []:
                row += "0,"
            else:
                row += str(numpy.median(tool_count)) + ","

        # if prob_true_positive == [] there were no clusters in the image
        # each the image was blank and there were no clusters at all - or none of them met the threshold of
        # 3 users per cluster
        # todo - might drop that 3 markings cluster threshold and report everything - let the researchers decide
        if prob_true_positive == []:
            row += "NA,NA,"
        else:
            row += str(numpy.mean(prob_true_positive)) + "," + str(numpy.median(prob_true_positive)) + ","

        # report how often people were in agreement about the tools used for each cluster
        # again, if there were no clusters at all - just report NA
        if aggreement == []:
            row += "NA,NA"
        else:

            row += str(numpy.mean(aggreement)) + "," + str(numpy.median(aggreement))

        id_ = task_id,given_shape,"summary"
        with open(self.file_names[id_],"a") as csv_file:
            csv_file.write(row + "\n")

    def __add_polygon_summary_row__(self,workflow_id,task_id,subject_id,aggregations):
        """
        print out a csv summary of the polygon aggregations (so not the individual xy points)
        need to know the workflow and task id so we can look up the instructions
        that way we can know if there is no output for a given tool - that tool wouldn't appear
        at all in the aggregations
        """
        polygon_tools = [t_index for t_index,t in enumerate(self.workflows[workflow_id][1][task_id]) if t == "polygon"]

        total_area = {t:0 for t in polygon_tools}

        id_ = task_id,"polygon","summary"
        for p_index,cluster in aggregations["polygon clusters"].items():
            if p_index == "all_users":
                continue

            tool_classification = cluster["tool_classification"][0].items()
            most_likely_tool,tool_probability = max(tool_classification, key = lambda x:x[1])
            total_area[int(most_likely_tool)] += cluster["area"]

        row = str(subject_id)
        for t in sorted([int(t) for t in polygon_tools]):
            row += ","+ str(total_area[t])

        with open(self.file_names[id_],"a") as csv_file:
            csv_file.write(row + "\n")

    def __classification_summary_row__(self,workflow_id,task_id,subject_id,aggregations,followup_id=None,tool_id = None,cluster_index=None):
        """
        given a result for a specific subject (and possibily a specific cluster within that specific subject)
        add one row of results to the summary file. that row contains
        subject_id,tool_index,cluster_index,most_likely,p(most_likely),shannon_entropy,mean_agreement,median_agreement,num_users
        tool_index & cluster_index are only there if we have a follow up to marking task
        :param id_:
        :param subject_id:
        :param results:
        :param answer_dict:
        :return:
        """
        # key for accessing the csv output in the dictionary
        id_ = (task_id,tool_id,followup_id,"summary")

        # get what percentage of users voted for each classification
        votes,num_users = aggregations[task_id]

        try:
            most_likely,top_probability = max(votes.items(), key = lambda x:x[1])

            # if tool_id is not None -> we have a follow up question
            # extract the text corresponding to the most likely answer
            # follow up questions for markings with have a different structure
            if tool_id is not None:
                answers = self.instructions[workflow_id][task_id]["tools"][tool_id]["followup_questions"][followup_id]["answers"]
                most_likely_label = answers[int(most_likely)]["label"]
            else:
                most_likely_label = self.instructions[workflow_id][task_id]["answers"][int(most_likely)]

            # and get rid of any bad characters
            most_likely_label = helper_functions.csv_string(most_likely_label)

            # calculate some summary values such as entropy and mean and median percentage of votes for each classification
            probabilities = votes.values()
            entropy = self.__shannon_entropy__(probabilities)

            mean_p = np.mean(votes.values())
            median_p = np.median(votes.values())

            with open(self.file_names[id_],"a") as results_file:
                results_file.write(str(subject_id)+",")

                if cluster_index is not None:
                    results_file.write(str(cluster_index)+",")

                # write out details regarding the top choice
                # this might not be a useful value if multiple choices are allowed - in which case just ignore it
                results_file.write(str(most_likely_label)+","+str(top_probability))
                # write out some summaries about the distributions of people's answers
                # again entropy probably only makes sense if only one answer is allowed
                # and mean_p and median_p probably only make sense if multiple answers are allowed
                # so people will need to pick and choose what they want
                results_file.write(","+str(entropy)+","+str(mean_p)+","+str(median_p))
                # finally - how many people have seen this subject for this task
                results_file.write(","+str(num_users)+"\n")
        # empty values should be ignored - but shouldn't happen too often either
        except ValueError:
            pass

    def __classification_file_setup__(self,output_directory,workflow_id):
        """
        create headers in the csv files - for both summary file and detailed results files for a given workflow/task
        :param output_directory:
        :param workflow_id:
        :param task_id:
        :param tool_id: if not None - then this is a follow up question to a marking task
        :param followup_id: if not None - then this is a follow up question to a marking task
        :return:
        """
        tasks = self.workflows[workflow_id]

        # go through the classification tasks - they will either be simple c. tasks (one answer allowed)
        # multiple c. tasks (more than one answer allowed) and possibly a follow up question to a marking
        for task_id in tasks['classification']:
            # is this task a simple classification task?
            # don't care if the questions allows for multiple answers, or requires a single one
            if tasks['classification'][task_id] in ["single","multiple"]:
                self.__detailed_classification_file_setup__(output_directory,workflow_id,task_id)
                self.__summary_classification_file_setup__(output_directory,workflow_id,task_id)

            else:
                # this classification task is actually a follow up to a marking task
                for tool_id in tasks['classification'][task_id]:
                    for followup_id,answer_type in enumerate(tasks['classification'][task_id][tool_id]):
                        self.__detailed_classification_file_setup__(output_directory,workflow_id,task_id,tool_id,followup_id)
                        self.__summary_classification_file_setup__(output_directory,workflow_id,task_id,tool_id,followup_id)

    def __detailed_classification_file_setup__(self,output_directory,workflow_id,task_id,tool_id=None,followup_id=None):
        """
        create a csv file for the detailed results of a classification task and set up the headers
        :param output_directory:
        :param workflow_id:
        :param task_id:
        :param tool_id:
        :param followup_id:
        :return:
        """
        # the file name will be based on the task label - which we need to make sure isn't too long and doesn't
        # have any characters which might cause trouble, such as spaces
        fname = self.__get_filename__(workflow_id,task_id,tool_id=tool_id,followup_id=followup_id)

        # start with the detailed results
        id_ = (task_id,tool_id,followup_id,"detailed")
        self.file_names[id_] = output_directory+fname

        # open the file and add the column headers
        with open(output_directory+fname,"wb") as detailed_results:
            # now write the headers
            detailed_results.write("subject_id")

            # the answer dictionary is structured differently for follow up questions markings
            if tool_id is not None:
                # if a follow up question - we will also add a column for the cluster id
                detailed_results.write(",cluster_id")

                answer_dict = dict()
                answers = self.instructions[workflow_id][task_id]["tools"]
                answers = answers[tool_id]["followup_questions"][followup_id]
                answers = answers.get("answers", {})

                for answer_key, answer in answers.items():
                    answer_dict[answer_key] = answer["label"]
            else:
                answer_dict = self.instructions[workflow_id][task_id]["answers"]

            # each possible response will have a separate column - this column will be the percentage of people
            # who selected a certain response. This works whether a single response or multiple ones are allowed
            for answer_key in sorted(answer_dict.keys()):
                # break this up into multiple lines so we can be sure that the answers are sorted correctly
                # order might not matter in the end, but just to be sure
                answer = answer_dict[answer_key]
                answer_string = helper_functions.csv_string(answer)[:50]
                detailed_results.write(",p("+answer_string+")")

            # the final column will give the number of user
            # for follow up question - num_users should be the number of users with markings in the cluster
            detailed_results.write(",num_users\n")

    def __detailed_marking_row__(self,workflow_id,task_id,subject_id,aggregations,shape):
        """
        output for line segments
        :param workflow_id:
        :param task_id:
        :param subject_id:
        :param aggregations:
        :return:
        """
        id_ = (task_id,shape,"detailed")

        for cluster_index,cluster in aggregations[shape + " clusters"].items():
            if cluster_index == "all_users":
                continue
            # convert to int - not really sure why but get stored as unicode
            cluster_index = int(cluster_index)

            # build up the row bit by bit to have the following structure
            # "subject_id,most_likely_tool,x,y,p(most_likely_tool),p(true_positive),num_users"
            row = str(subject_id)+","
            # todo for now - always give the cluster index
            row += str(cluster_index)+","

            # extract the most likely tool for this particular marking and convert it to
            # a string label
            # not completely sure why some clusters are missing this value but does seem to happen

            most_likely_tool = cluster["most_likely_tool"]
            # again - not sure why this percentage would be 0, but does seem to happen
            tool_probability = cluster["percentage"]
            assert tool_probability > 0

            # convert the tool into the string label
            tool_str = self.instructions[workflow_id][task_id]["tools"][int(most_likely_tool)]["marking tool"]
            row += helper_functions.csv_string(tool_str) + ","

            # get the central coordinates next
            for center_param in cluster["center"]:
                if isinstance(center_param,list) or isinstance(center_param,tuple):
                    # if we have a list, split it up into subpieces
                    for param in center_param:
                        row += str(param) + ","
                else:
                    row += str(center_param) + ","

            # add on how likely the most likely tool was
            row += str(tool_probability) + ","
            # how likely the cluster is to being a true positive and how many users (out of those who saw this
            # subject) actually marked it. For the most part p(true positive) is equal to the percentage
            # of people, so slightly redundant but allows for things like weighted voting and IBCC in the future
            prob_true_positive = cluster["existence"][0]["1"]
            num_users = cluster["existence"][1]
            row += str(prob_true_positive) + "," + str(num_users)

            with open(self.file_names[id_],"a") as csvfile:
                csvfile.write(row+"\n")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def __get_filename__(self,workflow_id,task_id,summary=False,tool_id=None,followup_id=None):
        """
        use the user's instructions to help create a file name to store the results in
        :param workflow_id:
        :param task_id:
        :param summary:
        :return:
        """
        assert (tool_id is None) or (followup_id is not None)

        # read in the instructions
        # if just a simple classification question
        if tool_id is None:
            instructions = self.instructions[workflow_id][task_id]["instruction"]
        # else a follow up question to a marking - so the instructions are stored in a sligghtly different spot
        else:
            instructions = (
                self.instructions[workflow_id][task_id]["tools"][tool_id]
                    ["followup_questions"][followup_id].get("question",  "")
            )

        fname = str(task_id) + instructions[:50]
        if summary:
            fname += "_summary"
        # get rid of any characters (like extra ","s) that could cause problems
        fname = helper_functions.csv_string(fname)
        fname += ".csv"

        return fname

    def __get_top_survey_followup__(self,votes,answers):
        """
        for a particular follow up classification question in a survey task where only one answer is allowed
        return the top/most likely classification and its associated probability
        :param aggregations:
        :return:
        """
        # list answer in decreasing order
        sorted_votes = sorted(votes.items(),key = lambda x:x[1],reverse=True)
        candidates,vote_counts = zip(*sorted_votes)

        top_candidate = candidates[0]
        percent = vote_counts[0]/float(sum(vote_counts))

        return answers[top_candidate]["label"],percent

    def __make_files__(self,workflow_id):
        """
        create all of the files necessary for this workflow
        :param workflow_id:
        :return:
        """
        # delete any reference to previous csv outputs - this means we don't have to worry about using
        # workflow ids in the keys and makes things simplier
        self.file_names = {}

        # now create a sub directory specific to the workflow
        try:
            workflow_name = self.workflow_names[workflow_id]
        except KeyError:
            warning(self.workflows)
            warning(self.workflow_names)
            raise

        # workflow names might have characters (such as spaces) which shouldn't be part of a filename, so clean up the
        # workflow names
        workflow_name = helper_functions.csv_string(workflow_name)
        output_directory = "/tmp/"+str(self.project_id)+"/" +str(workflow_id) + "_" + workflow_name + "/"

        if not os.path.exists(output_directory):
            os.makedirs(output_directory)
        self.workflow_directories[workflow_id] = output_directory

        # create the csv files for the classification tasks (both simple and follow up ones)
        self.__classification_file_setup__(output_directory,workflow_id)

        # now set things up for the marking tasks
        self.__marking_file_setup__(output_directory,workflow_id)

        self.__survey_file_setup__(output_directory,workflow_id)

        return output_directory

    def __marking_file_setup__(self,output_directory,workflow_id):
        """
        - create the csv output files for each workflow/task pairing where the task is a marking
        also write out the header line
        - since different tools (for the same task) can have completely different shapes, these shapes should
        be printed out to different files - hence the multiple output files
        - we will give both a summary file and a detailed report file
        """
        tasks = self.workflows[workflow_id]

        # iterate over each task and the shapes (not tools) available for each task
        for task_id,tools in tasks['marking'].items():
            for shape in set(tools):
                # get the file name - and remove any characters (such as spaces) which should not be in a file name
                fname = str(task_id) + self.instructions[workflow_id][task_id]["instruction"][:50]
                fname = helper_functions.csv_string(fname)

                # create the files - both detailed and summary
                self.file_names[(task_id,shape,"detailed")] = output_directory+"/"+fname + "_" + shape + ".csv"
                self.file_names[(task_id,shape,"summary")] = output_directory+"/"+fname + "_" + shape + "_summary.csv"

                # polygons - since they have an arbitary number of points are handled slightly differently
                if shape == "polygon":
                    self.__add_polygon_summary_row__()
                    self.__polygon_detailed_setup__(task_id)
                else:
                    # write the headers for the csv summary files
                    self.__marking_summary_header__(workflow_id,task_id,shape)
                    # and for the detailed
                    self.__marking_detailed_header__(task_id,shape)



    def __marking_detailed_header__(self,task_id,shape):
        """
        create the csv file headers for the detailed results
        :return:
        """
        assert shape != "polygon"

        id_ = task_id,shape,"detailed"
        with open(self.file_names[id_],"w") as csv_file:
            csv_file.write( "subject_id,cluster_index,most_likely_tool,")
            # the headers depend on the coordinates used to describe each shape
            if shape == "point":
                csv_file.write("x,y,")
            elif shape == "rectangle":
                # todo - fix this
                csv_file.write("x1,y1,x2,y2,")
            elif shape == "line":
                csv_file.write("x1,y1,x2,y2,")
            elif shape == "ellipse":
                csv_file.write("x1,y1,r1,r2,theta,")

            # how much agreement is there on the most likely tool and how likely this cluster is to be something real
            csv_file.write("p(most_likely_tool),p(true_positive),num_users\n")

    def __marking_summary_header__(self,workflow_id,task_id,shape):
        """
        setup the summary csv file for a given marking tool
        all shape aggregation will have a summary file - with one line per subject
        DON'T call this for polygons - they need to be handled differently
        :return:
        """
        assert shape != "polygon"

        id_ = task_id,shape,"summary"
        with open(self.file_names[id_],"w") as csv_file:
            # the summary file will contain just line per subject
            csv_file.write("subject_id")

            # extract only the tools which can actually make markings of the desired shape
            # [1] - is the list of marking tasks, i.e. [0] is the list of classification tasks and [2] is
            # survey tasks
            for tool_id,tool_shape in enumerate(self.workflows[workflow_id][1][task_id]):
                # does this particular tool use the desired shape?
                if tool_shape != shape:
                    continue

                # what is the label given to this tool - this is what we want to use in our column header
                # i.e. we don't want to say tool 0, or shape rectangle, we want to say "zebra"
                tool_label = self.instructions[workflow_id][task_id]["tools"][tool_id]["marking tool"]
                # remove any characters (such as spaces) which shouldn't be in a csv column header
                tool_label = helper_functions.csv_string(tool_label)

                csv_file.write(",median(" + tool_label +")")

            # as final stats to add
            csv_file.write(",mean_probability,median_probability,mean_tool,median_tool\n")


    def __polygon_detailed_setup__(self,task_id):
        """
        write out the headers for the detailed polygon output file
        slightly silly since its only one line but keeps things as in the same format as for other shapes
        :param workflow_id:
        :param task_id:
        :return:
        """
        id_ = task_id,"polygon","detailed"
        with open(self.file_names[id_],"w") as csv_file:
            csv_file.write("subject_id,cluster_index,most_likely_tool,area,list_of_xy_polygon_coordinates\n")

    def __polygon_row__(self,workflow_id,task_id,subject_id,aggregations):
        """
        print out results for a polygon - include the outline in pixels, the area (as a percentage of image area)
        and what is the most likely tool to have created this polygon
        :param workflow_id:
        :param task_id:
        :param subject_id:
        :param aggregations:
        :return:
        """
        id_ = task_id,"polygon","detailed"

        with open(self.file_names[id_],"a") as csv_file:
            for p_index,cluster in aggregations["polygon clusters"].items():
                if p_index == "all_users":
                    continue

                tool_classification = cluster["tool_classification"][0].items()
                most_likely_tool,tool_probability = max(tool_classification, key = lambda x:x[1])
                tool = self.instructions[workflow_id][task_id]["tools"][int(most_likely_tool)]["marking tool"]
                tool = helper_functions.csv_string(tool)

                row = str(subject_id) + ","+ str(p_index)+ ","+ tool + ","+ str(cluster["area"]) + ",\"" +str(cluster["center"]) + "\""

                csv_file.write(row+"\n")

    #
    #
    #
    # def __polygon_summary_setup__(self,workflow_id,task_id):
    #     """
    #     once the csv files have been created, write the headers
    #     :return:
    #     """
    #     id_ = task_id,"polygon","summary"
    #
    #     with open(self.file_names[id_],"w") as csv_file:
    #         # self.csv_files[id_].write("subject_id,\n")
    #         polygon_tools = [t_index for t_index,t in enumerate(self.workflows[workflow_id][1][task_id]) if t == "polygon"]
    #         csv_file.write("subject_id,")
    #         for tool_id in polygon_tools:
    #             tool = self.instructions[workflow_id][task_id]["tools"][tool_id]["marking tool"]
    #             tool = helper_functions.csv_string(tool)
    #             csv_file.write("area("+tool+"),")

    def __shannon_entropy__(self,probabilities):
        """
        calculate and return the shannon entropy
        :param probabilities:
        :return:
        """
        return -sum([p*math.log(p) for p in probabilities])

    def __subject_output__(self,subject_id,aggregations,workflow_id):
        """
        add csv rows for all the output related to this particular workflow/subject_id
        acts as a "dispatcher" for calling csv output for either classification tasks, marking tasks or survey tasks
        :param workflow_id:
        :param subject_id:
        :param aggregations:
        :return:
        """
        # get relevant information for this particular workflow
        tasks = self.workflows[workflow_id]
        instructions = self.instructions[workflow_id]

        # start with classification tasks
        for task_id in tasks['classification'].keys():
            # a subject might not have results for all tasks
            if task_id not in aggregations:
                continue

            # if this a marking task? - so we have follow up questions
            if task_id in tasks['marking']:
                # need the instructions for printing out labels
                followup_questions = tasks['classification'][task_id]
                self.__marking_followup_rows__(workflow_id,task_id,subject_id,aggregations)
            else:
                # we have a simple classification
                # start by output the summary
                self.__classification_summary_row__(workflow_id,task_id,subject_id,aggregations)
                self.__detailed_row__(workflow_id,task_id,subject_id,aggregations)


        for task_id,possible_shapes in tasks['marking'].items():
            for shape in set(possible_shapes):
                # not every task have been done for every aggregation
                if task_id in aggregations:
                    # polygons are different since they have an arbitrary number of points
                    if shape == "polygon":
                        self.__polygon_row__(workflow_id,task_id,subject_id,aggregations[task_id])
                        self.__add_polygon_summary_row__(workflow_id,task_id,subject_id,aggregations[task_id])
                    else:
                        self.__detailed_marking_row__(workflow_id,task_id,subject_id,aggregations[task_id],shape)
                        self.__marking_summary_row__(workflow_id,task_id,subject_id,aggregations,shape)

        for task_id in tasks['survey']:
            print(task_id)
            instructions = self.instructions[workflow_id][task_id]

            # id_ = (task_id,"summary")
            # with open(self.file_names[id_],"a") as f:
            #     summary_line = self.__survey_summary_row(aggregations)
            #     f.write(str(subject_id)+summary_line)
            # print(self.file_names.keys())
            id_ = task_id
            with open(self.file_names[id_],"a") as f:
                detailed_lines = self.__survey_row__(instructions,aggregations)
                for l in detailed_lines:
                    f.write(str(subject_id)+l)

    def __summary_classification_file_setup__(self,output_directory,workflow_id,task_id,tool_id=None,followup_id=None):
        """
        create the summary csv files and fill in the headers
        :param output_directory:
        :param workflow_id:
        :param task_id:
        :param tool_id:
        :param followup_id:
        :return:
        """
        fname = self.__get_filename__(workflow_id,task_id,summary = True,tool_id=tool_id,followup_id=followup_id)
        id_ = (task_id,tool_id,followup_id,"summary")
        self.file_names[id_] = output_directory+fname

        # add the columns
        with open(output_directory+fname,"wb") as summary_file:
            summary_file.write("subject_id,")

            # if a follow up question - we also provide cluster ids
            if tool_id is not None:
                summary_file.write("cluster_id,")

            summary_file.write("most_likely,p(most_likely),shannon_entropy,mean_agreement,median_agreement,num_users\n")

    def __survey_file_setup__(self,output_directory,workflow_id):
        """
        set up the csv files for surveys. we will just have one output file
        :param output_directory:
        :param workflow_id:
        :return:
        """
        tasks = self.workflows[workflow_id]

        for task_id in tasks['survey']:
            instructions = self.instructions[workflow_id][task_id]

            self.file_names[task_id] = output_directory+str(task_id) + ".csv"

            with open(self.file_names[task_id],"w") as csv_file:
                # now write the header
                header = "subject_id,num_classifications,pielou_score,species,"
                header += "percentage_of_votes_for_species,number_of_votes_for_species"

                # always include these headers for HWMN follow up question - these columns may be NA in output
                # but at least we have the header explaining why
                header += ",minimum_number_of_animals,most_likely_number_of_animals,percentage,maximum_number_of_animals"

                # todo - we'll assume, for now, that "how many" is always the first question
                # for followup_id in instructions["questionsOrder"]:
                for followup_id in instructions["questions"].keys():
                    multiple_answers = instructions["questions"][followup_id]["multiple"]
                    label = instructions["questions"][followup_id]["label"]

                    # the question "how many" is treated differently - we'll give the minimum, maximum and mostly likely
                    if followup_id == "HWMN":
                        continue
                    else:
                        if "behavior" in label:
                            stem = "behaviour:"
                        elif "behaviour" in label:
                            stem = "behaviour:"
                        else:
                            stem = helper_functions.csv_string(label)

                        if not multiple_answers:
                            header += ",most_likely(" + stem + ")"

                        for answer_id in instructions["questions"][followup_id]["answersOrder"]:
                            header += ",percentage(" + stem + helper_functions.csv_string(instructions["questions"][followup_id]["answers"][answer_id]["label"]) +")"

                csv_file.write(header+"\n")

    def __survey_how_many__(self,instructions,aggregations,species_id):
        """
        return the columns for the question how many animals are present in an image
        for survey tasks
        keep in mind that counts can be buckets - i.e. 10-19
        columns:
        min - the minimum number of animals anyone said
        most_likely - the bucket with the highest percentage
        percentage - how many people said the most likely
        max - the maximum number of animals anyone said
        :return:
        """

        followup_id = "HWMN"
        followup_question = instructions["questions"][followup_id]

        try:
            votes = aggregations[species_id]["followup"][followup_id].items()
        except KeyError:
            return ",NA,NA,NA,NA"
        # sort by num voters
        sorted_votes = sorted(votes,key = lambda x:x[1],reverse=True)
        candidates,vote_counts = zip(*sorted_votes)
        candidates = list(candidates)

        # top candidate is the most common response to the question of how many animals there are in the subject
        top_candidate = followup_question["answers"][candidates[0]]["label"]
        percentage = vote_counts[0]/float(sum(vote_counts))

        # what is the minimum/maximum number of animals of this species that people said were in the subject?
        answer_order = followup_question["answersOrder"]
        # resort by position in answer order
        candidates.sort(key = lambda x:answer_order.index(x))
        minimum_species = followup_question["answers"][candidates[0]]["label"]
        maximum_species = followup_question["answers"][candidates[-1]]["label"]

        return "," + str(minimum_species) + "," + str(top_candidate) + "," + str(percentage) + "," + str(maximum_species)

    def __survey_row__(self,instructions,aggregations):
        """
        for a given workflow, task and subject print one row of aggregations per species found to a csv file
        where the task correspond to a survey task
        :param workflow_id:
        :param task_id:
        :param subject_id:
        :param aggregations:
        :return:
        """
        # what we are returning (to be printed out to file elsewhere)
        rows = []

        # in dev - for a small project a few bad aggregations got into the system - so filer them out
        if max(aggregations["num species"]) == 0:
            return []

        # on average, how many species did people see?
        # note - nothing here (or empty or what ever) counts as a species - we just won't give any follow up
        # answer responses
        species_in_subject = aggregations.get("num species in image", [])

        views_of_subject = aggregations["num users"]

        pielou = aggregations["pielou index"]

        # only go through the top X species - where X is the median number of species seen
        for species_id,_ in species_in_subject:
            if species_id == "num users":
                continue

            # how many people voted for this species?
            num_votes = aggregations[species_id]["num votes"]
            percentage = num_votes/float(views_of_subject)

            # extract the species name - just to be sure, make sure that the label is "csv safe"
            species_label = helper_functions.csv_string(instructions["species"][species_id])
            row = "," + str(views_of_subject) + "," + str(pielou) + "," + species_label + "," + str(percentage) + "," + str(num_votes)

            # if there is nothing here - there are no follow up questions so just move on
            # same with FR - fire, NTHNG - nothing
            if species_id in ["NTHNGHR","NTHNG","FR"]:
                break

            # do the how many question first
            row += self.__survey_how_many__(instructions,aggregations,species_id)

            # now go through each of the other follow up questions
            # for followup_id in instructions["questionsOrder"]:
            for ii,followup_id in enumerate(instructions["questions"].keys()):
                followup_question = instructions["questions"][followup_id]

                if followup_question["label"] == "How many?":
                    # this gets dealt with separately
                    continue

                multiple_answers = instructions["questions"][followup_id]["multiple"]

                # this follow up question might not be relevant to the particular species
                if followup_id not in aggregations[species_id]["followup"]:
                    # if we do not allow for multiple answers, include blank columns for top candidate
                    # and corresponding percentage
                    if not multiple_answers:
                        row += ","

                    # add in a blank column for each follow up answer (since none of these answers are relevant)
                    for _ in instructions["questions"][followup_id]["answersOrder"]:
                        row += ","
                else:
                    votes = aggregations[species_id]["followup"][followup_id]

                    # if users are only allowed to pick a single answer - return the most likely answer
                    # but still give the individual break downs

                    if not multiple_answers:
                        votes = aggregations[species_id]["followup"][followup_id]
                        answers =(instructions["questions"][followup_id]["answers"])
                        top_candidate,percent = self.__get_top_survey_followup__(votes,answers)

                        row += "," + str(top_candidate)# + "," + str(percent)

                    for answer_id in instructions["questions"][followup_id]["answersOrder"]:

                        if answer_id in votes:
                            row += "," + str(votes[answer_id]/float(num_votes))
                        else:
                            row += ",0"

            # print(len(row.split(",")))
            # assert len(row.split(",")) == 58
            rows.append(row+"\n")

        return rows

    def __write_out__(self,subject_set = None):
        """
        create the csv outputs for a given set of workflows
        the workflows are specified by self.workflows which is determined when the aggregation engine starts
        a zipped file is created in the end
        """
        assert (subject_set is None) or isinstance(subject_set,set) or isinstance(subject_set,list)

        project_prefix = str(self.project_id)

        # create an output directory if it doesn't already exist
        if not os.path.exists("/tmp/"+str(self.project_id)):
            os.makedirs("/tmp/"+str(self.project_id))

        # go through each workflow independently
        for workflow_id in self.workflows:
            print("writing out workflow " + str(workflow_id))

            if self.__count_subjects_classified__(workflow_id) == 0:
                print("skipping due to no subjects being classified for the given workflow")
                continue

            # # create the output files for this workflow
            self.__make_files__(workflow_id)

            # results are going to be ordered by subject id (because that's how the results are stored)
            # so we can going to be cycling through task_ids. That's why we can't loop through classification_tasks etc.
            for subject_id,aggregations in self.__yield_aggregations__(workflow_id,subject_set):
                print(subject_id)
                self.__subject_output__(subject_id,aggregations,workflow_id)

        with open("/tmp/"+project_prefix+"/readme.txt", "w") as readme_file:
            readme_file.write("For documentation about the aggregation results please see https://github.com/zooniverse/aggregation/wiki/Understanding-Aggregation-Results")

        # compress the results directory
        tar_file_path = "/tmp/" + project_prefix + "_export.tar.gz"
        with tarfile.open(tar_file_path, "w:gz") as tar:
            tar.add("/tmp/"+project_prefix+"/",arcname=project_prefix)

        return tar_file_path

    # def __polygon_heatmap_output__(self,workflow_id,task_id,subject_id,aggregations):
    #     """
    #     print out regions according to how many users selected that user - so we can a heatmap
    #     of the results
    #     :param workflow_id:
    #     :param task_id:
    #     :param subject_id:
    #     :param aggregations:
    #     :return:
    #     """
    #     key = task_id+"polygon_heatmap"
    #     for cluster_index,cluster in aggregations["polygon clusters"].items():
    #         # each cluster refers to a specific tool type - so there can actually be multiple blobs
    #         # (or clusters) per cluster
    #         # not actually clusters
    #
    #         if cluster_index in ["param","all_users"]:
    #             continue
    #
    #         if cluster["tool classification"] is not None:
    #             # this result is not relevant to the heatmap
    #             continue
    #
    #         row = str(subject_id) + "," + str(cluster["num users"]) + ",\"" + str(cluster["center"]) + "\""
    #         self.csv_files[key].write(row+"\n")



if __name__ == "__main__":
    import aggregation_api
    project_id = sys.argv[1]
    project = aggregation_api.AggregationAPI(project_id,"development")

    w = CsvOut(project)
    w.__write_out__()
