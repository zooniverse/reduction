import clustering
import matplotlib.pyplot as plt
from shapely.geometry import Polygon,MultiPolygon
import itertools
import math
from shapely.validation import explain_validity
import matplotlib
from shapely.ops import cascaded_union
import numpy

def findsubsets(S,m):
    return set(itertools.combinations(S, m))


def nCr(n,r):
    f = math.factorial
    return f(n) / f(r) / f(n-r)


class QuadTree:
    def __init__(self,((lb_x,lb_y),(ub_x,ub_y)),parent=None):
        self.lb_x = lb_x
        self.ub_x = ub_x
        self.lb_y = lb_y
        self.ub_y = ub_y

        self.children = None
        self.parent = parent
        self.polygons = {}

        try:
            self.bounding_box = Polygon([(lb_x,lb_y),(ub_x,lb_y),(ub_x,ub_y),(lb_x,ub_y)])
        except:
            print [(lb_x,lb_y),(ub_x,lb_y),(ub_x,ub_y),(lb_x,ub_y)]
            raise

        self.user_ids = []

    def __get_splits__(self):
        if (self.bounding_box.area < 5000) or (len(self.polygons) < 8):
            return []

        complete_agreement = 0

        # check to see if there are at least three users with polygons completely covering this particular area
        # if so - we consider this area to be not noise
        # todo - check if this is an actual problem (not just a hypothetical one)
        # for one area, we could have three users who have each covered this area with 2 (possibly overlapping)
        # polygons that just happen to line up perfectly so that they completely cover the area.
        # The polygons (or rectangles) of each user probably refer to two different things but since we won't
        # subdivide this box any further, we act as if all of the users are referring to only one thing
        for user in self.polygons:
            # such a user is referring to two or more different things so we should skip them
            if len(zip(*self.polygons[user])[0]) > 1:
                continue

            # extract just the polygons - don't worry about type
            u = cascaded_union(zip(*self.polygons[user])[0])
            # 1 here is a margin of error - the area will be in terms of pixels squared so a pretty large
            # number - 1 is pretty trivial compared to
            if math.fabs(self.bounding_box.intersection(u).area - self.bounding_box.area) < 1:
                # if this is the root node, the bounding box should cover every thing

                if self.parent is None:
                    x,y = self.polygons[user][0][0].exterior.xy
                    assert self.polygons[user][0][0].area <= self.bounding_box.area

                complete_agreement += 1

        if complete_agreement >= 8:
            return []

        # calculate the height and width of the new children nodes
        new_width = (self.lb_x+self.ub_x)/2. - self.lb_x
        new_height = (self.ub_y+self.lb_y)/2. - self.lb_y

        lower_left = (self.lb_x,self.lb_y),(self.lb_x+new_width,self.lb_y+new_height)
        lower_right = (self.lb_x+new_width,self.lb_y),(self.ub_x,self.lb_y+new_height)
        upper_left = (self.lb_x,self.lb_y+new_height),(self.lb_x+new_width,self.ub_y)
        upper_right = (self.lb_x+new_width,self.lb_y+new_height),(self.ub_x,self.ub_y)

        self.children = [QuadTree(lower_left,self) ,QuadTree(lower_right,self),QuadTree(upper_left,self),QuadTree(upper_right,self)]
        for c in self.children:
            assert isinstance(c,QuadTree)
            assert math.fabs((c.bounding_box.area - self.bounding_box.area/4.) < 0.0001)

        return self.children

    def __plot__(self,ax):
        if self.children is None:
            if len(self.polygons) >= 3:
                plt.plot((self.lb_x,self.ub_x,self.ub_x,self.lb_x,self.lb_x),(self.lb_y,self.lb_y,self.ub_y,self.ub_y,self.lb_y),color="red")
                # rect = plt.Rectangle((self.lb_x,self.lb_y),(self.ub_x-self.lb_x),(self.ub_y-self.lb_y),color="red")
                # print (self.lb_x,self.lb_y),(self.ub_x-self.lb_x),(self.ub_y-self.lb_y)
                # ax.add_artist(rect)
        else:
            for c in self.children:
                assert isinstance(c,QuadTree)
                c.__plot__(ax)

    def __aggregate__(self,total_area):
        """
        total_area is needed for calculating the "noise" area
        :param total_area:
        :return:
        """
        if self.children is None:
            if len(self.polygons) >= 8:
                # what is the majority vote for what type of "kind" this box outlines
                # for example, some people might say broad leave tree while others say it is a needle leaf tree
                # technically speaking, people could outline this region with different polygons
                # if so, we'll ignore such users, under the assumption that we don't really know
                vote_counts = {}
                for u in self.polygons:
                    polys, types = zip(*self.polygons[u])
                    if min(types) == max(types):
                        vote = min(types)
                        if vote not in vote_counts:
                            vote_counts[vote] = 1
                        else:
                            vote_counts[vote] += 1

                # in the very rare case where vote_counts == -1 - that means everyone outlined with more than
                # one polygon/rectangle. Use mostlikely = -1 to denote
                if vote_counts == {}:
                    most_likely = -1
                    percentage = -1
                else:
                    # extract the most likely type according to pluraity voting
                    # ties will get resolved in an arbitrary fashion
                    most_likely,num_votes = sorted(vote_counts.items(),key = lambda x:x[1],reverse=True)[0]
                    percentage = num_votes/float(sum(vote_counts.values()))

                # return two sets of values - one with the bounding box
                # the other with the voting results
                # last value is the noise area

                polygons_by_user_density = {i:[self.bounding_box] for i in range(3,len(self.polygons)+1)}
                return {most_likely:self.bounding_box},{most_likely:(percentage,self.bounding_box.area)},0,polygons_by_user_density
            else:
                # no polygons in this box - so no noise either
                if len(self.polygons) == 0:
                    return {},{},0,{}
                else:
                    # we have come polygons inside this box which amount to noise
                    # find out the area of these polygons - with respect to inside this box
                    # for smaller boxes, we could just use the area of the box as an approximation
                    # but for larger boxes, especially if we are the root, we need to do better
                    if (self.bounding_box.area/float(total_area)) > 0.02:
                        noise_polygons = []
                        for poly_list in self.polygons.values():
                            noise_polygons.extend(zip(*poly_list)[0])
                        combined_polygon = cascaded_union(noise_polygons).intersection(self.bounding_box)

                        return {},{},combined_polygon.area,{}
                    else:
                        return {},{},self.bounding_box.area,{}
        else:
            return_polygons = {}
            return_stats = {}
            new_area = {}
            new_percentage = {}

            all_users = set()

            total_incorrect_area = 0

            total_polygons_user_density = {}

            for c in self.children:
                # get all the polygons that are in c's bounding boxes plus stats about which tools made
                # which reasons
                c_polygons,c_stats,incorrect_area,polygons_by_user_density = c.__aggregate__(total_area)

                for u in polygons_by_user_density:
                    if u not in total_polygons_user_density:
                        total_polygons_user_density[u] = polygons_by_user_density[u]
                    else:
                        total_polygons_user_density[u].extend(polygons_by_user_density[u])

                total_incorrect_area += incorrect_area

                # go through the
                for tool_id in c_polygons:
                    # first time we've seen this polygon
                    if tool_id not in return_polygons:
                        return_polygons[tool_id] = c_polygons[tool_id]
                        # return_stats[tool_id] = c_stats[tool_id]

                        new_area[tool_id] = [c_stats[tool_id][1],]
                        new_percentage[tool_id] = [c_stats[tool_id][0],]
                    else:
                        # we need to merge (yay!!)
                        # note this will probably result in more than one polygon
                        return_polygons[tool_id] = return_polygons[tool_id].union(c_polygons[tool_id])
                        # I think I could fold these values in as I go, but just to be careful (don't want to mess
                        # with the stats) save the values until end
                        new_area[tool_id].append(c_stats[tool_id][1])
                        new_percentage[tool_id].append(c_stats[tool_id][0])

            # now that we've gone through all of the children
            # calculate the weighted values
            for tool_id in new_area:
                # print new_percentage[tool_id]
                return_stats[tool_id] = numpy.average(new_percentage[tool_id],weights=new_area[tool_id]),sum(new_area[tool_id])

                assert not isinstance(return_polygons[tool_id],list)

            if self.parent == None:
                for u in total_polygons_user_density:
                    total_polygons_user_density[u] = cascaded_union(total_polygons_user_density[u])

            return return_polygons,return_stats,total_incorrect_area,total_polygons_user_density

    def __add_polygon__(self,user,polygon,poly_type):
        assert isinstance(polygon,Polygon) or isinstance(polygon,MultiPolygon)
        # don't add it if there is no intersection
        if self.bounding_box.intersection(polygon).is_empty:
            return

        if user not in self.polygons:
            self.polygons[user] = [(polygon,poly_type)]
            self.user_ids.append(user)
        else:
            self.polygons[user].append((polygon,poly_type))

    def __poly_iteration__(self):
        class Iterator:
            def __init__(self,node):
                assert isinstance(node,QuadTree)
                self.node = node
                self.user_index = None
                self.polygon_index = None

            def __iter__(self):
                return self

            def next(self):
                if self.user_index is None:
                    self.user_index = 0
                    self.polygon_index = 0
                else:
                    self.polygon_index += 1
                    if self.polygon_index == len(self.node.polygons[self.node.user_ids[self.user_index]]):
                        self.polygon_index = 0
                        self.user_index += 1

                    if self.user_index == len(self.node.user_ids):
                        raise StopIteration

                user_id = self.node.user_ids[self.user_index]
                return user_id,self.node.polygons[user_id][self.polygon_index]

        return Iterator(self)


