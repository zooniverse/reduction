#!/usr/bin/env python
__author__ = 'greg'
import math
import panoptesPythonAPI
import time
import yaml

# calculate the score associated with a given classification according to the algorithm
# in the paper Galaxy Zoo Supernovae
# an example of the json format used is
# [{u'task': u'centered_in_crosshairs', u'value': 1}, {u'task': u'subtracted', u'value': 1}, {u'task': u'circular', u'value': 1}, {u'task': u'centered_in_host', u'value': 0}]

def score_index(annotations):
    assert annotations[0]["task"] == "centered_in_crosshairs"
    if annotations[0]["value"] == 0:
        return 0  #-1

    # they should have answered yes
    assert annotations[1]["task"] == "subtracted"
    if annotations[1]["value"] == 0:
        return 0  #-1

    assert annotations[2]["task"] == "circular"
    if annotations[2]["value"] == 0:
        return 0  #-1

    assert annotations[3]["task"] == "centered_in_host"
    if annotations[3]["value"] == 0:
        return 2  #3
    else:
        return 1  #1

# get my userID and password
# purely for testing, if this file does not exist, try opening on Greg's computer
try:
    panoptes_file = open("config/panoptes_login","rb")
except IOError:
    panoptes_file = open("/home/greg/Databases/panoptes_login","rb")
login_details = yaml.load(panoptes_file)
userid = login_details["name"]
password = login_details["password"]

# get the token necessary to connect with panoptes
token = panoptesPythonAPI.get_bearer_token(userid,password)

# get the project id for Supernovae and the workflow version
project_id = panoptesPythonAPI.get_project_id("Supernovae",token)
workflow_version = panoptesPythonAPI.get_workflow_id(project_id,token)

def calc_scores(scores = {}):
    """
    :param scores: default scores - only override for testing (specifically load testing)
    :return:
    """

    # go through all of the classifications/annotations (terminology isn't completely consistent but not sure of what
    # would be better)
    for index,classification in enumerate(panoptesPythonAPI.classifications_iterator(project_id,token)):
        # we need the workflow, subject ids
        workflow_id = classification["links"]["workflow"]
        subject_id = classification["links"]["subjects"][0]

        # if this is the first time we have encountered this subject, add it to the dictionary
        if not((workflow_id,subject_id) in scores):
            scores[(workflow_id,subject_id)] = [0,0,0]

        # get the score index and increment that "box"
        annotations = classification["annotations"]
        scores[(workflow_id,subject_id)][score_index(annotations)] += 1

    return scores

def aggregate(scores):
    # now do the aggregation
    for (workflow_id,subject_id),values in scores.items():
        # calculate the average score, std and set up the JSON results
        avg_score = (values[0]*-1+ + values[1]*1 + values[2]*3)/float(sum(values))
        std = math.sqrt((-1-avg_score)**2*(values[0]/float(sum(values))) + (1-avg_score)**2*(values[1]/float(sum(values))) + (3-avg_score)**2*(values[1]/float(sum(values))))
        aggregation = {"mean":avg_score,"std":std,"count":values}

        # try creating the aggregation
        status,explanation = panoptesPythonAPI.create_aggregation(workflow_id,subject_id,token,aggregation)

        # if we had a problem, try updating the aggregation
        if status == 400:
            aggregation_id,etag = panoptesPythonAPI.find_aggregation_etag(workflow_id,subject_id,token)
            panoptesPythonAPI.update_aggregation(workflow_id,workflow_version,subject_id,aggregation_id,token,aggregation,etag)

if __name__ == "__main__":
    scores = {}
    for i in range(10000):
        print i
        start = time.time()
        scores = calc_scores(scores)
        end = time.time()

        print end - start
    aggregate(scores)

