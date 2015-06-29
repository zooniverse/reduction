#!/usr/bin/env python

import os
import yaml
import urllib2
import psycopg2
import cookielib
import re
import json
import cassandra
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent
import urllib
import datetime
import classification
from copy import deepcopy
import matplotlib.pyplot as plt
import matplotlib.cbook as cbook
import math
from matplotlib.patches import Ellipse
# from clustering import  cnames
# import numpy
# import datetime
import sys
from PIL import Image
import agglomerative
import cluster_count

if os.path.exists("/home/ggdhines"):
    base_directory = "/home/ggdhines"
else:
    base_directory = "/home/greg"

class InvalidMarking(Exception):
    def __init__(self,pt):
        self.pt = pt
    def __str__(self):
        return "invalid marking: " + str(self.pt)

def line_mapping(marking,image_dimensions):
    # want to extract the params x1,x2,y1,y2 but
    # ALSO make sure that x1 <= x2 and flip if necessary
    x1 = marking["x1"]
    x2 = marking["x2"]
    y1 = marking["y1"]
    y2 = marking["y2"]

    if min(x1,x2,y1,y2) < 0:
        raise InvalidMarking(marking)

    if (max(x1,x2) >= image_dimensions[0]) or (max(y1,y2) >= image_dimensions[1]):
        raise InvalidMarking(marking)

    if x1 <= x2:
        return x1,x2,y1,y2
    else:
        return x2,x1,y2,y1

def point_mapping(marking,image_dimensions):
    x = marking["x"]
    y = marking["y"]

    if (x<0)or(y<0)or(x > image_dimensions[0]) or(y>image_dimensions[1]):
        raise InvalidMarking(marking)

    return x,y

def ellipse_mapping(marking,image_dimensions):
    return marking["x"],marking["y"],marking["rx"],marking["ry"],marking["angle"]

