__author__ = 'greg'
import clustering
import ouroboros_api
import os
import re
import matplotlib.pyplot as plt
import networkx as nx
import itertools
import ibcc
import abc

def findsubsets(S,m):
    return set(itertools.combinations(S, m))

class Classification:
    def __init__(self,project,clustering_alg=None):
        # assert isinstance(project,ouroboros_api.OuroborosAPI)
        self.project = project

        if clustering_alg is not None:
            assert isinstance(clustering_alg,clustering.Cluster)
        self.cluster_alg = clustering_alg

        current_directory = os.getcwd()
        slash_indices = [m.start() for m in re.finditer('/', current_directory)]
        self.base_directory = current_directory[:slash_indices[2]+1]
        # print self.base_directory

        self.species = {"lobate":0,"larvaceanhouse":0,"salp":0,"thalasso":0,"doliolidwithouttail":0,"rocketthimble":1,"rockettriangle":1,"siphocorncob":1,"siphotwocups":1,"doliolidwithtail":1,"cydippid":2,"solmaris":2,"medusafourtentacles":2,"medusamorethanfourtentacles":2,"medusagoblet":2,"beroida":3,"cestida":3,"radiolariancolonies":3,"larvacean":3,"arrowworm":3,"shrimp":4,"polychaeteworm":4,"copepod":4}
        self.candidates = self.species.keys()
        self.results = {}

    @abc.abstractmethod
    def __task_aggregation__(self,classifications,gold_standard=False):
        pass

    def __aggregate__(self,raw_classifications,workflow,clustering_results=None):
        # use the first subject_id to find out which tasks we are aggregating the classifications for
        self.results = {}
        classification_tasks,marking_tasks = workflow

        for task_id in classification_tasks:
            # print task_id
            if isinstance(classification_tasks[task_id],bool):
                # filtered_classifications = {subject_id:classifications[subject_id][task_id] for subject_id in classifications if task_id in classifications[subject_id]}
                task_results = self.__task_aggregation__(raw_classifications[task_id])
                assert isinstance(task_results,dict)
                for subject_id in task_results:
                    if subject_id not in self.results:
                        self.results[subject_id] = {"param":"task_id"}
                    self.results[subject_id][task_id] = task_results[subject_id]
            else:
                # # we have classifications associated with markings
                # # are these shapes "uncertain" - ie. was there more than one tool that could have made them?
                # assert isinstance(classification_tasks[task_id],dict)
                # print "====------"
                # print classification_tasks[task_id]
                # print "shapes" in classification_tasks[task_id]
                # print classification_tasks[task_id]["shapes"]
                print classification_tasks
                if "shapes" in classification_tasks[task_id]:
                    print classification_tasks[task_id]
                    # for shape in classification_tasks[task_id]["shapes"]:
                    #     # print shape
                    #     for subject_id in clustering_results[task_id][shape]:
                    #         print clustering_results[task_id][shape][subject_id]
                    #     # print clustering_results[task_id][shape]
                    #     print shape
                    #     print "hello"
                    #     assert False
                assert False
                continue
                # we have markings
                for shape in classification_tasks[task_id]:
                    # are we uncertain about the shape?
                    # did multiple tools make the same shape - if so, we need to figure out which tool
                    # is the most likely
                    if (task_id in uncertain_shapes) and (shape in uncertain_shapes[task_id]):
                        assert False

                    for follow_up_question_index in classification_tasks[task_id][shape]:
                        for subject_id in classifications:
                            # did anyone mark this shape for this task?
                            if task_id in classifications[subject_id]:
                                for cluster_index in classifications[subject_id][task_id][shape]:
                                    if cluster_index == "param":
                                        continue
                                    details = classifications[subject_id][task_id][shape][cluster_index]["details"]
                                    for user_id in details:
                                        print details[user_id]
                                        print [d["value"] for d in details[user_id] if d["value"] is not None]
                                        print
                                    tools = classifications[subject_id][task_id][shape][cluster_index]["tool"]

                    assert False
                # print classifications[temp_subject_id][task_id]

        # for subject_id in classifications:
        #     for task_id in classifications[subject_id]:
        #         if isinstance(classifications[subject_id][task_id],list):
        #             print classifications[subject_id][task_id]
        #             assert False
        #
        #             # we have a simple classification - #todo I think
        #             vote_counts = {}
        #             users,votes = zip(*classifications[subject_id][task_id])
        #             for vote in votes:
        #                 if vote in vote_counts:
        #                     vote_counts[vote] += 1
        #                 else:
        #                     vote_counts[vote] = 1
        #             print vote_counts
        #
        #             if subject_id not in self.results:
        #                 self.results[subject_id] = {"type":"task_id"}
        #
        #             most_votes = max(vote_counts,key=lambda x:vote_counts[x])
        #             percentage = vote_counts[most_votes]/float(sum(vote_counts.values()))
        #             self.results[subject_id][task_id] = most_votes,percentage
        #         else:
        #             print classifications[subject_id][task_id]
        #             assert False