class BlobClustering(clustering.Cluster):
    def __init__(self,shape,**kwargs):
        assert shape != "point"
        clustering.Cluster.__init__(self,shape,kwargs)
        self.rectangle = (shape == "rectangle")

    def __fix_polygon__(self,points):
        fixed_polygons = None

        points = list(points)

        validity = explain_validity(Polygon(points))

        # x,y = zip(*Polygon(points).exterior.coords)
        # x = list(x)
        # y = list(y)
        # x.append(x[0])
        # y.append(y[0])
        # plt.plot(x,y)
        # plt.show()

        assert isinstance(validity,str)
        s,t = validity.split("[")
        x_0,y_0 = t.split(" ")
        x_0 = float(x_0)
        y_0 = float(y_0[:-1])

        # search for all of the line segments which touch the intersection point
        # we need to wrap around to the beginning to get all of the line segments
        splits = []
        for line_index in range(len(points)):
            (x_1,y_1) = points[line_index]
            (x_2,y_2) = points[(line_index+1)%len(points)]

            # the equation from a point to the nearest place on a line is from
            # https://en.wikipedia.org/wiki/Distance_from_a_point_to_a_line
            try:
                dist = math.fabs((y_2-y_1)*x_0-(x_2-x_1)*y_0+x_2*y_1-y_2*x_1)/math.sqrt((y_2-y_1)**2+(x_2-x_1)**2)
            except ZeroDivisionError:
                print points
                print line_index
                raise

            if dist < 0.01:
                splits.append(line_index)

        # seems to be the easiest way to dealing with needing to extract
        # sublists which wrap around the end/beginning of the list

        points.extend(points)
        for intersection_index,line_index in enumerate(splits):
            # find the index for the next line segment with intersect (x_0,y_0)
            # if we have reached the end of the list then we need to wrap around
            if (intersection_index+1) < len(splits):
                line_index2 = splits[intersection_index+1]
            else:
                # keep in mind that we've doubled the length of points
                line_index2 = splits[0] + len(points)/2

            # always create the new polygon starting at the intersection point
            new_polygon_points = [(x_0,y_0)]
            new_polygon_points.extend(points[line_index+1:line_index2+1])

            if explain_validity(Polygon(new_polygon_points)) != "Valid Geometry":
                # if this is the first "sub"polygon - just accept it
                if fixed_polygons is None:
                    fixed_polygons = self.__fix_polygon__(new_polygon_points)
                # else try to merge the results in
                else:
                    fixed_polygons.extend(self.__fix_polygon__(new_polygon_points))
            else:
                if fixed_polygons is None:
                    fixed_polygons = [Polygon(new_polygon_points)]
                else:
                    fixed_polygons.append(Polygon(new_polygon_points))

        return fixed_polygons

    def __cluster__(self,markings,user_ids,tools,reduced_markings,dimensions):
        poly_dictionary = {}
        # the polygon dictionary will contain the "processed" polygons for each user along with that
        # polygon's type so the points stored for those polygons might not actually correspond to the users
        # original points. This means that we cannot use those points as a reference (or pointer if you will ;))
        # when dealing with followup questions
        # so we will also add an index value so that we can look back at the original set of markings
        for marking_index,(polygon_pts,u,t) in enumerate(zip(markings,user_ids,tools)):
            # we need at least 3 points to made a valid polygon
            if len(polygon_pts) < 3:
                continue

            poly = Polygon(polygon_pts)
            validity = explain_validity(poly)

            if "Too few points" in validity:
                continue
            # correct the geometry if we have to - will probably result in a multipolygon
            # which we will keep as one object and NOT split into individual polygons
            elif validity != "Valid Geometry":
                corrected_polygon = self.__fix_polygon__(polygon_pts)
                corrected_polygon = cascaded_union(corrected_polygon)

                if u not in poly_dictionary:
                    poly_dictionary[u] = [(corrected_polygon,t,marking_index),]
                else:
                    poly_dictionary[u].append((corrected_polygon,t,marking_index))

            else:
                if u not in poly_dictionary:
                    poly_dictionary[u] = [(poly,t,marking_index)]
                else:
                    poly_dictionary[u].append((poly,t,marking_index))

        # if dimensions have been provided, use those as our initial bounding box
        # otherwise, use the minimum and maximum values actually found
        # todo - might this be best in any case - even if we have the image dimensions?
        if dimensions == (None,None):
            max_x = -float("inf")
            max_y = -float("inf")
            min_x = float("inf")
            min_y = float("inf")
            for m in markings:
                X,Y = zip(*m)

                max_x = max(max_x,max(X))
                max_y = max(max_y,max(Y))
                min_x = min(min_x,min(X))
                min_y = min(min_y,min(Y))

            assert max_x != min_x
            assert max_y != min_y

            box = [[min_x,min_y],[max_x,min_y],[max_x,max_y],[min_x,max_y]]
            # bit of a proxy
            image_area = max_x*max_y
        else:
            box = [[0,0],[dimensions[1],0],[dimensions[1],dimensions[0]],[0,dimensions[1]]]
            image_area = dimensions[0]*dimensions[1]

        quad_root = QuadTree((box[0],box[2]))

        for user,polygon_list in poly_dictionary.items():
            for polygon,poly_type,index in polygon_list:
                quad_root.__add_polygon__(user,polygon,poly_type)

        to_process = [quad_root]

        # do a depth first traversal of the tree to populate each of the nodes
        while to_process != []:
            node = to_process.pop(-1)
            assert isinstance(node,QuadTree)

            # if (we have parent =>  !the root) => need to read in parent's polygons
            # some of which will become ours
            if node.parent is not None:
                for user,(poly,poly_type) in node.parent.__poly_iteration__():
                    node.__add_polygon__(user,poly,poly_type)

            new_children = node.__get_splits__()

            to_process.extend(new_children)

        # now get the results - start from the root node
        aggregate_polygons,aggregate_stats,total_incorrect_area,polygons_by_user_density = quad_root.__aggregate__(image_area)

        for tool_id in aggregate_stats:
            vote_percentage,tool_area = aggregate_stats[tool_id]
            aggregate_stats[tool_id] = vote_percentage,tool_area/float(image_area)

        # incorrect_area_as_percent = total_incorrect_area/image_area

        # find which users have a polygon actually intersecting with this particular aggregate one
        matched_polygons = self.__match_individual_to_aggregate__(poly_dictionary,aggregate_polygons)

        return self.__get_results__(aggregate_polygons,markings,matched_polygons,image_area)

    def __match_individual_to_aggregate__(self,poly_dictionary,aggregate_polygons):
        """
        find which user polygon maps to which aggregate polygon
        note that the types might not match up - the user could have said that
        a polygon outlines a region of one type of tree while the majority
        said a different kind
        however, we will ignore such mismatched polygons since that means that the follow up questions must match up
        """
        # decompose each aggregate polygon into a list of polygons (if we have a multipolygon)
        # or just a singleton list if we have just one polygon
        # use a dictionary to keep track of type
        # might not be necessary but I want to make sure that the ordering of the individual polygons
        # inside of a multipolygon doesn't change
        # also a good moment to set up the cluster members list

        # contains which individual polygons are members of which aggregate polygons
        members_of_aggregate = {}
        for poly_type,agg_poly in aggregate_polygons.items():
            members_of_aggregate[poly_type] = []
            if isinstance(agg_poly,Polygon):
                aggregate_polygons[poly_type] = [agg_poly]
                members_of_aggregate[poly_type].append([])
            else:
                assert isinstance(agg_poly,MultiPolygon)
                aggregate_polygons[poly_type] = []
                for p in agg_poly:
                    aggregate_polygons[poly_type].append(p)
                    members_of_aggregate[poly_type].append([])

        # go through each user
        for u in poly_dictionary:

            # go through every polygon that this user drew
            for user_poly,poly_type,marking_index in poly_dictionary[u]:
                # covers => all the aggregate polygons which this user's polygon "mostly" covers
                # so below the threshold is at least half the aggregate polyon
                # kinda like a superset but a bit relaxed
                covers = []
                # belongs_to => all the aggregate polygons which this user's polygon is "mostly" in
                # again kinda like a subset but a bit relaxed
                belongs_to = []

                # were there any aggregate polygons of the right type?
                if poly_type in aggregate_polygons:
                    for poly_index,p in enumerate(aggregate_polygons[poly_type]):
                        inter = p.intersection(user_poly)

                        if inter.area/p.area > 0.5:
                            covers.append(poly_index)
                        if inter.area/user_poly.area > 0.5:
                            belongs_to.append(poly_index)

                    # we have found a strong and unique mapping from an individual polygon/rectangle
                    # to an aggregate one
                    if (len(covers) == 1) and (covers == belongs_to):
                        members_of_aggregate[poly_type][covers[0]].append((u,user_poly,marking_index))

        return members_of_aggregate

    def __get_results__(self,aggregate_polygons,markings,polygon_members,image_area):
        """
        actually combine everything done so far into the results that we will return
        :return:
        """

        results = []
        # a lot of this stuff is done in the classification code for other tool types but it makes more
        # sense for polygons to do it here
        for tool_id in aggregate_polygons:
            # have one set of results per tool type
            # the center will be a list of all polygons

            for poly_index,agg_poly in enumerate(aggregate_polygons[tool_id]):
                next_result = dict()
                # if we are doing rectangles, make sure to keep them as rectangles
                if self.rectangle:
                    x,y = agg_poly.exterior.xy
                    next_result["center"] = [(max(x),max(y)),(min(x),min(y))]
                else:
                    next_result["center"] = [zip(agg_poly.exterior.xy[0],agg_poly.exterior.xy[0])]

                next_result["area"] = agg_poly.area/float(image_area)

                # cluster members are the individual polygons
                # users are the corresponding user ids
                next_result["cluster members"] = []
                next_result["users"] = []
                next_result["tools"] = []
                for user,poly,marking_index in polygon_members[tool_id][poly_index]:
                    next_result["cluster members"].append(markings[marking_index][:5])
                    next_result["users"].append(user)
                    next_result["tools"].append(tool_id)

                # put this in the format that is used by the other shapes - 1 for now
                # todo - if it really matters calculate an actual value instead of 1
                next_result["tool_classification"] = ({tool_id:1},-1)

                # such cases correspond to weird unexpected polygons, so just ignore them
                if next_result["cluster members"] != []:
                    results.append(next_result)

        return results,0
