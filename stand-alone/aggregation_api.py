#!/usr/bin/env python
# from setuptools import setup, find_packages
import os
import csv
import tarfile
#import yaml
import urllib2
import cookielib
import re
import json
import urllib
import datetime
import classification
import matplotlib.pyplot as plt
import matplotlib.cbook as cbook
import math
import sys
import agglomerative
import clustering
import blob_clustering
from collections import OrderedDict
import random
import cPickle as pickle
from os.path import expanduser
import csv_output

# these are libraries which are only needed if you are working directly with the db
# so if they are not on your computer - we'll just skip them
try:
    import cassandra
    from cassandra.cluster import Cluster
    from cassandra.concurrent import execute_concurrent
    import psycopg2
    import rollbar
except:
    pass

if os.path.exists("/home/ggdhines"):
    base_directory = "/home/ggdhines"
else:
    base_directory = "/home/greg"

# see below for a discussion of inserting date times into casssandra - code is taken from there
# http://stackoverflow.com/questions/16532566/how-to-insert-a-datetime-into-a-cassandra-1-2-timestamp-column
def unix_time(dt):
    epoch = datetime.datetime.utcfromtimestamp(0)
    delta = dt - epoch
    return delta.total_seconds()

def unix_time_millis(dt):
    return long(unix_time(dt) * 1000.0)


class InvalidMarking(Exception):
    def __init__(self,pt):
        self.pt = pt
    def __str__(self):
        return "invalid marking: " + str(self.pt)

class WorkflowNotfound(Exception):
    def __init__(self,workflow_id):
        self.workflow_id = workflow_id
    def __str__(self):
        return "workflow " + str(self.workflow_id) + " not found"

class ImageNotDownloaded(Exception):
    def __init__(self):
        pass
    def __str__(self):
        return 'image not downloaded'


class ImproperTool(Exception):
    def __init__(self,tool):
        self.tool = tool
    def __str__(self):
        return "improper tool: " + str(self.tool)


class InstanceAlreadyRunning(Exception):
    def __init__(self):
        pass
    def __str__(self):
        return "aggregation engine already running"


# extract the relevant params for different shapes from the json blob
# todo - do a better job of checking to make sure that the marking lies within the image dimension
# todo - also generalize to ROI
def relevant_line_params(marking,image_dimensions):
    # want to extract the params x1,x2,y1,y2 but
    # ALSO make sure that x1 <= x2 and flip if necessary
    x1 = marking["x1"]
    x2 = marking["x2"]
    y1 = marking["y1"]
    y2 = marking["y2"]

    if min(x1,x2,y1,y2) < 0:
        raise InvalidMarking(marking)

    # only do this part if we have been provided dimensions
    if image_dimensions is not None:
        if (max(x1,x2) >= image_dimensions[0]) or (max(y1,y2) >= image_dimensions[1]):
            raise InvalidMarking(marking)

    if x1 <= x2:
        return x1,y1,x2,y2
    else:
        return x2,y2,x1,y1


# the following convert json blobs into sets of values we can actually cluster on
# todo - do a better job with checking whether the markings fall within the image_dimensions
def relevant_point_params(marking,image_dimensions):
    # todo - this has to be changed
    image_dimensions = 1000,1000
    if (marking["x"] == "") or (marking["y"] == ""):
        raise InvalidMarking(marking)

    try:
        x = float(marking["x"])
        y = float(marking["y"])
    except ValueError:
        print marking
        raise

    if (x<0)or(y<0)or(x > image_dimensions[0]) or(y>image_dimensions[1]):
        raise InvalidMarking(marking)

    return x,y


def relevant_rectangle_params(marking,image_dimensions):
    x = marking["x"]
    y = marking["y"]

    x2 = x + marking["width"]
    y2 = y + marking["height"]

    if (x<0)or(y<0):
        raise InvalidMarking(marking)

    if image_dimensions is not None:
        if(x2 > image_dimensions[0]) or(y2>image_dimensions[1]):
            raise InvalidMarking(marking)

    # return x,y,x2,y2
    return (x,y),(x,y2),(x2,y2),(x2,y)


def relevant_circle_params(marking,image_dimensions):
    return marking["x"],marking["y"],marking["r"]


def relevant_ellipse_params(marking,image_dimensions):
    return marking["x"],marking["y"],marking["rx"],marking["ry"],marking["angle"]


def relevant_polygon_params(marking,image_dimensions):
    points = marking["points"]
    return tuple([(p["x"],p["y"]) for p in points])






def hesse_line_reduction(line_segments):
    """
    use if we want to cluster based on Hesse normal form - but want to retain the original values
    :param line_segment:
    :return:
    """
    reduced_markings = []

    for line_seg in line_segments:
        x1,y1,x2,y2 = line_seg[:4]

        x2 += random.uniform(-0.0001,0.0001)
        x1 += random.uniform(-0.0001,0.0001)

        dist = (x2*y1-y2*x1)/math.sqrt((y2-y1)**2+(x2-x1)**2)

        try:
            tan_theta = math.fabs(y1-y2)/math.fabs(x1-x2)
            theta = math.atan(tan_theta)
        except ZeroDivisionError:
            theta = math.pi/2.

        reduced_markings.append((dist,theta))

    return reduced_markings