class VoteCount(Classification):
    def __init__(self,project,clustering_alg=None):
        Classification.__init__(self,project,clustering_alg)

    def __task_aggregation__(self,raw_classifications,gold_standard=False):
        """
        question_id is not None if and only if the classification relates to a marking
        :param subject_ids:
        :param task_id:
        :param question_id:
        :param gold_standard:
        :return:
        """
        results = {}

        for subject_id in raw_classifications:
            vote_counts = {}
            for user,ballot in raw_classifications[subject_id]:
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

            results[subject_id] = percentages,sum(vote_counts.values())

        return results




        # for subject_id in subject_ids:
        #     if subject_id not in self.results:
        #         self.results[subject_id] = {"type":"task_id"}
        #
        #     vote_counts = {}
        #     for user,vote in self.project.__get_classifications__(subject_id,task_id,question_id):
        #         print user,vote
        #         if vote in vote_counts:
        #             vote_counts[vote] += 1
        #         else:
        #             vote_counts[vote] = 1
        #
        #     most_votes = max(vote_counts,key=lambda x:vote_counts[x])
        #     percentage = vote_counts[most_votes]/float(sum(vote_counts.values()))
        #
        #     if question_id is None:
        #         self.results[subject_id][task_id] = most_votes,percentage
        #     else:
        #         if task_id not in self.results[subject_id]:
        #             self.results[subject_id][task_id] = {"type":"marking_id"}
        #         if tool_id not in  self.results[subject_id][task_id]:
        #             self.results[subject_id][task_id][tool_id] = {"type":"question_id"}
        #
        #         self.results[subject_id][task_id][tool_id]["q"+str(question_id)] =  most_votes,percentage
        #
        #
        #
        # print self.results
        # # print self.results
        # # return self.results


