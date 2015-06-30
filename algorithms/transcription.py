#!/usr/bin/env python
import panoptes_api

project = panoptes_api.PanoptesAPI("manuscript-adventure")
# project.__migrate__()
# project.__list_workflows__()
# 43,44,45,47
# 47 - circle
# 45 - line
project.__set_workflow__(45)

import agglomerative
project.__set_clustering_alg__(agglomerative.Agglomerative)
project.__plot_individual_points__()
# project.__cluster__()
# project.__plot_cluster_results__()