class AggregationAPI:

    def __init__(self,csv_classification_file,csv_subject_file,workflows_file):
    
    #def __init__(self,project_id,environment,user_id=None,password=None,(csv_classification_file,csv_subject_file)=(None,None),public_panoptes_connection=False,report_rollbar=False):
        
        # the panoptes project id - and the environment are the two main things to set
        #self.project_id = int(project_id)
        #self.environment = environment

        # a dictionary of clustering algorithms - one per shape
        # todo - currently all possible algorithms are created for every shape, regardless of whether they are
        # todo actually used
        self.cluster_algs = None
        # the one classification algorithm
        self.classification_alg = None
        # a dictionary of workflows - each workflow id number will map to a tuple - marking tasks and
        # classification tasks
        self.workflows = None
        # a list of the current workflow versions - so we can filter out any classifications made via a previous
        # version (which can really mess things up)
        self.versions = None
        self.classifications = None

        # which version of panoptes - staging or production to call
        #self.host_api = None

        #self.public_panoptes_connection = public_panoptes_connection

        #self.postgres_session = None
        #self.cassandra_session = None

        # user id and password used to connect to the panoptes api
        #self.user_id = user_id
        #self.password = password

        # todo - allow users to provide their own classification and subject files
        self.csv_classification_file = csv_classification_file
        self.csv_subject_file = csv_subject_file

        # aggregations runs called through the crontab will want this code to report errors to rollbar
        # as opposed to via rq (which is what happens when someone presses the aggregation button)
        #self.report_roll = report_rollbar

        self.__setup__()

    def __setup_clustering_algs__(self):
        # functions for converting json instances into values we can actually cluster on
        self.marking_params_per_shape = dict()
        self.marking_params_per_shape["line"] = relevant_line_params
        self.marking_params_per_shape["point"] = relevant_point_params
        self.marking_params_per_shape["ellipse"] = relevant_ellipse_params
        self.marking_params_per_shape["rectangle"] = relevant_rectangle_params
        self.marking_params_per_shape["circle"] = relevant_circle_params
        self.marking_params_per_shape["polygon"] = relevant_polygon_params

        # load the default clustering algorithms
        self.default_clustering_algs = dict()
        # the following shapes using the basic agglomerative clustering
        self.default_clustering_algs["point"] = agglomerative.Agglomerative
        self.default_clustering_algs["circle"] = agglomerative.Agglomerative
        self.default_clustering_algs["ellipse"] = agglomerative.Agglomerative
        self.default_clustering_algs["line"] = agglomerative.Agglomerative
        # these shapes use the blob clustering approach
        self.default_clustering_algs["rectangle"] = blob_clustering.BlobClustering
        self.default_clustering_algs["polygon"] = blob_clustering.BlobClustering
        # and set any reduction algorithms - to reduce the dimensionality of markings
        self.additional_clustering_args = {"line": {"reduction":hesse_line_reduction}}
        # self.__set_clustering_algs__(default_clustering_algs,reduction_algs)

        self.cluster_algs = {}

    def __setup__(self):


        print "setup"
        
        # just for when we are treating an ouroboros project like a panoptes one
        # in which the subject ids will be zooniverse_ids, which are strings
        self.subject_id_type = "int"

        # todo - some time in the far future - complete support for expert annotations
        #self.experts = []

        # load in the project id (a number)
        # if one isn't provided, tried reading it from the yaml config file
        # todo - if we are not using a secure connection, this forces the project_id
        # todo - to be provided as a param (since we don't read in the yaml file)
        # todo - probably want to change that at some point as there is value in
        # todo - non logged in users having a yaml file (where they can give csv classification files etc.)

        # if we are using a public panoptes connection
        # we won't be able to connect to the back end databases, so might as well exit here
        #if self.public_panoptes_connection:
            # go with the very basic connection
            #print "trying public Panoptes connection - no login"
            #self.host = "https://panoptes.zooniverse.org/"
            #self.host_api = self.host+"api/"
            #self.token = None
            #return

        # todo - can probably get rid of public_panoptes_connection  - a bit redundant given
        # todo - csv_classification_file
        assert self.csv_classification_file is not None
        #########
        # everything that follows assumes you have a secure connection to Panoptes
        # plus the DBs (either production or staging)

        #param_file = open("/app/config/aggregation.yml","rb")
        #param_details = yaml.load(param_file)

        # sometimes we want params specific to a project - ie. we are in development but want to read
        # off the staging postgres db - in such case we just provide an extra yaml file
        #if self.project_id in param_details:
        #    project_details = param_details[self.project_id]
        #    if "project_name" in project_details:
        #        print "aggregating project: " + project_details["project_name"]
        #else:
        #    project_details = param_details[self.environment]

        # connect to whatever postgres db we want to
        #self.__postgres_connect__(project_details)

        # connect to the Cassandra DB
        #self.__cassandra_connect__(project_details["cassandra"])
        # as soon as we have a cassandra connection - check to see when the last time we ran
        # the aggregation engine for this project - if this query fails for whatever reason
        # fall back on 2000,1,1
        #self.previous_runtime = datetime.datetime(2000,1,1)
        # use this one for figuring out the most recent classification read in
        # we need to use as our runtime value, not the clock (since classifications could still be coming in
        # if we used datetime.datetime.now() we might skip some classifications)
        #self.new_runtime = datetime.datetime(2000,1,1)

        #try:
        #    r = self.cassandra_session.execute("select classification from most_recent where project_id = " + str(self.project_id))
        #    if r != []:
        #        self.previous_runtime = r[0].classification
        #except:
        #    pass

        #print "we have already aggregated classifications up to: " + str(self.previous_runtime)

        # use this to determine the time frame for reading in classifications
        # self.old_new_classification = None

        # use for Cassandra connection - can override for Ourboros projects
        #self.classification_table = "classifications"

        # make the actual connection to Panoptes
        #print "trying secure Panoptes connection"
        #self.__panoptes_connect__(project_details)

        # todo - refactor all this?
        # there may be more than one workflow associated with a project - read them all in
        # and set up the associated tasks

        # Make sure these set up properly
        self.workflows,self.versions,self.instructions,self.retirement_thresholds,self.workflow_names = self.__get_workflow_details_from_file__(workflows_file)

        #print self.workflows
        #print self.versions
        #print self.instructions
        #print self.retirement_thresholds
        #print self.workflow_names

        #self.workflows,self.versions,self.instructions,self.updated_at_timestamps = self.__get_workflow_details__()
        #self.retirement_thresholds = self.__get_retirement_threshold__()
        #self.workflow_names = self.__get_workflow_names__()

        # is there an entry for the project in the yaml file?
        # if so, has a specific workflow id has been provided?
        #if "workflow_id" in project_details:
        #    workflow_id = int(project_details["workflow_id"])
        #    try:
        #        print "aggregating only for workflow id : " + str(workflow_id)
        #        self.workflows = {workflow_id: self.workflows[workflow_id]}
        #    except KeyError:
        #        print "did not have given desired workflow: " + str(workflow_id)
        #        print "here's the workflows we do have"
        #        print self.workflows
        #        raise

        # set up the clustering algorithms
        self.__setup_clustering_algs__()
        # load the default classification algorithm
        self.__set_classification_alg__(classification.VoteCount)

        # # todo - do in this in Cassandra
        # # for reading in from classifications only done since the last run
        # # if any trouble - start over from the beginning
        # try:
        #     self.old_time = pickle.load(open("/tmp/"+str(self.project_id)+".time","rb"))
        # except:
        #     self.old_time = datetime.datetime(2000,01,01)
        #
        # self.current_time = datetime.datetime.now()

        self.ignore_versions = False
        self.only_retired_subjects = True
        
        # a bit of a sanity check in case I forget to change back up before uploading
        # production and staging should ALWAYS pay attention to the version and only
        # aggregate retired subjects
        
        #if self.environment in ["production","staging"]:
        #    self.ignore_versions = False
        #    self.only_retired_subjects = True

        # bit of a stop gap measure - stores how many people have classified a given subject
        self.classifications_per_subject = {}

        # do we want to aggregate over only retired subjects?

        # do we want to aggregate over only subjects that have been retired/classified since
        # the last time we ran the code?
        self.only_recent_subjects = False



    def __aggregate__(self,workflows=None,subject_set=None,gold_standard_clusters=([],[]),expert=None,store_values=True):
        """
        you can provide a list of clusters - hopefully examples of both true positives and false positives
        note this means you have already run the aggregation before and are just coming back with
        more info
        for now, only one expert - easily generalizable but just want to avoid the situation where
        multiple experts have marked the same subject - need to be a bit careful there
        :param workflows:
        :param subject_set:
        :param gold_standard_clusters:
        :return:
        """
        # todo - set things up so that you don't have to redo all of the aggregations just to rerun ibcc
        if workflows is None:
            workflows = self.workflows
        print self.workflows
        given_subject_set = (subject_set != None)

        for workflow_id in workflows:
            if subject_set is None:
                subject_set = self.__get_subjects__(workflow_id)#,only_retired_subjects=False)
                # subject_set = self.__load_subjects__(workflow_id)

            print "workflow id : " + str(workflow_id)
            print "aggregating " + str(len(subject_set)) + " subjects"
            # self.__describe__(workflow_id)
            classification_tasks,marking_tasks = self.workflows[workflow_id]

            # set up the clustering algorithms for the shapes we actually use
            used_shapes = set()
            for shapes in marking_tasks.values():
                used_shapes = used_shapes.union(shapes)

            aggregations = {}

            # image_dimensions can be used by some clustering approaches - ie. for blob clustering
            # to give area as percentage of the total image area
            raw_classifications,raw_markings,image_dimensions = self.__sort_annotations__(workflow_id,subject_set,expert)

            # do we have any marking tasks?
            if marking_tasks != {}:
                print "clustering"
                aggregations = self.__cluster__(used_shapes,raw_markings,image_dimensions)
                # assert (clustering_aggregations != {}) and (clustering_aggregations is not None)

            if (self.classification_alg is not None) and (classification_tasks != {}):
                # we may need the clustering results
                print "classifying"
                # aggregations = self.__classify__(raw_classifications,aggregations,workflow_id,gold_standard_clusters)
                # print classification_aggregations
                aggregations = self.classification_alg.__aggregate__(raw_classifications,self.workflows[workflow_id],aggregations)

            # unless we are provided with specific subjects, reset for the extra workflow
            if not given_subject_set:
                subject_set = None

            # finally, store the results
            # if gold_standard_clusters is not None, assume that we are playing around with values
            # and we don't want to automatically save the results

            if store_values:
                print "upserting results"
                self.__upsert_results__(workflow_id,aggregations)
            else:
                return aggregations

    def __cassandra_annotations__(self):
        """
        use inner function so param can be set
        get the annotations from Cassandra

        note that we may need to read in previously read classifications if there are new classifications for that
        same subject
        :return:
        """
        def annotation_generator(workflow_id,subject_set):
            assert isinstance(subject_set,list) or isinstance(subject_set,set)
            # filter on only the major version (the whole number part)
            version = int(math.floor(float(self.versions[workflow_id])))

            # classification_tasks,marking_tasks = self.workflows[workflow_id]
            # raw_classifications = {}
            # raw_markings = {}

            if subject_set is None:
                subject_set = self.__load_subjects__(workflow_id)

            # do this in bite sized pieces to avoid overwhelming DB
            for s in self.__chunks__(subject_set,15):
                statements_and_params = []

                if self.ignore_versions:
                    select_statement = self.cassandra_session.prepare("select user_id,annotations,workflow_version,created_at,metadata from "+self.classification_table+" where project_id = ? and subject_id = ? and workflow_id = ?")
                else:
                    select_statement = self.cassandra_session.prepare("select user_id,annotations,workflow_version,created_at,metadata from "+self.classification_table+" where project_id = ? and subject_id = ? and workflow_id = ? and workflow_version = ?")

                for subject_id in s:
                    if self.ignore_versions:
                        params = (int(self.project_id),subject_id,int(workflow_id))
                    else:
                        params = (int(self.project_id),subject_id,int(workflow_id),version)
                    statements_and_params.append((select_statement, params))
                results = execute_concurrent(self.cassandra_session, statements_and_params, raise_on_first_error=False)

                for subject_id,(success,record_list) in zip(s,results):
                    if not success:
                        print record_list
                    assert success


                    # seem to have the occasional "retired" subject with no classifications, not sure
                    # why this is possible but if it can happen, just make a note of the subject id and skip
                    if record_list == []:
                        # print "warning :: subject " + str(subject_id) + " has no classifications"
                        continue


                    for ii,record in enumerate(record_list):
                        # if record.created_at < self.starting_date:#datetime.datetime(2015,8,27):
                        #     print "too early"
                        #     print record.created_at
                        #     continue

                        # check to see if the metadata contains image size
                        metadata = record.metadata
                        if isinstance(metadata,str) or isinstance(metadata,unicode):
                            metadata = json.loads(metadata)

                        height = None
                        width = None

                        if "subject_dimensions" in metadata:
                            for dimensions in metadata["subject_dimensions"]:
                                if dimensions is not None:
                                    assert isinstance(dimensions,dict)
                                    height = dimensions["naturalHeight"]
                                    width = dimensions["naturalWidth"]

                        yield int(subject_id),int(record.user_id),record.annotations,(height,width)

            raise StopIteration()
        return annotation_generator

    def __cassandra_connect__(self,cassandra_instance):
        """
        connect to the AWS instance of Cassandra - try 10 times and raise an error
        :return:
        """
        for i in range(10):
            try:
                if cassandra_instance == "local":
                    print "connecting to local Cassandra instance"
                    self.cluster = Cluster()
                else:
                    print "connecting to Cassandra: " + cassandra_instance
                    self.cluster = Cluster([cassandra_instance])

                try:
                    self.cassandra_session = self.cluster.connect("zooniverse")
                except cassandra.InvalidRequest:
                    cassandra_session = self.cluster.connect()
                    cassandra_session.execute("CREATE KEYSPACE zooniverse WITH REPLICATION = { 'class' : 'SimpleStrategy', 'replication_factor' : 2 }")
                    self.cassandra_session = self.cluster.connect('zooniverse')

                return
            except cassandra.cluster.NoHostAvailable as err:
                print err

        assert False

    def __chunks__(self,l, n):
        """Yield successive n-sized chunks from l."""
        for i in xrange(0, len(l), n):
            yield l[i:i+n]

    def __classification_json_dump__(self):
        annotation_generator = self.__cassandra_annotations__()
        for workflow_id in self.workflows:
            subject_set = self.__get_subjects__(workflow_id,only_retired_subjects=False)

            for subject_id,user_id,annotation,dimensions in annotation_generator(workflow_id,subject_set):
                print annotation
                assert False

    # def __classify__(self,raw_classifications,clustering_aggregations,workflow_id,gold_standard_classifications=None):
    #     # get the raw classifications for the given workflow
    #     # raw_classifications = self.__sort_classifications__(workflow_id,subject_set)
    #     # assert False
    #     return self.classification_alg.__aggregate__(raw_classifications,self.workflows[workflow_id],clustering_aggregations,gold_standard_classifications)

    def __cluster__(self,used_shapes,raw_markings,image_dimensions):
        """
        run the clustering algorithm for a given workflow
        need to have already checked that the workflow requires clustering
        :param workflow_id:
        :return:
        """
        if raw_markings == {}:
            print "warning - empty set of images"
            # print subject_set
            return {}

        # will store the aggregations for all clustering
        # go through the shapes actually used by this project - one at a time
        cluster_aggregation = {}
        for shape in used_shapes:
            # were any additional params provided?
            if shape in self.additional_clustering_args:
                algorithm = self.default_clustering_algs[shape](shape,self.additional_clustering_args[shape])
            else:
                algorithm = self.default_clustering_algs[shape](shape)



            shape_aggregation = algorithm.__aggregate__(raw_markings,image_dimensions)

            # if this is not the first shape we've aggregated - merge in with previous results
            if cluster_aggregation == {}:
                cluster_aggregation = shape_aggregation
            else:
                assert isinstance(cluster_aggregation,dict)
                cluster_aggregation = self.__merge_aggregations__(cluster_aggregation,shape_aggregation)

        return cluster_aggregation

    def __count_check__(self,workflow_id,subject_id):
        """
        for when we want to double check the number of classifications a subject has received
        """
        print subject_id
        # check to see if we have previously stored values, hopefully will task on calls to the DB
        if workflow_id in self.classifications_per_subject:
            if subject_id in self.classifications_per_subject[workflow_id]:
                return self.classifications_per_subject[workflow_id][subject_id]
        else:
            self.classifications_per_subject[workflow_id] = {}

        cursor = self.postgres_session.cursor()
        cursor.execute("SELECT count(*) from classifications where workflow_id="+str(workflow_id) +" AND subject_ids=ARRAY["+ str(subject_id) + "]")
        count = int(cursor.fetchone()[0])

        self.classifications_per_subject[workflow_id][subject_id] = count

        return count


    
    def __enter__(self):
        # check if another instance of the aggregation engine is already running
        # if so, raise an error
        # if not, create the lock file to prevent another instance from starting
        # todo - maybe write something to the lock file in case another instance checks at the
        # todo - exact same time. What about instances for different projects?

        # don't bother with this stuff for stand-alone
        # print expanduser("~")+"/aggregation.lock"
        #  if os.path.isfile(expanduser("~")+"/aggregation.lock"):
        #     raise InstanceAlreadyRunning()
        #  open(expanduser("~")+"/aggregation.lock","w").close()

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # only report to rollbar if we are not in development
        #if (exc_type is not None) and self.report_roll and (self.environment != "development"):
            # load in the yml file - again - this time to get the rollbar token
            #try:
            #    panoptes_file = open("/app/config/aggregation.yml","rb")
            #except IOError:
            #    panoptes_file = open(base_directory+"/Databases/aggregation.yml","rb")
            #api_details = yaml.load(panoptes_file)
            #
            #rollbar_token = api_details[self.environment]["rollbar"]
            #rollbar.init(rollbar_token,self.environment)
            #rollbar.report_exc_info()

        # only update time stamp if there were no problems
        #if exc_type is None:
            #statements_and_params = []
            #insert_statement = self.cassandra_session.prepare("insert into most_recent (project_id,classification) values (?,?)")
            #statements_and_params.append((insert_statement, (self.project_id,self.new_runtime)))
            #execute_concurrent(self.cassandra_session, statements_and_params)

        # shutdown the connection to Cassandra and remove the lock so other aggregation instances
        # can run, regardless of whether an error occurred
        #if self.cassandra_session is not None:
        #    self.cassandra_session.shutdown()

        # remove the lock only if we created the lock
        #if exc_type != InstanceAlreadyRunning:
        #    os.remove(expanduser("~")+"/aggregation.lock")
        return

    def __get_classifications__(self,subject_id,task_id,cluster_index=None,question_id=None):
        # either both of these variables are None or neither of them are
        assert (cluster_index is None) == (question_id is None)

        if cluster_index is None:
            return self.classifications[subject_id][task_id]
        else:
            return self.classifications[subject_id][task_id][cluster_index][question_id]

    def __get_most_recent_cassandra_classification__(self):
        select_statement = "select created_at from classifications where project_id = " + str(self.project_id) + " order by created_at"
        classification_timestamps = self.cassandra_session.execute(select_statement)

        most_recent_date = datetime.datetime(2000,1,1)
        for r in classification_timestamps:
            print classification_timestamps
            most_recent_date = max(most_recent_date,r.created_at)
        print most_recent_date

    def __get_raw_classifications__(self,subject_id,workflow_id):
        version = int(math.floor(float(self.versions[workflow_id])))
        select_statement = self.cassandra_session.prepare("select annotations from "+self.classification_table+" where project_id = ? and subject_id = ? and workflow_id = ? and workflow_version = ?")
        params = (int(self.project_id),subject_id,int(workflow_id),version)
        statements_and_params = []
        statements_and_params.append((select_statement, params))
        results = execute_concurrent(self.cassandra_session, statements_and_params, raise_on_first_error=False)

        assert results[0][0]
        for r in results[0][1]:
            yield json.loads(r.annotations)

        raise StopIteration()

    def __get_retirement_threshold__(self):
        """
        return the number of classifications needed for a subject to be retired
        :param workflow_id:
        :return:
        """
        data = self.__panoptes_call__("workflows?project_id="+str(self.project_id))
        retirement_thresholds = {int(workflow["id"]):workflow["retirement"] for workflow in data["workflows"]}

        # deal with any empty thresholds by using the default value
        for workflow_id,threshold in retirement_thresholds.items():
            if threshold == {}:
                retirement_thresholds[workflow_id] = 15
            else:
                if "options" in threshold:
                    retirement_thresholds[workflow_id] = threshold["options"]["count"]
                else:
                    retirement_thresholds[workflow_id] = threshold["classification_count"]["count"]

        return retirement_thresholds

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
        # print self.host_api+"projects?display_name="+urllib2.quote(self.project_name)
        request = urllib2.Request(self.host_api+"projects?search="+urllib2.quote(self.project_name))
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
        try:
            # put it in json structure and extract id
            return data["projects"][0]["id"]
        except IndexError:
            print self.host_api+"projects?display_name="+urllib2.quote(self.project_name)
            print data
            raise
        # return None

    def __get_subjects__(self,workflow_id):#,only_retired_subjects=False,only_recent_subjects=True):
        """
        gets the subjects to aggregate
        if we need retired subjects, query against the production postgresDB
        if we need only recent subjects, query against the cassandra DB
        :param workflow_id:
        :param only_retired_subjects: return only subjects which have been retired
        :param only_recent_subjects: return subjects which have been classified/marked/transcribed/retired since the last running of the algorithm
        :return:
        """
        subjects = []

        if self.only_retired_subjects:
            stmt = """SELECT * FROM "subjects"
            INNER JOIN "set_member_subjects" ON "set_member_subjects"."subject_id" = "subjects"."id"
            INNER JOIN "subject_workflow_counts" ON "subject_workflow_counts"."set_member_subject_id" = "set_member_subjects"."id"
            WHERE "subject_workflow_counts"."workflow_id" = """+str(workflow_id)+ """ AND "subject_workflow_counts"."retired_at" >= '""" + str(self.previous_runtime) + """'"""
            # WHERE "subject_workflow_counts"."workflow_id" = """+str(workflow_id)+ """ AND "subject_workflow_counts"."retired_at" IS NOT NULL"""

            cursor = self.postgres_session.cursor()
            cursor.execute(stmt)

            for subject in cursor.fetchall():
                subjects.append(subject[0])
        else:
            # stmt = "SELECT subject_id,workflow_version FROM \"classifications\" WHERE \"project_id\" = " + str(self.project_id) + " and \"workflow_id\" = " + str(workflow_id) + " and \"updated_at\" > '" + str(datetime.datetime(2000,1,1)) +"'"
            stmt = "SELECT subject_id,workflow_version FROM classifications WHERE project_id = " + str(self.project_id) + " and workflow_id = " + str(workflow_id)# + " and \"updated_at\" > '" + str(datetime.datetime(2000,1,1)) +"'"
            # filter for subjects which have the correct major version number
            if not self.ignore_versions:
                subjects = set([r.subject_id for r in self.cassandra_session.execute(stmt) if int(r.workflow_version) == int(self.versions[workflow_id]) ])
                if subjects == set():
                    print "no subjects found - maybe remove version filter"
            else:
                subjects = set([r.subject_id for r in self.cassandra_session.execute(stmt)])

        return list(subjects)

    def __get_subject_metadata__(self,subject_id):
        print self.host_api+"subjects/"+str(subject_id)+"?"
        request = urllib2.Request(self.host_api+"subjects/"+str(subject_id)+"?")
        request.add_header("Accept","application/vnd.api+json; version=1")
        request.add_header("Authorization","Bearer "+self.token)

        response = urllib2.urlopen(request)
        body = response.read()

        data = json.loads(body)
        print data

        select = "SELECT workflow_id from classifications where project_id="+str(6) +" and subject_ids = ARRAY[" + str(subject_id) +"]"
        select = "SELECT count(*) from classifications where workflow_id=6 AND subject_ids=ARRAY[493554]"
        print select
        cur = self.postgres_session.cursor()
        cur.execute(select)
        print cur.fetchall()


    def __get_workflow_details_from_file__(self,workflow_file):

        print "get_workflow_details_from_file"
        
        instructions = {}
        workflows = {}
        #updated_at_timestamps = {} # we will use the version for keeping track of what to use
        versions = {}
        retirement = {}
        names = {}

        with open(workflow_file,'rb') as wffile:
            wfreader = csv.reader(wffile,delimiter=',')

            print "workflow file opened: " + workflow_file

            # skip the header
            wfreader.next() # or is it next(wfreader)

            # for each workflow-version in the file
            for row in wfreader:

                # put these all together so easy to change if zooniverse
                # changes the workflow output format (though not the most efficient)
                workflow_id = int(row[0])
                workflow_name = row[1]
                workflow_version = int(row[2])
                workflow_active = (row[3].lower()=="true")
                workflow_tasks = json.loads(row[12])
                workflow_retirement = json.loads(row[13])

                #print "id: " + str(workflow_id)
                #print "active: " + str(workflow_active)
                #print row[3]
                
                # process if it's the active version of the workflow
                if (workflow_active):

                    # save the workflow
                    workflows[workflow_id] = workflow_tasks

                    # and its version
                    versions[workflow_id] = workflow_version

                    # and its name
                    names[workflow_id] = workflow_name

                    # get the retirement limit
                    retirement[workflow_id] = int(workflow_retirement["options"]["count"])

                    # read in the instructions associated with the workflow
                    # not used for the actual aggregation but for printing out results to the user
                    instructions[workflow_id] = {}

                    #print
                    #print workflow_tasks
                    #print
                    
                    for task_id,task in workflow_tasks.iteritems():
                        instructions[workflow_id][task_id] = {}
                        # classification task
                        if task["type"] in ["single","multiple"]:
                            question = task["question"]
                            instructions[workflow_id][task_id]["instruction"] = re.sub("'","",question)
                            instructions[workflow_id][task_id]["answers"] = {}
                            for answer_id,answer in enumerate(task["answers"]):
                                label = answer["label"]
                                label = re.sub("'","",label)
                                instructions[workflow_id][task_id]["answers"][answer_id] = label

                        elif task["type"] == "drawing":
                            instruct_string = task["instruction"]
                            instructions[workflow_id][task_id]["instruction"] = re.sub("'","",instruct_string)

                            instructions[workflow_id][task_id]["tools"] = {}

                            # assert False
                            for tool_index,tool in enumerate(task["tools"]):
                                instructions[workflow_id][task_id]["tools"][tool_index] = {}
                                label = tool["label"]
                                instructions[workflow_id][task_id]["tools"][tool_index]["marking tool"] = re.sub("'","",label)

                                if ("details" in tool) and (tool["details"] != []):
                                    instructions[workflow_id][task_id]["tools"][tool_index]["followup_questions"] = {}
    
                                    for subtask_index,subtask in enumerate(tool["details"]):
                                        instructions[workflow_id][task_id]["tools"][tool_index]["followup_questions"][subtask_index] = {}
                                        instructions[workflow_id][task_id]["tools"][tool_index]["followup_questions"][subtask_index]["question"] = subtask["question"]
                                        instructions[workflow_id][task_id]["tools"][tool_index]["followup_questions"][subtask_index]["answers"] = {}
                                        for answer_index,answers in enumerate(subtask["answers"]):
                                            instructions[workflow_id][task_id]["tools"][tool_index]["followup_questions"][subtask_index]["answers"][answer_index] = answers
                        else:
                            assert False

        return workflows,versions,instructions,retirement,names
                
                
                

        

    def __get_workflow_details__(self,given_workflow_id=None):
        """
        get everything about the workflows - if no id is provided, go with everything
        :param workflow_id:
        :return:
        """
        request = "workflows?project_id="+str(self.project_id)
        data = self.__panoptes_call__(request)
        
        instructions = {}
        workflows = {}
        updated_at_timestamps = {}
        versions = {}

        for individual_workflow in data["workflows"]:
            workflow_id = int(individual_workflow["id"])
            if (given_workflow_id is None) or (workflow_id == given_workflow_id):
                # read in the basic structure of the workflow
                workflows[workflow_id] = self.__readin_tasks__(workflow_id)

                # read in the instructions associated with the workflow
                # not used for the actual aggregation but for printing out results to the user
                instructions[workflow_id] = {}
                for task_id,task in individual_workflow["tasks"].items():
                    instructions[workflow_id][task_id] = {}
                    # classification task
                    if task["type"] in ["single","multiple"]:
                        question = task["question"]
                        instructions[workflow_id][task_id]["instruction"] = re.sub("'","",question)
                        instructions[workflow_id][task_id]["answers"] = {}
                        for answer_id,answer in enumerate(task["answers"]):
                            label = answer["label"]
                            label = re.sub("'","",label)
                            instructions[workflow_id][task_id]["answers"][answer_id] = label

                    elif task["type"] == "drawing":
                        instruct_string = task["instruction"]
                        instructions[workflow_id][task_id]["instruction"] = re.sub("'","",instruct_string)

                        instructions[workflow_id][task_id]["tools"] = {}

                        # assert False
                        for tool_index,tool in enumerate(task["tools"]):
                            instructions[workflow_id][task_id]["tools"][tool_index] = {}
                            label = tool["label"]
                            instructions[workflow_id][task_id]["tools"][tool_index]["marking tool"] = re.sub("'","",label)

                            if ("details" in tool) and (tool["details"] != []):
                                instructions[workflow_id][task_id]["tools"][tool_index]["followup_questions"] = {}

                                for subtask_index,subtask in enumerate(tool["details"]):
                                    instructions[workflow_id][task_id]["tools"][tool_index]["followup_questions"][subtask_index] = {}
                                    instructions[workflow_id][task_id]["tools"][tool_index]["followup_questions"][subtask_index]["question"] = subtask["question"]
                                    instructions[workflow_id][task_id]["tools"][tool_index]["followup_questions"][subtask_index]["answers"] = {}
                                    for answer_index,answers in enumerate(subtask["answers"]):
                                        instructions[workflow_id][task_id]["tools"][tool_index]["followup_questions"][subtask_index]["answers"][answer_index] = answers
                    else:
                        assert False

                # read in when the workflow last went through a major change
                # real problems with subjects that were retired before that date or classifications
                # given for a subject before that date (since the workflow may have changed completely)
                updated_at_timestamps[workflow_id] = individual_workflow["updated_at"]

                # get the MAJOR version number
                versions[workflow_id] = int(math.floor(float(individual_workflow["version"])))

        return workflows,versions,instructions,updated_at_timestamps

    def __get_users_per_cluster__(self,workflow_id,subject_id,task_id,shape):
        """
        return the center of each cluster - for plotting - and associated probability of existing
        :param workflow_id:
        :param subject_id:
        :param task_id:
        :param axes:
        :param threshold:
        :return:
        """
        postgres_cursor = self.postgres_session.cursor()
        # todo - generalize for panoptes
        stmt = "select aggregation from aggregations where workflow_id = " + str(workflow_id) + " and subject_id = '" + str(subject_id) + "'"
        # stmt = "select aggregation from aggregations where subject_id = '" + str(subject_id) + "'"
        postgres_cursor.execute(stmt)

        # todo - this should be a dict but doesn't seem to be - hmmmm :/
        agg = postgres_cursor.fetchone()

        if agg is None:
            print "returning none"
            return {}

        if isinstance(agg[0],str):
            aggregations = json.loads(agg[0])
        else:
            aggregations = agg[0]

        assert isinstance(aggregations,dict)

        users = {}
        for cluster in aggregations[str(task_id)][shape + " clusters"].values():
            if cluster == "cluster_index":
                continue

            center = tuple(cluster["center"])
            print cluster
            users[center] = cluster["users"]
            # # todo - should be only one way - check why both are necessary
            # if isinstance(cluster['existence'][0],dict):
            #     probabilities[center] = cluster['existence'][0]['1']
            # else:
            #     probabilities[center] = cluster['existence'][0][1]

        return users

    def __get_workflow_names__(self):
        """
        get the names for each workflow
        :return:
        """
        data = self.__panoptes_call__("workflows?project_id="+str(self.project_id))

        names = {int(workflow["id"]) : workflow["display_name"] for workflow in data["workflows"]}
        return names

    def __image_setup__(self,subject_id,download=True):
        """
        get the local file name for a given subject id and downloads that image if necessary
        :param subject_id:
        :return:
        """

        data = self.__panoptes_call__("subjects/"+str(subject_id)+"?")

        url = str(data["subjects"][0]["locations"][0]["image/jpeg"])

        slash_index = url.rfind("/")
        fname = url[slash_index+1:]
        url = "http://zooniverse-static.s3.amazonaws.com/panoptes-uploads.zooniverse.org/production/subject_location/"+url[slash_index+1:]


        image_path = base_directory+"/Databases/images/"+fname

        if not(os.path.isfile(image_path)):
            if download:
                print "downloading"
                urllib.urlretrieve(url, image_path)
            # raise ImageNotDownloaded()

        return image_path

    def __load_subjects__(self,workflow_id):
        """
        load the list of subject ids from Cassandra
        :param workflow_id:
        :return:
        """
        # version = int(math.floor(float(self.versions[workflow_id])))
        stmt = "SELECT subject_id FROM subjects WHERE project_id = " + str(self.project_id) + " and workflow_id = " + str(workflow_id)# + " and workflow_version = " + str(version)
        subjects = set([r.subject_id for r in self.cassandra_session.execute(stmt)])

        assert subjects != ()

        return list(subjects)

    def __merge_aggregations__(self,agg1,agg2):
        """
        merge aggregations - could be clustering and classification aggregations
        could be two different clustering aggregations for different shapes
        :param clust_agg:
        :param class_agg:
        :return:
        """
        # start with the clustering results and merge in the classification results
        # assert (agg1 is not None) or (agg2 is not None)
        assert isinstance(agg1,dict) and isinstance(agg2,dict)

        if agg1 == {}:
            return agg2
        elif agg2 == {}:
            return agg1

        for kw in agg2:
            if kw not in agg1:
                agg1[kw] = agg2[kw]
            elif agg1[kw] != agg2[kw]:
                try:
                    agg1[kw] = self.__merge_aggregations__(agg1[kw],agg2[kw])
                except TypeError:
                    print "====-----"
                    print type(agg1)
                    print type(agg2)
                    print agg1
                    print agg2
                    print kw
                    assert False
        return agg1

    def __migrate__(self):
        """
        move data from postgres to cassandra
        :return:
        """
        # no need to migrate if we are using csv input files
        if self.csv_classification_file is not None:
            return

        try:
            self.cassandra_session.execute("CREATE TABLE most_recent (project_id int, classification timestamp, PRIMARY KEY(project_id))")
        except cassandra.AlreadyExists:
            pass

        # uncomment this code if this is the first time you've run migration on whatever machine
        # will create the necessary cassandra tables for you - also useful if you need to reset
        # try:
        #     self.cassandra_session.execute("drop table classifications")
        #     self.cassandra_session.execute("drop table subjects")
        #     print "tables dropped"
        # except cassandra.InvalidRequest:
        #     print "tables did not already exist"
        #
        # try:
        #     self.cassandra_session.execute("CREATE TABLE classifications( project_id int, user_id int, workflow_id int, created_at timestamp,annotations text,  updated_at timestamp, user_group_id int, user_ip inet,  completed boolean, gold_standard boolean, subject_id int, workflow_version int,metadata text, PRIMARY KEY(project_id,workflow_id,subject_id,workflow_version,user_ip,user_id) ) WITH CLUSTERING ORDER BY (workflow_id ASC,subject_id ASC,workflow_version ASC,user_ip ASC,user_id ASC);")
        # except cassandra.AlreadyExists:
        #     pass
        #
        # try:
        #     self.cassandra_session.execute("CREATE TABLE subjects (project_id int, workflow_id int, workflow_version int, subject_id int, PRIMARY KEY(project_id,workflow_id,subject_id,workflow_version));")
        # except cassandra.AlreadyExists:
        #     pass

        subject_listing = set()

        # only migrate classifications created since we last ran this code
        # use >= just in case some classifications have the exact same time stamp - rare but could happen
        select = "SELECT * from classifications where project_id="+str(self.project_id)+ " and created_at >= '" + str(self.previous_runtime) +"'"
        cur = self.postgres_session.cursor()
        cur.execute(select)

        # self.migrated_subjects = set()
        print "trying to migrate " + str(self.project_id)
        insert_statement = self.cassandra_session.prepare("""
                insert into classifications (project_id, user_id, workflow_id,  created_at,annotations, updated_at, user_group_id, user_ip, completed, gold_standard, subject_id, workflow_version,metadata)
                values (?,?,?,?,?,?,?,?,?,?,?,?,?)""")

        statements_and_params = []
        migrated = {}

        most_recent_classification = datetime.datetime(2000,1,1)

        for ii,t in enumerate(cur.fetchall()):
            id_,project_id,user_id,workflow_id,annotations,created_at,updated_at,user_group_id,user_ip,completed,gold_standard,expert_classifier,metadata,subject_ids,workflow_version = t

            self.new_runtime = max(self.new_runtime,created_at)

            most_recent_classification = max(most_recent_classification,updated_at)

            # can't really handle pairwise comparisons yet
            assert len(subject_ids) == 1
            # self.migrated_subjects.add(subject_ids[0])

            if gold_standard != True:
                gold_standard = False

            if not isinstance(user_group_id,int):
                user_group_id = -1

            if not isinstance(user_id,int):
                user_id = -1
            # get only the major version of the workflow
            workflow_version = int(math.floor(float(workflow_version)))
            id = workflow_id,subject_ids[0]
            # if subject_ids[0] == 4153:
            #     print workflow_id,user_ip

            if id not in migrated:
                migrated[id] = 0
            migrated[id] += 1

            # cassandra can only handle json in str format - so convert if necessary
            # "if necessary" - I think annotations should always start off as json format but
            # I seem to remember sometime, somehow, that that wasn't the case - so just to be sure
            if isinstance(annotations,dict) or isinstance(annotations,list):
                annotations = json.dumps(annotations)

            assert isinstance(annotations,str)
            # print ii, project_id,workflow_id

            params = (project_id, user_id, workflow_id,created_at, annotations, updated_at, user_group_id, user_ip,  completed, gold_standard,  subject_ids[0], workflow_version,json.dumps(metadata))
            statements_and_params.append((insert_statement, params))

            # params2 = (project_id,workflow_id,workflow_version,subject_ids[0])
            # statements_and_params.append((insert_statement2,params2))
            subject_listing.add((project_id,workflow_id,workflow_version,subject_ids[0]))

            if len(statements_and_params) == 100:
                results = execute_concurrent(self.cassandra_session, statements_and_params, raise_on_first_error=True)
                # print results
                statements_and_params = []

        # insert any "left over" classifications
        if statements_and_params != []:
            results = execute_concurrent(self.cassandra_session, statements_and_params, raise_on_first_error=True)
            # print results

        # now update the subject ids
        statements_and_params = []
        insert_statement = self.cassandra_session.prepare("""
                insert into subjects (project_id,workflow_id,workflow_version,subject_id)
                values (?,?,?,?)""")
        for s in subject_listing:
            statements_and_params.append((insert_statement, s))

            if len(statements_and_params) == 100:
                results = execute_concurrent(self.cassandra_session, statements_and_params, raise_on_first_error=True)
                statements_and_params = []
        if statements_and_params != []:
            results = execute_concurrent(self.cassandra_session, statements_and_params, raise_on_first_error=True)
            # print results

        # code based on from http://stackoverflow.com/questions/16532566/how-to-insert-a-datetime-into-a-cassandra-1-2-timestamp-column
        # todo - get this to work. I've tired every combination I can think of
        # self.cassandra_session.execute("UPDATE most_recent SET classification=:ts WHERE project_id=:id;", dict(ts=most_recent_classification.isoformat(), id=self.project_id))

        print self.new_runtime



    def __panoptes_call__(self,url):
        """
        for all the times we want to call the panoptes api
        :param url:
        :return:
        """
        request = urllib2.Request(self.host_api+url)
        request.add_header("Accept","application/vnd.api+json; version=1")
        # only add the token if we have a secure connection
        if self.token is not None:
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

        data = json.loads(body)

        return data

    def __panoptes_connect__(self,api_details):
        """
        make the main connection to Panoptes - through http
        the below code is based heavily on code originally by Margaret Kosmala
        https://github.com/mkosmala/PanoptesScripts
        :return:
        """
        # details for connecting to Panoptes
        self.host = api_details["panoptes"]
        self.host_api = self.host+"api/"
        self.app_client_id = api_details["app_client_id"]
        self.token = None

        # the http api for connecting to Panoptes
        self.http_api = None

        user_name = api_details["panoptes_username"]
        password = api_details["panoptes_password"]

        for i in range(20):
            try:
                print "attempt: " + str(i)
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
                devise_login_data=("{\"user\": {\"login\":\""+user_name+"\",\"password\":\""+password+
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

    def __panoptes_aggregation__(self):

        # request = urllib2.Request(self.host_api+"aggregations?workflow_id="+str(2)+"&subject_id="+str(458021)+"&admin=true")
        request = urllib2.Request(self.host_api+"aggregations?workflow_id="+str(2)+"&admin=true")
        print self.host_api+"aggregations?workflow_id="+str(2)+",subject_id="+str(458021)
        # request = urllib2.Request(self.host_api+"workflows/project_id="+str(self.project_id))
        request.add_header("Accept","application/vnd.api+json; version=1")
        request.add_header("Authorization","Bearer "+self.token)

        # request
        try:
            response = urllib2.urlopen(request)
        except urllib2.HTTPError as e:
            sys.stderr.write('The server couldn\'t fulfill the request.\n')
            sys.stderr.write('Error code: ' + str(e.code) + "\n")
            sys.stderr.write('Error response body: ' + str(e.read()) + "\n")
            raise
        except urllib2.URLError as e:
            sys.stderr.write('We failed to reach a server.\n')
            sys.stderr.write('Reason: ' + str(e.reason) + "\n")
            raise
        else:
            # everything is fine
            body = response.read()

        # put it in json structure and extract id
        data = json.loads(body)

        print data


    def __plot_image__(self,subject_id,axes):
        # todo - still learning about Matplotlib and axes
        # see http://matplotlib.org/users/artists.html
        fname = self.__image_setup__(subject_id)

        for i in range(10):
            try:
                # fig = plt.figure()
                # ax = fig.add_subplot(1, 1, 1)
                image_file = cbook.get_sample_data(fname)
                image = plt.imread(image_file)
                # fig, ax = plt.subplots()
                im = axes.imshow(image)

                return self.__get_subject_dimension__(subject_id)
            except IOError:
                # try downloading that image again
                os.remove(fname)
                self.__image_setup__(subject_id)

        assert False

    # def __plot_individual_points__(self,subject_id,task_id,shape):
    #     for cluster in self.cluster_alg.clusterResults[task_id][shape][subject_id]:
    #         for pt in cluster["points"]:
    #             if shape == "line":
    #                 plt.plot([pt[0],pt[1]],[pt[2],pt[3]],color="red")
    #             elif shape == "point":
    #                 plt.plot([pt[0]],[pt[1]],".",color="red")
    #             elif shape == "circle":
    #                 print (pt[0],pt[1]),pt[2]
    #                 e = Ellipse((pt[0],pt[1]),width = pt[2],height=pt[2],fill=False,color="red")
    #                 # circle = plt.Circle((pt[0],pt[1]),pt[2],color=cnames.values()[users.index(user_id)])
    #                 plt.gca().add_patch(e)
    #                 # ax.add_artist(e)
    #                 # e.set_alpha(0)
    #             elif shape == "ellipse":
    #                 # ("angle","rx","ry","x","y")
    #                 e = Ellipse((pt[3],pt[4]),width = pt[2],height=pt[1],fill=False,angle=pt[0],color="red")
    #             elif shape == "rectangle":
    #                 plt.plot([pt[0],pt[0]+pt[2]],[pt[1],pt[1]],color="red")
    #                 plt.plot([pt[0],pt[0]],[pt[1],pt[1]+pt[3]],color="red")
    #                 plt.plot([pt[0]+pt[2],pt[0]+pt[2]],[pt[1],pt[1]+pt[3]],color="red")
    #                 plt.plot([pt[0],pt[0]+pt[2]],[pt[1]+pt[3],pt[1]+pt[3]],color="red")
    #             else:
    #                 print shape
    #                 assert False
    #
    #     plt.axis('scaled')

    # def __get_cluster_markings__(self,workflow_id,subject_id,task_id,shape,axes,percentile_threshold=None,correct_pts=None,incorrect_pts=None):
    def __get_cluster_markings__(self,workflow_id,subject_id,task_id,shape):
        """
        return the center of each cluster - for plotting - and associated probability of existing
        :param workflow_id:
        :param subject_id:
        :param task_id:
        :param axes:
        :param threshold:
        :return:
        """
        postgres_cursor = self.postgres_session.cursor()
        # todo - generalize for panoptes
        stmt = "select aggregation from aggregations where workflow_id = " + str(workflow_id) + " and subject_id = '" + str(subject_id) + "'"
        # stmt = "select aggregation from aggregations where subject_id = '" + str(subject_id) + "'"
        postgres_cursor.execute(stmt)

        # todo - this should be a dict but doesn't seem to be - hmmmm :/
        agg = postgres_cursor.fetchone()

        if agg is None:
            print "returning none"
            return {}

        if isinstance(agg[0],str):
            aggregations = json.loads(agg[0])
        else:
            aggregations = agg[0]

        assert isinstance(aggregations,dict)

        probabilities = {}
        for cluster in aggregations[str(task_id)][shape + " clusters"].values():
            if cluster == "cluster_index":
                continue

            center = tuple(cluster["center"])

            # todo - should be only one way - check why both are necessary
            if isinstance(cluster['existence'][0],dict):
                probabilities[center] = cluster['existence'][0]['1']
            else:
                probabilities[center] = cluster['existence'][0][1]

        return probabilities




    # def __plot__(self,workflow_id,task_id):
    #     print "plotting"
    #     try:
    #         print "----"
    #         for shape in self.cluster_alg.clusterResults[task_id]:
    #             for subject_id in self.cluster_alg.clusterResults[task_id][shape]:
    #                 print subject_id
    #                 if (len(self.users_per_subject[subject_id]) >= 1):# and (subject_id in self.classification_alg.results):
    #                     # if self.cluster_alg.clusterResults[task][shape][subject_id]["users"]
    #                     self.__plot_image__(subject_id)
    #                     self.__plot_individual_points__(subject_id,task_id,shape)
    #                     # self.__plot_cluster_results__(subject_id,task,shape)
    #
    #                     if (self.classification_alg is not None) and (subject_id in self.classification_alg.results):
    #                         classification_task = "init"
    #                         classifications = self.classification_alg.results[subject_id][classification_task]
    #                         # print classifications
    #                         votes,total = classifications
    #                         title = self.description[classification_task][0]
    #                         # print self.description
    #                         for answer_index,percentage in votes.items():
    #                             if title != "":
    #                                 title += "\n"
    #                             title += self.description[classification_task][answer_index+1] + ": " + str(int(percentage*total))
    #                         # print  self.description[classification_task][0]
    #                         # print title
    #
    #                         plt.title(title)
    #                     plt.title("number of users: " + str(len(self.users_per_subject[subject_id][task_id])))
    #                     plt.savefig("/home/greg/Databases/"+self.project_short_name+"/markings/"+str(subject_id)+".jpg")
    #                     plt.close()
    #                     # assert False
    #     except KeyError as e:
    #         print self.cluster_alg.clusterResults.keys()
    #         raise

    def __postgres_connect__(self,database_details):
        print "connecting to postgres db: " + database_details["postgres_host"]

        # build up the connection details
        details = ""
        details += "dbname = '" +database_details["postgres_db"] +"'"
        details += " user = '" + database_details["postgres_username"] + "'"
        details += " password = '"+database_details["postgres_password"]+"' "
        details += " host ='" + database_details["postgres_host"] + "'"

        # host = database_details["host"]

        for i in range(20):
            try:
                self.postgres_session = psycopg2.connect(details)
                # self.postgres_cursor = self.postgres_session.cursor()
                break
            except psycopg2.OperationalError as e:
                print e
                pass

        if self.postgres_session is None:
            raise psycopg2.OperationalError()

        # cursor = self.postgres_session.cursor()

    def __readin_tasks__(self,workflow_id):
        """
        get the details for each task - for example, what tasks might we want to run clustering algorithms on
        and if so, what params related to that task are relevant
        :return:
        """
        # get the tasks associated with the given workflow
        select = "SELECT tasks from workflows where id = " + str(workflow_id)
        cursor = self.postgres_session.cursor()

        cursor.execute(select)
        try:
            tasks = cursor.fetchone()[0]
        except:
            raise WorkflowNotfound(workflow_id)


        # which of these tasks have classifications associated with them?
        classification_tasks = {}
        # which have drawings associated with them
        marking_tasks = {}

        # convert to json is necessary - not sure why this is necessary but it does happen
        # see https://github.com/zooniverse/aggregation/issues/7
        if isinstance(tasks,str) or isinstance(tasks,unicode):
            tasks = json.loads(tasks)

        for task_id in tasks:
            # self.task_type[task_id] = tasks[task_id]["type"]
            # if the task is a drawing one, get the necessary details for clustering
            print tasks[task_id]["type"]
            # print tasks[task_id]

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
                    if ("details" in tool) and (tool["details"] is not None) and (tool["details"] != []):
                        print tool["details"]
                        # is this the first follow up question associated with this task?
                        if task_id not in classification_tasks:
                            classification_tasks[task_id] = {}
                        classification_tasks[task_id][tool_id] = []

                        # note whether each of these questions are single or multiple response
                        for followup_question in tool["details"]:
                            question_type = followup_question["type"]
                            classification_tasks[task_id][tool_id].append(question_type)

                    if tool["type"] == "line":
                        marking_tasks[task_id].append("line")
                    elif tool["type"] == "ellipse":
                        marking_tasks[task_id].append("ellipse")
                    elif tool["type"] == "point":
                        marking_tasks[task_id].append("point")
                    elif tool["type"] == "circle":
                        marking_tasks[task_id].append("circle")
                    elif tool["type"] == "rectangle":
                        marking_tasks[task_id].append("rectangle")
                    elif tool["type"] == "polygon":
                        marking_tasks[task_id].append("polygon")
                    else:
                        print tool
                        assert False

            elif tasks[task_id]["type"] in ["single","multiple"]:
                # multiple means that more than one response is allowed
                classification_tasks[task_id] = tasks[task_id]["type"]
            else:
                # unknown task type
                assert False

        return classification_tasks,marking_tasks

    def __set_classification_alg__(self,alg,params={}):
        self.classification_alg = alg(params)
        assert isinstance(self.classification_alg,classification.Classification)

    def __sort_annotations__(self,workflow_id,subject_set=None,expert=None):
        """
        experts is when you have experts for whom you don't want to read in there classifications
        :param workflow_id:
        :param subject_set:
        :param experts:
        :return:
        """
        # if we have not been provided with a csv classification file, connect to cassandra
        if self.csv_classification_file is None:
            annotation_generator = self.__cassandra_annotations__()
        else:
            # todo - add support for csv annotatons
            annotation_generator = self.__csv_annotations__

        # keep track of the non-logged in users for each subject
        non_logged_in_users = dict()

        # load the classification and marking json dicts - helps parse annotations
        classification_tasks,marking_tasks = self.workflows[workflow_id]

        # this is what we return
        raw_classifications = {}
        raw_markings = {}

        users_per_marking_task = {}

        image_dimensions = {}

        for subject_id,user_id,annotation,dimensions in annotation_generator(workflow_id,subject_set):
            if user_id == expert:
                continue

            if dimensions is not None:
                image_dimensions[subject_id] = dimensions

            # todo - maybe having user_id=="" would be useful for penguins
            if (user_id == -1):
                # if this is the first non-logged-in-user for this subject
                if subject_id not in non_logged_in_users:
                    non_logged_in_users[subject_id] = 0
                else:
                    non_logged_in_users[subject_id] += 1
                # non_logged_in_users += -1
                user_id = non_logged_in_users[subject_id]

            # annotations = json.loads(record.annotations)
            annotation = json.loads(annotation)

            # go through each annotation and get the associated task
            for task in annotation:
                task_id = task["task"]

                # is this a marking task?
                if task_id in marking_tasks:
                    # if a user gets to marking task but makes no markings, we want to record that the user
                    # has still seen that image/task. If a user never gets to a marking task for that image
                    # than they are irrelevant
                    # create here so even if we have empty images, we will know that we aggregated them
                    # make sure to not overwrite/delete existing information - sigh
                    if task_id not in raw_markings:
                        raw_markings[task_id] = {}
                    for shape in set(marking_tasks[task_id]):
                        if shape not in raw_markings[task_id]:
                            raw_markings[task_id][shape] = {}
                        if subject_id not in raw_markings[task_id][shape]:
                            raw_markings[task_id][shape][subject_id] = []

                    # if (subject_id,workflow_id,task_id) not in users_per_marking_task:
                    #     users_per_marking_task[(subject_id,workflow_id,task_id)] = 1
                    # else:
                    #     users_per_marking_task[(subject_id,workflow_id,task_id)] += 1

                    if not isinstance(task["value"],list):
                        print "not properly formed marking - skipping"
                        continue

                    # kind track of which shapes the user did mark - we need to keep track of any shapes
                    # for which the user did not make any marks at all of
                    # because a user not seeing something is important
                    spotted_shapes = set()

                    for marking in task["value"]:
                        # what kind of tool made this marking and what was the shape of that tool?
                        try:
                            tool = marking["tool"]
                            shape = marking_tasks[task_id][tool]
                        except KeyError:
                            tool = None
                            shape = marking["type"]

                        if shape ==  "image":
                            # todo - treat image like a rectangle
                            continue

                        if shape not in self.marking_params_per_shape:
                            print "unrecognized shape: (skipping) " + shape
                            continue

                        try:
                            # extract the params specifically relevant to the given shape
                            relevant_params = self.marking_params_per_shape[shape](marking,dimensions)
                        except InvalidMarking as e:
                            # print e
                            continue

                        spotted_shapes.add(shape)
                        raw_markings[task_id][shape][subject_id].append((user_id,relevant_params,tool))

                        # is this a confusing shape?
                        if (task_id in classification_tasks) and ("shapes" in classification_tasks[task_id]) and (shape in classification_tasks[task_id]["shapes"]):
                            if task_id not in raw_classifications:
                                raw_classifications[task_id] = {}
                            if shape not in raw_classifications[task_id]:
                                raw_classifications[task_id][shape] = {}
                            if subject_id not in raw_classifications[task_id][shape]:
                                raw_classifications[task_id][shape][subject_id] = {}

                            # the [:5] is to make sure that the relevant params don't become any arbitrarly long list of values (which could happen with polygons)
                            raw_classifications[task_id][shape][subject_id][(relevant_params[:5],user_id)] = tool

                        # are there follow up questions? - check that both this task has any follow ups
                        # and that this particular tool has a follow up
                        if (task_id in classification_tasks) and (tool in classification_tasks[task_id]):

                            # there could be multiple follow up questions
                            # need to use range(len()) since the individual values are either "single" or "multiple"
                            for local_subtask_id in range(len(classification_tasks[task_id][tool])):
                                global_subtask_id = str(task_id)+"_"+str(tool)+"_"+str(local_subtask_id)
                                if global_subtask_id not in raw_classifications:
                                    raw_classifications[global_subtask_id] = {}
                                if subject_id not in raw_classifications[global_subtask_id]:
                                    raw_classifications[global_subtask_id][subject_id] = {}

                                # # specific tool matters, not just shape
                                subtask_value = marking["details"][local_subtask_id]["value"]
                                # if tool not in raw_classifications[global_subtask_id][subject_id]:
                                #     raw_classifications[global_subtask_id][subject_id][tool] = {}
                                raw_classifications[global_subtask_id][subject_id][(relevant_params[:5],user_id)] = subtask_value

                    # note which shapes the user saw nothing of
                    # otherwise, it will be as if the user didn't see the subject in the first place
                    # useful for calculating the probability of existence for clusters
                    for shape in set(marking_tasks[task_id]):
                        if shape not in spotted_shapes:
                            raw_markings[task_id][shape][subject_id].append((user_id,None,None))

                # we a have a pure classification task
                else:
                    if task_id not in raw_classifications:
                        raw_classifications[task_id] = {}
                    if subject_id not in raw_classifications[task_id]:
                        raw_classifications[task_id][subject_id] = []
                    # if task_id == "init":
                    #     print task_id,task["value"]
                    # todo - I think [[]] is an old annotation output
                    # todo - the value doesn't really make sense, so I'm skipping it (should be rare)
                    if task["value"] != [[]]:
                        raw_classifications[task_id][subject_id].append((user_id,task["value"]))


        return raw_classifications,raw_markings,image_dimensions

    def __subject_ids_in_set__(self,set_id):
        # request = urllib2.Request(self.host_api+"aggregations?workflow_id="+str(2)+"&subject_id="+str(458021)+"&admin=true")
        request = urllib2.Request(self.host_api+"set_member_subjects?subject_set_id="+str(set_id))
        # request = urllib2.Request(self.host_api+"workflows/project_id="+str(self.project_id))
        request.add_header("Accept","application/vnd.api+json; version=1")
        request.add_header("Authorization","Bearer "+self.token)

        # request
        try:
            response = urllib2.urlopen(request)
        except urllib2.HTTPError as e:
            sys.stderr.write('The server couldn\'t fulfill the request.\n')
            sys.stderr.write('Error code: ' + str(e.code) + "\n")
            sys.stderr.write('Error response body: ' + str(e.read()) + "\n")
            raise
        except urllib2.URLError as e:
            sys.stderr.write('We failed to reach a server.\n')
            sys.stderr.write('Reason: ' + str(e.reason) + "\n")
            raise
        else:
            # everything is fine
            body = response.read()

        # put it in json structure and extract id
        data = json.loads(body)

        subjects = []

        for u in data["set_member_subjects"]:
            subjects.append(u["links"]["subject"])

        return subjects

    def __upsert_results__(self,workflow_id,aggregations):
        """
        see
        # http://stackoverflow.com/questions/8134602/psycopg2-insert-multiple-rows-with-one-query
        :param workflow_id:
        :param aggregations:
        :return:
        """
        # subject_ids = [id_ for id_ in aggregations if id_ != "param"]
        # cur.executemany("""INSERT INTO bar(first_name,last_name) VALUES (%(first_name)s, %(last_name)s)""", namedict)

        # self.postgres_cursor.execute("CREATE TEMPORARY TABLE newvals(workflow_id int, subject_id int, aggregation jsonb, created_at timestamp, updated_at timestamp)")
        postgres_cursor = self.postgres_session.cursor()

        try:
            postgres_cursor.execute("CREATE TEMPORARY TABLE newvals(workflow_id int, subject_id " + self.subject_id_type+ ", aggregation jsonb)")
        except psycopg2.ProgrammingError as e:
            # todo - the table should always be deleted after its use, so this should rarely happen
            # todo - need to reset the connection
            print "temporary table already exists - huh"
            self.postgres_session.rollback()
            postgres_cursor = self.postgres_session.cursor()
            postgres_cursor.execute("truncate table newvals")
            self.postgres_session.commit()


        try:
            postgres_cursor.execute("select subject_id from aggregations where workflow_id = " + str(workflow_id))
            r = [i[0] for i in postgres_cursor.fetchall()]
        except psycopg2.ProgrammingError:
            self.postgres_session.rollback()
            postgres_cursor = self.postgres_session.cursor()
            postgres_cursor.execute("create table aggregations(workflow_id int, subject_id " + self.subject_id_type+ ", aggregation json,created_at timestamp, updated_at timestamp)")
            r = []

        update_str = ""
        insert_str = ""

        update_counter = 0
        insert_counter = 0

        # todo - sort the subject ids so that searching is faster
        for subject_id in aggregations:
            # todo - maybe get rid of param in subject_ids - end users won't see it anyways
            if subject_id == "param":
                continue

            if subject_id in r:
                # we are updating
                try:
                    update_str += ","+postgres_cursor.mogrify("(%s,%s,%s)", (workflow_id,subject_id,json.dumps(aggregations[subject_id])))
                    update_counter += 1
                except UnicodeDecodeError:
                    print workflow_id
                    print subject_id
                    print aggregations[subject_id]
                    raise
            else:
                # we are inserting a brand new aggregation
                insert_str += ","+postgres_cursor.mogrify("(%s,%s,%s,%s,%s)", (workflow_id,subject_id,json.dumps(aggregations[subject_id]),str(datetime.datetime.now()),str(datetime.datetime.now())))
                insert_counter += 1

        if update_str != "":
            # are there any updates to actually be done?
            # todo - the updated and created at dates are not being maintained - I'm happy with that
            print "updating " + str(update_counter) + " subjects"
            postgres_cursor.execute("INSERT INTO newvals (workflow_id, subject_id, aggregation) VALUES " + update_str[1:])
            postgres_cursor.execute("UPDATE aggregations SET aggregation = newvals.aggregation FROM newvals WHERE newvals.subject_id = aggregations.subject_id and newvals.workflow_id = aggregations.workflow_id")
        if insert_str != "":
            print "inserting " + str(insert_counter) + " subjects"
            postgres_cursor.execute("INSERT INTO aggregations (workflow_id, subject_id, aggregation, created_at, updated_at) VALUES " + insert_str[1:])
        self.postgres_session.commit()

    def __yield_aggregations__(self,workflow_id,subject_set=None):
        """
        generator for giving aggregation results per subject id/task
        """

        # we'll have to come up with another way to do this rather than using databases...
        # this bit will have to be rewritten to retrieve the aggregations
        # but we'll need to store them somewhere first...


        stmt = "select subject_id,aggregation,updated_at from aggregations where workflow_id = " + str(workflow_id)
        if subject_set != None:
            stmt += " and subject_id = " + str(subject_set)
        cursor = self.postgres_session.cursor()

        cursor.execute(stmt)

        for r in cursor.fetchall():
            aggregation = r[1]

            if isinstance(aggregation,str):
                aggregation = json.loads(aggregation)
            elif not isinstance(aggregation,dict):
                print type(aggregation)
            assert isinstance(aggregation,dict)

            yield r[0],aggregation

            # for task_id in aggregation:
            #     if task_id in [" instructions"," metadata","param"]:
            #         continue
            #
            #     # we have an instance of marking
            #     # if isinstance(aggregation[task_id],dict):
            #     yield r[0],task_id,aggregation[task_id]

if __name__ == "__main__":
    # todo - use getopt

    if len(sys.argv) < 5:
        print "Format: aggregation_api.py <classifications file> <subjects file> <workflows file> <output dir>"
        exit(1)

    # we'd like to be passed the name of the classifications file
    classifications_file = sys.argv[1]

    # do we need the subjects file, too? why not...
    subjects_file = sys.argv[2]

    # and the workflows
    workflows_file = sys.argv[3]

    # output directory
    output_dir = sys.argv[4]

    # I don't need to identify projects, just need the csv file
    #project_identifier = sys.argv[1]

    # Nor do I care about the environment
    #if len(sys.argv) > 2:
    #    environment = sys.argv[2]
    #else:
    #    environment = "development"

    with AggregationAPI(classifications_file,subjects_file,workflows_file) as project:
#    with AggregationAPI(project_identifier,environment,report_rollbar=True) as project:
        # project.__migrate__()
        # project.__aggregate__()

        c = csv_output.CsvOut(project,output_dir)
        c.__write_out__()



