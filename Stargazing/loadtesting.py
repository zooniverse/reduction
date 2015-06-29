__author__ = 'greg'
import random
import math
import sys
import gc
steps = ["centered_in_crosshairs", "subtracted", "circular", "centered_in_host"]
gc.set_debug(gc.DEBUG_LEAK)

def create_annotations():
    annotations = []
    end_point = random.randint(0,4)

    for i in range(end_point):
        annotations.append({"task":steps[i],"value":1})

    try:
        annotations.append({"task":steps[end_point],"value":0})
    except IndexError:
        pass


    return annotations


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

l = []

#@profile
def create_list():
    for classification_count in range(1000000):
        subject_id = random.randint(0,50000)
        annotations = create_annotations()

        l.append((subject_id,annotations[:]))
create_list()
print sys.getsizeof(l)

scores = {}

#@profile
def test():
    for subject_id,annotations in l:
        #print classification
        # if this is the first time we have encountered this subject, add it to the dictionary
        if not(subject_id in scores):
            scores[subject_id] = [0,0,0]

        # get the score index and increment that "box"
        scores[subject_id][score_index(annotations)] += 1


    for subject_id,values in scores.items():
        avg_score = (values[0]*-1+ + values[1]*1 + values[2]*3)/float(sum(values))
        std = math.sqrt((-1-avg_score)**2*(values[0]/float(sum(values))) + (1-avg_score)**2*(values[1]/float(sum(values))) + (3-avg_score)**2*(values[1]/float(sum(values))))
        aggregation = {"mean":avg_score,"std":std,"count":values}


test()
