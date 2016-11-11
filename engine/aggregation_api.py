#!/usr/bin/env python
from __future__ import print_function
import matplotlib
matplotlib.use('WXAgg')
import os
import yaml
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
import blob_clustering
import rectangle_clustering
import gorongosa_aggregation
import time
import survey_aggregation
from dateutil import parser
# import setproctitle
import cassandra
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent
import psycopg2
import csv_output
import helper_functions
from helper_functions import warning
from panoptes_client import Panoptes

base_directory = "/home/ggdhines/"



# see below for a discussion of inserting date times into casssandra - code is taken from there
# http://stackoverflow.com/questions/16532566/how-to-insert-a-datetime-into-a-cassandra-1-2-timestamp-column
def unix_time(dt):
    epoch = datetime.datetime.utcfromtimestamp(0)
    delta = dt - epoch
    return delta.total_seconds()

def unix_time_millis(dt):
    return long(unix_time(dt) * 1000.0)


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


class AggregationAPI:
    def __init__(self,project_id,environment,end_date=None,user_id=None,password=None):
        # the panoptes project id - and the environment are the two main things to set
        self.project_id = int(project_id)
        self.environment = environment

        # a dictionary of clustering algorithms - one per shape
        # TODO - currently all possible algorithms are created for every shape, regardless of whether they are
        # TODO actually used
        self.cluster_algs = None
        # the one classification algorithm
        self.classification_alg = None
        self.survey_alg = None
        # a dictionary of workflows - each workflow id number will map to a tuple - marking tasks and
        # classification tasks
        self.workflows = None
        # a list of the current workflow versions - so we can filter out any classifications made via a previous
        # version (which can really mess things up)
        self.versions = None
        self.classifications = None

        # which version of panoptes - staging or production to call
        self.host_api = None

        self.postgres_session = None
        self.postgres_writeable_session = None
        self.cassandra_session = None

        # user id and password used to connect to the panoptes api
        self.user_id = user_id
        self.password = password

        self.end_date = end_date

        self.marking_params_per_shape = dict()

        # default filters for which subjects we look at
        self.only_retired_subjects = False

        self.previous_runtime = datetime.datetime(2000,1,1)

        # so ps will show us which projects are actually aggregating and for now long
        # setproctitle.setproctitle("aggregation project " + str(project_id))

        # some survey projects have incorrectly labelled task ids (the id given is task type)
        # so for these projects we will have individually correct the ids
        # for now such projects have only one task - so for each annotation we will just need to relabel
        # the task id
        self.survey_projects = [593]

        self.oldest_new_classification = None

    def __setup_clustering_algs__(self):
        # functions for converting json instances into values we can actually cluster on

        self.marking_params_per_shape["line"] = helper_functions.relevant_line_params
        self.marking_params_per_shape["point"] = helper_functions.relevant_point_params
        self.marking_params_per_shape["ellipse"] = helper_functions.relevant_ellipse_params
        self.marking_params_per_shape["rectangle"] = helper_functions.relevant_rectangle_params
        self.marking_params_per_shape["circle"] = helper_functions.relevant_circle_params
        self.marking_params_per_shape["polygon"] = helper_functions.relevant_polygon_params
        self.marking_params_per_shape["bezier"] = helper_functions.relevant_bezier_params
        self.marking_params_per_shape["image"] = helper_functions.relevant_rectangle_params

        # load the default clustering algorithms
        self.default_clustering_algs = dict()
        # the following shapes using the basic agglomerative clustering
        self.default_clustering_algs["point"] = agglomerative.Agglomerative
        self.default_clustering_algs["circle"] = agglomerative.Agglomerative
        self.default_clustering_algs["ellipse"] = agglomerative.Agglomerative
        self.default_clustering_algs["line"] = agglomerative.Agglomerative
        # these shapes use the blob clustering approach
        self.default_clustering_algs["rectangle"] = rectangle_clustering.RectangleClustering
        # self.default_clustering_algs["rectangle"] = agglomerative.Agglomerative
        self.default_clustering_algs["polygon"] = blob_clustering.BlobClustering
        self.default_clustering_algs["bezier"] = blob_clustering.BlobClustering
        self.default_clustering_algs["image"] = rectangle_clustering.RectangleClustering
        # and set any reduction algorithms - to reduce the dimensionality of markings
        self.additional_clustering_args = {"line": {"reduction":helper_functions.hesse_line_reduction},"rectangle":{"reduction":helper_functions.rectangle_reduction}}
        # self.__set_clustering_algs__(default_clustering_algs,reduction_algs)

        self.cluster_algs = {}

    def __setup__(self):
        """
        set up all the connections to panoptes and different databases
        :return:
        """
        print("setting up")
        # just for when we are treating an ouroboros project like a panoptes
        # one in which the subject ids will be zooniverse_ids, which are
        # strings
        self.subject_id_type = "int"

        # TODO - some time in the far future - complete support for expert
        # annotations
        self.experts = []

        # load in the project id (a number)
        # if one isn't provided, tried reading it from the yaml config file

        # TODO: If we are not using a secure connection, this forces the
        #       project_id to be provided as a param (since we don't read in
        #       the yaml file) probably want to change that at some point as
        #       there is value in non logged in users having a yaml file (where
        #       they can give csv classification files etc.)

        #########
        # everything that follows assumes you have a secure connection to
        # Panoptes plus the DBs (either production or staging)

        param_file = open("/app/config/aggregation.yml","rb")
        param_details = yaml.load(param_file)

        environment_details = param_details[self.environment]
        # do we have a specific date as the minimum date for this project?
        if (
            (self.project_id in param_details) and
            ("default_date" in param_details[self.project_id])
        ):
            self.previous_runtime = parser.parse(
                param_details[self.project_id]["default_date"]
            )
        # connect to the Cassandra DB
        # only if we have given the necessary param
        # and register this run
        if "cassandra" in environment_details:
            self.cassandra_session = self.__cassandra_connect__(
                environment_details["cassandra"]
            )
            self.__register_run__()

        # connect to whatever postgres db we want to
        print("connecting to postgres")
        self.__postgres_connect__(environment_details)

        # use for Cassandra connection - can override for Ourboros projects
        self.classification_table = "classifications"

        # if we are using a public panoptes connection
        if (
            ("public_connection" in environment_details) and
            (environment_details["public_connection"] == True)
        ):
            # go with the very basic connection
            print("trying public Panoptes connection - no login")
            self.host = "https://panoptes.zooniverse.org/"
            self.host_api = self.host+"api/"
            self.token = None
        else:
            # make the actual connection to Panoptes
            print("trying secure Panoptes connection")
            self.__panoptes_connect__(environment_details)

        self.__get_project_details__()

        # TODO - refactor all this?
        # there may be more than one workflow associated with a project - read
        # them all in and set up the associated tasks
        (
            self.workflows,
            self.versions,
            self.instructions,
            self.updated_at_timestamps
        ) = self.__get_workflow_details__()

        self.retirement_thresholds = self.__get_retirement_threshold__()
        self.workflow_names = self.__get_workflow_names__()

        # is there an entry for the project in the yaml file?
        # if so, has a specific workflow id has been provided?
        # TODO - this can be removed or rewritten
        if "workflow_id" in environment_details:
            workflow_id = int(environment_details["workflow_id"])
            try:
                print("aggregating only for workflow id : " + str(workflow_id))
                self.workflows = {workflow_id: self.workflows[workflow_id]}
            except KeyError:
                warning(
                    "did not have given desired workflow: " + str(workflow_id)
                )
                warning("here's the workflows we do have")
                warning(self.workflows)
                raise

        # set up the clustering algorithms
        self.__setup_clustering_algs__()
        # load the default classification algorithm
        self.__set_classification_alg__(classification.VoteCount)

        # a bit of a sanity check in case I forget to change back up before
        # uploading production and staging should ALWAYS pay attention to the
        # version and only
        # aggregate retired subjects
        if self.environment in ["production","staging"]:
            self.only_retired_subjects = True

        # bit of a stop gap measure - stores how many people have classified a
        # given subject
        self.classifications_per_subject = {}

        # do we want to aggregate over only retired subjects?

        # do we want to aggregate over only subjects that have been
        # retired/classified since the last time we ran the code?
        self.only_recent_subjects = False

        self.oldest_new_classification = datetime.datetime.now()

    def __aggregate__(self, given_workflow_id=None, given_subject_ids=None):
        """
        the main function to call when running aggregation
        """
        # start by migrating any new classifications (since previous run) from
        # postgres into cassandra this will also give us a list of the
        # migrated subjects, which is the list of subjects we want to run
        # aggregation on (if a subject has no new classifications, why bother
        # rerunning aggregation) this is actually just for projects like
        # annotate and folger where we run aggregation on subjects that have
        # not be retired. If we want subjects that have been specifically
        # retired, we'll make a separate call for that
        for workflow_id, version in self.versions.items():
            if (
                given_workflow_id is not None and
                workflow_id != given_workflow_id
            ):
                continue

            if given_subject_ids is None:
                migrated_subjects = self.__migrate__(workflow_id,version)
                previously_aggregated = self.__get_previously_aggregated__(
                    workflow_id
                )

                # the migrated_subject can contain classifications for subjects
                # which are not yet retired so if we want only retired
                # subjects, make a special call otherwise, use the migrated
                # list of subjects
                if self.only_retired_subjects:
                    subject_set = self.__get_newly_retired_subjects__(
                        workflow_id
                    )
                else:
                    subject_set = migrated_subjects
            else:
                # self.__migrate__(workflow_id,version)
                subject_set = given_subject_ids
                previously_aggregated = subject_set

            if subject_set == []:
                print(
                    "skipping workflow {} due to an empty subject set".format(
                        workflow_id
                    )
                )
                continue
            print(self.only_retired_subjects)
            print("workflow id : " + str(workflow_id))
            print("aggregating " + str(len(subject_set)) + " subjects")

            tasks = self.workflows[workflow_id]

            # set up the clustering algorithms for the shapes we actually use
            used_shapes = set()
            for shapes in tasks['marking'].values():
                used_shapes = used_shapes.union(shapes)

            aggregations = {}

            # iterate subject by subject
            for ii, (
                raw_classifications,
                raw_markings,
                raw_surveys,
                image_dimensions
            ) in enumerate(
                self.__sort_annotations__(workflow_id, subject_set)
            ):
                if not tasks.get('survey'):
                    if tasks.get('marking'):
                        aggregations = self.__cluster__(
                            used_shapes,
                            raw_markings,
                            image_dimensions,
                            aggregations
                        )

                    # we ALWAYS have to do classifications - even if we only
                    # have marking tasks, we need to do tool classification
                    # and existence classifications
                    aggregations = self.classification_alg.__aggregate__(
                        raw_classifications,
                        self.workflows[workflow_id],
                        aggregations,
                        workflow_id
                    )
                else:
                    if self.project_id == 593:
                        survey_alg = gorongosa_aggregation.GorongosaSurvey()
                    else:
                        survey_alg = survey_aggregation.Survey()

                    print("aggregating survey results")
                    aggregations = survey_alg.__aggregate__(
                        raw_surveys,
                        aggregations
                    )

                # upsert at every 250th subject - not sure if that's actually
                # ideal but might be a good trade off
                if (ii > 0) and (ii % 250 == 0):
                    print("upserting results")
                    self.__upsert_results__(
                        workflow_id,
                        aggregations,
                        previously_aggregated
                    )
                    aggregations = {}

            print(aggregations)
            if aggregations != {}:
                print("upserting results")
                self.__upsert_results__(
                    workflow_id,
                    aggregations,
                    previously_aggregated
                )

    def __extract_width_height__(self,metadata):
        """
        given the metadata results for an annotation (probably returned from cassandra
        see if we can extrac the image height/width - useful for some aggregation
        if we can't get that data - just return None,None - not the end of the world
        :param metadata:
        :return:
        """
        height = None
        width = None

        if isinstance(metadata,str) or isinstance(metadata,unicode):
            metadata = json.loads(metadata)

        # TODO - not sure why this second conversion is needed, but seems to be
        if isinstance(metadata,str) or isinstance(metadata,unicode):
            metadata = json.loads(metadata)

        if "subject_dimensions" in metadata:
            try:
                for dimensions in metadata["subject_dimensions"]:
                    if dimensions is not None:
                        assert isinstance(dimensions,dict)
                        height = dimensions["naturalHeight"]
                        width = dimensions["naturalWidth"]
            except TypeError:
                warning(metadata)
                raise

        return height,width

    def __yield_annotations__(self,workflow_id,subject_set):
        """
        Yields
        ------
        annotations
        """
        assert subject_set != []
        # def annotation_generator(workflow_id,subject_set):
        assert isinstance(subject_set,list) or isinstance(subject_set,set)
        # filter on only the major version (the whole number part)
        version = int(math.floor(float(self.versions[workflow_id])))

        if subject_set is None:
            subject_set = self.__load_subjects__(workflow_id)

        # do this in bite sized pieces to avoid overwhelming DB
        for s in self.__chunks__(subject_set,50):
            statements_and_params = []

            select_statement = self.cassandra_session.prepare("select user_id,annotations,workflow_version,created_at,metadata from "+self.classification_table+" where subject_id = ? and workflow_id = ? and workflow_version = ?")

            for subject_id in s:
                params = (subject_id,int(workflow_id),version)
                statements_and_params.append((select_statement, params))

            results = execute_concurrent(self.cassandra_session, statements_and_params, raise_on_first_error=False)
            # go through each subject independently
            for subject_id,(success,record_list) in zip(s,results):
                # these are the values that we will return for this subject
                annotations_per_subjects = []
                users_per_subjects = []
                height = None
                width = None

                # if the query was not successful - print out the error message and raise an error
                if not success:
                    warning(record_list)
                assert success

                # seem to have the occasional "retired" subject with no classifications, not sure
                # why this is possible but if it can happen, just make a note of the subject id and skip
                if record_list == []:
                    continue

                # go through every annotation for this particular subject
                for ii,record in enumerate(record_list):
                    # check to see if the metadata contains image size
                    if ii == 0:
                        metadata = record.metadata
                        height,width = self.__extract_width_height__(metadata)

                    # the main stuff we want to return user id and their annotations
                    users_per_subjects.append(int(record.user_id))
                    annotations_per_subjects.append(record.annotations)

                yield int(subject_id),users_per_subjects,annotations_per_subjects,(height,width)

        raise StopIteration()

    @staticmethod
    def __cassandra_connect__(cassandra_instance):
        """
        Connect to the Cassandra DB - either a local one or the Zooniverse aws one. If unable to connect, re-try up to 10 times and then raise an error.

        Raises
        ------
        cassandra.cluster.NoHostAvailable
            If we are not able to connect to the Cassandra DB after 10 tries.
        """
        for i in range(10):
            try:
                if cassandra_instance == "local":
                    print("connecting to local Cassandra instance")
                    cluster = Cluster()
                else:
                    print("connecting to Cassandra: " + cassandra_instance)
                    cluster = Cluster([cassandra_instance])

                try:
                    cassandra_session = cluster.connect("zooniverse")
                except cassandra.InvalidRequest:
                    cassandra_session = cluster.connect()
                    cassandra_session.execute("CREATE KEYSPACE zooniverse WITH REPLICATION = { 'class' : 'SimpleStrategy', 'replication_factor' : 2 }")
                    cassandra_session = cluster.connect('zooniverse')

                return cassandra_session
            except cassandra.cluster.NoHostAvailable as err:
                if i == 9:
                    raise err
                warning(err)

        raise Exception('Could not connect to cassandra due to unknown error')

    def __register_run__(self):
        """
        write to the cassandra db to note that this project is running in case it gets interrupted
        :param project_id:
        :return:
        """
        # have both the pid and project id in the primary key in case multiple people from the same project run
        # aggregation at once
        try:
            self.cassandra_session.execute("CREATE TABLE running_processes(pid int, project_id int, PRIMARY KEY(pid,project_id))")
        except cassandra.AlreadyExists:
            pass

        self.cassandra_session.execute("insert into running_processes (pid,project_id) values ("+str(os.getpid())+","+str(self.project_id)+")")

    def __deregister_run__(self):
        """
        at the very end, remove this project from the list of running projects
        :return:
        """
        self.cassandra_session.execute("delete from running_processes where pid = " + str(os.getpid()) + " and project_id = " + str(self.project_id))

    def __chunks__(self,l, n):
        """Yield successive n-sized chunks from l."""
        for i in xrange(0, len(l), n):
            yield l[i:i+n]

    def __get_login_name__(self,id):
        cur = self.postgres_session.cursor()

        cur.execute("select login from users where id = " + str(id))

        login_name = cur.fetchone()

        # since login_name is a tuple
        if login_name is not None:
            return login_name[0]
        else:
            return None

    def __cluster__(self,used_shapes,raw_markings,image_dimensions,aggregations_so_far):
        """
        Run the clustering algorithm(s).
        Since we are dividing up the aggregation into smaller bits - so that we don't overwhelm the DB
        we may have aggregations from previous iterations - "fold" them in

        Parameters
        ----------

        :param workflow_id:
        :return:
        """

        if raw_markings == {}:
            warning("warning - empty set of images")
            return aggregations_so_far

        # will store the aggregations for all clustering
        # go through the shapes actually used by this project - one at a time
        # cluster_aggregation = {}
        for shape in used_shapes:
            # were any additional params provided?
            if shape in self.additional_clustering_args:
                algorithm = self.default_clustering_algs[shape](shape,self,self.additional_clustering_args[shape])
            else:
                algorithm = self.default_clustering_algs[shape](shape,self,{})

            shape_aggregation = algorithm.__aggregate__(raw_markings,image_dimensions)

            # if this is not the first shape we've aggregated - merge in with previous results
            if aggregations_so_far == {}:
                aggregations_so_far = shape_aggregation
            else:
                assert isinstance(aggregations_so_far,dict)
                aggregations_so_far = self.__merge_aggregations__(aggregations_so_far,shape_aggregation)

        return aggregations_so_far

    # def __count_check__(self,workflow_id,subject_id):
    #     """
    #     for when we want to double check the number of classifications a subject has received
    #     """
    #     # TODO - implement correct version - subject_ids no longer exists in the postgres db
    #     # TODO - not sure if this function is ever called - so only fixed if it is actually called somewhere
    #     # print subject_id
    #     # # check to see if we have previously stored values, hopefully will task on calls to the DB
    #     # if workflow_id in self.classifications_per_subject:
    #     #     if subject_id in self.classifications_per_subject[workflow_id]:
    #     #         return self.classifications_per_subject[workflow_id][subject_id]
    #     # else:
    #     #     self.classifications_per_subject[workflow_id] = {}
    #     #
    #     # cursor = self.postgres_session.cursor()
    #     # cursor.execute("SELECT count(*) from classifications where workflow_id="+str(workflow_id) +" AND subject_ids=ARRAY["+ str(subject_id) + "]")
    #     # count = int(cursor.fetchone()[0])
    #     #
    #     # self.classifications_per_subject[workflow_id][subject_id] = count
    #     #
    #     # return count
    #     assert False

    def __count_subjects__(self,workflow_id):
        stmt = """ SELECT count(*) FROM "subjects"
                    INNER JOIN "subject_workflow_counts" ON "subject_workflow_counts"."subject_id" = "subjects"."id"
                    WHERE "subject_workflow_counts"."workflow_id" = """ + str(workflow_id)

        cursor = self.postgres_session.cursor()
        cursor.execute(stmt)
        print(cursor.fetchall())

    def __count_subjects_classified__(self,workflow_id):
        """
        there are sometimes workflows which haven't received any classifications (for any subjects)
        this may be either due to just needing or wait, or more likely, the scientists created a workflow and
        then changed to another - in these cases we don't want to confuse people and return empty csv files
        so check first to see if any subjects have been classified (for the given workflow)
        """

        stmt = "select count(*) from aggregations where workflow_id = " + str(workflow_id)
        cursor = self.postgres_session.cursor()

        cursor.execute(stmt)
        subjects_classified = cursor.fetchone()[0]

        return subjects_classified

    def __enter__(self):
        # check if another instance of the aggregation engine is already running
        # if so, raise an error
        # if not, create the lock file to prevent another instance from starting
        # TODO - maybe write something to the lock file in case another instance checks at the
        # TODO - exact same time. What about instances for different projects?

        # if os.path.isfile(expanduser("~")+"/aggregation.lock"):
        #     raise InstanceAlreadyRunning()
        # open(expanduser("~")+"/aggregation.lock","w").close()

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # remove the temporary table
        # if we got that far in the code
        if self.postgres_writeable_session is not None:
            postgres_cursor = self.postgres_writeable_session.cursor()
            # truncate the temporary table for this project so we're just re-uploading aggregations
            postgres_cursor.execute("drop table newvals" + str(self.project_id))

        # shutdown the connection to Cassandra and remove the lock so other aggregation instances
        # can run, regardless of whether an error occurred
        if self.cassandra_session is not None:
            self.__deregister_run__()
            self.cassandra_session.shutdown()

    def __get_classifications__(self,subject_id,task_id,cluster_index=None,question_id=None):
        # either both of these variables are None or neither of them are
        assert (cluster_index is None) == (question_id is None)

        if cluster_index is None:
            return self.classifications[subject_id][task_id]
        else:
            return self.classifications[subject_id][task_id][cluster_index][question_id]

    def __is_project_live__(self):
        request = "projects/"+str(self.project_id)
        data = self.__panoptes_call__(request)

        return data["projects"][0]["live"]

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

    def __get_user_name__(self,user_id):
        cursor = self.postgres_session.cursor()
        cursor.execute("select display_name from users where id = " + str(user_id))

        return cursor.fetchone()[0]

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

    def __get_project_details__(self):
        """
        prints out the project name
        :return:
        """
        request = "projects/"+str(self.project_id)+"?"
        try:
            data = self.__panoptes_call__(request)
            display_name = data["projects"][0]["display_name"]
            ascii_name = display_name.encode('ascii', 'ignore')
        except urllib2.HTTPError:
            ascii_name = "unable to connect"
            pass

        print("project is " + ascii_name)

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
            warning(self.host_api+"projects?owner="+self.owner+"&display_name="+self.project_name)
            warning( 'The server couldn\'t fulfill the request.')
            warning('Error code: ' + e.code)
            warning('Error response body: '+ e.read())
            raise
        except urllib2.URLError as e:
            warning('We failed to reach a server.')
            warning('Reason: ', e.reason)
            raise

        data = json.loads(body)
        try:
            # put it in json structure and extract id
            return data["projects"][0]["id"]
        except IndexError:
            warning(self.host_api+"projects?display_name="+urllib2.quote(self.project_name))
            warning(data)
            raise
        # return None

    def __get_subjects_in_workflow__(self,workflow_id):
        stmt = """ SELECT * FROM "subjects"
                    INNER JOIN "subject_workflow_counts" ON "subject_workflow_counts"."subject_id" = "subjects"."id"
                    WHERE "subject_workflow_counts"."workflow_id" = """ + str(workflow_id)

        cursor = self.postgres_session.cursor()
        cursor.execute(stmt)


        return [r[0] for r in cursor.fetchall()]

    def __get_newly_retired_subjects__(self, workflow_id):
        """
        gets the subjects to aggregate
        if we need retired subjects, query against the production postgresDB
        if we need only recent subjects, query against the cassandra DB
        :param workflow_id:
        :param only_retired_subjects: return only subjects which have been
            retired
        :param only_recent_subjects: return subjects which have been
            classified/marked/transcribed/retired since the last running of the
            algorithm
        :return:
        """

        subjects = []
        print('finding subjects classified for workflow ' + str(workflow_id))
        print("selecting only subjects retired since last run")
        stmt = (
            'SELECT * FROM "subjects" '
            'INNER JOIN "subject_workflow_counts" '
            'ON "subject_workflow_counts"."subject_id" = "subjects"."id" '
            'WHERE "subject_workflow_counts"."workflow_id" = {} AND '
            '"subject_workflow_counts"."retired_at" >= \'{}\''
        ).format(workflow_id, self.oldest_new_classification)

        cursor = self.postgres_session.cursor()
        cursor.execute(stmt)
        self.postgres_session.commit()

        for subject in cursor.fetchall():
            subjects.append(subject[0])

        return subjects

    def __get_subject_metadata__(self,workflow_id):
        """
        return the set of all subjects and their associated metadata for a given workflow
        :param workflow_id:
        :return:
        """
        metadata = dict()

        stmt = """ SELECT subject_id,metadata FROM "subjects"
            INNER JOIN "subject_workflow_counts" ON "subject_workflow_counts"."subject_id" = "subjects"."id"
            WHERE "subject_workflow_counts"."workflow_id" = """ + str(workflow_id) + """ AND "subject_workflow_counts"."retired_at" >= '""" + str(datetime.datetime(2000,1,1)) + """'"""

        cursor = self.postgres_session.cursor()
        cursor.execute(stmt)
        self.postgres_session.commit()

        for id_,met in cursor.fetchall():
            metadata[int(id_)] = met

        return metadata





    def __get_workflow_instructions__(self,task_dict):
        # read in the instructions associated with the workflow
        # not used for the actual aggregation but for printing out results to the user
        instructions = {}

        for task_id,task in task_dict.items():
            instructions[task_id] = {}
            # classification task
            if task["type"] in ["single","multiple"]:
                question = task["question"]
                instructions[task_id]["instruction"] = re.sub("'","",question)
                instructions[task_id]["answers"] = {}
                for answer_id,answer in enumerate(task["answers"]):
                    label = answer["label"]
                    label = re.sub("'","",label)
                    instructions[task_id]["answers"][answer_id] = label

            elif task["type"] == "drawing":
                instruct_string = task["instruction"]
                instructions[task_id]["instruction"] = re.sub("'","",instruct_string)

                instructions[task_id]["tools"] = {}

                # assert False
                for tool_index,tool in enumerate(task["tools"]):
                    instructions[task_id]["tools"][tool_index] = {}
                    label = tool["label"]
                    instructions[task_id]["tools"][tool_index]["marking tool"] = re.sub("'","",label)

                    if ("details" in tool) and (tool["details"] != []):
                        instructions[task_id]["tools"][tool_index]["followup_questions"] = {}

                        try:
                            for subtask_index,subtask in enumerate(tool["details"]):
                                instructions[task_id]["tools"][tool_index]["followup_questions"][subtask_index] = {}

                                # what kind of follow up question is this?
                                # could be a multiple choice or could be a text field
                                if "question" in subtask:
                                    instructions[task_id]["tools"][tool_index]["followup_questions"][subtask_index]["type"] = "question"
                                    instructions[task_id]["tools"][tool_index]["followup_questions"][subtask_index]["question"] = subtask["question"]
                                    instructions[task_id]["tools"][tool_index]["followup_questions"][subtask_index]["answers"] = {}
                                    for answer_index,answers in enumerate(subtask["answers"]):
                                        instructions[task_id]["tools"][tool_index]["followup_questions"][subtask_index]["answers"][answer_index] = answers
                                else:
                                    # for now the only other type of follow up question is a text field
                                    assert "type" in subtask
                                    assert subtask["type"] == "text"
                                    instructions[task_id]["tools"][tool_index]["followup_questions"][subtask_index]["type"] = "text"
                        except KeyError:
                            warning(subtask)
                            raise
            elif task["type"] in ["survey","flexibleSurvey"]:
                instructions[task_id]["species"] = {}

                for species in task["choices"]:
                    label = task["choices"][species]["label"]
                    instructions[task_id]["species"][species] = label

                instructions[task_id]["questions"] = task["questions"]
                instructions[task_id]["questionsOrder"] = task["questionsOrder"]

            else:
                warning(task["type"])
                raise Exception('Unknown task type: %s' % task["type"])

        return instructions

    def __get_workflow_details__(self, given_workflow_id=None):
        """
        get everything about the workflows - if no id is provided, go with
        everything
        :param workflow_id:
        :return:
        """
        request = "workflows?project_id="+str(self.project_id)
        data = self.__panoptes_call__(request)

        instructions = {}
        workflows = {}
        updated_at_timestamps = {}
        versions = {}

        for workflow in data["workflows"]:
            workflow_id = int(workflow["id"])
            tasks = workflow["tasks"]

            if (
                (given_workflow_id is None) or
                (workflow_id == given_workflow_id)
            ):
                # read in the basic structure of the workflow
                workflows[workflow_id] = self.__readin_tasks__(tasks)

                # and then the instructions - used for printing out csv files
                instructions[workflow_id] = self.__get_workflow_instructions__(
                    tasks
                )

                # read in when the workflow last went through a major change
                # real problems with subjects that were retired before that
                # date or classifications given for a subject before that
                # date (since the workflow may have changed completely)
                updated_at_timestamps[workflow_id] = workflow["updated_at"]

                # get the MAJOR version number
                versions[workflow_id] = int(
                    math.floor(float(workflow["version"]))
                )

        return (workflows, versions, instructions, updated_at_timestamps)

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
        # TODO - generalize for panoptes
        stmt = "select aggregation from aggregations where workflow_id = " + str(workflow_id) + " and subject_id = '" + str(subject_id) + "'"
        # stmt = "select aggregation from aggregations where subject_id = '" + str(subject_id) + "'"
        postgres_cursor.execute(stmt)

        # TODO - this should be a dict but doesn't seem to be - hmmmm :/
        agg = postgres_cursor.fetchone()

        if agg is None:
            print("returning none")
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
            print(cluster)
            users[center] = cluster["users"]
            # # TODO - should be only one way - check why both are necessary
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

        # url = str(data["subjects"][0]["locations"][0]["image/jpeg"])

        image_paths = []
        for image in data["subjects"][0]["locations"]:
            if "image/jpeg" in image:
                url = image["image/jpeg"]
            elif "image/png" in image:
                url = image["image/png"]
            else:
                raise Exception('Unknown image type: %s' % image)

            slash_index = url.rfind("/")
            fname = url[slash_index+1:]
            url = "http://zooniverse-static.s3.amazonaws.com/panoptes-uploads.zooniverse.org/production/subject_location/"+url[slash_index+1:]

            path = base_directory+"/Databases/images/"+fname
            image_paths.append(path)

            if not(os.path.isfile(path)):
                if download:
                    print("downloading",url,path)
                    urllib.urlretrieve(url, path)
                # raise ImageNotDownloaded()

        return image_paths

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
                    warning("====-----")
                    warning(type(agg1))
                    warning(type(agg2))
                    warning(agg1)
                    warning(agg2)
                    warning(kw)
                    raise

        assert isinstance(agg1,dict)
        return agg1

    def __get_most_recent__(self):
        """
        get the id of the most recent classification that was processed
        :return:
        """
        results = self.cassandra_session.execute("SELECT classification_id from most_recent where project_id = " + str(self.project_id))

        if results == []:
            return 0
        else:
            return results[0]

    def __reset_cassandra_dbs__(self):
        # start by specifying the needed columns for cassandra
        # metadata is needed to possibly get image dimensions which are used to make sure that a marking is valid
        # and not off the screen (problem sometimes with smart phones etc.)
        columns = "id int, user_id int, workflow_id int, created_at timestamp,annotations text, user_ip inet, gold_standard boolean, subject_id int, workflow_version int,metadata text"
        # user_id and user_ip are used so that each user's classifications are stored for a given
        # workflow/subject. Otherwise we can only store at most one classification per workflow/subject
        # realized this the part way (sigh). User_ip ensures that non logged in users will be stored correctly
        # so although we will never (for now) search based on user_id or user_ip, still REALLY important
        primary_key = "workflow_id,subject_id,workflow_version,user_id,user_ip"
        ordering = "subject_id ASC,workflow_version ASC"

        try:
            self.cassandra_session.execute("drop table classifications")
            print("classification table dropped")
        except cassandra.InvalidRequest:
            print("classification table did not already exist")

        self.cassandra_session.execute("CREATE TABLE classifications(" + columns + ", PRIMARY KEY( " + primary_key + ")) WITH CLUSTERING ORDER BY ( " + ordering + ");")

        try:
            self.cassandra_session.execute("drop table most_recent")
            print("most_recent table dropped")
        except cassandra.InvalidRequest:
            print("most_recent table did not already exist")

        recent_table = "CREATE TABLE most_recent (project_id int, classification_id int, PRIMARY KEY(project_id))"
        self.cassandra_session.execute(recent_table)

    def __migrate_with_id_limits__(self,select_stmt,lb_id=None):
        """
        migrate from postgres to cassandra with the additional requirement that classification ids must be
        at least a given value - trying to avoid overwhelming the postgres db by getting too many classifications
        at once
        :param select_stmt:
        :param lb_id:
        :return:
        """
        step = "10000"
        if lb_id is not None:
            select_stmt += " and id > " + str(lb_id)

        # only process a small number of classifications
        print("step size is " + str(step))
        select_stmt += " order by id limit " + str(step)

        # setup the postgres connection and make the select query
        cur = self.postgres_session.cursor()
        cur.execute(select_stmt)

        # setup the insert statement for cassandra
        insert_statement = self.cassandra_session.prepare("""
                insert into classifications (id, user_id, workflow_id, created_at,annotations, user_ip, gold_standard, subject_id, workflow_version,metadata)
                values (?,?,?,?,?,?,?,?,?,?)""")

        statements_and_params = []

        subjects_migrated = set()

        max_classification_id = -1

        # finally go through the annotations
        for ii,t in enumerate(cur.fetchall()):
            if (ii % 10000 == 0) and (ii > 0):
                print(ii)

            id_,user_id,workflow_id,annotations,created_at,user_ip,gold_standard,workflow_version,subject_id,metadata = t
            max_classification_id = max(max_classification_id,id_)

            # store migrated subjects by workflow_id
            subjects_migrated.add(subject_id)

            self.oldest_new_classification = min(self.oldest_new_classification,created_at)

            # TODO - not why exactly, but I guess gold_standard could be something other than boolean
            if gold_standard != True:
                gold_standard = False

            # TODO - again, not sure why exactly, but we might have something like user_id = None
            if not isinstance(user_id,int):
                user_id = -1
            # get only the major version of the workflow
            workflow_version = int(math.floor(float(workflow_version)))

            # for some reason on both of Greg's computers, this extra step is needed
            if os.path.exists("/home/ggdhines"):
                annotations = json.dumps(annotations)
                metadata = json.dumps(metadata)

            params = (id_, user_id, workflow_id,created_at, annotations, user_ip, gold_standard,  subject_id, workflow_version,metadata)
            statements_and_params.append((insert_statement, params))

            # to get a good read/write balance, insert at every 1000 classifications
            if len(statements_and_params) == 1000:
                self.__cassandra_insertion__(statements_and_params)
                statements_and_params = []

        # insert any "left over" classifications
        if statements_and_params != []:
            # Cassandra might have time out issues, if so, try again up to 10 times after which, raise an error
            self.__cassandra_insertion__(statements_and_params)

        return max_classification_id,subjects_migrated

    def __cassandra_insertion__(self,statements_and_params):
        """
        for inserting classifications into the cassandra db - will try a few times in case of time outs
        :param statements_and_params:
        :return:
        """
        for i in range(10):
            try:
                results = execute_concurrent(self.cassandra_session, statements_and_params, raise_on_first_error=True)
                results_boolean,_ = zip(*results)
                assert (False not in results_boolean)
                break
            except (cassandra.WriteTimeout,cassandra.InvalidRequest) as e:
                if i == 9:
                    raise

    def __migrate__(self,workflow_id,version,subject_set=None):
        """
        move data from postgres to cassandra
        set up the postgres queries and then break up the actual migrations into steps - trying to not
        overwhelm the postgres db
        :return:
        """

        # what is the most recent classification we read in
        most_recent = self.__get_most_recent__()

        # some useful postgres bits of code
        postgres_constraint = "where workflow_id="+str(workflow_id) + " and workflow_version like '" + str(version) + "%'"
        # if subject_set != None:
        #     assert isinstance(subject_set,list) and len(subject_set) == 1
        #     postgres_constraint += " and classification_subjects.subject_id = " + str(subject_set[0])

        # postgres_constraint += " and id > 3373491"
        postgres_table = "classifications INNER JOIN classification_subjects on classification_subjects.classification_id = classifications.id"

        # what do we want from the classifications table?
        postgres_columns = "id,user_id,workflow_id,annotations,created_at,user_ip,gold_standard,workflow_version, classification_subjects.subject_id,metadata"
        select = "SELECT " + postgres_columns + " from " + postgres_table + " " + postgres_constraint

        # if we are in development - we don't need all the classifications, so make life simple and just get some
        # if self.environment == "development":
        #     select += " order by id limit 12000"

        # actually get the classifications
        print("about to get all the relevant classifications")

        # all the subjects migrated over every step
        all_subjects_migrated = set()
        # the subjects migrated per step
        subjects_migrated = None
        lower_bound_id = None

        while subjects_migrated != set():
            lower_bound_id,subjects_migrated = self.__migrate_with_id_limits__(select,lower_bound_id)
            all_subjects_migrated.update(subjects_migrated)
            if self.environment in ["development",["quasi"]]:
                break
            print(lower_bound_id)

        return list(all_subjects_migrated)

    def __panoptes_call__(self,query):
        """
        for all the times we want to call the panoptes api
        :param url:
        :return:
        """
        request = urllib2.Request(self.host_api+query)
        request.add_header("Accept","application/vnd.api+json; version=1")
        # only add the token if we have a secure connection
        if self.token is not None:
            request.add_header("Authorization","Bearer "+self.token)

        data = None

        for i in range(10):
            try:
                response = urllib2.urlopen(request)
                body = response.read()
                data = json.loads(body)
                break
            except urllib2.HTTPError as e:
                warning('The server couldn\'t fulfill the request.')
                warning('Error code: ' + str(e.code))
                warning('Error response body: ' + str(e.read()))

                if i == 9:
                    raise

            except urllib2.URLError as e:
                warning('We failed to reach a server.')
                warning('Reason: ' + str(e.reason))

                if i == 9:
                    raise

            time.sleep(10)

        assert data is not None
        return data

    def __panoptes_connect__(self,api_details=None):
        """
        make the main connection to Panoptes - through http
        the below code is based heavily on code originally by Margaret Kosmala
        https://github.com/mkosmala/PanoptesScripts
        :return:
        """
        # details for connecting to Panoptes
        if api_details is not None:
            self.host = api_details["panoptes"]
            self.host_api = self.host+"api/"
            self.app_client_id = api_details["app_client_id"]

            self.user_name = api_details["panoptes_username"]
            self.password = api_details["panoptes_password"]
            Panoptes.connect(
                endpoint=self.host,
                username=self.user_name,
                password=self.password
            )

        self.token = None

        for i in range(20):
            try:
                print("attempt: " + str(i))
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
                    warning(body)
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
                    warning('In get_bearer_token, stage 2:')
                    warning('The server couldn\'t fulfill the request.')
                    warning('Error code: ', e.code)
                    warning('Error response body: ', e.read())
                    raise
                except urllib2.URLError as e:
                    warning('We failed to reach a server.')
                    warning('Reason: ', e.reason)
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
                    warning('In get_bearer_token, stage 3:')
                    warning('The server couldn\'t fulfill the request.')
                    warning('Error code: ', e.code)
                    warning('Error response body: ', e.read())
                    raise
                except urllib2.URLError as e:
                    warning('We failed to reach a server.')
                    warning('Reason: ', e.reason)
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
                print("trying to connect/init again again")
                pass


    def __plot_image__(self,subject_id,axes):
        # TODO - still learning about Matplotlib and axes
        # see http://matplotlib.org/users/artists.html
        fname = self.__image_setup__(subject_id)

        exception = None
        for i in range(10):
            try:
                # fig = plt.figure()
                # ax = fig.add_subplot(1, 1, 1)
                image_file = cbook.get_sample_data(fname)
                image = plt.imread(image_file)
                # fig, ax = plt.subplots()
                im = axes.imshow(image)

                return self.__get_subject_dimension__(subject_id)
            except IOError as e:
                # try downloading that image again
                os.remove(fname)
                self.__image_setup__(subject_id)
                exception = e

        raise exception or Exception('Failed to plot image')

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
        # TODO - generalize for panoptes
        stmt = "select aggregation from aggregations where workflow_id = " + str(workflow_id) + " and subject_id = '" + str(subject_id) + "'"
        # stmt = "select aggregation from aggregations where subject_id = '" + str(subject_id) + "'"
        postgres_cursor.execute(stmt)
        self.postgres_session.commit()

        # TODO - this should be a dict but doesn't seem to be - hmmmm :/
        agg = postgres_cursor.fetchone()

        if agg is None:
            print("returning none")
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

            # TODO - should be only one way - check why both are necessary
            if isinstance(cluster['existence'][0],dict):
                probabilities[center] = cluster['existence'][0]['1']
            else:
                probabilities[center] = cluster['existence'][0][1]

        return probabilities

    def __postgres_connect__(self,database_details):
        print("connecting to postgres db: " + database_details["postgres_host"])

        # build up the connection details
        db = database_details["postgres_db"]
        user = database_details["postgres_username"]
        password = database_details["postgres_password"]
        host = database_details["postgres_host"]

        for i in range(20):
            try:
                self.postgres_session = psycopg2.connect(database=db, user=user, password= password, host= host, port='5432',sslmode='require')
                self.postgres_session.autocommit = True
                break
            except psycopg2.OperationalError as e:
                warning(e)
                pass

        if self.postgres_session is None:
            raise psycopg2.OperationalError()

        # in the past there have been times where we are using different postgres dbs to read and write from
        # if this is the case, here is where we make a new connection to the db that we will be writing to
        if "writeable_postgres_host" in database_details:
            details = ""
            details += "host ='" + database_details["writeable_postgres_host"] + "' "

            # sometimes I'll want to write to my personal computer but read from somewhere else
            # mainly just for SGL stuff
            if "writeable_postgres_username" in database_details:
                details += " dbname = '" +database_details["writeable_postgres_db"] +"' "
                details += " user = '" + database_details["writeable_postgres_username"] + "' "
                details += " password = '"+database_details["writeable_postgres_password"]+"' "
            else:
                details += " dbname = '" +database_details["postgres_db"] +"' "
                details += " user = '" + database_details["postgres_username"] + "' "
                details += " password = '"+database_details["postgres_password"]+"' "

            print("the writeable postgres db is: " + database_details["writeable_postgres_host"])

            # print details

            for i in range(20):
                try:
                    self.postgres_writeable_session = psycopg2.connect(details)
                    self.postgres_writeable_session.autocommit = True
                    break
                except psycopg2.OperationalError as e:
                    warning(e)
                    pass

            if self.postgres_writeable_session is None:
                raise psycopg2.OperationalError()
        else:
            self.postgres_writeable_session = self.postgres_session

        assert self.postgres_writeable_session is not None
        assert self.postgres_session is not None


        # create a new temporary table just for this project (in case multiple people are running aggregation at once)
        # will use this table later for doing upserts
        try:
            postgres_cursor = self.postgres_writeable_session.cursor()
            postgres_cursor.execute(
                "CREATE TEMPORARY TABLE newvals"+str(self.project_id)+"(workflow_id int, subject_id " + self.subject_id_type + ", aggregation jsonb)")
        except psycopg2.ProgrammingError as e:
            # not sure why the temp table should already exist but it might
            # in which case just truncate it and start again
            self.postgres_session.rollback()
            postgres_cursor = self.postgres_writeable_session.cursor()
            postgres_cursor.execute("truncate table newvals"+str(self.project_id))
            self.postgres_session.commit()

    def __get_previously_aggregated__(self,workflow_id):
        """
        get the list of all previously aggregated subjects - so we when upserting new results
        we know which subjects we are updating and which we are inserting (i.e. no previously existing results)
        :param workflow_id:
        :return:
        """

        try:
            postgres_cursor = self.postgres_writeable_session.cursor()
            postgres_cursor.execute("select subject_id from aggregations where workflow_id = " + str(workflow_id))
            previously_aggregated = [i[0] for i in postgres_cursor.fetchall()]
        except psycopg2.ProgrammingError as e:
            # again, not sure why there would be an error - but in this case just to be certain
            # assume that there are no pre-existing aggregation results
            print(e)
            self.postgres_session.rollback()
            previously_aggregated = []

        return previously_aggregated

    def __readin_tasks__(self, task_dict):
        """
        get the details for each task - for example, what tasks might we want
        to run clustering algorithms on and if so, what params related to that
        task are relevant
        :return:
        """
        tasks = {
            'classification': {},
            'marking': {},
            'survey': {},
            'unknown': {},
        }

        # convert to json if necessary - not sure why this is necessary but it
        # does happen
        # see https://github.com/zooniverse/aggregation/issues/7
        if isinstance(task_dict, str) or isinstance(task_dict, unicode):
            task_dict = json.loads(task_dict)

        for task_id, task in task_dict.items():
            # self.task_type[task_id] = tasks[task_id]["type"]
            # if the task is a drawing one, get the necessary details for
            # clustering

            task_type = task["type"]

            if task_type == "drawing":
                tasks['marking'][task_id] = []
                # manage marking tools by the marking type and not the index
                # so all ellipses will be clustered together

                for tool_id, tool in enumerate(task["tools"]):
                    # are there any classification questions associated with
                    # this marking?
                    if (
                        ("details" in tool) and
                        (tool["details"] is not None) and
                        (tool["details"] != [])
                    ):
                        # extract the label of the tool - this means that
                        # things don't have to ordered

                        # is this the first follow up question associated with
                        # this task?
                        tasks['classification'].setdefault(task_id, {})
                        tasks['classification'][task_id].setdefault(
                            tool_id,
                            []
                        )

                        # note whether each of these questions are single or
                        # multiple response
                        for followup_question in tool["details"]:
                            tasks['classification'][task_id][tool_id].append(
                                followup_question["type"]
                            )

                    # if the tool is the one of the recognized ones, add it.
                    # Otherwise report an error
                    if tool["type"] in (
                        "line",
                        "ellipse",
                        "point",
                        "circle",
                        "rectangle",
                        "polygon",
                        "bezier"
                    ):
                        tasks['marking'][task_id].append(tool["type"])
                    else:
                        raise Exception('Unknown tool type: %s' % tool['type'])

            elif task_type in ("single", "multiple"):
                # multiple means that more than one response is allowed
                tasks['classification'][task_id] = task["type"]
            elif task_type in ("survey", "flexibleSurvey"):
                tasks['survey'][task_id] = []
            else:
                warning(task)
                warning(task["type"])
                # unknown task type
                tasks['unknown'][task_id] = task['type']

        # note that for follow up questions to marking tasks - the key used is
        # the marking tool label NOT the follow up question label

        return tasks

    def __set_classification_alg__(self,alg,params={}):
        self.classification_alg = alg(self.environment,params)
        assert isinstance(self.classification_alg,classification.Classification)

    def __set_survey_alg__(self,alg,params={}):
        self.survey_alg = alg(self.environment,params)
        assert isinstance(self.survey_alg,classification.Classification)

    def __add_markings_annotations__(self,subject_id,workflow_id,task_id,user_id,task_value,raw_markings,raw_classifications,marking_tasks,classification_tasks,dimensions):
        """
        given a certain marking for a given subject_id,workflow_id and task_id add the marking to our overall list of marking annotations
        also add in any follow up classification ids
        :param subject_id:
        :param workflow_id:
        :param task_id:
        :param user_id:
        :param task_value:
        :param raw_markings:
        :param raw_classifications:
        :param marking_tasks:
        :param classification_tasks:
        :param dimensions:
        :return:
        """
        # if this is the first we have encountered this task
        if task_id not in raw_markings:
            raw_markings[task_id] = {}

        # for each shape associated with this task - is this the first time we've encountered this shape?
        # remember that there can be multiple marking tools associated with each task and multiple marking
        # tools can be made with the same shape
        for shape in set(marking_tasks[task_id]):
            if shape not in raw_markings[task_id]:
                raw_markings[task_id][shape] = {}

            # is this the first time we've seen this subject_id?
            if subject_id not in raw_markings[task_id][shape]:
                raw_markings[task_id][shape][subject_id] = []

        # kind track of which shapes the user did mark - we need to keep track of any shapes
        # for which the user did not make any marks at all of
        # because a user not seeing something is important
        spotted_shapes = set()

        for marking in task_value:
            # what kind of tool made this marking and what was the shape of that tool?
            if "tool" in marking:
                tool = marking["tool"]
                shape = marking_tasks[task_id][tool]
            elif "type" in marking:
                tool = None
                shape = marking["type"]
            else:
                print("skipping unknown type of marking")
                print(marking)
                continue

            # for development only really - if we are not interested in a certain type of marking
            # right now - just skip it
            if shape not in self.workflows[workflow_id]['marking'][task_id]:
                continue

            if shape not in self.marking_params_per_shape:
                print("unrecognized shape: (skipping) " + shape)
                continue

            try:
                # extract the params specifically relevant to the given shape
                relevant_params = self.marking_params_per_shape[shape](marking,dimensions)
            except (helper_functions.InvalidMarking,helper_functions.EmptyPolygon,KeyError,TypeError) as e:
                # badly formed marking - or the marking is slightly off the image
                # either way - just skip it
                continue

            spotted_shapes.add(shape)
            raw_markings[task_id][shape][subject_id].append((user_id,relevant_params,tool))

            # is this a confusing shape?
            # i.e. multiple tools can be make this shape - if so, we can a classification task of deciding which
            # tool should actually be associated with each aggregate marking
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

        return raw_markings,raw_classifications

    def __add_survey_annotation__(self,subject_id,user_id,task_id,task,raw_survey_annotations):
        """
        add a user's survey annotations for a specific task to the overall survey annotations
        :param subject_id:
        :param user_id:
        :param task:
        :param raw_survey_annotations:
        :return:
        """

        if task_id not in raw_survey_annotations:
            raw_survey_annotations[task_id] = {}
        if subject_id not in raw_survey_annotations[task_id]:
            raw_survey_annotations[task_id][subject_id] = {}
        # TODO - think the below can happen when a task is skipped, double check
        # note that if a user sees more than one species - they will be recorded more than once
        # i..e their user id will show up more than once
        if task["value"] != [[]]:
            # this setup is best for dealing with when users record more than one species in an image
            if user_id not in raw_survey_annotations[task_id][subject_id]:
                raw_survey_annotations[task_id][subject_id][user_id] = [task["value"]]
            else:
                raw_survey_annotations[task_id][subject_id][user_id].append(task["value"])

        return raw_survey_annotations

    def __add_classification_annotation__(self,subject_id,user_id,task_id,task,raw_classification_annotations):
        if task_id not in raw_classification_annotations:
            raw_classification_annotations[task_id] = {}
        if subject_id not in raw_classification_annotations[task_id]:
            raw_classification_annotations[task_id][subject_id] = []

        if task["value"] != [[]]:
            raw_classification_annotations[task_id][subject_id].append((user_id,task["value"]))

        return raw_classification_annotations

    def __sort_annotations__(self,workflow_id,subject_set):
        """
        return the annotations for a given subject set
        each iteration yields a set for a SINGLE different annotation
        :param workflow_id:
        :param subject_set:
        :return:
        """

        # load the classification, marking and survey json dicts - helps parse annotations
        tasks = self.workflows[workflow_id]

        for subject_id,user_list,annotation_list,dimensions in self.__yield_annotations__(workflow_id,subject_set):
            print(subject_id)
            # print(subject_id == 572437)
            # this is what we return
            raw_classifications = {}
            raw_markings = {}
            raw_surveys = {}
            image_dimensions = {}

            non_logged_in_users = 0


            if dimensions is not (None,None):
                image_dimensions[subject_id] = dimensions

            for user_id,annotation in zip(user_list,annotation_list):
                # if user_id == -1, that user was not logged in. We need to be able to differentiate between
                # multiple non logged in users - so if we have a list of user ids [-1,-1,-1] we need to map
                # each of those -1's to a different number (a lot of algorithms depend on knowing that different
                # annotations were made by different people
                if user_id == -1:
                    non_logged_in_users += -1
                    user_id = non_logged_in_users

                # convert to json format - from string
                annotation = json.loads(annotation)

                # go through each annotation and get the associated task
                for task in annotation:
                    # extract the task id
                    task_id = task["task"]

                    # see https://github.com/zooniverse/Panoptes-Front-End/issues/2155 for why this is needed
                    if self.project_id in self.survey_projects:
                        task_id = tasks.get('survey', {}).keys()[0]

                    # is this a marking task?
                    if task_id in tasks.get('marking', {}):
                        # skip over any improperly formed annotations - due to browser problems etc.
                        if not isinstance(task["value"],list):
                            print("not properly formed marking - skipping")
                            continue

                        # a marking task will have follow up classification tasks - even if none are explicitly asked
                        # i.e. existence, or how many users clicked on a given "area"
                        raw_markings, raw_classifications = (
                            self.__add_markings_annotations__(
                                subject_id,
                                workflow_id,
                                task_id,
                                user_id,
                                task["value"],
                                raw_markings,
                                raw_classifications,
                                tasks.get('marking', {}),
                                tasks.get('classification', {}),
                                dimensions
                            )
                        )

                    # we a have a pure classification task
                    elif task_id in tasks.get('classification', {}):
                        raw_classifications = self.__add_classification_annotation__(subject_id,user_id,task_id,task,raw_classifications)
                    elif task_id in tasks.get('survey', {}):
                        raw_surveys = self.__add_survey_annotation__(subject_id,user_id,task_id,task,raw_surveys)
                    else:
                        warning(
                            tasks.get('marking'),
                            tasks.get('classification'),
                            tasks.get('survey')
                        )
                        warning(task_id)
                        warning(task)
                        raise Exception('Unknown task ID: %s' % task_id)

            yield raw_classifications,raw_markings,raw_surveys,image_dimensions

        raise StopIteration()

    def __subject_ids_in_set__(self,set_id):
        """
        return the subjects in a given subject set
        :param set_id:
        :return:
        """
        request = urllib2.Request(self.host_api+"set_member_subjects?subject_set_id="+str(set_id))
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

    def __upsert_results__(self,workflow_id,aggregations,previously_aggregated):
        """
        see
        # http://stackoverflow.com/questions/8134602/psycopg2-insert-multiple-rows-with-one-query
        :param workflow_id:
        :param aggregations:
        :return:
        """
        postgres_cursor = self.postgres_writeable_session.cursor()

        # truncate the temporary table for this project so we're just re-uploading aggregations
        postgres_cursor.execute("truncate table newvals" + str(self.project_id))

        update_str = ""
        insert_str = ""

        update_counter = 0
        insert_counter = 0

        # TODO - sort the subject ids so that searching is faster

        for subject_id in aggregations:
            # TODO - maybe get rid of param in subject_ids - end users won't see it anyways
            if subject_id == "param":
                continue

            if subject_id in previously_aggregated:
                # we are updating
                try:
                    update_str += ","+postgres_cursor.mogrify("(%s,%s,%s)", (workflow_id,subject_id,json.dumps(aggregations[subject_id])))
                    update_counter += 1
                except UnicodeDecodeError:
                    warning(workflow_id)
                    warning(subject_id)
                    warning(aggregations[subject_id])
                    raise
            else:
                # we are inserting a brand new aggregation
                try:
                    insert_str += ","+postgres_cursor.mogrify("(%s,%s,%s,%s,%s)", (workflow_id,subject_id,json.dumps(aggregations[subject_id]),str(datetime.datetime.now()),str(datetime.datetime.now())))
                    insert_counter += 1
                except UnicodeDecodeError:
                    warning(json.dumps(aggregations[subject_id],indent=4, separators=(',', ': ')))
                    raise

        if update_str != "":
            # are there any updates to actually be done?
            # TODO - the updated and created at dates are not being maintained - I'm happy with that
            print("updating " + str(update_counter) + " subjects")
            postgres_cursor.execute("INSERT INTO newvals"+str(self.project_id)+" (workflow_id, subject_id, aggregation) VALUES " + update_str[1:])
            postgres_cursor.execute("UPDATE aggregations SET aggregation = newvals"+str(self.project_id)+".aggregation FROM newvals"+str(self.project_id)+" WHERE newvals"+str(self.project_id)+".subject_id = aggregations.subject_id and newvals"+str(self.project_id)+".workflow_id = aggregations.workflow_id")
        if insert_str != "":
            print("inserting " + str(insert_counter) + " subjects")
            try:
                postgres_cursor.execute("INSERT INTO aggregations (workflow_id, subject_id, aggregation, created_at, updated_at) VALUES " + insert_str[1:])
            except psycopg2.IntegrityError:
                print("duplicate error!!!!")
        self.postgres_writeable_session.commit()

    def __yield_aggregations__(self,workflow_id,subject_set=None):
        """
        generator for giving aggregation results per subject id/task
        """
        # connect to the postgres db
        cursor = self.postgres_session.cursor()

        stmt = "select count(*) from aggregations where workflow_id = " + str(workflow_id)
        cursor.execute(stmt)
        print("aggregations to date: " + str(cursor.fetchone()))

        stmt = "select subject_id,aggregation,updated_at from aggregations where workflow_id = " + str(workflow_id)
        cursor.execute(stmt)

        # go through each of the results
        for r in cursor.fetchall():
            aggregation = r[1]
            subject_id = r[0]

            # not efficient but will only really matter in development environment
            # TODO but could probably be made more efficient
            if (subject_set is not None) and (subject_id not in subject_set):
                continue

            if isinstance(aggregation,str):
                aggregation = json.loads(aggregation)
            elif not isinstance(aggregation,dict):
                warning(type(aggregation))
            assert isinstance(aggregation,dict)

            yield r[0],aggregation
        print("done")
        raise StopIteration()

if __name__ == "__main__":
    # TODO - use getopt
    project_identifier = sys.argv[1]

    if len(sys.argv) > 2:
        environment = sys.argv[2]
    else:
        environment = "development"

    if len(sys.argv) > 3:
        workflow_id = int(sys.argv[3])
    else:
        workflow_id = None

    if len(sys.argv) > 4:
        subject_set = [int(sys.argv[4])]
    else:
        subject_set = None

    with AggregationAPI(project_identifier,environment) as project:

        project.__setup__()
        # project.__reset_cassandra_dbs__()
        project.__aggregate__(workflow_id,subject_set)

        with csv_output.CsvOut(project) as c:
            # c.__write_out__(subject_set=aggregated_subjects)
            c.__write_out__(subject_set)
