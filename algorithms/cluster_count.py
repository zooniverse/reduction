__author__ = 'greg'
import clustering
import numpy as np

class Counting(clustering.Cluster):
    def __init__(self,project_api,min_cluster_size=1,mapping =None):
        clustering.Cluster.__init__(self,project_api,min_cluster_size,mapping)
        self.algorithm_name = "counting"

    def __inner_fit__(self,markings,user_ids,tools):
        counts= {}
        for tool_id in set(tools):
            values = []
            for user in set(user_ids):
                # check that both the user id and tool id match
                values.append(sum([1 for t,u in zip(tools,user_ids) if (t == tool_id) and (u == user)]))

            counts[tool_id] = np.mean(values)

        return counts,0