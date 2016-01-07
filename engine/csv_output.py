__author__ = 'greg'
import re
import os
import numpy
import tarfile
import math
import sys
import shapely.geometry as geometry
import unicodedata

class CsvOut:
    def __init__(self,project):
        # assert isinstance(project,aggregation_api.AggregationAPI)
        self.project = project

        self.project_id = project.project_id
        self.instructions = project.instructions
        self.workflow_names = project.workflow_names
        self.workflows = project.workflows

        print "workflows are " + str(self.workflows)

        self.__yield_aggregations__ = project.__yield_aggregations__
        self.__count_check__ = project.__count_check__
        self.retirement_thresholds = project.retirement_thresholds
        self.versions = project.versions

        self.__count_subjects_classified__ = project.__count_subjects_classified__

        # dictionary to hold the output files
        self.csv_files = {}
        # stores the file names
        self.file_names = {}
        self.workflow_directories = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def __classification_output__(self,workflow_id,task_id,subject_id,aggregations):
        """
        add a row to the classifciation csv output file
        """
        # first column is the subject id
        row = str(subject_id)

        # now go through each of the possible resposnes
        for answer_index in self.instructions[workflow_id][task_id]["answers"].keys():
            # at some point the integer indices seem to have been converted into strings
            # if a value isn't there - use 0
            if str(answer_index) in aggregations[0].keys():
                row += "," + str(aggregations[0][str(answer_index)])
            else:
                row += ",0"

        # add the number of people who saw this subject
        row += "," + str(aggregations[1])
        self.csv_files[task_id].write(row+"\n")

    def __single_response_csv_header__(self,output_directory,id_,instructions):
        fname = str(id_) + instructions[:50]
        fname = self.__csv_string__(fname)
        fname += ".csv"

        self.file_names[id_] = fname
        self.csv_files[id_] = open(output_directory+fname,"wb")

        # now write the header
        self.csv_files[id_].write("subject_id,most_likely_label,p(most_likely_label),shannon_entropy,num_users\n")

    def __multi_response_csv_header__(self,output_directory,id_,instructions):
        fname = str(id_) + instructions[:50]
        fname = self.__csv_string__(fname)
        fname += ".csv"

        self.file_names[(id_,"detailed")] = fname
        self.csv_files[(id_,"detailed")] = open(output_directory+fname,"wb")

        # and now the summary now
        fname = str(id_) + instructions[:50] + "_summary"
        fname = self.__csv_string__(fname)
        fname += ".csv"

        self.file_names[(id_,"summary")] = fname
        self.csv_files[(id_,"summary")] = open(output_directory+fname,"wb")

        # now write the headers
        self.csv_files[(id_,"detailed")].write("subject_id,label,p(label),num_users\n")
        self.csv_files[(id_,"summary")].write("subject_id,mean_agreement,median_agreement,num_users\n")

    def __make_files__(self,workflow_id):
        """
        create all of the files necessary for this workflow
        :param workflow_id:
        :return:
        """
        # close any previously used files (and delete their pointers)
        for f in self.csv_files.values():
            f.close()
        self.csv_files = {}

        # now create a sub directory specific to the workflow
        workflow_name = self.workflow_names[workflow_id]
        workflow_name = self.__csv_string__(workflow_name)
        output_directory = "/tmp/"+str(self.project_id)+"/" +str(workflow_id) + "_" + workflow_name + "/"

        if not os.path.exists(output_directory):
            os.makedirs(output_directory)
        self.workflow_directories[workflow_id] = output_directory

        classification_tasks,marking_tasks,survey_tasks = self.workflows[workflow_id]

        # go through the classification tasks - they will either be simple c. tasks (one answer allowed)
        # multiple c. tasks (more than one answer allowed) and possibly a follow up question to a marking
        for task_id in classification_tasks:
            # is this task a simple classification task?
            if classification_tasks[task_id] == "single":
                instructions = self.instructions[workflow_id][task_id]["instruction"]
                self.__single_response_csv_header__(output_directory,task_id,instructions)
            elif classification_tasks[task_id] == "multiple":
                # create both a detailed view and a summary view
                instructions = self.instructions[workflow_id][task_id]["instruction"]
                self.__multi_response_csv_header__(output_directory,task_id,instructions)
            else:
                # this task is a marking task
                for tool_id in classification_tasks[task_id]:
                    for followup_index,answer_type in enumerate(classification_tasks[task_id][tool_id]):
                        instructions = self.instructions[workflow_id][task_id]["tools"][tool_id]["followup_questions"][followup_index]["question"]
                        id_ = (task_id,tool_id,followup_index)
                        if answer_type == "single":
                            self.__single_response_csv_header__(output_directory,id_,instructions)
                        else:
                            self.__multi_response_csv_header__(output_directory,id_,instructions)

        # now set things up for the marking tasks
        for task_id in marking_tasks:
            shapes = set(marking_tasks[task_id])
            self.__marking_header_setup__(workflow_id,task_id,shapes,output_directory)

        # and finally the survey tasks
        for task_id in survey_tasks:
            instructions = self.instructions[workflow_id][task_id]
            self.__survey_header_setup__(output_directory,task_id,instructions)

        return output_directory

    def __shannon_entropy__(self,probabilities):
        return -sum([p*math.log(p) for p in probabilities])

    def __multi_choice_classification_row__(self,answers,task_id,subject_id,results,cluster_index=None):
        votes,num_users = results
        if votes == {}:
            return

        for candidate,percent in votes.items():
            row = str(subject_id) + ","
            if cluster_index is not None:
                row += str(cluster_index) + ","
            # todo - figure out if both choices are needed
            if isinstance(answers[int(candidate)],dict):
                row += self.__csv_string__(answers[int(candidate)]["label"]) + "," + str(percent) + "," + str(num_users) + "\n"
            else:
                row += self.__csv_string__(answers[int(candidate)]) + "," + str(percent) + "," + str(num_users) + "\n"

            self.csv_files[(task_id,"detailed")].write(row)

        percentages = votes.values()
        mean_percent = numpy.mean(percentages)
        median_percent = numpy.median(percentages)

        row = str(subject_id) + ","
        if cluster_index is not None:
            row += str(cluster_index) + ","

        row += str(mean_percent) + "," + str(median_percent) + "," + str(num_users) + "\n"
        self.csv_files[(task_id,"summary")].write(row)

    def __single_choice_classification_row__(self,answers,task_id,subject_id,results,cluster_index=None):
        """
        output a row for a classification task which only allowed allowed one answer
        global_task_id => the task might actually be a subtask, in which case the id needs to contain
        the task id, tool and follow up question id
        :param global_task_id:
        :param subject_id:
        :param results:
        :return:
        """
        # since only one choice is allowed, go for the maximum
        votes,num_users = results
        if votes == {}:
            return
        most_likely,top_probability = max(votes.items(), key = lambda x:x[1])

        # extract the text corresponding to the most likely answer
        most_likely_label = answers[int(most_likely)]
        # this corresponds to when the question is a follow up
        if isinstance(most_likely_label,dict):
            most_likely_label = most_likely_label["label"]
        most_likely_label = self.__csv_string__(most_likely_label)

        probabilities = votes.values()
        entropy = self.__shannon_entropy__(probabilities)

        row = str(subject_id)+","
        if cluster_index is not None:
            row += str(cluster_index) + ","
        row += most_likely_label+","+str(top_probability)+","+str(entropy)+","+str(num_users)+"\n"

        # finally write the stuff out to file
        self.csv_files[task_id].write(row)

    def __subject_output__(self,workflow_id,subject_id,aggregations):
        """
        add csv rows for all the output related to this particular workflow/subject_id
        :param workflow_id:
        :param subject_id:
        :param aggregations:
        :return:
        """
        # if self.__count_check__(workflow_id,subject_id) < self.retirement_thresholds[workflow_id]:
        #     return

        classification_tasks,marking_tasks,survey_tasks = self.workflows[workflow_id]

        for task_id,task_type in classification_tasks.items():
            # a subject might not have results for all tasks
            if task_id not in aggregations:
                continue

            # we have follow up questions
            if isinstance(task_type,dict):
                for tool_id in task_type:
                    for followup_index,answer_type in enumerate(task_type[tool_id]):
                        # what sort of shape are we looking for - help us find relevant clusters
                        shape = self.workflows[workflow_id][1][task_id][tool_id]
                        for cluster_index,cluster in aggregations[task_id][shape + " clusters"].items():
                            if cluster_index == "all_users":
                                continue

                            classification = cluster["tool_classification"][0]
                            most_likely_tool,_ = max(classification.items(),key = lambda x:x[1])

                            # only consider clusters which most likely correspond to the correct tool
                            if int(most_likely_tool) != int(tool_id):
                                continue

                            possible_answers = self.instructions[workflow_id][task_id]["tools"][tool_id]["followup_questions"][followup_index]["answers"]
                            if "followup_question" not in aggregations[task_id][shape + " clusters"][cluster_index]:
                                print "missing follow up response"
                                continue

                            try:
                                results = aggregations[task_id][shape + " clusters"][cluster_index]["followup_question"][str(followup_index)]
                            except KeyError:
                                print aggregations[task_id][shape + " clusters"][cluster_index]
                                raise
                            id_ = task_id,tool_id,followup_index
                            if answer_type == "single":
                                self.__single_choice_classification_row__(possible_answers,id_,subject_id,results,cluster_index)
                            else:
                                self.__multi_choice_classification_row__(possible_answers,id_,subject_id,results,cluster_index)
            else:
                answers = self.instructions[workflow_id][task_id]["answers"]
                results = aggregations[task_id]
                print "workflow id is " + str(workflow_id)
                if task_type == "single":
                    answers = self.instructions[workflow_id][task_id]["answers"]
                    self.__single_choice_classification_row__(answers,task_id,subject_id,results)
                else:
                    self.__multi_choice_classification_row__(answers,task_id,subject_id,results)

        for task_id,possible_shapes in marking_tasks.items():
            for shape in set(possible_shapes):
                # not every task have been done for every aggregation
                if task_id in aggregations:
                    if shape == "polygon":
                        self.__polygon_row__(workflow_id,task_id,subject_id,aggregations[task_id])
                        self.__polygon_summary_output__(workflow_id,task_id,subject_id,aggregations[task_id])
                    else:
                        self.__marking_row__(workflow_id,task_id,subject_id,aggregations[task_id],shape)
                        self.__shape_summary_output__(workflow_id,task_id,subject_id,aggregations,shape)

        for task_id in survey_tasks:
            # print aggregations
            self.__survey_row__(workflow_id,task_id,subject_id,aggregations)

    def __survey_header_setup__(self,output_directory,task_id,instructions):
        """
        create the csv output file for a survey task
        and give the header row
        :param output_directory:
        :param task_id:
        :param instructions:
        :return:
        """
        fname = str(task_id) + "_survey"
        fname += ".csv"

        self.file_names[task_id] = fname
        self.csv_files[task_id] = open(output_directory+fname,"wb")

        # now write the header
        header = "subject_id,num_classifications,species"

        # todo - we'll assume, for now, that "how many" is always the first question
        for followup_id in instructions["questionsOrder"]:
            multiple_answers = instructions["questions"][followup_id]["multiple"]
            label = instructions["questions"][followup_id]["label"]

            # the question "how many" is treated differently - we'll give the minimum, maximum and mostly likely
            if followup_id == "HWMN":
                header += ",minimum_number_of_animals,most_likely_number_of_animals,percentage,maximum_number_of_animals"
            elif multiple_answers:
                if "behavior" in label:
                    stem = "behaviour:"
                elif "behaviour" in label:
                    stem = "behaviour:"
                else:
                    stem = self.__csv_string__(label)

                for answer_id in instructions["questions"][followup_id]["answersOrder"]:
                    header += "," + stem + self.__csv_string__(instructions["questions"][followup_id]["answers"][answer_id]["label"])

            else:
                # we have a followup question with just one answer allowed
                header += ","+ self.__csv_string__(instructions["questions"][followup_id]["label"]) + ",percentage"

        self.csv_files[task_id].write(header+"\n")

    def __survey_row__(self,workflow_id,task_id,subject_id,aggregations):
        """
        for a given workflow, task and subject print one row of aggregations per species found to a csv file
        where the task correspond to a survey task
        :param workflow_id:
        :param task_id:
        :param subject_id:
        :param aggregations:
        :return:
        """

        for species_id in aggregations:
            if species_id == "num_users":
                continue

            species_label = self.__csv_string__(self.instructions[workflow_id][task_id]["species"][species_id])
            row = str(subject_id) + "," + str(aggregations["num_users"]) + "," + self.__csv_string__(species_label)

            for followup_id in self.instructions[workflow_id][task_id]["questionsOrder"]:
                followup_question = self.instructions[workflow_id][task_id]["questions"][followup_id]

                # not every question is going to be asked of every species
                if followup_id not in aggregations[species_id]:
                    continue

                if followup_question["multiple"]:
                    votes = aggregations[species_id][followup_id]
                    total_votes = sum(votes.values())
                    for answer_id in self.instructions[workflow_id][task_id]["questions"][followup_id]["answersOrder"]:
                        if answer_id in votes:
                            row += "," + str(votes[answer_id]/float(total_votes))
                        else:
                            row += ",0"
                else:
                    votes = aggregations[species_id][followup_id].items()
                    top_candidate,num_votes = sorted(votes,key = lambda x:x[1])[0]
                    percent = num_votes/float(sum(aggregations[species_id][followup_id].values()))
                    if followup_question["label"] == "How many?":
                        # what is the maximum answer given - because of bucket ranges (e.g. 10+ or 10 to 15)
                        # we can't just convert the bucket labels into numerical values
                        # first map from labels to indices
                        votes_indices = [followup_question["answersOrder"].index(v) for (v,c) in votes]
                        maximum_species = followup_question["answersOrder"][max(votes_indices)]
                        minimum_species = followup_question["answersOrder"][min(votes_indices)]

                        row += "," + minimum_species + ","+str(top_candidate)+","+str(percent)+","+maximum_species
                    else:
                        # for any other follow up question (without just one answer) just give the most likely
                        # answer and the percentage
                        label = followup_question["answers"][top_candidate]["label"]
                        row += "," + label + "," + str(percent)

            self.csv_files[task_id].write(row+"\n")



    def __polygon_row__(self,workflow_id,task_id,subject_id,aggregations):
        id_ = task_id,"polygon","detailed"

        # for p_index,cluster in aggregations["polygon clusters"].items():
        #     if p_index == "all_users":
        #         continue
        #
        #     tool_classification = cluster["tool_classification"][0].items()
        #     most_likely_tool,tool_probability = max(tool_classification, key = lambda x:x[1])
        #     total_area[int(most_likely_tool)] += cluster["area"]

        for p_index,cluster in aggregations["polygon clusters"].items():
            if p_index == "all_users":
                continue

            tool_classification = cluster["tool_classification"][0].items()
            most_likely_tool,tool_probability = max(tool_classification, key = lambda x:x[1])
            tool = self.instructions[workflow_id][task_id]["tools"][int(most_likely_tool)]["marking tool"]
            tool = self.__csv_string__(tool)

            for polygon in cluster["center"]:
                p = geometry.Polygon(polygon)

                row = str(subject_id) + ","+ str(p_index)+ ","+ tool + ","+ str(p.area/float(cluster["image area"])) + ",\"" +str(polygon) + "\""
                self.csv_files[id_].write(row+"\n")

    def __write_out__(self,subject_set = None,compress=True):
        """
        create the csv outputs for a given set of workflows
        the workflows are specified by self.workflows which is determined when the aggregation engine starts
        a zipped file is created in the end
        """
        assert (subject_set is None) or isinstance(subject_set,int)

        project_prefix = str(self.project_id)

        # with open("/tmp/"+str(self.project_id)+"/readme.md", "w") as readme_file:
        #     readme_file.truncate()

        if not os.path.exists("/tmp/"+str(self.project_id)):
            os.makedirs("/tmp/"+str(self.project_id))

        # go through each workflow indepedently
        for workflow_id in self.workflows:
            print "writing out workflow " + str(workflow_id)

            if self.__count_subjects_classified__(workflow_id) == 0:
                print "skipping due to no subjects being classified for the given workflow"
                continue

            # # create the output files for this workflow
            self.__make_files__(workflow_id)

            # results are going to be ordered by subject id (because that's how the results are stored)
            # so we can going to be cycling through task_ids. That's why we can't loop through classification_tasks etc.
            for subject_id,aggregations in self.__yield_aggregations__(workflow_id,subject_set):
                self.__subject_output__(workflow_id,subject_id,aggregations)

        for f in self.csv_files.values():
            f.close()

        # # add some final details to the read me file

        try:
            with open("/tmp/"+project_prefix+"/readme.md", "w") as readme_file:
                # readme_file.write("Details and food for thought:\n")
                with open(os.getcwd()+"/readme.txt","rb") as f:
                    text = f.readlines()
                    for l in text:
                        readme_file.write(l)
        except IOError:

            with open("/tmp/"+project_prefix+"/readme.md", "w") as readme_file:
                readme_file.write("There are no retired subjects for this project")

        if compress:
            tar_file_path = "/tmp/" + project_prefix + "_export.tar.gz"
            with tarfile.open(tar_file_path, "w:gz") as tar:
                tar.add("/tmp/"+project_prefix+"/")

            return tar_file_path

    def __csv_string__(self,string):
        """
        remove or replace all characters which might cause problems in a csv template
        :param str:
        :return:
        """
        if type(string) == unicode:
            string = unicodedata.normalize('NFKD', string).encode('ascii','ignore')
        string = re.sub(' ', '_', string)
        string = re.sub(r'\W+', '', string)

        return string

    def __marking_row__(self,workflow_id,task_id,subject_id,aggregations,shape):
        """
        output for line segments
        :param workflow_id:
        :param task_id:
        :param subject_id:
        :param aggregations:
        :return:
        """
        key = task_id,shape,"detailed"
        for cluster_index,cluster in aggregations[shape + " clusters"].items():
            if cluster_index == "all_users":
                continue

            # build up the row bit by bit to have the following structure
            # "subject_id,most_likely_tool,x,y,p(most_likely_tool),p(true_positive),num_users"
            row = str(subject_id)+","
            # todo for now - always give the cluster index
            row += str(cluster_index)+","

            # extract the most likely tool for this particular marking and convert it to
            # a string label
            try:
                tool_classification = cluster["tool_classification"][0].items()
            except KeyError:
                print shape
                print cluster
                raise
            most_likely_tool,tool_probability = max(tool_classification, key = lambda x:x[1])
            tool_str = self.instructions[workflow_id][task_id]["tools"][int(most_likely_tool)]["marking tool"]
            row += self.__csv_string__(tool_str) + ","

            # get the central coordinates next
            for center_param in cluster["center"]:
                if isinstance(center_param,list) or isinstance(center_param,tuple):
                    row += "\"" + str(tuple(center_param)) + "\","
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
            self.csv_files[key].write(row+"\n")

    def __shape_summary_output__(self,workflow_id,task_id,subject_id,aggregations,given_shape):
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

        for cluster_index,cluster in aggregations[task_id][given_shape + " clusters"].items():
            if cluster_index == "all_users":
                continue

            # how much agreement was their on the most likely tool?
            tool_classification = cluster["tool_classification"][0].items()
            most_likely_tool,tool_prob = max(tool_classification, key = lambda x:x[1])
            aggreement.append(tool_prob)

            prob_true_positive.append(cluster["existence"][0]["1"])

            for u,t in zip(cluster["users"],cluster["tools"]):
                if u in counter[t]:
                    counter[t][u] += 1
                else:
                    counter[t][u] = 1

            # print


        # # start by figuring all the points which correspond to the desired type
        # cluster_count = {}
        # for tool_id in sorted(self.instructions[workflow_id][task_id]["tools"].keys()):
        #     tool_id = int(tool_id)
        #
        #     assert task_id in self.workflows[workflow_id][1]
        #     shape = self.workflows[workflow_id][1][task_id][tool_id]
        #     if shape == given_shape:
        #         cluster_count[tool_id] = 0
        #
        # # now go through the actual clusters and count all which at least half of everyone has marked
        # # or p(existence) >= 0.5 which is basically the same thing unless you've used weighted voting, IBCC etc.
        # for cluster_index,cluster in aggregations[task_id][given_shape + " clusters"].items():
        #     if cluster_index == "all_users":
        #         continue
        #
        #     prob_true_positive = cluster["existence"][0]["1"]
        #     if prob_true_positive > 0.5:
        #         tool_classification = cluster["tool_classification"][0].items()
        #         most_likely_tool,tool_prob = max(tool_classification, key = lambda x:x[1])
        #         all_tool_prob.append(tool_prob)
        #         cluster_count[int(most_likely_tool)] += 1
        #
        #     # keep track of this no matter what the value is
        #     all_exist_probability.append(prob_true_positive)

        row = str(subject_id) + ","
        for tool_id in sorted(counter.keys()):
            tool_count = counter[tool_id].values()
            if tool_count == []:
                row += "0,"
            else:
                row += str(numpy.median(tool_count)) + ","

        if prob_true_positive == []:
            row += "NA,NA,"
        else:
            row += str(numpy.mean(prob_true_positive)) + "," + str(numpy.median(prob_true_positive)) + ","

        if aggreement == []:
            row += "NA,NA"
        else:

            row += str(numpy.mean(aggreement)) + "," + str(numpy.median(aggreement))



        # # if there were no clusters found (at least which met the threshold) use empty columns
        # if all_exist_probability == []:
        #     row += ",,"
        # else:
        #     row += str(numpy.mean(all_exist_probability)) + "," + str(numpy.median(all_exist_probability)) + ","
        #
        # if all_tool_prob == []:
        #     row += ","
        # else:
        #     row += str(numpy.mean(all_tool_prob)) + "," + str(numpy.median(all_tool_prob))
        #
        id_ = task_id,given_shape,"summary"
        self.csv_files[id_].write(row+"\n")

    def __marking_header_setup__(self,workflow_id,task_id,shapes,output_directory):
        """
        - create the csv output files for each workflow/task pairing where the task is a marking
        also write out the header line
        - since different tools (for the same task) can have completely different shapes, these shapes should
        be printed out to different files - hence the multiple output files
        - we will give both a summary file and a detailed report file
        """
        for shape in shapes:
            fname = str(task_id) + self.instructions[workflow_id][task_id]["instruction"][:50]
            fname = self.__csv_string__(fname)
            # fname += ".csv"


            self.file_names[(task_id,shape,"detailed")] = fname + "_" + shape + ".csv"
            self.file_names[(task_id,shape,"summary")] = fname + "_" + shape + "_summary.csv"

            # polygons - since they have an arbitary number of points are handled slightly differently
            if shape == "polygon":
                id_ = task_id,shape,"detailed"
                self.csv_files[id_] = open(output_directory+fname+"_"+shape+".csv","wb")
                self.csv_files[id_].write("subject_id,cluster_index,most_likely_tool,area,list_of_xy_polygon_coordinates\n")

                id_ = task_id,shape,"summary"
                self.csv_files[id_] = open(output_directory+fname+"_"+shape+"_summary.csv","wb")
                # self.csv_files[id_].write("subject_id,\n")
                polygon_tools = [t_index for t_index,t in enumerate(self.workflows[workflow_id][1][task_id]) if t == "polygon"]
                header = "subject_id,"
                for tool_id in polygon_tools:
                    tool = self.instructions[workflow_id][task_id]["tools"][tool_id]["marking tool"]
                    tool = self.__csv_string__(tool)
                    header += "area("+tool+"),"
                print header
                self.csv_files[id_].write(header+"\n")

            else:
                id_ = task_id,shape,"detailed"
                # fname += "_"+shape+".csv"
                self.csv_files[id_] = open(output_directory+fname+"_"+shape+".csv","wb")

                header = "subject_id,cluster_index,most_likely_tool,"
                if shape == "point":
                    header += "x,y,"
                elif shape == "rectangle":
                    # todo - fix this
                    header += "x1,y1,x2,y2,"
                elif shape == "line":
                    header += "x1,y1,x2,y2,"
                elif shape == "ellipse":
                    header += "x1,y1,r1,r2,theta,"

                header += "p(most_likely_tool),p(true_positive),num_users"
                self.csv_files[id_].write(header+"\n")
                # do the summary output else where
                self.__summary_header_setup__(output_directory,workflow_id,fname,task_id,shape)

    def __summary_header_setup__(self,output_directory,workflow_id,fname,task_id,shape):
        """
        all shape aggregation will have a summary file - with one line per subject
        :return:
        """
        # the summary file will contain just line per subject
        id_ = task_id,shape,"summary"
        self.csv_files[id_] = open(output_directory+fname+"_"+shape+"_summary.csv","wb")
        header = "subject_id"
        # extract only the tools which can actually make point markings
        for tool_id in sorted(self.instructions[workflow_id][task_id]["tools"].keys()):
            tool_id = int(tool_id)
            # self.workflows[workflow_id][0] is the list of classification tasks
            # we want [1] which is the list of marking tasks
            found_shape = self.workflows[workflow_id][1][task_id][tool_id]
            if found_shape == shape:
                tool_label = self.instructions[workflow_id][task_id]["tools"][tool_id]["marking tool"]
                tool_label = self.__csv_string__(tool_label)
                header += ",median(" + tool_label +")"
        header += ",mean_probability,median_probability,mean_tool,median_tool"
        self.csv_files[id_].write(header+"\n")

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

    def __polygon_summary_output__(self,workflow_id,task_id,subject_id,aggregations):
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

        self.csv_files[id_].write(row+"\n")

if __name__ == "__main__":
    import aggregation_api
    project_id = sys.argv[1]
    project = aggregation_api.AggregationAPI(project_id,"development")

    w = CsvOut(project)
    w.__write_out__()