class IBCC(Classification):
    def __init__(self,project,clustering_alg=None):
        Classification.__init__(self,project,clustering_alg)


    def create_configfile(self,priors,confusion_matrix):
        """
        write out the config file for running IBCC
        :return:
        """
        try:
            os.remove(self.base_directory+"Databases/plankton_ibcc.csv.dat")
        except OSError:
            pass

        num_classes = len(priors)

        with open(self.base_directory+"Databases/config.py",'wb') as f:
            f.write("import numpy as np\n")
            f.write("scores = np.array("+str(range(num_classes))+")\n")
            f.write("nScores = len(scores)\n")
            f.write("nClasses = "+str(num_classes)+"\n")
            f.write("inputFile = \""+self.base_directory+"Databases/plankton_ibcc.csv\"\n")
            f.write("outputFile = \""+self.base_directory+"Databases/plankton_ibcc.out\"\n")
            f.write("confMatFile = \""+self.base_directory+"Databases/plankton_ibcc.mat\"\n")
            # f.write("nu0 = np.array("+str([100/num_classes for i in range(num_classes)])+")\n")
            f.write("nu0 = np.array("+str([priors[s] for s in self.candidates])+")\n")
            # confusion_matrix = [[1 for i in range(num_classes)] for j in range(num_classes)]
            # for i in range(num_classes):
            #     confusion_matrix[i][i] = 20

            f.write("alpha0 = np.array("+str(confusion_matrix)+")\n")

    def __classify__(self,subject_ids,gold_standard=False):
        self.results = {}
        # might be over doing the elections analogy but can't think of a better way to describe things
        # ridings is a list of tuples (subject_ids, cluster_center) so we can match up the results from IBCC
        # if no clustering was involved (so only one classification per subject_id) then cluster_center should
        # be None
        ridings = []
        # ridings_dict stores the "ridings" by subject id - that way, we don't need to search through all
        # of the ridings, everytime we want to find the "elections" for a given subject_id
        ridings_dict = {}
        # candidates = []
        users = []
        agreement = 0
        nonagreement = 0
        notenough = 0
        # all_elections = {}
        # self.create_configfile(len(self.species))
        nclasses = len(self.species)
        nu0 = [100/nclasses for i in range(nclasses)]
        confusion_matrix = [[0.2 for i in range(nclasses)] for j in range(nclasses)]



        # classifer = ibcc.IBCC(nclasses=nclasses,nscores=nclasses,alpha0=confusion_matrix,nu0=nu0)

        priors = {s:1 for s in self.candidates}
        # confusion = [[1 for i in self.candidates] for j in self.candidates]

        # for i in range(nclasses):
        #     confusion[i][i] = 20

        with open(self.base_directory+"Databases/plankton_ibcc.csv",'wb') as f:
            f.write("a,b,c\n")
            for subject_id in subject_ids:
                # print "-----"
                # print self.project.gold_annotations[subject_id]
                self.results[subject_id] = []

                # cluster centers only make sense if we have a clustering setup - otherwise they should just be empty
                cluster_centers,polls = self.project.__get_classifications__(subject_id,cluster_alg=self.cluster_alg,gold_standard=gold_standard)

                for poll_index,(center,poll) in enumerate(zip(cluster_centers,polls)):
                    print center
                    print poll
                    print
                    # local_candidates = set()
                    vote_counts = {}
                    if len(poll) >=4:
                        # classification_counter  += 1
                        ridings.append((subject_id,center))
                        if not(subject_id in ridings_dict):
                            ridings_dict[subject_id] = [center]
                        else:
                            ridings_dict[subject_id].append(center)

                        for user,vote,pt in poll:
                            # assert isinstance(vote,unicode)
                            # local_candidates.add(vote)

                            # use majority voting to establish priors
                            if not(vote in vote_counts):
                                vote_counts[vote] = 1
                            else:
                                vote_counts[vote] += 1
                            # if not(vote in candidates):
                            #     candidates.append(vote)
                            if not(user in users):
                                users.append(user)
                            # print vote,self.species[vote.lower()],pt
                            f.write(str(users.index(user))+","+str(len(ridings)-1)+","+str(self.candidates.index(vote.lower()))+"\n")
                            # print users.index(user),classification_counter,self.candidates.index(vote)

                        most_votes = max(vote_counts,key=lambda x:vote_counts[x])
                        priors[most_votes.lower()] += 1

                        # now that we know what the majority vote estimate is, estimate the confusion matrix
                        most_votes_index = self.candidates.index(most_votes.lower())
                        for user,vote,pt in poll:
                            confusion_matrix[most_votes_index][self.candidates.index(vote.lower())] += 1/float(len(poll))

                        if len(vote_counts) ==1:
                            agreement +=1
                        else:
                            nonagreement += 1
                        # print local_candidates
                        # local_candidates = tuple(sorted(list(local_candidates)))
                        # if not(local_candidates in all_elections):
                        #     all_elections[local_candidates] = 1
                        # else:
                        #     all_elections[local_candidates] += 1
                    else:
                        notenough +=1

        # confusion_matrix = []
        print "^^^^^"
        for i,row in enumerate(confusion_matrix):
            # print c
            confusion_matrix[i] = [int(a/min(row)) for a in row]

            # print
        print
        print sum(priors.values())
        self.create_configfile(priors,confusion_matrix)

        # ibcc.runIbcc(self.base_directory+"Databases/config.py")
        ibcc.load_and_run_ibcc(self.base_directory+"Databases/config.py")
        results = {}
        with open(self.base_directory+"Databases/plankton_ibcc.out","rb") as f:
            for i,l in enumerate(f.readlines()):
                # print "===-----"
                subject_id,center = ridings[i]

                if not(subject_id in results):
                    results[subject_id] = []

                # print elections[i]
                probabilities = [float(p) for j,p in enumerate(l.split(" ")[1:])]
                results[subject_id].append(probabilities)
                # print probabilities
                # ibcc_most_likely = max(probabilities, key= lambda x:x[1])
                # print ibcc_most_likely
                # print self.candidates[ibcc_most_likely[0]]
                # self.results[subject_id].append(max(vote_counts,key=lambda x:vote_counts[x]))
        # print all_elections
        # G=nx.Graph()
        # species_keys = self.species.keys()
        # G.add_nodes_from(range(len(species_keys)))
        # for e in all_elections.keys():
        #     for a,b in findsubsets(e,2):
        #         G.add_edge(species_keys.index(a.lower()),species_keys.index(b.lower()))
        #
        # nx.draw(G)
        # plt.show()
        # print agreement,nonagreement,notenough
        return self.candidates,ridings_dict,results