class PanoptesAPI:
    #@profile
    def __init__(self,project):#,user_threshold= None, score_threshold= None): #Supernovae
        # # self.user_threshold = user_threshold
        # # first find out which environment we are working with
        # self.environment = os.getenv('ENVIRONMENT', "staging")
        # self.environment = "staging"

        self.project_short_name = project
        # get my userID and password
        # purely for testing, if this file does not exist, try opening on Greg's computer
        try:
            panoptes_file = open("config/aggregation.yml","rb")
        except IOError:
            panoptes_file = open(base_directory+"/Databases/aggregation.yml","rb")
        api_details = yaml.load(panoptes_file)

        # details for connecting to Panoptes
        self.user_name = api_details[project]["name"]
        self.password = api_details[project]["password"]
        self.host = api_details[project]["host"] #"https://panoptes-staging.zooniverse.org/"
        self.host_api = self.host+"api/"
        self.owner = api_details[project]["owner"] #"brian-testing" or zooniverse
        self.project_name = api_details[project]["project_name"]
        self.app_client_id = api_details[project]["app_client_id"]
        self.environment = api_details[project]["environment"]
        self.token = None

        # the http api for connecting to Panoptes
        self.http_api = None
        print "connecting to Panoptes http api"
        # set the http_api and basic project details
        self.__panoptes_connect__()

        # # details about the project we are going to work with
        try:
            self.project_id = api_details[project]["project_id"]
        except KeyError:
            self.project_id = self.__get_project_id()

        # # get the most recent workflow version
        # # todo - probably need to make sure that we only read in classifications from the most recent workflow version
        # try:
        #     self.workflow_version = api_details[project]["workflow_version"]
        # except KeyError:
        #     self.workflow_version = self.__get_workflow_version()
        #
        # try:
        #     self.workflow_id = api_details[project]["workflow_id"]
        # except KeyError:
        #     self.workflow_id = self.__get_workflow_id()
        # print self.workflow_id
        # assert False
        # assert self.workflow_id is not None



        # now connect to the Panoptes db - postgres
        try:
            database_file = open("config/database.yml")
        except IOError:
            database_file = open(base_directory+"/Databases/database.yml")

        database_details = yaml.load(database_file)
        self.postgres_session = None

        self.__postgres_connect(database_details)

        # and to the cassandra db as well
        self.__cassandra_connect()

        # there may be more than one workflow associated with a project - read them all in
        # and set up the associated tasks
        self.workflows = {}
        self.__setup_workflows__()

        # # self.task_type = {}
        # # used to extract the relevant parameters from a marking
        # self.marking_params_per_task = {}
        # # used to store the shapes per tool - useful for when we want to plot out results
        # # not strictly necessary but should make things a lot easier to understand/follow
        # self.shapes_per_tool = {}
        #
        # # cluster algorithm to be used, if any
        self.cluster_alg = None
        self.classification_alg = None
        #
        #
        # self.workflows = {}
        # self.__load_workflows__()
        # # if there is only one workflow for the project, just use that
        # # otherwise, we will need to specify which workflow we want to use
        # # self.workflow_id = None
        # # subjects don't have to be the same for all workflows for the same project - so only load the subjects
        # # if there workflow is given (e.g. there is only one workflow)
        # self.subjects = []
        # if len(self.workflows) == 1:
        #     self.workflow_id = self.workflows.keys()[0]
        #

        # load in the subjects for the project
        # self.__get_subject_ids__()

        #     # load the tasks associated with this workflow
        #     self.__task_setup__()
        #
        self.classifications = None
        self.aggregations = {}
        #
        self.marking_params_per_shape = dict()
        self.marking_params_per_shape["line"] = line_mapping
        self.marking_params_per_shape["point"] = point_mapping
        self.marking_params_per_shape["ellipse"] = ellipse_mapping

    def __aggregate__(self,workflow_id=None):
        if workflow_id is None:
            workflows = self.workflows
        else:
            workflows = [workflow_id]

        for workflow_id in workflows:
            print workflow_id
            self.__describe__(workflow_id)
            classification_tasks,marking_tasks = self.workflows[workflow_id]

            if self.cluster_alg is not None:
                print "clustering"
                self.__cluster__(workflow_id)
            if self.classification_alg is not None:
                self.__classify__(workflow_id)

    def __classify__(self,workflow_id):
        # get the raw classifications for the given workflow
        raw_classifications = self.__sort_classifications__(workflow_id)
        self.classification_alg.__aggregate__(raw_classifications,self.workflows[workflow_id],self.cluster_alg.clusterResults)

        # # set up the final aggregations - which made involve combining the classification aggregations with
        # # the marking aggregations - i.e. we get to aggregate the aggregations :)
        # if workflow_id not in self.aggregations:
        #     self.aggregations[workflow_id] = self.classification_alg.results
        # else:
        #     assert False
        #     # we must merge clustering and classification results
        #
        #         for subject_id in self.classification_alg.results:
        #             if subject_id not in self.aggregations:
        #                 self.aggregations[subject_id] = self.classification_alg.results[subject_id]
        #             else:
        #                 for task_id in self.classification_alg.results[subject_id]:
        #                     if task_id not in self.aggregations[subject_id]:
        #                         self.aggregations[subject_id][task_id] = self.classification_alg.results[subject_id][task_id]
        #                     else:
        #                         # todo - fill this in
        #                         assert False

        # print json.dumps(self.aggregations, indent=4, sort_keys=True)
        # print self.aggregations

        # for task_id in self.classification_tasks:
        #     # if we have a simple type of classification
        #     if isinstance(self.classification_tasks[task_id],bool):
        #         self.classification_alg.__classify__(self.subjects,task_id)
        #     else:
        #         assert False
        #         self.classification_alg.__classify__(self.subjects,task_id)


        #     # self.votes[subject_id] = votes_per_subject
        #     print json.dumps(classifications,indent=4,sort_keys=True)
        # return
        # # now that we gone through and extracted the annotations for each subject, go through according
        # # to question,task and tool index
        # for task_id in self.votes[subject_ids[0]]:
        #     if isinstance(self.votes[subject_ids[0]][task_id],list):
        #         self.classification_alg.__classify__(subject_ids,task_id)
        #     else:
        #         for tool_id in self.votes[subject_ids[0]][task_id].keys():
        #             for question_id in self.votes[subject_ids[0]][task_id][tool_id].keys():
        #                 self.classification_alg.__classify__(subject_ids,task_id,tool_id,question_id)


    def __cluster__(self,workflow_id):
        print "workflow id is " + str(workflow_id)
        """
        run the clustering algorithm for a given workflow
        need to have already checked that the workflow requires clustering
        :param workflow_id:
        :return:
        """
        # get the raw classifications for the given workflow
        raw_markings = self.__sort_markings__(workflow_id)
        print raw_markings
        # assert False

        self.cluster_alg.__aggregate__(raw_markings)

        self.aggregations[workflow_id] = {}

        # need to reverse order - current order is good for calculations, bad for output
        for task_id in self.cluster_alg.clusterResults:
            for shape in self.cluster_alg.clusterResults[task_id]:
                for subject_id in self.cluster_alg.clusterResults[task_id][shape]:
                    if subject_id not in self.aggregations[workflow_id]:
                        self.aggregations[workflow_id][subject_id] = {}
                    if task_id not in self.aggregations[workflow_id][subject_id]:
                        self.aggregations[workflow_id][subject_id][task_id] = {}

                    self.aggregations[workflow_id][subject_id][task_id][shape] = self.cluster_alg.clusterResults[task_id][shape][subject_id]
        print self.aggregations

    # def __set_workflow__(self,workflow_id):
    #     """
    #     set the workflow id - must be an actual workflow associated with this project
    #     :param workflow_id:
    #     :return:
    #     """
    #     assert workflow_id in self.workflows
    #     self.workflow_id = workflow_id
    #
    #     # load in the subjects specific to that workflow
    #     self.__get_subject_ids__()
    #
    #     # load the tasks associated with this workflow
    #     self.__task_setup__()




    def __cassandra_connect(self):
        """
        connect to the AWS instance of Cassandra - try 10 times and raise an error
        :return:
        """
        for i in range(10):
            try:
                self.cluster = Cluster()#['panoptes-cassandra.zooniverse.org'],protocol_version = 3)
                self.cassandra_session = self.cluster.connect('zooniverse')
                return
            except cassandra.cluster.NoHostAvailable:
                pass

        assert False

    def __chunks(self,l, n):
        """Yield successive n-sized chunks from l."""
        for i in xrange(0, len(l), n):
            yield l[i:i+n]

    def __describe__(self,workflow_id):
        select = "SELECT tasks from workflows where id = " + str(workflow_id)
        self.postgres_cursor.execute(select)
        tasks = self.postgres_cursor.fetchone()[0]

        select = "SELECT strings from workflow_contents where id = " + str(workflow_id)
        self.postgres_cursor.execute(select)
        contents = self.postgres_cursor.fetchone()[0]

        self.description = {}
        print "===---"
        for task_id in tasks:
            print tasks[task_id].keys()
            # print task_id
            self.description[task_id] = []
            # print tasks[task_id]
            if "question" in tasks[task_id]:
                question = tasks[task_id]["question"]
                self.description[task_id].append(contents[question])
                # print contents[question]
                answers = tasks[task_id]["answers"]
                # print answers
                for ans in answers:
                    # print ans
                    label = ans["label"]
                    labels = label.split(".")
                    # question_index = labels[2]
                    self.description[task_id].append(contents[label])
                    # print self.description[task_id][-1]
            else:
                assert "tools" in tasks[task_id]
                print tasks[task_id]["tools"]
        # self. description

    def __get_subjects__(self):
        rows = self.cassandra_session.execute("select subject_id from classifications where project_id = " + str(self.project_id))
        subjects = set([r.subject_id for r in rows])
        print subjects

    def __get_subject_ids__(self,workflow_id):
        assert isinstance(workflow_id,int)
        assert isinstance(self.project_id,int)
        """
        return the subjects associated with a given workflow (which needs to be specific for the project)
        :return:
        """
        # select = "SELECT subject_set_id from subject_sets_workflows where workflow_id = " + str(workflow_id)
        # cur = self.postgres_session.cursor()
        # cur.execute(select)
        #
        # subject_set = set()

        # for subject_set_id in cur.fetchall():
        #     select = "SELECT subject_id FROM set_member_subjects WHERE subject_set_id = " + str(subject_set_id[0])
        #     cur2 = self.postgres_session.cursor()
        #     cur2.execute(select)
        #     subjects = cur2.fetchall()
        #     subject_set.update([s[0] for s in subjects])
        #
        # print list(subject_set)
        # return list(subject_set)
        workflow_version = int(math.floor(float(self.versions[workflow_id])))

        stmt = "select distinct subject_id from classifications where project_id = " + str(self.project_id) + " and workflow_id = " + str(workflow_id) + " and workflow_version = " + str(workflow_version)
        print stmt
        print self.cassandra_session.execute(stmt)

    def __get_num_clusters_(self,subject_id,task_id):
        return len(self.cluster_alg.clusterResults[subject_id][task_id])

    def __get_classifications__(self,subject_id,task_id,cluster_index=None,question_id=None):
        # either both of these variables are None or neither of them are
        assert (cluster_index is None) == (question_id is None)

        if cluster_index is None:
            return self.classifications[subject_id][task_id]
        else:
            return self.classifications[subject_id][task_id][cluster_index][question_id]

    def __get_project_id(self):
        """
        get the id number for our project
        this is mostly a "beta" feature so that given a name of a project, I can find the id
        in practice, aggregation will be run with just giving the project id
        :return:
        """
        # print self.host_api+"projects?owner="+urllib2.quote(self.owner)+"&display_name="+urllib2.quote(self.project_name)
        # assert False
        # request = urllib2.Request(self.host_api+"projects?owner="+urllib2.quote(self.owner)+"&display_name="+urllib2.quote(self.project_name))
        print self.host_api+"projects?display_name="+urllib2.quote(self.project_name)
        request = urllib2.Request(self.host_api+"projects?display_name="+urllib2.quote(self.project_name))
        # request = urllib2.Request(self.host_api+"projects?owner="+self.owner+"&display_name=Galaxy%20Zoo%20Bar%20Lengths")
        # print hostapi+"projects?owner="+owner+"&display_name="+project_name
        request.add_header("Accept","application/vnd.api+json; version=1")
        request.add_header("Authorization","Bearer "+self.token)

        # request
        try:
            response = urllib2.urlopen(request)
            body = response.read()
        except urllib2.HTTPError as e:
            print self.host_api+"projects?owner="+self.owner+"&display_name="+self.project_name
            print 'The server couldn\'t fulfill the request.'
            print 'Error code: ', e.code
            print 'Error response body: ', e.read()
            raise
        except urllib2.URLError as e:
            print 'We failed to reach a server.'
            print 'Reason: ', e.reason
            raise

        data = json.loads(body)
        # put it in json structure and extract id
        return data["projects"][0]["id"]
        # return None

    def __get_old_workflow__(self):
        version = self.versions[6]
        print "** " + str(version)
        # request = urllib2.Request(self.host_api+"workflows/project_id="+str(self.project_id))
        # print self.host_api+"workflows/6/versions/97"
        # request = urllib2.Request(self.host_api+"workflows/6/versions/97")
        print self.host_api+"workflow_contents/6/versions?page_size=100"
        request = urllib2.Request(self.host_api+"workflow_contents/6/versions?page_size=100")
        request.add_header("Accept","application/vnd.api+json; version=1")
        request.add_header("Authorization","Bearer "+self.token)

        # request
        try:
            response = urllib2.urlopen(request)
        except urllib2.HTTPError as e:
            print 'The server couldn\'t fulfill the request.'
            print 'Error code: ', e.code
            print 'Error response body: ', e.read()
            raise
        except urllib2.URLError as e:
            print 'We failed to reach a server.'
            print 'Reason: ', e.reason
            raise
        else:
            # everything is fine
            body = response.read()

        # put it in json structure and extract id
        data = json.loads(body)
        print data

        return versions

    def __get_workflow_versions__(self):#,project_id):
        request = urllib2.Request(self.host_api+"workflows?project_id="+str(self.project_id))
        # request = urllib2.Request(self.host_api+"workflows/project_id="+str(self.project_id))
        request.add_header("Accept","application/vnd.api+json; version=1")
        request.add_header("Authorization","Bearer "+self.token)

        # request
        try:
            response = urllib2.urlopen(request)
        except urllib2.HTTPError as e:
            print 'The server couldn\'t fulfill the request.'
            print 'Error code: ', e.code
            print 'Error response body: ', e.read()
            raise
        except urllib2.URLError as e:
            print 'We failed to reach a server.'
            print 'Reason: ', e.reason
            raise
        else:
            # everything is fine
            body = response.read()

        # put it in json structure and extract id
        data = json.loads(body)

        versions = {}

        for w in data["workflows"]:
            versions[int(w["id"])] = w["version"] #int(math.floor(float(w["version"])))

        return versions

    def __image_setup__(self,subject_id):
        """
        get the local file name for a given subject id and downloads that image if necessary
        :param subject_id:
        :return:
        """
        request = urllib2.Request(self.host_api+"subjects/"+str(subject_id))
        request.add_header("Accept","application/vnd.api+json; version=1")
        request.add_header("Authorization","Bearer "+self.token)
        # request
        try:
            response = urllib2.urlopen(request)
            body = response.read()
        except urllib2.HTTPError as e:
            print self.host_api+"subjects/"+str(subject_id)
            print 'The server couldn\'t fulfill the request.'
            print 'Error code: ', e.code
            print 'Error response body: ', e.read()
            raise
        except urllib2.URLError as e:
            print 'We failed to reach a server.'
            print 'Reason: ', e.reason
            raise

        data = json.loads(body)

        url = str(data["subjects"][0]["locations"][0]["image/jpeg"])

        slash_index = url.rfind("/")
        fname = url[slash_index+1:]

        image_path = base_directory+"/Databases/images/"+fname

        if not(os.path.isfile(image_path)):
            print "downloading"
            urllib.urlretrieve(url, image_path)

        return image_path

    def __list_all_versions__(self):
        request = urllib2.Request(self.host_api+"workflows/6/versions?")
        request.add_header("Accept","application/vnd.api+json; version=1")
        request.add_header("Authorization","Bearer "+self.token)

        # request
        try:
            response = urllib2.urlopen(request)
        except urllib2.HTTPError as e:
            print 'The server couldn\'t fulfill the request.'
            print 'Error code: ', e.code
            print 'Error response body: ', e.read()
            raise
        except urllib2.URLError as e:
            print 'We failed to reach a server.'
            print 'Reason: ', e.reason
            raise
        else:
            # everything is fine
            body = response.read()

        # put it in json structure and extract id
        data = json.loads(body)
        print data["meta"].keys()
        print data["versions"]


    def __migrate__(self):
        tt = set([465026, 465003, 493062, 492809, 465034, 465172, 493205, 465048, 465177, 493211, 464965, 492960, 465057, 465058, 492707, 492836, 465121, 492975, 464951, 464952, 464953, 464954, 464955, 464956, 464957, 464958, 464959, 464960, 464961, 492611, 492741, 492615, 465100, 492623, 492728, 492626, 492886, 464975, 464988, 492897, 464998, 492776, 492907, 492914, 465019, 492669])
        # print self.versions
        # assert False
        try:
            self.cassandra_session.execute("drop table classifications")
            print "table dropped"
        except cassandra.InvalidRequest:
            print "table did not exist"
            pass

        try:
            self.cassandra_session.execute("CREATE TABLE subjects (project_id int, workflow_id int, workflow_version int, subject_id int, PRIMARY KEY(project_id,workflow_id,workflow_version,subject_id));")
        except cassandra.AlreadyExists:
            pass

        try:
            self.cassandra_session.execute("CREATE TABLE classifications( project_id int, user_id int, workflow_id int, created_at timestamp,annotations text,  updated_at timestamp, user_group_id int, user_ip inet,  completed boolean, gold_standard boolean, subject_id int, workflow_version int,metadata text, PRIMARY KEY(project_id,workflow_id,workflow_version,subject_id,created_at) ) WITH CLUSTERING ORDER BY (workflow_id ASC,workflow_version ASC,subject_id ASC,  created_at ASC);")
        except cassandra.AlreadyExists:
            pass


        not_found = set()

        select = "SELECT * from classifications where project_id="+str(self.project_id)
        cur = self.postgres_session.cursor()
        cur.execute(select)

        self.migrated_subjects = set()
        print "trying to migrate " + str(self.project_id)
        insert_statement = self.cassandra_session.prepare("""
                insert into classifications (project_id, user_id, workflow_id,  created_at,annotations, updated_at, user_group_id, user_ip, completed, gold_standard, subject_id, workflow_version,metadata)
                values (?,?,?,?,?,?,?,?,?,?,?,?,?) IF NOT EXISTS""")

        insert_statement2 = self.cassandra_session.prepare("""
                insert into subjects (project_id,workflow_id,workflow_version,subject_id)
                values (?,?,?,?)""")

        statements_and_params = []
        for ii,t in enumerate(cur.fetchall()):

            # print ii
            id_,project_id,user_id,workflow_id,annotations,created_at,updated_at,user_group_id,user_ip,completed,gold_standard,expert_classifier,metadata,subject_ids,workflow_version = t
            if subject_ids[0] not in tt:
                not_found.add(subject_ids[0])
            # print t
            # assert False

            self.migrated_subjects.add(subject_ids[0])

            if gold_standard != True:
                gold_standard = False

            if not isinstance(user_group_id,int):
                user_group_id = -1

            if not isinstance(user_id,int):
                user_id = -1
            # get only the major version of the workflow
            workflow_version = int(math.floor(float(workflow_version)))
            print self.project_id,workflow_id,workflow_version
            params = (project_id, user_id, workflow_id,created_at, json.dumps(annotations), updated_at, user_group_id, user_ip,  completed, gold_standard,  subject_ids[0], workflow_version,json.dumps(metadata))
            statements_and_params.append((insert_statement, params))

            params2 = (project_id,workflow_id,workflow_version,subject_ids[0])
            statements_and_params.append((insert_statement2,params2))

            if len(statements_and_params) == 100:
                results = execute_concurrent(self.cassandra_session, statements_and_params, raise_on_first_error=True)
                statements_and_params = []
                # print results

        stmt = "select count(*) from subjects"
        print "====---"
        print self.cassandra_session.execute(stmt)
        # print self.subject_sets.keys()
        # print self.project_id
        # print [i for i in self.migrated_subjects if not(i in self.subject_sets[3])]
        # assert False
        # print not_found
        # print len(not_found)
        # assert False

        #     # print annotations
        #     # print subject_ids
        #     print ii
        #
        #
        #     if gold_standard != True:
        #         gold_standard = False
        #
        #     if not isinstance(user_group_id,int):
        #         user_group_id = -1
        #
        #     if not isinstance(user_id,int):
        #         user_id = -1
        #
        #     migrated_subjects.add(subject_ids[0])
        #
        #     self.cassandra_session.execute(
        #         # project_id int, user_id int, workflow_id int, created_at timestamp,annotations text,  updated_at timestamp, user_group_id int, user_ip inet,  completed boolean, gold_standard boolean, subject_id
        #         """
        #         insert into classifications (project_id, user_id, workflow_id,  created_at,annotations, updated_at, user_group_id, user_ip, completed, gold_standard, subject_id, workflow_version,metadata)
        #         values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) IF NOT EXISTS
        #         """,
        #         (project_id, user_id, workflow_id,created_at, json.dumps(annotations), updated_at, user_group_id, user_ip,  completed, gold_standard,  subject_ids[0], float(workflow_version),json.dumps(metadata)))
        # # print "migrated " + str(ii) + " classifications "
        # # print sorted(list(migrated_subjects))

    # def __list_projects__(self):
    #     stmt = "select * from projects"
    #     self.postgres_cursor.execute(stmt)
    #     for r in self.postgres_cursor.fetchall():
    #         print r[0],r[2]









    def __panoptes_connect__(self):
        """
        make the main connection to Panoptes - through http
        :return:
        """
        for i in range(20):
            try:
                print "connecting to Pantopes, attempt: " + str(i)
                cj = cookielib.CookieJar()
                opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))

                #1. get the csrf token

                request = urllib2.Request(self.host+"users/sign_in",None)
                response = opener.open(request)

                body = response.read()
                # grep for csrf-token
                try:
                    csrf_token = re.findall(".+csrf-token.\s+content=\"(.+)\"",body)[0]
                except IndexError:
                    print body
                    raise

                #2. use the token to get a devise session via JSON stored in a cookie
                devise_login_data=("{\"user\": {\"login\":\""+self.user_name+"\",\"password\":\""+self.password+
                                   "\"}, \"authenticity_token\": \""+csrf_token+"\"}")

                request = urllib2.Request(self.host+"users/sign_in",data=devise_login_data)
                request.add_header("Content-Type","application/json")
                request.add_header("Accept","application/json")

                try:
                    response = opener.open(request)
                except urllib2.HTTPError as e:
                    print 'In get_bearer_token, stage 2:'
                    print 'The server couldn\'t fulfill the request.'
                    print 'Error code: ', e.code
                    print 'Error response body: ', e.read()
                    raise
                except urllib2.URLError as e:
                    print 'We failed to reach a server.'
                    print 'Reason: ', e.reason
                    raise
                else:
                    # everything is fine
                    body = response.read()

                #3. use the devise session to get a bearer token for API access
                if self.app_client_id != "":
                    bearer_req_data=("{\"grant_type\":\"password\",\"client_id\":\"" + self.app_client_id + "\"}")
                else:
                    bearer_req_data=("{\"grant_type\":\"password\"}")
                request = urllib2.Request(self.host+"oauth/token",bearer_req_data)
                request.add_header("Content-Type","application/json")
                request.add_header("Accept","application/json")

                try:
                    response = opener.open(request)
                except urllib2.HTTPError as e:
                    print 'In get_bearer_token, stage 3:'
                    print 'The server couldn\'t fulfill the request.'
                    print 'Error code: ', e.code
                    print 'Error response body: ', e.read()
                    raise
                except urllib2.URLError as e:
                    print 'We failed to reach a server.'
                    print 'Reason: ', e.reason
                    raise
                else:
                    # everything is fine
                    body = response.read()

                # extract the bearer token
                json_data = json.loads(body)
                bearer_token = json_data["access_token"]

                self.token = bearer_token
                break
            except (urllib2.HTTPError,urllib2.URLError) as e:
                print "trying to connect/init again again"
                pass


    def __print_annotations__(self):
        """
        for debugging - print out the annotations/classifications
        :return:
        """
        select = "SELECT * from classifications where project_id="+str(self.project_id)
        cur = self.postgres_session.cursor()
        cur.execute(select)

        for record in cur.fetchall():
            print record



    def __plot_image__(self,subject_id):
        fname = self.__image_setup__(subject_id)

        for i in range(10):
            try:
                fig = plt.figure()
                ax = fig.add_subplot(1, 1, 1)
                image_file = cbook.get_sample_data(fname)
                image = plt.imread(image_file)
                # fig, ax = plt.subplots()
                im = ax.imshow(image)

                return
            except IOError:
                # try downloading that image again
                os.remove(fname)
                self.__image_setup__(subject_id)

    def __plot_individual_points__(self,subject_id,task_id,shape):
        for cluster in self.cluster_alg.clusterResults[task_id][shape][subject_id]:
            for pt in cluster["points"]:
                if shape == "line":
                    plt.plot([pt[0],pt[1]],[pt[2],pt[3]],color="red")
                elif shape == "point":
                    plt.plot([pt[0]],[pt[1]],".",color="red")
                elif shape == "circle":
                    print (pt[0],pt[1]),pt[2]
                    e = Ellipse((pt[0],pt[1]),width = pt[2],height=pt[2],fill=False,color="red")
                    # circle = plt.Circle((pt[0],pt[1]),pt[2],color=cnames.values()[users.index(user_id)])
                    plt.gca().add_patch(e)
                    # ax.add_artist(e)
                    # e.set_alpha(0)
                elif shape == "ellipse":
                    # ("angle","rx","ry","x","y")
                    e = Ellipse((pt[3],pt[4]),width = pt[2],height=pt[1],fill=False,angle=pt[0],color="red")
                elif shape == "rectangle":
                    plt.plot([pt[0],pt[0]+pt[2]],[pt[1],pt[1]],color="red")
                    plt.plot([pt[0],pt[0]],[pt[1],pt[1]+pt[3]],color="red")
                    plt.plot([pt[0]+pt[2],pt[0]+pt[2]],[pt[1],pt[1]+pt[3]],color="red")
                    plt.plot([pt[0],pt[0]+pt[2]],[pt[1]+pt[3],pt[1]+pt[3]],color="red")
                else:
                    print shape
                    assert False

        plt.axis('scaled')

    def __plot_cluster_results__(self,subject_id,task_id,shape):
        # for task in self.cluster_alg.clusterResults[subject_id]:
        #     not really a task - just there to make things easier to understand
            # if task == "param":
            #     continue
        for cluster in self.cluster_alg.clusterResults[task_id][shape][subject_id]:
            center = cluster["center"]
            points = cluster["points"]
            if shape == "line":
                plt.plot([center[0],center[1]],[center[2],center[3]],color="blue")
            elif shape == "point":
                for pt in points:
                    plt.plot([pt[0],],[pt[1],],'.',color="red")
                plt.plot([center[0],],[center[1],],"o",color="blue")
            else:
                assert False
            plt.title("number of users: " + str(len(cluster["points"])))

        # plt.show()

    def __plot__(self,workflow_id,task):
        print "plotting"
        try:
            for shape in self.cluster_alg.clusterResults[task]:
                for subject_id in self.cluster_alg.clusterResults[task][shape]:
                    print subject_id
                    if (len(self.users_per_subject[subject_id]) >= 5):# and (subject_id in self.classification_alg.results):
                        # if self.cluster_alg.clusterResults[task][shape][subject_id]["users"]
                        self.__plot_image__(subject_id)
                        self.__plot_individual_points__(subject_id,task,shape)
                        self.__plot_cluster_results__(subject_id,task,shape)

                        if subject_id in self.classification_alg.results:
                            classification_task = "init"
                            classifications = self.classification_alg.results[subject_id][classification_task]
                            # print classifications
                            votes,total = classifications
                            title = self.description[classification_task][0]
                            # print self.description
                            for answer_index,percentage in votes.items():
                                if title != "":
                                    title += "\n"
                                title += self.description[classification_task][answer_index+1] + ": " + str(int(percentage*total))
                            # print  self.description[classification_task][0]
                            # print title

                            plt.title(title)
                        # plt.title("number of users: " + str(len(all_users)))
                        plt.savefig("/home/greg/Databases/"+self.project_short_name+"/markings/"+str(subject_id)+".jpg")
                        plt.close()
                        # assert False
        except KeyError as e:
            print self.cluster_alg.clusterResults.keys()
            raise

    def __postgres_connect(self,database_details):

        database = database_details[self.environment]["database"]
        username = database_details[self.environment]["username"]
        password = database_details[self.environment]["password"]
        host = database_details[self.environment]["host"]

        # try connecting to the db
        details = "dbname='"+database+"' user='"+ username+ "' host='"+ host + "' password='"+password+"'"
        for i in range(20):
            try:
                self.postgres_session = psycopg2.connect(details)
                self.postgres_cursor = self.postgres_session.cursor()
                break
            except psycopg2.OperationalError as e:
                pass

        if self.postgres_session is None:
            raise psycopg2.OperationalError()

        # select = "SELECT * from project_contents"
        # cur = self.postgres_session.cursor()
        # cur.execute(select)

    def __readin_tasks__(self,workflow_id):
        """
        get the details for each task - for example, what tasks might we want to run clustering algorithms on
        and if so, what params related to that task are relevant
        :return:
        """
        # get the tasks associated with the given workflow
        select = "SELECT tasks from workflows where id = " + str(workflow_id)
        self.postgres_cursor.execute(select)
        tasks = self.postgres_cursor.fetchone()[0]

        # select = "SELECT * from workflow_contents where id = " + str(workflow_id)
        # self.postgres_cursor.execute(select)
        # print
        # print self.postgres_cursor.fetchone()

        # which of these tasks have classifications associated with them?
        classification_tasks = {}
        # which have drawings associated with them
        marking_tasks = {}

        for task_id in tasks:
            # self.task_type[task_id] = tasks[task_id]["type"]

            # if the task is a drawing one, get the necessary details for clustering
            if tasks[task_id]["type"] == "drawing":
                marking_tasks[task_id] = []
                # manage marking tools by the marking type and not the index
                # so all ellipses will be clustered together

                # # see if mulitple tools are creating the same shape
                # counter = {}

                for tool in tasks[task_id]["tools"]:
                    # shape = ellipse, line, pt etc.
                    shape = tool["type"]

                    # extract the label of the tool - this means that things don't have to ordered
                    label = tool["label"]
                    label_words = label.split(".")
                    tool_id = int(label_words[2])

                    # are there any classification questions associated with this marking?
                    if (tool["details"] is not None) and (tool["details"] != []):
                        if task_id not in classification_tasks:
                            classification_tasks[task_id] = {}
                        if "subtask" not in classification_tasks[task_id]:
                            classification_tasks[task_id]["subtask"] = {}
                        if tool_id not in classification_tasks[task_id]["subtask"]:
                            classification_tasks[task_id]["subtask"][tool_id] = range(len(tool["details"]))
                        # if tool_id not in self.classification_tasks[task_id]:
                        #     self.classification_tasks[task_id][tool_id] = {}
                        # classification_tasks[task_id][tool_id]= [i for i in range(len(tool["details"]))]
                        # todo - fix this

                    print "tool is " + tool["type"]
                    if tool["type"] == "line":
                        marking_tasks[task_id].append("line")
                        # self.marking_params_per_task[task_id].append(line_mapping)
                    elif tool["type"] == "ellipse":
                        marking_tasks[task_id].append("ellipse")
                        # self.marking_params_per_task[task_id].append(("angle","rx","ry","x","y"))
                    elif tool["type"] == "point":
                        marking_tasks[task_id].append("point")
                        # self.marking_params_per_task[task_id].append(("x","y"))
                    elif tool["type"] == "circle":
                        marking_tasks[task_id].append("circle")
                        # self.marking_params_per_task[task_id].append(("x","y","r"))
                    elif tool["type"] == "rectangle":
                        marking_tasks[task_id].append("rectangle")
                        # self.marking_params_per_task[task_id].append(("x","y","width","height"))
                    else:
                        print tool
                        assert False

            else:
                # self.marking_params_per_task[task_id] = []
                classification_tasks[task_id] = True

        # find out if any of the shapes for a given task are "confusing"
        # that is more, there is more than 1 tool which can create that shape
        for task_id in marking_tasks:
            for shape in ["line","ellipse","point","circle","rectangle"]:
                if sum([1 for s in marking_tasks[task_id] if s == shape]) > 1:
                    # this shape is confusing
                    if task_id not in classification_tasks:
                        classification_tasks[task_id] = {}
                    if "shapes" not in classification_tasks[task_id]:
                        classification_tasks[task_id]["shapes"] = []

                    classification_tasks[task_id]["shapes"].append(shape)

        # print workflow_id
        # print tasks
        # print classification_tasks
        # print marking_tasks
        # assert False
        # assert False
        return classification_tasks,marking_tasks


    def __set_subjects__(self,subjects):
        self.subjects = subjects

    def __set_classification_alg__(self,alg):
        self.classification_alg = alg(self)
        assert isinstance(self.classification_alg,classification.Classification)

    def __set_clustering_alg__(self,clustering_alg):
        self.cluster_alg = clustering_alg(self)
    #
    # def __load_workflows__(self):
    #     select = "SELECT id,display_name from workflows where project_id="+str(self.project_id)
    #     cur = self.postgres_session.cursor()
    #     cur.execute(select)
    #
    #     for record in cur.fetchall():
    #         self.workflows[record[0]] = record[1]
    #
    # def __list_workflows__(self):
    #     select = "SELECT * from workflows where project_id="+str(self.project_id)
    #     cur = self.postgres_session.cursor()
    #     cur.execute(select)
    #
    #     for record in cur.fetchall():
    #         print record

    # def __plot__(self):

    def __setup_workflows__(self):#,project_id):
        request = urllib2.Request(self.host_api+"workflows?project_id="+str(self.project_id))
        request.add_header("Accept","application/vnd.api+json; version=1")
        request.add_header("Authorization","Bearer "+self.token)

        # request
        try:
            response = urllib2.urlopen(request)
        except urllib2.HTTPError as e:
            print 'The server couldn\'t fulfill the request.'
            print 'Error code: ', e.code
            print 'Error response body: ', e.read()
            raise
        except urllib2.URLError as e:
            print 'We failed to reach a server.'
            print 'Reason: ', e.reason
            raise
        else:
            # everything is fine
            body = response.read()

        # put it in json structure and extract id
        data = json.loads(body)

        # for each workflow, read in the tasks
        self.workflows = {}
        self.subject_sets = {}
        for workflows in data["workflows"]:
            id_ = int(workflows["id"])
            # self.workflows.append(id_)
            self.workflows[id_] = self.__readin_tasks__(id_)
            # self.subject_sets[id_] = self.__get_subject_ids__(id_)
        # print self.project_id
        # print self.workflows
        # assert False
        # read in the most current version of each of the workflows
        self.versions = self.__get_workflow_versions__()



    def __sort_classifications__(self,workflow_id,version=None):
        if version is None:
            version = self.versions[workflow_id]

        classification_tasks,marking_tasks = self.workflows[workflow_id]
        raw_classifications = {}


        total = 0
        for s in self.__chunks(self.subject_sets[workflow_id],15):
            statements_and_params = []
            select_statement = self.cassandra_session.prepare("select user_id,annotations,workflow_version from classifications where project_id = ? and subject_id = ? and workflow_id = ? and workflow_version = ?")
            for subject_id in s:
                params = (int(self.project_id),subject_id,int(workflow_id),version)
                statements_and_params.append((select_statement, params))
            results = execute_concurrent(self.cassandra_session, statements_and_params, raise_on_first_error=False)


            for subject_id,(success,record_list) in zip(s,results):
                if not success:
                    print record_list
                    assert success

                # to help us tell apart between different users who are not logged in
                # todo- a non logged in user might see this subject multiple times - how to protect against that?
                non_logged_in_users = 0
                # print "==++ " + str(subject_id)
                for record in record_list:
                    total += 1
                    user_id = record.user_id
                    if user_id == -1:
                        non_logged_in_users += -1
                        user_id = non_logged_in_users

                    annotations = json.loads(record.annotations)

                    # go through each annotation and get the associated task
                    for task in annotations:
                        task_id = task["task"]

                        # is this a classification task
                        if task_id in classification_tasks:
                            # is this classification task associated with a marking task?
                            # i.e. a sub task?
                            if isinstance(classification_tasks[task_id],dict):
                                # does this correspond to a confusing shape?
                                # print classification_tasks[task_id]
                                for marking in task["value"]:
                                    tool = marking["tool"]
                                    shape = marking_tasks[task_id][tool]

                                    # is this shape confusing?
                                    if ("shapes" in classification_tasks[task_id]) and (shape in classification_tasks[task_id]["shapes"]):
                                        print marking

                                        if task_id not in raw_classifications:
                                            raw_classifications[task_id] = {}
                                        if shape not in raw_classifications[task_id]:
                                            raw_classifications[task_id][shape] = {}
                                        if subject_id not in raw_classifications[task_id][shape]:
                                            raw_classifications[task_id][shape][subject_id] = []

                                        # todo - FIX!!!
                                        relevant_params = self.marking_params_per_shape[shape](marking,(10000,10000))
                                        raw_classifications[task_id][shape][subject_id].append((user_id,relevant_params,tool))
                                # print raw_classifications
                                # assert False
                                # print marking_tasks[task_id]
                                # print classification_tasks[task_id]
                                # assert False
                            else:
                                if task_id not in raw_classifications:
                                    raw_classifications[task_id] = {}
                                if subject_id not in raw_classifications[task_id]:
                                    raw_classifications[task_id][subject_id] = []
                                # if task_id == "init":
                                #     print task_id,task["value"]
                                raw_classifications[task_id][subject_id].append((user_id,task["value"]))
        print total
        return raw_classifications

    def __sort_markings__(self,workflow_id):
        # print self.project_id,workflow_id
        # assert False
        classification_tasks,marking_tasks = self.workflows[workflow_id]

        if marking_tasks == {}:
            return {}

        raw_markings = {}

        # use one image from the workflow to determine the size of all images
        # todo - BAD ASSUMPTION, think of something better
        fname = self.__image_setup__(self.subject_sets[workflow_id][0])
        im=Image.open(fname)
        width,height= im.size

        self.users_per_subject={}

        # print len(self.subject_sets[workflow_id])

        loaded_subjects = set()
        read_in = set()
        for s in self.__chunks(self.subject_sets[workflow_id],15):
            statements_and_params = []
            # select_statement = self.cassandra_session.prepare("select id,user_id,annotations from classifications where project_id = ? and subject_id = ? and workflow_id = ?")
            select_statement = self.cassandra_session.prepare("select * from classifications where project_id = ? and subject_id = ?")# and workflow_id = ?")# and workflow_version = ?")
            # select_statement = self.cassandra_session.prepare("select * from classifications where project_id = ?")# and workflow_id = ? and workflow_version = ?")

            # assert 458701 not in s
            # print s

            for subject_id in s:
                params = (int(self.project_id),subject_id,)#int(workflow_id))#,int(math.floor(float(self.versions[workflow_id]))))
                # params = (int(self.project_id),)#,int(workflow_id),int(math.floor(float(self.versions[workflow_id]))))
                statements_and_params.append((select_statement, params))
                # print params
            print [1 if subject_id in self.migrated_subjects else 0 for subject_id in s]



            results = execute_concurrent(self.cassandra_session, statements_and_params, raise_on_first_error=False)
            for subject_id,(success,record_list) in zip(s,results):
                # print subject_id,(success,record_list)
                non_logged_in_users = 0
                # print (success,record_list)
                for record in record_list:
                    # print success,record
                    print "+",workflow_id,record.workflow_id #in self.subject_sets[workflow_id]
                    user_id = record.user_id
                    if user_id == -1:
                        non_logged_in_users += -1
                        user_id = non_logged_in_users
                    loaded_subjects.add(subject_id)
                    # for counting the number of users who have seen this subject
                    # set => in case someone has seen this image twice
                    if subject_id not in self.users_per_subject:
                        self.users_per_subject[subject_id] = set()

                    # # todo - how to handle cases where someone has seen an image more than once?
                    # if user_id in self.users_per_subject[subject_id]:
                    #     select = "SELECT * from users where id="+str(user_id)
                    #     cur = self.postgres_session.cursor()
                    #     cur.execute(select)
                    #
                    #     print cur.fetchone()

                    self.users_per_subject[subject_id].add(user_id)

                    annotations = json.loads(record.annotations)

                    # go through each annotation and get the associated task
                    for task in annotations:
                        task_id = task["task"]

                        if task_id in marking_tasks:
                            for marking in task["value"]:

                                # what kind of tool made this marking and what was the shape of that tool?
                                try:
                                    tool = marking["tool"]
                                    shape = marking_tasks[task_id][tool]
                                except KeyError:
                                    tool = None
                                    shape = marking["type"]
                                except IndexError as e:
                                    print marking
                                    print marking_tasks
                                    print task_id
                                    print tool
                                    raise

                                if shape ==  "image":
                                    # todo - treat image like a rectangle
                                    continue

                                try:
                                    # extract the params specifically relevant to the given shape
                                    relevant_params = self.marking_params_per_shape[shape](marking,(width,height))

                                    # only create these if we have a valid marking
                                    if task_id not in raw_markings:
                                        raw_markings[task_id] = {}
                                    if shape not in raw_markings[task_id]:
                                        raw_markings[task_id][shape] = {}
                                    if subject_id not in raw_markings[task_id][shape]:
                                        raw_markings[task_id][shape][subject_id] = []

                                    raw_markings[task_id][shape][subject_id].append((user_id,relevant_params,tool))
                                except InvalidMarking as e:
                                    print e
                break

        print [i for i in self.migrated_subjects if not(i in self.subject_sets[workflow_id])]
        # print loaded_subjects
        assert False
        print "raw is " + str(raw_markings)
        return raw_markings

        # for subject_id in subjects:
        #     t_markings = {}
        #     # print subject_id
        #     total += 1
        #     print total
        #
        #     # use to track non-logged in users
        #     non_logged_in_users = 0
        #
        #     # go through each of the classifications for the given subject
        #     # select_stmt = "select user_id,annotations,workflow_version from classifications where project_id = " + str(self.project_id) + " and subject_id = " + str(subject_id) + " and workflow_id = " + str(self.workflow_id)
        #     select_stmt = "select user_id,annotations from classifications where project_id = " + str(self.project_id) + " and subject_id = " + str(subject_id)
        #
        #     for classification in self.cassandra_session.execute(select_stmt):
        #         # print classification.workflow_version
        #         user_id = classification.user_id
        #
        #         # if the user is not logged in, use counter to help differiniate between users
        #         # todo - if someone views the same image twice, this approach will count both of those
        #         # todo classifications which is probably not what we want
        #         if user_id == -1:
        #             non_logged_in_users += -1
        #             user_id = non_logged_in_users
        #
        #         # convert from string into json
        #         annotations = json.loads(classification.annotations)
        #
        #         # go through each annotation, looking for markings
        #         for task in annotations:
        #             task_id = task["task"]
        #             print annotations
        #             # print task
        #             # print self.task_type
        #             assert task_id in self.task_type
        #
        #             # if we have found a list of markings, associated each one with the tool that made it
        #             if self.task_type[task_id] == "drawing":
        #                 if task["value"] is None:
        #                     continue
        #
        #                 for marking in task["value"]:
        #                     # get the index of the tool that made the marking
        #
        #                     # different markings can use the same tool - so this may have the affect of clustering
        #                     # across different marking types
        #                     # see https://github.com/zooniverse/Panoptes-Front-End/issues/525
        #                     # for discussion
        #                     try:
        #                         tool = marking["tool"]
        #                         shape = self.shapes_per_tool[task_id][tool]
        #                     except KeyError:
        #                         tool = None
        #                         shape = marking["type"]
        #
        #                     if shape ==  "image":
        #                         # todo - treat image like a rectangle
        #                         continue
        #
        #                     # drawing_params = self.marking_params_per_task[task_id][drawing["tool"]]
        #                     # extract the params that are relevant to the marking
        #                     try:
        #                         relevant_params = self.marking_params_per_shape[shape](marking)
        #                     except KeyError:
        #                         continue
        #
        #                     id_ = (task_id,shape)
        #
        #                     if id_ not in t_markings:
        #                         t_markings[id_] = [(user_id,relevant_params)]
        #                     else:
        #                         t_markings[id_].append((user_id,relevant_params))
        #     markings[subject_id] = deepcopy(t_markings)
        # return markings


    # def __sort_classifications2__(self,workflow_id):
    #     classification_tasks,marking_tasks = self.workflows[workflow_id]
    #     print "here here"
    #     classifications = {}
    #     for subject_id in self.subject_sets[workflow_id]:
    #         print subject_id
    #         t_classifications = {}
    #         non_logged_in_users = 0
    #         # todo - take care of workflow version
    #         # print "select user_id,annotations from classifications where project_id = " + str(self.project_id) + " and subject_id = " + str(subject_id) + " and workflow_id = " + str(workflow_id)
    #         print "--"
    #         t=  datetime.datetime.now()
    #         ii = 0
    #         for record in self.cassandra_session.execute("select user_id,annotations from classifications where project_id = " + str(self.project_id)):# + " and subject_id = " + str(subject_id) + " and workflow_id = " + str(workflow_id)):
    #             ii += 1
    #             # print datetime.datetime.now()-t,len()
    #             continue
    #             # convert from string into json
    #             t = datetime.datetime.now()
    #             annotations = json.loads(record.annotations)
    #
    #             user_id = record.user_id
    #             # print user_id
    #             if user_id == -1:
    #                 non_logged_in_users += -1
    #                 user_id = non_logged_in_users
    #
    #             for task in annotations:
    #                 task_id = task["task"]
    #
    #                 # need to separate "simple" classifications and those based on markings
    #                 # if based on markings, we need to use the clustering results
    #                 if task_id in classification_tasks:
    #                     if task_id in marking_tasks:
    #                         assert False
    #                         assert self.cluster_alg is not None
    #
    #                         # go through each marking the user made, and see if there is a corresponding
    #                         # classification, if so, find the appropriate cluster
    #                         for marking in task["value"]:
    #                             if marking["details"] == []:
    #                                 continue
    #
    #                             # may result in merging from different markings which use the same tool -
    #                             # could be problems if those markings
    #                             # have different classification questions associated with them
    #                             # again - see https://github.com/zooniverse/Panoptes-Front-End/issues/525
    #                             # for discussion
    #                             tool_index = marking["tool"]
    #
    #                             shape = self.shapes_per_tool[task_id][tool_index]
    #
    #                             # extract the necessary params
    #                             mapped_marking = [marking[p] for p in self.marking_params_per_task[task_id][tool_index]]
    #
    #                             # find which cluster this point belongs to
    #                             cluster_found = False
    #                             # go through all of the cluster results for the given shape
    #                             cluster_results = self.cluster_alg.clusterResults[subject_id][task_id][shape]
    #                             for cluster_index,cluster in enumerate(cluster_results):
    #                                 if mapped_marking in cluster["points"]:
    #                                     cluster_found = True
    #                                     break
    #                             assert cluster_found
    #
    #                             if task_id not in t_classifications:
    #                                 t_classifications[task_id] = {"param":"shape"}
    #
    #                             if shape not in t_classifications[task_id]:
    #                                 t_classifications[task_id][shape] = {"param":"cluster_index"}
    #
    #                             if cluster_index not in t_classifications[task_id][shape]:
    #                                 # details_list = {i:None for i in cluster["users"]}
    #                                 # tools_list = {i:None for i in cluster["users"]}
    #                                 t_classifications[task_id][shape][cluster_index] = {"details":{},"tool":{}}
    #                             # # if cluster_index not in t_classifications[task_id]:
    #                             # #     # markings for the different tools will be stored separately
    #                             # #     t_classifications[task_id][cluster_index] = {"param":"shape_type"}
    #                             #
    #                             #
    #                             #     details_list = {i:None for i in cluster["users"]}
    #                             #     tools_list = {i:None for i in cluster["users"]}
    #                             #     # create an entry for each cluster of this shape
    #                             #     for cluster in self.cluster_alg.clusterResults[subject_id][task_id][shape]:
    #                             #         t_classifications[task_id][cluster_index][shape] = []
    #                             #
    #                             #         # = {"points":cluster["points"],"users":cluster["users"],"details":details_list,"tool":tools_list}
    #
    #                             t_classifications[task_id][shape][cluster_index]["details"][user_id] = marking["details"]
    #                             t_classifications[task_id][shape][cluster_index]["tool"][user_id] = marking["tool"]
    #
    #                             # # is there more than one one type of tool that makes this shape?
    #                             # # if so, we will need to classify which tool made the marking
    #                             # shape_count = sum([1 for shape_2 in self.shapes_per_tool[task_id] if shape_2 == shape])
    #                             #
    #                             # #if shape_count > 1:
    #                             #
    #                             # # print self.classification_tasks[task_id]
    #                             # # t_classifications[task_id][cluster_index]
    #                             # assert False
    #                             #
    #                             # # are there classification questions associated with this marking tool specifically
    #                             # if tool not in self.classification_tasks[task_id]:
    #                             #     print marking
    #                             #     print "**"
    #                             #     # if not, continue
    #                             #     continue
    #                             #
    #                             # # extract the necessary params
    #                             # mapped_marking = [marking[p] for p in self.marking_params_per_task[task_id][tool]]
    #                             #
    #                             # # find which cluster this point belongs to
    #                             # cluster_found = False
    #                             # for cluster_index,cluster in enumerate(self.cluster_alg.clusterResults[subject_id][task_id]):
    #                             #     if mapped_marking in cluster["points"]:
    #                             #         cluster_found = True
    #                             #         break
    #                             # assert cluster_found
    #                             #
    #                             # if task_id not in t_classifications:
    #                             #     t_classifications[task_id] = []
    #                             # # extend the classifications list for this task as necessary
    #                             # if len(t_classifications[task_id]) <= cluster_index:
    #                             #     diff = cluster_index - len(t_classifications[task_id])+1
    #                             #
    #                             #     # extend the classifications for each question
    #                             #     question_list = [[] for i in self.classification_tasks[task_id][tool]]
    #                             #     t_classifications[task_id].extend([question_list for i in range(diff)])
    #                             #
    #                             # # finally add the details to the correct cluster
    #                             # # might be an empty list if the user didn't answer the question
    #                             # print marking["details"]
    #                             # for question_id,classification in enumerate(marking["details"]):
    #                             #     t_classifications[task_id][cluster_index][question_id].append((user_id,classification["value"]))
    #                     # else we have a simple classification - makes things so much easier :)
    #                     else:
    #                         if task_id not in t_classifications:
    #                             t_classifications[task_id] = []
    #
    #                         t_classifications[task_id].append((user_id,task["value"]))
    #         print "** " + str(datetime.datetime.now() - t) + str(ii)
    #         classifications[subject_id] = deepcopy(t_classifications)
    #
    #     return classifications


    def __store_results__(self):
        aggregate_results = {}

        for subject_id in self.subjects:
            # there have been requests for the aggregation to also contain the metadata
            select = "SELECT metadata from subjects where id="+str(subject_id)
            cur = self.postgres_session.cursor()
            cur.execute(select)
            metadata = cur.fetchone()

            aggregation = {"metadata":metadata,"param":"task_id"}

            if self.cluster_alg is not None:
                cluster_results = self.cluster_alg.clusterResults[subject_id]

                # check to see if an aggregation already exists, if so, use that created_at time
                old_aggregation = self.cassandra_session.execute("select created_at from aggregations where subject_id = 1" + str(subject_id) + " and workflow_id = " + str(self.workflow_id))
                if old_aggregation == []:
                    created_at = datetime.datetime.now()
                else:
                    created_at = old_aggregation.created_at

                for key in cluster_results:
                    aggregation[key] = deepcopy(cluster_results[key])

            print aggregation

            # now merge in the classification aggregation results
            if self.classification_alg is not None:
                classification_results = self.classification_alg.results[subject_id]
                for task_id in self.classification_alg.results[subject_id]:
                    if task_id == "type":
                        continue

                    if task_id not in aggregation:
                        aggregation[task_id] = deepcopy(classification_results[task_id])
                    else:
                        for tool_id in cluster_results[task_id]:
                            if tool_id not in aggregation[task_id]:
                                aggregation[task_id][tool_id] = deepcopy(classification_results[task_id][tool_id])
                            else:
                                # if we are here, there should be some clustering results as well - which we
                                # need to merge with and not simply overwrite
                                for question_id in cluster_results[task_id][tool_id]:
                                    aggregation[task_id][tool_id][question_id] = deepcopy(classification_results[task_id][tool_id][question_id])

            print aggregation
        return

        updated_at = datetime.datetime.now()

        # insert into cassandra
        self.cassandra_session.execute(
            """
            insert into aggregations (subject_id,workflow_id, aggregation, created_at, updated_at,metadata)
            values (%s,%s,%s,%s,%s,%s)
            """,
            (subject_id,self.workflow_id,json.dumps(aggregation),created_at,updated_at,json.dumps(metadata)))

        # now insert into postgres as well
        self.postgres_cursor.execute("INSERT INTO aggregations(workflow_id,subject_id,aggregation,created_at,updated_at) VALUES (%s,%s,%s,%s,%s);",
                                     (self.workflow_id,subject_id,json.dumps(aggregation),created_at,updated_at))




def mapping(pt):
    x1,x2,y1,y2 = pt
    print x1,x2,y1,y2
    dist = (x2*y1-y2*x1)/math.sqrt((y2-y1)**2+(x2-x1)**2)

    try:
        tan_theta = math.fabs(y1-y2)/math.fabs(x1-x2)
        theta = math.atan(tan_theta)
    except ZeroDivisionError:
        theta = math.pi/2.

    return dist,theta

if __name__ == "__main__":
    print sys.argv[1]
    project = PanoptesAPI(sys.argv[1])
    # project.__get_old_workflow__()
    project.__migrate__()
    # project.__get_subject_ids__(3)
    # assert False
    #
    # project.__get_subjects__()
    # # # brooke.__get_markings__(3266)
    # #
    # project.__set_subjects__([458813])

    # project.__set_clustering_alg__(agglomerative.Agglomerative)
    # project.__set_classification_alg__(classification.VoteCount)
    # # # # # a = agglomerative.Agglomerative(brooke)
    # project.__cluster__()
    # project.__aggregate__()
    # project.__plot__(6,"T1")
    # project.__plot_cluster_results__(15)
    # #

    # project.__classify__()
    # # # project.__store_results__()