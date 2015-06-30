#!/usr/bin/env python
from postgres_aggregation import Aggregation,PanoptesAPI
import cPickle as pickle
import datetime
import os
import getopt
import sys

class IterativeAggregation(Aggregation):
    def __init__(self):
        Aggregation.__init__(self)

        # only try loading previous stuff if we don't have a failed run

        try:
                self.aggregations = pickle.load(open("/tmp/aggregations.pickle","rb"))
                self.current_timestamp = pickle.load(open("/tmp/timestamp.pickle","rb"))
                print "time is " + str(self.current_timestamp)
        except (IOError,EOFError) as e:
            # just in case we got part way through loading the files
            self.aggregations = []
            # makes it slightly easier to have an actual date in this variable
            # the value doesn't matter as long as it is before any classifications
            self.current_timestamp = self.threshold_date

    def __init__accumulator__(self,subject_id=None):
        if (subject_id is None) or (len(self.aggregations) <= subject_id) or (self.aggregations[subject_id] is None):
            return [0,0,0]
        else:
            return self.aggregations[subject_id]["count"]




class IterativePantopesAPI(PanoptesAPI):
    def __init__(self,http_update=False):
        PanoptesAPI.__init__(self,http_update,aggregator=IterativeAggregation)

        # overwrite the base aggregator
        # self.aggregator = IterativeAggregation()

    def __update_aggregations__(self,additional_constraints=""):
        # get the current time stamp from the aggregator
        current_timestamp = self.aggregator.__get_timestamp__()
        print current_timestamp
        count, new_time = PanoptesAPI.__update_aggregations__(self," and created_at>\'" + str(current_timestamp) + "\'")
        self.aggregator.__set_timestamp__(new_time)

        return count,new_time
        # select = "SELECT subject_ids,annotations,created_at from classifications where project_id="+str(self.project_id)+" and workflow_id=" + str(self.workflow_id) + " and created_at>\'" + str(current_timestamp) + "\' ORDER BY subject_ids"
        # cur = self.conn.cursor()
        # cur.execute(select)
        #
        # current_subject_id = None
        # annotation_accumulator = self.aggregator.__init__accumulator__()
        #
        # for count,(subject_ids,annotations,timestamp) in enumerate(cur.fetchall()):
        #     current_timestamp = max(current_timestamp,timestamp)
        #     #print timestamp
        #     #print count, subject_ids
        #     # have we moved on to a new subject?
        #     if subject_ids[0] != current_subject_id:
        #         # if this is not the first subject, aggregate the previous one
        #         if current_subject_id is not None:
        #             # save the results of old/previous subject
        #
        #             # if by some chance all of the classifications we've read in have been discarded
        #             # just skip it
        #             if annotation_accumulator != [0,0,0]:
        #                 metadata = self.__get_metadata__(current_subject_id)
        #                 self.aggregator.__update_subject__(current_subject_id,annotation_accumulator,metadata)
        #
        #         # reset and move on to the next subject
        #         current_subject_id = subject_ids[0]
        #         annotation_accumulator = self.aggregator.__init__accumulator__(current_subject_id)
        #
        #
        #     annotation_accumulator = self.aggregator.__accumulate__(annotations,annotation_accumulator)
        #
        # self.aggregator.__set_timestamp__(current_timestamp)
        #
        # # make sure we update the aggregation for the final subject we read in
        # # on the very off chance that we haven't read in any classifications, double check
        # if current_subject_id is not None:
        #     if annotation_accumulator != [0,0,0]:
        #         metadata = self.__get_metadata__(current_subject_id)
        #         self.aggregator.__update_subject__(current_subject_id,annotation_accumulator,metadata)
        #
        # return count

if __name__ == "__main__":
    update = "complete"
    http_update = True
    start = datetime.datetime.now()
    try:
        opts, args = getopt.getopt(sys.argv[1:],"u:m:",["update=",])
    except getopt.GetoptError:
        print "postgres_aggregation -u <COMPLETE or PARTIAL update> -m <http update method TRUE or FALSE>"
        sys.exit(2)

    for opt,arg in opts:
        # are we doing a partial or complete update?
        if opt in ["-u", "-update"]:
            update = arg.lower()
            assert update in ["complete", "partial"]
        elif opt in ["-m", "-method"]:
            http_update = arg.lower()
            # convert from string into boolean
            http_update = (http_update[0] == "t")

    # hard code this for now
    http_update = False
    stargazing = IterativePantopesAPI(http_update=http_update)
    num_updated = stargazing.__update__()

    # cleanup makes sure that we are dumping the aggregation results back to disk
    stargazing.__cleanup__()

    end = datetime.datetime.now()
    print "updated " + str(num_updated) + " in " + str(end - start)