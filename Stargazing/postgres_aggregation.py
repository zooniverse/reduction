#!/usr/bin/env python
__author__ = 'greg'
import math
import panoptesPythonAPI
import yaml
import psycopg2
import os
import sys
import cPickle as pickle
import getopt
import boto
from boto.s3.key import Key
import datetime
import json
import urllib2

# for Greg running on either office/home - which computer am I on?
if os.path.exists("/home/ggdhines"):
    base_directory = "/home/ggdhines"
else:
    base_directory = "/home/greg"

class AnnotationException(Exception):
    def __init__(self, value):
        self.annotation, self.index, self.task = value

    def __str__(self):
        return "With annotation: " + str(self.annotation) + " at index " + str(self.index) + " did not find task: " + str(self.task)


class Aggregation:
    #@profile
    def __init__(self, user_threshold, score_threshold):
        # set the aggregations to be nothing
        self.aggregations = []

        # try load previously read in metadata - if we can't we'll just have to download it again
        # not the end of the world
        try:
            self.metadata = pickle.load(open("/tmp/metadata.pickle","rb"))
        except (IOError, EOFError) as e:
            self.metadata = []

        # the current current timestamp - we need something that is guaranteed to be before any of the
        # actual classifications - the specific datetime doesn't matter
        self.threshold_date = datetime.datetime(2015,3,20,12,0,0)
        self.current_timestamp = self.threshold_date

        self.user_threshold = user_threshold
        self.score_threshold = score_threshold

        print self.user_threshold,self.score_threshold

    def __cleanup__(self):
        """
        dumps the results to file so that they can be used for future runs
        :return:
        """
        pickle.dump(self.metadata,open("/tmp/metadata.pickle","wb"))
        pickle.dump((self.aggregations,self.current_timestamp),open("/tmp/aggregations.pickle","wb"))

    def __get_timestamp__(self):
        return self.current_timestamp

    def __set_experts_sets__(self, subject_ids):
        self.expert_sets = subject_ids

    def __get_experts_sets__(self):
        return self.expert_sets

    def __score_index__(self,annotations):
        """calculate the score associated with a given classification according to the algorithm
        in the paper Galaxy Zoo Supernovae
        an example of the json format used is
        [{u'task': u'centered_in_crosshairs', u'value': 1}, {u'task': u'subtracted', u'value': 1}, {u'task': u'circular', u'value': 1}, {u'task': u'centered_in_host', u'value': 0}]
        """

        try:
            if annotations[0]["task"] != "centered_in_crosshairs":
                raise AnnotationException((annotations,0,"centered_in_crosshairs"))
            if annotations[0]["value"] == 1:
                return 0  #-1

            if annotations[1]["task"] != "subtracted":
                raise AnnotationException((annotations,1,"subtracted"))
            if annotations[1]["value"] == 1:
                return 0  #-1

            if annotations[2]["task"] != "circular":
                raise AnnotationException((annotations,2,"circular"))
            if annotations[2]["value"] == 1:
                return 0  #-1

            if annotations[3]["task"] != "centered_in_host":
                raise AnnotationException((annotations,3,"centered_in_host"))
            if annotations[3]["value"] == 1:
                return 2  #3
            else:
                return 1  #1
        except IndexError:
            print >> sys.stderr, "badly formed annotation - should skip"
            raise

    def __expand__(self,subject_id):
        """
        expand the aggregations list and metadata list so that there is room for the given subject_ic
        :param subject_id:
        :return:
        """

        while len(self.aggregations) <= subject_id:
            self.aggregations.append(None)

            # some subjects will not have any meta data associated with them, so there is a difference between
            # metadata = None, and metadata = -1 (None means in the Panoptes DB there is no metadata)
            # this should probably never happen - but just in case
            self.metadata.append(None)

    def __update_subject__(self,subject_id,accumulated_scores):
        """
        set the aggregation result for the given subject_id using the accumulated scores
        for now, assume that the accumulated scores are based on ALL classifications, including ones
        we have read in before hand, so we completely overwrite all pre-existing results. In the future we
        could merge the results - this means we only have to read in new classifications, but at the same time
        we have to sure that we don't read in any old classifications
        :param subject_id:
        :param accumulated_scores:
        :return:
        """
        # the following four lines of code are taken (and slightly adapted from):
        # http://astro-wise.org/awesoft/awehome/AWBASE/common/math/statistics.py
        # calculate the weighted average - same as the average if we hadn't compressed all of the scores into
        # one accumulated value
        # score_sum = reduce(operator.add, accumulated_scores)
        # mean = reduce(operator.add, [weight*x for x, weight in zip([-1,1,3], accumulated_scores)])/score_sum

        #stdv  = reduce(operator.add, [weight*(x-mean)**2 for x, weight in zip([-1,1,3], accumulated_scores)])
        #stdev = math.sqrt(stdv/score_sum)

        values = accumulated_scores
        mean = (values[0]*-1 + values[1]*1 + values[2]*3)/float(sum(values))
        # note this gives a biased estimate
        stdev = math.sqrt(((-1-mean)**2*values[0] + (1-mean)**2*values[1] + (3-mean)**2*values[1])/float(sum(values)))

        # save the resulting aggregation - this is the first and only time these values are actually associated
        # with the particular subject id
        # extend the list if we need to
        self.__expand__(subject_id)

        #assert len(self.aggregations) == len(self.classification_count)
        self.aggregations[subject_id] = {"mean":mean,"std":stdev,"count":accumulated_scores}

    def __update_metadata__(self,subject_id,metadata):
        """
        store the metadata for the given subject - convert from str to dict is necessary
        :param subject_id:
        :param metadata:
        :return:
        """
        self.__expand__(subject_id)
        if metadata is not None:
            if isinstance(metadata,str):
                self.metadata[subject_id] = json.loads(metadata)
            else:
                self.metadata[subject_id] = metadata

    def __have_metadata__(self,subject_id):
        """
        do we have the metadata for this subject?
        :param subject_id:
        :return:
        """
        if len(self.metadata) <= subject_id:
            return False
        elif self.metadata[subject_id] is None:
            return False
        else:
            return True

    def __metadata_equals_none__(self, subject_id):
        assert len(self.metadata) > subject_id
        assert self.metadata[subject_id] is not -1

        return self.metadata[subject_id] is None

    def __list_aggregations__(self,subjects_ids=None):
        """
        generate a list of subject ids and their corresponding aggregations in JSON form
        :param subjects_ids:
        :return:
        """
        # now seems a good a time as any to save the classification_count and scores
        if subjects_ids is None:
            subjects_ids = range(len(self.aggregations))

        print "the number of subjects is " + str(len(subjects_ids))

        for subject_id in subjects_ids:
            if self.aggregations[subject_id] is not None:
                yield subject_id,self.aggregations[subject_id]

    def __init__accumulator__(self,subject_id = None):
        return [0,0,0]

    def __accumulate__(self,annotation,accumulator):
        """
        :param annotation - the next annotation to "merge into" the set of existing annotations
         for future work - the merge into could be just appending to a list but here we should be able to keep
         the memory usage low
        :param accumulator - the merged results from the previous annotations
        :return:
        """
        # if the accumulator was read in directly from the sql file - we will need to convert it into json format
        if isinstance(annotation,str):
            annotation = json.loads(annotation)

        try:
            accumulator[self.__score_index__(annotation)] += 1
        except (IndexError,AnnotationException) as e:
            pass

        return accumulator

    def __aggregations_to_string__(self):
        """
        convert the aggregation into string format - useful for when you want to print the aggregations out to
        a csv file
        """
        # start by getting all aggregations that have at least 5 classifications
        # print self.aggregations[1:10]
        # print self.user_threshold,self.score_threshold
        # print type(self.user_threshold),type(self.score_threshold)
        subjects_to_print = [subject_id for subject_id,agg in enumerate(self.aggregations) if (agg is not None) and (sum(agg["count"]) >= 5) and (agg["mean"] >= 1)]
        # print len(subjects_to_print)
        # now sort these aggregations
        subjects_to_print.sort(key = lambda x: sum(self.aggregations[x]["count"]),reverse = True)
        subjects_to_print.sort(key = lambda x: self.aggregations[x]["mean"],reverse = True)

        results = ""
        for subject_id in subjects_to_print:

            agg = self.aggregations[subject_id]
            # add the metadata first
            metadata = self.metadata[subject_id]
            #print subject_id,agg
            # print subject_id,metadata
            #
            #results += str(subject_id) + ","
            try:
                if "candidateID" in metadata:
                    results += str(subject_id)+","+metadata["candidateID"] + ","
                    results += str(agg["mean"]) + "," + str(sum(agg["count"])) + ",https://stargazing2015.zooniverse.org/#/projects/zooniverse/Snapshot%20Supernova/subjects/"+str(subject_id)+"\n"
                else:
                    pass
                    #results += "NA,"
            except TypeError:
                pass


            # try:
            #
            #     if metadata is None:
            #         # should never happen but just in case
            #         results += str(subject_id) + ",NA,NA,NA,NA"
            #     else:
            #         for property in ["candidateID","RA","DEC","mag","mjd"]:
            #             try:
            #                 results += str(metadata[property]) + "," #+ str(metadata["RA"]) + "," + str(metadata["DEC"]) + "," + str(metadata["mag"]) + "," + str(metadata["mjd"])
            #             except KeyError:
            #                 print >> sys.stderr, "missing property: " + property
            #                 if property == "candidateID":
            #                     results += str(subject_id) + ","
            #                 else:
            #                     results += "NA,"
            # except TypeError:
            #     print metadata
            #     raise
            # #print results
            #
            # results += str(agg["mean"]) + "," + str(agg["std"]) + "," + str(agg["count"][0]) + "," + str(agg["count"][1]) + ","+ str(agg["count"][2]) + "\n"

        return results

    def __set_timestamp__(self,timestamp):
        self.current_timestamp = timestamp

    def __to_prune__(self):
        subjects_to_prune = [subject_id for subject_id,agg in enumerate(self.aggregations) if (agg is not None) and (sum(agg["count"]) >= 5) and (agg["mean"] == -1)]

        return subjects_to_prune


