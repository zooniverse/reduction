__author__ = 'greg'
from classification import Classification
import copy


class ExpertClassification(Classification):
    def __init__(self,project,clustering_alg=None):
        Classification.__init__(self,project,clustering_alg)

    def __classify__(self,subject_ids,gold_standard=False):
        assert gold_standard

        ridings_dict = {}

        # print cluster_centers
        for subject_id in subject_ids:
            cluster_centers,polls = self.project.__get_classifications__(subject_ids,cluster_alg=self.cluster_alg,gold_standard=gold_standard)

            for poll_index,(center,poll) in enumerate(zip(cluster_centers,polls)):
                # users,classifications,pts = zip(*p)
                count = {s:0 for s in self.species}

                if not(subject_id in ridings_dict):
                    ridings_dict[subject_id] = [center]
                else:
                    ridings_dict[subject_id].append(center)

                # for user,vote,pt in poll:
                    

                for c in classifications:
                    assert isinstance(c,unicode)
                    count[c.lower()] +=1

                print {s:count[s] for s in self.species if count[s]>0}


        return self.candidates,ridings_dict,results