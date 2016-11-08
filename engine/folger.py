#!/usr/bin/env python
import numpy as np
import math
import networkx
import re

from text_clustering import TextClustering
from helper_functions import warning
__author__ = 'greg'


def longest_common_substring(s1, s2):
    """
    taken from https://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/Longest_common_substring#Python2
    :param s1:
    :param s2:
    :return:
    """
    m = [[0] * (1 + len(s2)) for i in xrange(1 + len(s1))]
    longest, x_longest = 0, 0
    for x in xrange(1, 1 + len(s1)):
        for y in xrange(1, 1 + len(s2)):
            if s1[x - 1] == s2[y - 1]:
                m[x][y] = m[x - 1][y - 1] + 1
                if m[x][y] > longest:
                    longest = m[x][y]
                    x_longest = x
            else:
                m[x][y] = 0
    return s1[x_longest - longest: x_longest]


class FolgerClustering(TextClustering):
    def __init__(self,shape,project,param_dict):
        TextClustering.__init__(self,shape,project,param_dict)

        self.folger_safe_tags = dict()

        # for folger the tags in the transcriptions are not actually the tags that folger wants
        for key,tag in self.tags.items():
            self.folger_safe_tags[key] = tag.replace("sw-","")

        self.total = 0
        self.error = 0

    def __line_alignment__(self, lines):
        _lines = []
        for line in lines:
            _lines.append(re.sub(r'</?(ex|del|ins|unclear|sup)>', '', line))

        return super(FolgerClustering, self).__line_alignment__(_lines)

    def __accuracy__(self,s):
        assert isinstance(s,str)
        assert len(s) > 0
        return sum([1 for c in s if c != "-"])/float(len(s))

    def __reset_tags__(self,text):
        """
        with text, we will have tags represented by a single character (with ord() > 128 to indicate
        that something is special) Convert these back to the full text representation
        also take care of folger specific stuff right
        :param text:
        :return:
        """
        assert type(text) in [str,unicode]

        # reverse_map = {v: k for k, v in self.tags.items()}
        # also go with something different for "not sure"
        # this matter when the function is called on the aggregate text
        # reverse_map[200] = chr(27)
        # and for gaps inserted by MAFFT
        # reverse_map[201] = chr(24)

        ret_text = ""

        for c in text:
            if ord(c) > 128:
                ret_text += self.folger_safe_tags[ord(c)]
            else:
                ret_text += c

        return ret_text

    def __find_completed_components__(self,aligned_text,coordinates):
        """
        go through the aggregated text looking for subsets where at least 3 people have transcribed everything
        for example if A,B,C also intersect, and C,D,E all intersect (without any overlap other than C between the two
        subsets) return the two separate
        :param aligned_text:
        :param coordinates:
        :return:
        """
        completed_indices = []
        # find all character indices where at least 3 people have transcribed
        for char_index in range(len(aligned_text[0])):
            # 25 corresponds to before or after users started transcribing
            num_char = len([1 for text in aligned_text if ord(text[char_index]) != 25])

            if num_char >= 3:
                completed_indices.append(char_index)

        starting_points = {}
        ending_points = {}

        # find consecutive blocks
        if completed_indices != []:
            # find the contiguous blocks of completed transcriptions
            # the first block of connected transcriptions
            blocks = [[completed_indices[0]],]

            for i,char_index in list(enumerate(completed_indices))[1:]:
                # do we have a jump - if so, start a new block
                if completed_indices[i] != (completed_indices[i-1]+1):
                    blocks.append([char_index])
                else:
                    blocks[-1].append(completed_indices[i])

            # if the last character started a new block (kinda weird but happens)
            # then we have a block only one character long - skip it
            if len(blocks[-1]) == 1:
                blocks = blocks[:-1]

            # technically we can have multiple transcriptions from the same user so
            # instead of user_index, I'll use transcription_index
            # also, technically the same user could give transcribe the same piece of text twice (or more)
            # and include those transcriptions in different annotations. Going to assume that doesn't happen
            for transcription_index,(text,coord) in enumerate(zip(aligned_text,coordinates)):
                x1,x2,y1,y2 = coord
                non_space_characters = [i for (i,c) in enumerate(text) if ord(c) != 25]

                first_char = min(non_space_characters)
                last_char = max(non_space_characters)

                # transcription_range[transcription_index] = (first_char,last_char)

                # look for transcriptions which exactly match up with the completed segment
                # match on either starting OR ending point matching up
                # we'll use these transcriptions to determine where to place the red dots
                # telling people to no longer transcribe that text
                # such transcriptions may not exist - in which case we cannot really do anything
                for b in blocks:
                    b = tuple(b)
                    # does the start of the transcription match up with the start of the completed segment
                    if b[0] == first_char:
                        if b in starting_points:
                            starting_points[b].append((x1,y1))
                        else:
                            starting_points[b] = [(x1,y1)]

                    # does the end of the transcription match up with the end of the completed segment?
                    if b[-1] == last_char:
                        if b in ending_points:
                            ending_points[b].append((x2,y2))
                        else:
                            ending_points[b] = [(x2,y2)]

        return starting_points,ending_points

    def __setup_aligned_text__(self,aligned_text,text_coordinates,user_ids,x1,y1,x2,y2):
        """
        when printing out the individual transcriptions that make up a cluster we need to do a few things
        including sorting them.
        :return:
        """
        # todo - honestly not sure if most of this function is necessary

        new_aligned = []

        for t in aligned_text:
            # todo - figure out if this is necessary or useful
            if t is None:
                warning("text was none - really not sure why but skipping")
                continue
            # put tags back into multicharacter format
            t = self.__reset_tags__(t)
            new_aligned.append(unicode(t))

        # if the text is horizontal - i.e. the angle of the center is less than 45 degrees
        # sort the aligned text by x coordinates - otherwise sort by DECREASING y coordinates
        # (since 0,0 is at the top left)
        try:
            tan_theta = math.fabs(y1-y2)/math.fabs(x1-x2)
            theta = math.atan(tan_theta)
        except ZeroDivisionError:
            theta = math.pi/2.

        # horizontal
        # pretty sure that X1 < X2 but don't want to make an assumption
        if math.fabs(theta) <= math.pi/4.:
            starting_coordinates = [min(x1,x2) for x1,x2,_,_ in text_coordinates]
        # vertical text
        # pretty not sure about whether Y1<Y2 so playing it safe
        else:
            starting_coordinates = [-max(y1,y2) for _,_,y1,y2 in text_coordinates]
        text_and_ids_with_coordinates = zip(starting_coordinates,new_aligned,user_ids)
        # sort
        text_and_ids_with_coordinates.sort(key = lambda x:x[0])
        _,aligned_text,user_id = zip(*text_and_ids_with_coordinates)

        return aligned_text

    def __create_clusters__(self,(starting_points,ending_points),aggregated_text,cluster_index,aligned_text,variants,user_ids,text_coordinates):
        """
        the aggregated text, split up into completed components and make a result (aggregate) cluster for each
        of those components
        :param aggregated_text:
        :param transcription_range: where (relative to the aggregate text) each transcription string starts and stops
        useful for differentiating between gap markers before or after the text and gaps inside the text
        :param markings: the original markings - without the tags tokenized
        :return:
        """
        clusters = []

        # go through every segment that is considered done
        for block in starting_points:
            # not sure how likely this is to happen, but just to be sure
            # make sure that we have both a starting and ending point
            if block not in ending_points:
                continue

            # get the start and the end of the completed block
            lb = min(block)
            ub = max(block)

            new_cluster = {}

            # get the coordinates of the transcriptions which matched up with the start or the end of this
            # transcribed block - use those transcriptions to create the aggregate coordinates
            X1,Y1 = zip(*starting_points[block])
            X2,Y2 = zip(*ending_points[block])

            x1 = np.median(X1)
            x2 = np.median(X2)
            y1 = np.median(Y1)
            y2 = np.median(Y2)

            completed_text = self.__reset_tags__(aggregated_text[lb:ub+1])
            # chr(26) means not enough people have transcribed at a given position
            # but we specifically chose this substring as a substring where all the characters have
            # been transcribed by enough people. So sanity check
            assert chr(26) not in completed_text
            assert isinstance(completed_text,str)

            # set the different parameters for this cluster
            new_cluster["center"] = (x1,x2,y1,y2,completed_text)
            new_cluster["individual points"] = text_coordinates
            new_cluster["set index"] = cluster_index
            new_cluster["aligned_text"] = self.__setup_aligned_text__(aligned_text,text_coordinates,user_ids,x1,y1,x2,y2)
            new_cluster["cluster members"] = user_ids
            new_cluster["num users"] = len(new_cluster["cluster members"])

            new_cluster["variants"] = []
            # since a simple spelling mistake can count as a variant, look for cases where at least
            # two people have given the same variant
            variant_dict = dict()
            assert len(variants) == len(user_ids)
            for i,u in enumerate(user_ids):
                if u < 0:
                    continue

                for v in variants[i]:
                    if v not in variant_dict:
                        variant_dict[v] = [u]
                    else:
                        variant_dict[v].append(u)

            # see if any of the variants have been transcribed by at least two people
            for v,user_list in variant_dict.items():
                if len(user_list) >= 2:
                    display_names = []
                    for u in user_list:
                        display_names.append(self.project.__get_user_name__(u))
                    new_cluster["variants"].append((v,display_names))

            clusters.append(new_cluster)

        return clusters

    def __merge_aligned_text__(self,aligned_text):
        """
        once we have aligned the text using MAFFT, use this function to actually decide on an aggregate
        result - will also return the % of agreement
        and the percentage of how many characters for each transcription agree with the agree
        handles special tags just fine - and assumes that we have dealt with capitalization already
        """
        aggregate_text = ""
        num_agreed = 0

        # will keep track of the percentage of characters from each transcription which agree
        # with the aggregate
        agreement_per_user = [0 for i in aligned_text]

        # self.stats["line_length"].append(len(aligned_text[0]))

        vote_history = []

        uncompleted_characters = 0

        for char_index in range(len(aligned_text[0])):
            # get all the possible characters
            # todo - we can reduce this down to having to loop over each character once
            # todo - handle case (lower case vs. upper case) better
            char_set = set(text[char_index] for text in aligned_text)
            # get the percentage of votes for each character at this position
            char_vote = {c:sum([1 for text in aligned_text if text[char_index] == c]) for c in char_set if ord(c) != 25}
            vote_history.append(char_vote)

            # get the most common character (also the most likely to be the correct one) and the percentage of users
            # who "voted" for it

            # have at least 3 people transcribed this character?
            if sum(char_vote.values()) >= 3:
                self.stats["characters"] += 1

                most_likely_char,max_votes = max(char_vote.items(),key=lambda x:x[1])
                vote_percentage = max_votes/float(sum(char_vote.values()))

                # is there general agreement about what this character is?
                if vote_percentage > 0.5:
                    num_agreed += 1
                    aggregate_text += most_likely_char

                # check for special cases with double spaces or only differences about capitalization
                elif len(char_vote) == 2:
                    sorted_keys = [c for c in sorted(char_vote.keys())]
                    # this case => at least one person transcribed " " and at least one other
                    # person transcribed 24 (i.e. nothing) - so it might be that the first person accidentally
                    # gave " " which we'll assume means a double space so skip
                    if (ord(sorted_keys[0]) == 24) and (sorted_keys[1] == " "):
                        # but only skip it if at least two person gave 24
                        if char_vote[chr(24)] >= 2:
                            aggregate_text += chr(24)
                        else:
                            # 27 => disagreement
                            aggregate_text += chr(27)
                            self.stats["errors"] += 1

                    # capitalization issues? only two different transcriptions given
                    # one the lower case version of the other
                    elif sorted_keys[0].lower() == sorted_keys[1].lower():
                        aggregate_text += sorted_keys[0].upper()
                    # otherwise two different transcriptions but doesn't meet either of the special cases
                    else:
                        aggregate_text += chr(27)
                        self.stats["errors"] += 1
                else:
                    # chr(27) => disagreement
                    aggregate_text += chr(27)
                    self.stats["errors"] += 1
            else:
                # not enough people have transcribed this character
                aggregate_text += chr(26)
                uncompleted_characters += 1

        if uncompleted_characters == 0:
            self.stats["retired lines"] += 1
        assert len(aggregate_text) > 0

        try:
            percent_consensus = num_agreed/float(len([a for a in aggregate_text if ord(a) != 26]))
            percent_complete = len([a for a in aggregate_text if ord(a) != 26])/float(len(aggregate_text))
        except ZeroDivisionError:
            percent_complete = 0
            percent_consensus = -1

        return aggregate_text

    def __add_alignment_spaces__(self,aligned_text_list,tokenized_text):
        """
        take the text representation where we still have upper case and lower case letters
        plus special characters for tags (so definitely not the input for MAFFT) and add in whatever
        alignment characters are needed (say char(201)) so that the first text representations are all
        aligned
        fasta is the format the MAFFT reads in from - so non_fasta_text contains non-alpha-numeric ascii chars
        pts_and_users is used to match text in aligned text with non_fasta_text
        """

        aligned_nf_text_list = []
        transcription_range = []
        for text,nf_text in zip(aligned_text_list,tokenized_text):
            aligned_nf_text = ""

            # added spaces before or after all of the text need to be treated differently
            non_space_characters = [i for (i,c) in enumerate(text) if c != "-"]
            try:
                first_char = min(non_space_characters)
            except ValueError:
                print text
                print nf_text
                print aligned_text_list
                raise
            last_char = max(non_space_characters)

            transcription_range.append((first_char,last_char))

            i = 0
            for j,c in enumerate(text):
                if c == "-":
                    if first_char <= j <= last_char:
                        # this is a gap where the person may have missed something
                        aligned_nf_text += chr(24)
                    else:
                        # this corresponds to before or after the person started transcribing
                        aligned_nf_text += chr(25)
                else:
                    aligned_nf_text += nf_text[i]
                    i += 1
            aligned_nf_text_list.append(aligned_nf_text)

        # todo - I think transcription_range isn't necessary. I think find_completed_components does the job
        return aligned_nf_text_list,transcription_range

    def __filter_markings__(self,markings,user_ids,horizontal=True,strict=False):
        """
        filter out any markings which are not horizontal or are empty after removing bad characters
        :return:
        """
        assert len(markings) == len(user_ids)
        # todo - generalize for non-horizontal markings
        filtered_markings = []

        points_plotted = False

        for m_i,((x1,x2,y1,y2,t,variants),id_) in enumerate(zip(markings,user_ids)):
            # skip empty strings - but make sure when checking to first remove tags that shouldn't
            # be there in the first place
            # set_tags removes some tags (such as <br>) which we don't want at all
            # so if a transcription is just "<br>" we should skip it
            processed_text = self.__set_tags__(t.encode('ascii','ignore'))
            if processed_text == "":
                continue

            # check the angle
            try:
                tan_theta = math.fabs(y1-y2)/math.fabs(x1-x2)
                theta = math.atan(tan_theta)
            except ZeroDivisionError:
                theta = math.pi/2.

            self.total += 1

            if horizontal:
                valid = False
                words = t.split(" ")
                is_horizontal = math.fabs(theta) < 0.15
                is_kinda_horizontal = math.fabs(theta) < math.pi/5.

                if is_horizontal or ((not strict) and (len(words) <= 1) and is_kinda_horizontal):
                    valid = True
                    filtered_markings.append((x1,x2,y1,y2,processed_text,variants,id_))

            else: # vertical
                words = t.split(" ")
                is_vertical = math.fabs(theta-math.pi/2.) < 0.15
                is_kinda_vertical = math.fabs(theta-math.pi/2.) < math.pi/5.

                if is_vertical or ((not strict) and (len(words) <= 1) and is_kinda_vertical):
                    valid = True
                    filtered_markings.append((x1,x2,y1,y2,processed_text,variants,id_))

        return filtered_markings,points_plotted

    def __find_connected_transcriptions__(self,markings):
        """
        cluster transcriptions such that each cluster corresponds to the same line of text
        do this with connected components in a graph - hence the function name
        :return a list of lists - each "sub" list is list of indices for markings in that transcription:
        """
        G = networkx.Graph()
        G.add_nodes_from(range(len(markings)))

         # now look for the overlapping parts
        # examine every pair - note that distance from A to B does not necessarily equal
        # the distance from B to A - so order matters
        for m_i,(x1,x2,y1,y2,_,_,_) in enumerate(markings):
            for m_i2,(x1_,x2_,y1_,y2_,_,_,_) in enumerate(markings):
                # assuming two purely horizontal lines - consider the following example
                # x1 ----------- x2
                #     x1_----x2_
                # here the distance from x1 to the second line is the distance from x1 to x1_
                # but the distance from x1_ to the first line, is purely the vertical distance
                # since ignoring vertical distance, the second line is a subset of the first
                # so we can be pretty sure that the second line transcribes a subset of the first
                if m_i == m_i2:
                    continue

                # define our line according to ax+by+c=0
                try:
                    slope = (y2_-y1_)/float(x2_-x1_)
                    a = -slope
                    b = 1
                    inter = y2_ - slope*x2_
                    c = -inter
                except ZeroDivisionError:
                    # we have a vertical line
                    a = 1
                    b = 0
                    c = x2

                # see https://en.wikipedia.org/wiki/Distance_from_a_point_to_a_line
                # for explanation of the below code

                dist_1 = math.fabs(a*x1+b*y1+c)/math.sqrt(a**2+b**2)
                x = (b*(b*x1-a*y1)-a*c)/float(a**2+b**2)

                # if x is outside of the line segment in either direction - recalculate the distance as explained
                # above
                # todo - we could probably merge this if statement with the next one
                if x < x1_:
                    x = x1_
                    y = y1_
                    dist_1 = math.sqrt((x-x1)**2+(y-y1)**2)
                elif x > x2_:
                    x = x2_
                    y = y2_
                    dist_1 = math.sqrt((x-x1)**2+(y-y1)**2)

                # repeat for x2,y2
                dist_2 = math.fabs(a*x2+b*y2+c)/math.sqrt(a**2+b**2)
                x = (b*(b*x2-a*y2)-a*c)/float(a**2+b**2)

                if x < x1_:
                    x = x1_
                    y = y1_
                    dist_2 = math.sqrt((x-x2)**2+(y-y2)**2)
                elif x > x2_:
                    x = x2_
                    y = y2_
                    dist_2 = math.sqrt((x-x2)**2+(y-y2)**2)

                # if the average distance is less than 10 (an arbitrary threshold) then assume there is an overlap
                # that is - these two transcriptions are transcribing at least some of the same text
                if (dist_1+dist_2)/2. < 10:
                    G.add_path([m_i,m_i2])

        # look for connect components - i.e. sets of overlapping transcriptions
        clusters = [c for c in list(networkx.connected_components(G)) if len(c) > 1]

        return clusters

    def __cluster__(self,markings,user_ids,tools,reduced_markings,image_dimensions,subject_id,recursive=False):
        """
        cluster the line segments transcriptions together - look for overlaping parts
        note that overlaping is not transitive - if A overlaps B and B overlap C, it does not follow
        that A overlaps C. So we'll use some graph theory instead to search for
        """
        print(subject_id)
        if len(set(user_ids)) <= 2:
            return [],0

        clusters = []

        # do horizontal and vertical lines separately
        # given that we can have multiple non-overlapping lines transcribing the same line of text
        # and people who transcribe multiple lines at once (which need to be removed), doing
        # both vertical and horizontal lines at once isn't really feasible

        for horizontal in [True,False]:
            filtered_markings,_ = self.__filter_markings__(markings,user_ids,horizontal)

            # if we didn't find any marks in this particular direction, skip to the next one
            if filtered_markings == []:
                continue

            # cluster the filtered components
            connected_components = self.__find_connected_transcriptions__(filtered_markings)

            # sanity check - adding into "kinda" vertical or "kinda" horizontal lines shouldn't change
            # the number of connected components (since that corresponds to the number of lines transcribed)
            # so if the number does change, we almost surely merged two distinct lines by including
            # the kinda vertical or horizontal lines - in which case, let's be safe and ignore such lines
            strict_filtered_markings,_ = self.__filter_markings__(markings,user_ids,horizontal,strict=True)
            strict_connected_components = self.__find_connected_transcriptions__(filtered_markings)

            if len(strict_connected_components) != len(connected_components):
                print "going with stricter definition of lines"
                connected_components = strict_connected_components
                filtered_markings = strict_filtered_markings

            # each connected component should correspond to a
            for ii,c in enumerate(connected_components):
                if len(c) <= 2:
                    continue

                # extract the starting/ending x-y coordinates for each transcription in the cluster
                try:
                    coordinates = [filtered_markings[i][:4] for i in c]
                except IndexError:
                    raise

                # as well as the text - at the same time deal with tags (make them all 1 character long)
                # and other special characters that MAFFT can't deal with
                # -2 since -1 is for variants
                tokenized_text = [filtered_markings[i][4] for i in c]

                variants = [filtered_markings[i][5] for i in c]

                # users_in_line = set([filtered_markings[i][6] for i in c])
                users_in_line = [filtered_markings[i][6] for i in c]

                # tokenized_text has each tag (several characters) represented by just one
                # (non-standard ascii) character, aka a token
                # mafft_safe_text converts all upper case letters to lower case
                # and uses upper case letters to represent things that MAFFT can't deal with (e.g. tag tokens)
                mafft_safe_text = [self.__set_special_characters__(t) for t in tokenized_text]

                # align based on the lower case items
                aligned_mafft_text = self.__line_alignment__(mafft_safe_text)
                # use that alignment to align the tokenized text items (which is isomorphic to the original text)
                # also a good place where to figure out which parts of the line can be considered "done", i.e. have
                # enough people transcribe them.
                # there is a difference for gaps inserted before or after the transcription (which really aren't
                # gaps at all) and gaps inside the transcription
                aligned_text,transcription_range = self.__add_alignment_spaces__(aligned_mafft_text,tokenized_text)

                # aggregate the individual pieces of text together
                aggregate_text = self.__merge_aligned_text__(aligned_text)
                # find where the text has been transcribed by at least 3 people
                completed_components = self.__find_completed_components__(aligned_text,coordinates)
                # (completed_starting_point,completed_ending_point),aggregated_text,transcription_range,markings
                text_coordinates = [filtered_markings[i][:4] for i in c]
                clusters.extend(self.__create_clusters__(completed_components,aggregate_text,ii,aligned_text,variants,users_in_line,text_coordinates))

        return clusters,0