class AccumulativeAggregation(Aggregation):
    def __init__(self):
        Aggregation.__init__(self)

        # only try loading previous stuff if we don't have a failed run

        try:
                self.aggregations, self.current_timestamp = pickle.load(open("/tmp/aggregations.pickle","rb"))
                #self.current_timestamp = pickle.load(open("/tmp/timestamp.pickle","rb"))
                print "time is " + str(self.current_timestamp)
        except (IOError,EOFError,ValueError) as e:
            print "resetting"
            # just in case we got part way through loading the files
            self.aggregations = []
            # makes it slightly easier to have an actual date in this variable
            # the value doesn't matter as long as it is before any classifications
            self.current_timestamp = self.threshold_date
            print "time is " + str(self.current_timestamp)


    def __init__accumulator__(self,subject_id=None):
        """
        use previously calculated values to init the accumulator
        if not possible - just return the default beginning accumulator
        note - the accumulator is the count, nothing else from the aggregations
        :param subject_id:
        :return:
        """
        if (subject_id is None) or (len(self.aggregations) <= subject_id) or (self.aggregations[subject_id] is None):
            return [0,0,0]
        else:
            return self.aggregations[subject_id]["count"]


class PanoptesAPI:
    #@profile
    def __init__(self,user_threshold= None, score_threshold= None): #Supernovae
        self.user_threshold = user_threshold
        # first find out which environment we are working with
        self.environment = os.getenv('ENVIRONMENT', "production")
        print self.environment
        # next connect to the Panoptes http API

        # get my userID and password
        # purely for testing, if this file does not exist, try opening on Greg's computer
        try:
            panoptes_file = open("config/aggregation.yml","rb")
        except IOError:
            panoptes_file = open(base_directory+"/Databases/aggregation.yml","rb")
        api_details = yaml.load(panoptes_file)

        userid = api_details[self.environment]["name"]
        password = api_details[self.environment]["password"]
        host = api_details[self.environment]["host"] #"https://panoptes-staging.zooniverse.org/"
        owner = api_details[self.environment]["owner"] #"brian-testing" or zooniverse
        project_name = api_details[self.environment]["project_name"]
        app_client_id = api_details[self.environment]["app_client_id"]

        # get the token necessary to connect with panoptes
        self.http_api = None
        self.project_id = None
        self.workflow_version = None
        self.workflow_id = None
        print "connecting to Panoptes http api"
        for i in range(20):
            try:
                self.http_api = panoptesPythonAPI.PanoptesAPI(host,userid,password,app_client_id)
                # get the project id for Supernovae and the workflow version
                self.project_id = self.http_api.get_project_id(project_name,owner=owner) #or zooniverse
                self.workflow_version = self.http_api.get_workflow_version(self.project_id)
                self.workflow_id = self.http_api.get_workflow_id(self.project_id)
                break
            except (urllib2.HTTPError,urllib2.URLError) as e:
                print "trying to connect/init again again"
                pass

        if None in [self.http_api,self.project_id,self.workflow_id ,self.workflow_version]:
            raise urllib2.HTTPError()

        #panoptesPythonAPI.get_bearer_token(userid,password)



        # print "project id  is " + str(project_id)
        # print "workflow id is " + str(workflow_id)
        print "connecting to Panoptes database"
        # now load in the details for accessing the database
        try:
            database_file = open("config/database.yml")
        except IOError:
            database_file = open(base_directory+"/Databases/database.yml")
        database_details = yaml.load(database_file)

        #environment = "staging"

        database = database_details[self.environment]["database"]
        username = database_details[self.environment]["username"]
        password = database_details[self.environment]["password"]
        host = database_details[self.environment]["host"]

        # try connecting to the db
        self.conn = None
        details = "dbname='"+database+"' user='"+ username+ "' host='"+ host + "' password='"+password+"'"
        for i in range(20):
            try:
                self.conn = psycopg2.connect(details)
                break
            except psycopg2.OperationalError as e:
                pass

        if self.conn is None:
            raise psycopg2.OperationalError()


        # are we doing an accumulative update where we try to use previous results?
        if True:
            self.aggregator = Aggregation(user_threshold,score_threshold)
            current_timestamp = self.aggregator.__get_timestamp__()
            self.time_constraints = " and created_at>\'" + str(current_timestamp) + "\'"
        else:
            assert False
            print "accumulative"
            self.aggregator = AccumulativeAggregation()


        # self.e = to_stargazing

        # assert update_type in ["partial","complete"]
        # self.update_type = update_type

        #assert http_update in [True,False]
        #self.http_update = http_update

        # set things up
        self.S3_conn = None
        print "connecting to s3 output bucket"
        try:
            # for dumping results to s3
            AWS_ACCESS_KEY_ID  = os.getenv('AWS_ACCESS_KEY_ID', None)
            AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', None)

            # if both are None, we should already be in aws
            self.S3_conn = boto.connect_s3(AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY)
        except boto.exception.NoAuthHandlerFound:
            print >> sys.stderr, "not able to connect to S3 - will try to keep going but this will probably give you errors later"

        print "setting meta data"
        self.__set_metadata__()
        #self.__set_expert_sets__()
        # cur = self.conn.cursor()
        # cur.execute("SELECT * from subject_sets where subject_sets.project_id="+str(self.project_id)+" and subject_sets.workflow_id=" + str(self.workflow_id))
        # rows = cur.fetchall()
        # print cur.description
        # for r in rows:
        #     print r
        #
        # assert False

        print "set up is done"

    def __cleanup__(self):
        self.aggregator.__cleanup__()


    def __to_prune__(self):
        return self.aggregator.__to_prune__()

    #@profile
    def __update__(self):
        print "about to update"
        num_updated = self.__update_aggregations__()
        # ids,counts = self.__find_classification_count__()

        # print ids[:10]
        # for i,c in zip(ids,counts):
        #     print i,c
        #     print self.aggregator.metadata[i]["candidateID"]
        # print
        # for i,agg in enumerate(self.aggregator.aggregations):
        #     if (agg is not None) and (sum(agg["count"]) >= 5):
        #
        #         print i,sum(agg["count"])

        # write out the results to an s3 bucket - file is a csv file labelled with day, hour and minute
        if self.S3_conn is not None:
            #csv_contents = "candidateID,RA,DEC,mag,mjd,mean,stdev,count0,count1,count2\n"
            csv_contents = "subjectID,candidateID,mean,count,url\n"
            csv_contents += self.aggregator.__aggregations_to_string__()
            t = datetime.datetime.now()
            fname = str(t.year) + "-" + str(t.month) + "-" + str(t.day) + "_" + str(t.hour) + "_" + str(t.minute)+"_"+str(self.user_threshold)+"users"
            print self.environment
            self.__write_to_s3__("zooniverse-aggregation","Stargazing/"+self.environment+"/",fname,csv_contents)

            #if self.to_stargazing:
            #    self.__write_gz_to_s3__("stargazing-data-upload","",fname,csv_contents)
            #self.__write_to_s3__("stargazing-data-upload","",csv_contents)
        else:
            print >> sys.stderr, "not able to connect to S3 - did not write any results to S3"

        # if we also want to use the http interface to put the results back onto Panoptes - seems to be running
        # rather slowly right now, so use with caution
        # if self.http_update is True:
        #     self.__http_score__update__(subjects_to_update)
        return num_updated

    def __write_to_s3__(self,bucket,path,fname,csv_contents):
        result_bucket = self.S3_conn.get_bucket(bucket)
        k = Key(result_bucket)
        t = datetime.datetime.now()
        #fname = str(t.year) + "-" + str(t.month) + "-" + str(t.day) + "_" + str(t.hour) + "_" + str(t.minute)
        k.key = path+fname+".csv"

        k.set_contents_from_string(csv_contents)


    def __set_metadata__(self):
        # check to see if the metadata file exists in the first place, if so, don't bother trying to download it
        if not os.path.isfile("/tmp/metadata.pickle"):
            select = "SELECT id,metadata from subjects"
            cur = self.conn.cursor()
            cur.execute(select)

            # rows = cur.fetchmany(200)
            # for subject_id,metadata in rows:
            #     print subject_id
            #     self.aggregator.__update_metadata__(subject_id,metadata)
            #
            # print "got past"

            rows = cur.fetchall()
            for subject_id,metadata in rows:
                # if "1339276" in metadata["candidateID"]:
                #     print metadata["candidateID"]
                #     print subject_id
                # if "FMTJ14303011-1152196" == metadata["candidateID"]:
                #     print 1
                #     print subject_id

                self.aggregator.__update_metadata__(subject_id,metadata)


    # def __update_metadata__(self,subject_id):
    #     if not self.aggregator.__have_metadata__(subject_id):
    #         # do we need to get the metadata for this subject?
    #         if not self.aggregator.__have_metadata__(subject_id):
    #             select = "SELECT metadata from subjects where id = " + str(subject_id)
    #             cur2 = self.conn.cursor()
    #             cur2.execute(select)
    #             metadata = cur2.fetchone()[0]
    #
    #
    #             self.aggregator.__update_metadata__(subject_id,metadata)

    def __is_expert__(self,subject_id):
        select = "SELECT expert from subjects where id = " + str(subject_id)
        cur2 = self.conn.cursor()
        cur2.execute(select)
        expert = cur2.fetchone()[0]

        return expert

    def __get_stats__(self):
        metadata_constraints =  " and metadata->>'workflow_version' = '"+str(self.workflow_version)+"'"
        select = "SELECT user_id,user_ip from classifications where project_id="+str(self.project_id)+" and workflow_id=" + str(self.workflow_id) + metadata_constraints
        #print select
        cur = self.conn.cursor()
        cur.execute(select)

        users_set = set()
        ip_set = set()

        classification_count = 0

        for i,(user_id,user_ip) in enumerate(cur.fetchall()):
            if user_id is not None:
                users_set.add(user_id)
            else:
                ip_set.add(user_ip)

            classification_count += 1

        return  (len(list(users_set))+len(list(ip_set))),classification_count

    def __yield_classifications__(self):
        metadata_constraints =  " and metadata->>'workflow_version' = '"+str(self.workflow_version)+"'"
        #metadata_constraints = ""
        #user_id = t[2], created_at = t[4], user_ip=t[3],annotations=t[1],subject_id=t[0][0]
        select = "SELECT user_id,created_at,user_ip,annotations,subject_ids from classifications where project_id="+str(self.project_id)+" and workflow_id=" + str(self.workflow_id)# +" and created_at > '"+ str(datetime.datetime(2015,3,18,18)) +"'"
        print select

        cur = self.conn.cursor()
        cur.execute(select)

        for ii,t in enumerate(cur.fetchall()):

            # if (t[0] is not None) and (int(t[0]) == 10):
            #     print t
            yield t

        # def __yield_classifications__(self):
        # metadata_constraints =  " and metadata->>'workflow_version' = '"+str(self.workflow_version)+"'"
        # #metadata_constraints = ""
        # #user_id = t[2], created_at = t[4], user_ip=t[3],annotations=t[1],subject_id=t[0][0]
        # select = "SELECT user_id,created_at,user_ip,annotations,subject_ids from classifications where project_id="+str(self.project_id)+" and workflow_id=" + str(self.workflow_id) + metadata_constraints
        # print select
        # return
        # # cur = self.conn.cursor()
        # # cur.execute(select)
        # #
        # # for ii,t in enumerate(cur.fetchall()):
        # #     yield t

    def __find_user__(self,user_name):
        select = "SELECT * FROM users where display_name = '" + user_name +"'"

        cur = self.conn.cursor()
        cur.execute(select)

        user_id = cur.fetchall()[0][0]


        select = "SELECT * from classifications where user_id = "+str(user_id)
        # # print select
        cur = self.conn.cursor()
        cur.execute(select)
        # print len(cur.fetchall())

        #
        for r in cur.fetchall():
            print r

    def __update_aggregations__(self):
        """
        update
        :param additional_conditions: if you want to restrict the updates to certain subjects
        :return:
        """
        # SELECT * FROM json_test WHERE data @> '{"a":1}';
        # select = "SELECT id from users where display_name = \'zookeeper\'"
        # print select
        # cur = self.conn.cursor()
        # cur.execute(select)
        # chris_id = cur.fetchone()[0]
        # print chris_id
        # select = "SELECT subject_ids,annotations,created_at from classifications where user_id = " + str(chris_id)
        # print select
        # cur = self.conn.cursor()
        # cur.execute(select)
        #
        # for subject_ids, annotations,created_at in cur.fetchall():
        #     print created_at, subject_ids, annotations
        # #print classification_list
        #
        # assert False
        #
        #
        start = datetime.datetime.now()


        metadata_constraints =  " and metadata->>'workflow_version' = '"+str(self.workflow_version)+"'"
        #metadata_constraints = ""
        select = "SELECT subject_ids,annotations,user_id from classifications where project_id="+str(self.project_id)+" and workflow_id=" + str(self.workflow_id) + metadata_constraints + self.time_constraints
        print select
        # select = "SELECT subject_ids,annotations,created_at,user_id,metadata,project_id,workflow_id from classifications"
        #print select
        #print select
        #print "going to get cursor"
        cur = self.conn.cursor()
        cur.execute(select)

        classification_list = list(cur.fetchall())
        print "fetched"
        classification_list.sort(key = lambda x:x[0])
        end = datetime.datetime.now()
        print "it took " + str(end-start)

        #print "got cursor and finished sorting"
        current_subject_id = None
        annotation_accumulator = self.aggregator.__init__accumulator__()

        current_time = self.aggregator.__get_timestamp__()
        count = 0

        #expert_sets = self.aggregator.__get_experts_sets__()
        #print expert_sets
        #assert False

        # print self.workflow_version
        for count,(subject_ids,annotations,user_id) in enumerate(classification_list):
            # if subject_ids[0] == 42056:
            #     print user_id
            #     print annotations
            #     print
            # print self.aggregator.metadata[subject_ids[0]]
            #print user_id
            # if user_id is not None:
            #     print type(user_id),type(chris_id)
            #     print user_id,chris_id
            #     assert False
            # if user_id == chris_id:
            #     print time_stamp
            #     print annotations
            #     print metadata
            #     print project_id
            #     print workflow_id
            #     print
            #print count
            # print count
            # print metadata["workflow_version"]
            # if self.workflow_version != metadata["workflow_version"]:
            #     print "old version"
            #     continue
            #if subject_ids[0] in range(11):
            #    continue

            #current_time = max(current_time,time_stamp)
            #print count, subject_ids
            # have we moved on to a new subject?
            if subject_ids[0] != current_subject_id:
                # if this is not the first subject, aggregate the previous one
                if current_subject_id is not None:
                    # save the results of old/previous subject

                    # if by some chance all of the classifications we've read in have been discarded
                    # just skip it
                    if annotation_accumulator != [0,0,0]:
                        # if a new subject has been added, we will need to download the metadata for this subject
                        # I realize that I have already downloaded the metadata field as part of my query so this
                        # is slightly inefficient - the idea being that in the future when I figure out how to
                        # I can add the metadata_constraints which will allow me to not have to get the metadata as
                        # part of my query
                        # self.aggregator.__update_metadata__(current_subject_id,metadata)

                        # we should skip over any subject which does not have metadata

                        # metadata = self.__get_metadata__(current_subject_id)
                        # if metadata is not None:


                        self.aggregator.__update_subject__(current_subject_id,annotation_accumulator)

                # reset and move on to the next subject
                current_subject_id = subject_ids[0]
                annotation_accumulator = self.aggregator.__init__accumulator__()

            annotation_accumulator = self.aggregator.__accumulate__(annotations,annotation_accumulator)

        # make sure we update the aggregation for the final subject we read in
        # on the very off chance that we haven't read in any classifications, double check
        if current_subject_id is not None:
            if annotation_accumulator != [0,0,0]:
                # metadata = self.__get_metadata__(current_subject_id)
                self.aggregator.__update_subject__(current_subject_id,annotation_accumulator)

        self.aggregator.__set_timestamp__(current_time)
        return count

    # def __update_scores__(self,additional_conditions = ""):
    #     select = "SELECT subject_ids,annotations from classifications where project_id="+str(self.project_id)+" and workflow_id=" + str(self.workflow_id) + additional_conditions
    #     cur = self.conn.cursor()
    #     cur.execute(select)
    #     # cur.execute("SELECT annotations from classifications where project_id="+str(self.project_id)+" and workflow_id=" + str(self.workflow_id) + " and subject_ids = ARRAY["+str(subject_id)+"]")
    #     rows = cur.fetchall()
    #
    #     for subject_ids,annotations in rows:
    #         subject_id = subject_ids[0]
    #         self.aggregator.__update_score__(subject_id,annotations)
    #
    #     # makes other functions easier if we just return None
    #     return None

    def __http_score__update__(self,subjects_to_update=None):
        """
        after we have updated the scores, return them to panoptes using the http api
        the alternative might be to upload to s3 or email someone the results
        :param subjects_to_update: if there are a certain select number of subjects you want to update
        so specifically, you used a heuristic to select which subjects to update and only want to send
        those back. Basically if you selected heuristic for update and after sending everything back, that is
        kinda silly - hence the assert
        :return:
        """
        assert (self.update_type == "complete") or (subjects_to_update is not None)

        for subject_id,aggregation in self.aggregator.__list_aggregations__(subjects_to_update):
            # try creating the aggregation
            status,explanation = panoptesPythonAPI.create_aggregation(self.workflow_id,subject_id,self.token,aggregation)

            # if we had a problem, try updating the aggregation
            if status == 400:
                aggregation_id,etag = panoptesPythonAPI.find_aggregation_etag(self.workflow_id,subject_id,self.token)
                panoptesPythonAPI.update_aggregation(self.workflow_id,self.workflow_version,subject_id,aggregation_id,self.token,aggregation,etag)

    def __set_expert_sets__(self):
        # check to see if the metadata file exists in the first place, if so, don't bother trying to download it
        if not os.path.isfile("/tmp/experts.pickle"):
            cur = self.conn.cursor()
            cur.execute("SELECT subject_id from set_member_subjects inner join subject_sets on set_member_subjects.subject_set_id=subject_sets.id where subject_sets.project_id="+str(self.project_id)+" and subject_sets.workflow_id=" + str(self.workflow_id) +" ORDER BY subject_id")
            rows = cur.fetchall()
            all_subjects = [c[0] for c in rows]

            cur.execute("SELECT subject_id from set_member_subjects inner join subject_sets on set_member_subjects.subject_set_id=subject_sets.id where (subject_sets.expert_set = FALSE or subject_sets.expert_set IS NULL) and subject_sets.project_id="+str(self.project_id)+" and subject_sets.workflow_id=" + str(self.workflow_id) +" ORDER BY subject_id")
            rows = cur.fetchall()
            non_expert_subjects = [c[0] for c in rows]

            print all_subjects[:100]
            print non_expert_subjects[:100]
            print [s for s in all_subjects if not(s in non_expert_subjects)]

            print subject_ids
            self.aggregator.__set_experts_sets__(subject_ids)

    def __find_classification_count__(self):
        """
        finds the classification count for every subject in the current project/workflow
        does not actually update the classification_count dict - we can use this function to determine
        which subjects have had enough additional classifications so that we show rerun the aggregation
        those subjects should have their classification count updated - otherwise, don't change the count
        :return:
        """
        new_classification_count = []
        ids = []

        cur = self.conn.cursor()
        #cur.execute("Select * from subject_sets where ")

        # keeping the below commands in as a reminder of how to do the relevant SQL commands
        # cur.execute("SELECT subject_id from set_member_subjects where subject_set_id=4 OR subject_set_id=3")
        cur.execute("SELECT expert_set from subject_sets where subject_sets.project_id="+str(project_id)+" and subject_sets.workflow_id=" + str(workflow_id))
        rows = cur.fetchall()


        cur.execute("SELECT subject_id,classification_count from set_member_subjects inner join subject_sets on set_member_subjects.subject_set_id=subject_sets.id where (subject_sets.expert_set = FALSE or subject_sets.expert_set IS NULL) and subject_sets.project_id="+str(self.project_id)+" and subject_sets.workflow_id=" + str(self.workflow_id) +" ORDER BY subject_id")
        rows = cur.fetchall()
        for subject_id,count in rows:
            if count >= 5:
                new_classification_count.append(count)
                ids.append(subject_id)

        return ids,new_classification_count

    def __heuristic_update(self):
        ids,new_classification_count = self.__find_classification_count__()
        subjects_to_update = self.aggregator.__subjects_to_update__(ids,new_classification_count)

        for subject_id in subjects_to_update:
            self.__update_aggregations(additional_conditions=" and subject_ids = ARRAY["+str(subject_id)+"]")

        return subjects_to_update



if __name__ == "__main__":
    update = "c"
    #to_stargazing = False
    user_threshold = 5
    score_threshold = 1
    start = datetime.datetime.now()
    try:
        opts, args = getopt.getopt(sys.argv[1:],"u:s:")
    except getopt.GetoptError:
        print "postgres_aggregation -u <user threshold for csv output> -s <score threshold for csv output>"
        sys.exit(2)

    for opt,arg in opts:
        # are we doing a partial or complete update?
        if opt == "-u":
            user_threshold = int(arg)
        elif opt == "-s":
            score_threshold = float(arg)


    # hard code this for now
    # http_update = False
    stargazing = PanoptesAPI(user_threshold,score_threshold)
    num_updated = stargazing.__update__()

    # cleanup makes sure that we are dumping the aggregation results back to disk
    stargazing.__cleanup__()

    end = datetime.datetime.now()
    #print "updated " + str(num_updated) + " in " + str(end - start)