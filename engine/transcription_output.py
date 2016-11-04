from __future__ import print_function

import codecs
import cStringIO
import csv
import json
import tarfile
import os
import re

from abc import ABCMeta, abstractmethod

"""
sets up the output for transcription projects like Annotate and Shakespeare's
world before being emailed out
"""

__author__ = 'ggdhines'

class EmptyString(Exception):
    pass

class UnicodeWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([self.convert(s).encode("utf-8") for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode("utf-8")
        # ... and reencode it into the target encoding
        data = self.encoder.encode(data)
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)

    def convert(self, v):
        if isinstance(v, bool):
            if v:
                return 'True'
            else:
                return 'False'
        if v is None:
            return ''
        if isinstance(v, list):
            return ",".join(map(self.convert, v))
        if isinstance(v, dict):
            return ",".join([
                '{}: {}'.format(k, self.convert(x)) for k, x in v.items()
            ])
        if isinstance(v, int):
            return str(v)
        return v


class TranscriptionOutput:
    __metaclass__ = ABCMeta

    def __init__(self, project, workflow_id):
        self.project = project

        if workflow_id:
            self.workflow_id = workflow_id
        else:
            self.workflow_id = self.project.workflows.keys()[0]
        self.metadata = self.project.__get_subject_metadata__(self.workflow_id)

        # tags and reverse tags allow you to tokenize tags (convert a
        # sub-string representing a character into # a single character, i.e. a
        # token) and then from that token back into the original string. Useful
        # for making sure that everyone's strings are the same length there
        # is a difference between tags and reverse_tags (i.e. you can't just
        # switch the key/value pairs in tags) # because with Folger we need to
        # worry about removing "sw-" from the tags
        self.tags = None
        self.reverse_tags = None

        self.safe_tags = dict()

    def write_csv_output(self, project_id, aggregation_data):
        aggregation_out = [
            ['subject_id', 'aggregated text', 'accuracy'],
        ]
        clustered_out = [
            ['subject_id', 'cluster number', 'coordinates',
             'individual transcription'],
        ]

        metadata_field_names = []

        for subject_id, subject_aggregation in aggregation_data.items():
            if not 'text' in subject_aggregation:
                continue
            subject_metadata = json.loads(
                subject_aggregation['metadata']
            )

            metadata_field_names = subject_metadata.keys()
            metadata_field_names.sort()

            total_text = len(subject_aggregation['text'])
            sum_accuracy = 0
            aggregated_text = ""

            for cluster_number, t in enumerate(subject_aggregation['text']):
                aggregated_text = aggregated_text + "\n" + re.sub(
                                 r'<disagreement>.*?</disagreement>',
                                 '?',
                                 t['aggregated_text']
                         )

                sum_accuracy += t['accuracy']

                for transcription in t['individual transcriptions']:
                    clustered_out.append([
                        subject_id,
                        cluster_number,
                        ", ".join(map(str, transcription['coordinates'])),
                        transcription['text']
                    ])

            new_row = [
                str(subject_id),
                aggregated_text,
                str(sum_accuracy/total_text)
            ]

            for field in metadata_field_names:
                new_row.append(unicode(subject_metadata[field]))

            aggregation_out.append(new_row)

        aggregation_out[0] = aggregation_out[0] + metadata_field_names

        with open(
            os.path.join('/', 'tmp', '{}.csv'.format(project_id)), 'w'
        ) as out_file:
            UnicodeWriter(out_file).writerows(aggregation_out)

        with open(
            os.path.join('/', 'tmp', '{} clusters.csv'.format(project_id)), 'w'
        ) as out_file:
            UnicodeWriter(out_file).writerows(clustered_out)

    def __json_output__(self,subject_id_filter=None):
        aggregations_to_json = dict()
        print("creating json output ready")
        # by using metadata.keys, we automatically restrict the results to
        # retired subjects

        for count, (subject_id, aggregations) in enumerate(self.project.__yield_aggregations__(self.workflow_id)):
            # we will have aggregation results for subjects which haven't been
            # retired yet (so we can show the black dots) # but we don't want
            # to include these subjects in the aggregation results.
            # self.metadata only includes metadata for retired subjects - so
            # if subject_id not in self.metadata, skip

            if subject_id not in self.metadata.keys():
                continue
            if (subject_id_filter is not None) and (subject_id not in subject_id_filter):
                continue
            print(subject_id)

            # on the off chance that the aggregations are in string format and
            # not json (seems to happen sometimes) not sure if its because on
            # running on Greg's computer vs. aws. But just playing it safe
            if isinstance(aggregations, str):
                aggregations = json.loads(aggregations)
            try:
                aggregations_to_json[subject_id] = self.__subject_to_json__(subject_id,aggregations)
            except IndexError:
                print("skipping " + str(subject_id))

        json.dump(aggregations_to_json, open("/tmp/" + str(self.project.project_id) + ".json", "wb"))
        self.write_csv_output(self.project.project_id, aggregations_to_json)
        self.__tar_output__()

    @abstractmethod
    def __tokenize_individual_transcriptions__(self,cluster):
        return None

    @abstractmethod
    def __generate_transcriptions_and_coordinates__(self,cluster):
        yield None

    def __write_out_cluster__(self,cluster):
        """
        set up the json output for a single individual cluster
        :param cluster:
        :return:
        """

        if isinstance(cluster,list):
            print("problem cluster")
            cluster = cluster[0]

        cluster_to_json = {}

        # we need to retokenize everything
        tokenized_strings = self.__tokenize_individual_transcriptions__(cluster)

        # and now repeat with aggregated line
        aggregated_line = str(cluster["center"][-1])

        # not sure why an empty aggregate string should exist but it does seem
        # to happen every so often
        if aggregated_line == "":
            raise EmptyString()

        for chr_representation,tag in self.tags.items():
            aggregated_line = aggregated_line.replace(tag,chr(chr_representation))
        assert isinstance(aggregated_line,str)

        # store this cleaned aggregate text
        cluster_to_json["aggregated_text"] = self.__write_out_aggregate_line__(aggregated_line,tokenized_strings)
        # plus the coordinates
        cluster_to_json["central coordinates"] = cluster["center"][:-1]
        # now add in the individual pieces of text
        cluster_to_json["individual transcriptions"] = self.__write_out_individual_lines__(cluster)

        cluster_to_json["accuracy"] = self.__calc_accuracy__(aggregated_line)

        if ("variants" in cluster) and (cluster["variants"] != []):
            variants = cluster["variants"]
        else:
            variants = []


        return cluster_to_json,variants

    def __calc_accuracy__(self,aggregate_line):
        """
        calculate the percentage of characters where we have reached agreement
        :param aggregate_line:
        :return:
        """
        agreed_characters = len([c for c in aggregate_line if ord(c) != 24])
        accuracy = agreed_characters/float(len(aggregate_line))

        return accuracy

    def __write_out_individual_lines__(self,cluster):
        """
        set up the output for each individual transcription in a cluster
        :param cluster:
        :return:
        """
        individual_text_to_json = []
        for coords,individual_text in self.__generate_transcriptions_and_coordinates__(cluster):
            assert isinstance(individual_text,unicode) or isinstance(individual_text,str)

            # again, convert the tags to the ones needed by Folger or Tate (as
            # opposed to the ones zooniverse is using)
            # assert isinstance(individual_text,str)
            # for old,new in replacement_tags.items():
            #     individual_text = individual_text.replace(old,new)

            temp_text = individual_text
            skip = 0
            is_skip = False

            # we need to "rebuild" the individual text so that we can insert
            # <skip>X</skip> to denote that MAFFT inserted X spaces into the
            # line
            individual_text = ""
            for c in temp_text:
                if ord(c) in [24,27]:
                    is_skip = True
                    skip += 1
                else:
                    if is_skip:
                        individual_text += "<skip>"+str(skip)+"</skip>"
                        skip = 0
                        is_skip = 0
                    individual_text += c

            individual_text_to_json.append({"coordinates":coords,"text":individual_text})

        return individual_text_to_json

    def __write_out_aggregate_line__(self,aggregated_line,tokenized_strings):
        """
        take care of setting up the output for one aggregate line
        :param tokenized_strings: so if there is disagreement, we can list the different options
        :return:
        """
        # convert some special characters and tokenize the disagreements

        line = ""

        agreement = True
        differences = {}

        for c_i,c in enumerate(aggregated_line):
            # if we have a disagreement (represented by either ord(c) = 27),
            # keep on a running tally of what all the differences are over
            # all users so we can report the disagreements per "word" of
            # disagreement, not per character
            if ord(c) == 27:
                agreement = False

                # get all of the different transcriptions given by each user
                try:
                    char_options = [(ii,individual_text[c_i]) for ii,individual_text in enumerate(tokenized_strings)]
                except IndexError:
                    raise

                # add these characters to the running total - ord(c) == 24 is
                # when MAFFT inserted a space to align the text, which
                # corresponds to not having anything there
                for ii,c in char_options:
                    if ord(c) != 24:
                        if ii not in differences:
                            differences[ii] = c
                        else:
                            differences[ii] += c
                    else:
                        if ii not in differences:
                            differences[ii] = ""
            elif ord(c) != 24:

                # if we just had a disagreement, print it out
                if not agreement:
                    line += "<disagreement>"
                    for options in set(differences.values()):
                        # when printing out convert all of the tokens for tags
                        # back into string format
                        for token,tag in self.reverse_tags.items():
                            assert isinstance(token,int)
                            options = options.replace(chr(token),tag)
                        line += "<option>"+options+"</option>"
                    line += "</disagreement>"
                    differences = {}

                agreement = True

                # untokenize any tokens we find - replace them with the
                # original tag
                for token,tag in self.tags.items():
                    c = c.replace(chr(token),tag)
                line += c

        # did we end on a disagreement?
        if not agreement:
            line += "<disagreement>"
            for c in set(differences.values()):
                for token,tag in self.tags.items():
                    c = c.replace(chr(token),tag)
                line += "<option>"+c+"</option>"
            line += "</disagreement>"

        # for the illegible tag, we added in some extra stuff, so now remove it
        line = line.replace(".*?","")
        return line

    def __subject_to_json__(self,subject_id,aggregation):
        """
        :param aggregation:
        :return subject_json:
        """
        subject_json = dict()
        # get the metadata for this subject
        subject_json["metadata"] = self.metadata[int(subject_id)]

        # are there any images in this subject?
        # there will always be "all_users" so we can looking for a list longer
        # than one
        if ("image clusters" in aggregation["T2"]) and (len(aggregation["T2"]["image clusters"]) > 1):
            subject_json["images"] = self.__add_image_aggregation__(aggregation)

        # are there text aggregations?
        if ("text clusters" in aggregation["T2"]) and (len(aggregation["T2"]["text clusters"]) > 1):
            subject_json["text"],subject_json["variants"] = self.__add_text_aggregation__(aggregation)

        # finally, give all of the individual transcriptions (removing
        # alignment tags) without regards to cluster - this way, people can
        # tell if any text was ignored
        subject_json["raw transcriptions"] = self.__add_global_transcriptions__(subject_id)

        return subject_json

    def __add_image_aggregation__(self,aggregation):
        """
        if a subject has images, add them to the aggregation results
        :param aggregation:
        :return:
        """
        image_results = []
        for image_index,image in aggregation["T2"]["image clusters"].items():
            if image_index == "all_users":
                continue
            image_results.append(image["center"])

        assert image_results != []
        return image_results

    def __add_text_aggregation__(self,aggregation):
        """
        if a subject has text aggregation (which will happen most of the time),
        add the aggregation results
        :param aggregation:
        :return:
        """
        text_results = []
        variants_per_subject = []

        # now build up each one of the results
        for cluster_index,cluster in aggregation["T2"]["text clusters"].items():
            # this isn't really a cluster - more metadata, so skip it
            if cluster_index == "all_users":
                continue

            # add this cluster to the total list
            try:
                text,variants = self.__write_out_cluster__(cluster)
                text_results.append(text)

                if variants != []:
                    variants_per_subject.append(variants)
            except EmptyString:
                pass

        # sort so they should appear in reading order
        text_results.sort(key = lambda x:x["central coordinates"][2])

        assert text_results != {}
        return text_results,variants_per_subject

    def __add_global_transcriptions__(self,subject_id):
        """
        add the individual transcriptions without regards to the cluster - so
        people can tell if any
        text was ignored
        :return:
        """
        global_list = []

        for annotations in self.project.__sort_annotations__(
            self.workflow_id,
            [subject_id]
        ):
            # annotation[1] is the list of markings for this subject -
            # annotation[0] is the list of classifications, [2] survey
            # annotations and [3] image dimensions
            transcriptions = annotations[1]

            # make sure that this user actually provided transcriptions,
            # otherwise, just skip
            if "T2" in transcriptions:
                for ii,(user_id,transcription,tool) in enumerate(transcriptions["T2"]["text"][subject_id]):
                    if transcription is None:
                        continue
                    coords = transcription[:4]
                    individual_text = transcription[4]
                    assert isinstance(individual_text,unicode)
                    if "\n" in individual_text:
                        continue

                    # convert to ascii - and if this is the folger project,
                    # remove "sw-"
                    individual_text = individual_text.encode('ascii','ignore')
                    for original,safe in self.safe_tags.items():
                        individual_text = individual_text.replace(original,safe)

                    global_list.append({"coordinates":coords,"text":individual_text})

        return global_list

    def __tar_output__(self):
        aws_tar = self.project.__get_aws_tar_name__()
        print("saving json results")
        with tarfile.open("/tmp/"+aws_tar,mode="w") as t:
            t.add(
                os.path.join('/', 'tmp', '{}.json'.format(
                    self.project.project_id
                )),
                arcname=self.project.project_name+".json"
            )
            t.add(
                os.path.join('/', 'tmp', '{}.csv'.format(
                    self.project.project_id
                )),
                arcname=self.project.project_name+".csv"
            )
            t.add(
                os.path.join('/', 'tmp', '{} clusters.csv'.format(
                    self.project.project_id
                )),
                arcname=self.project.project_name+".csv"
            )

class ShakespearesWorldOutput(TranscriptionOutput):
    def __init__(self, project, workflow_id):
        TranscriptionOutput.__init__(self, project, workflow_id)

        self.tags = self.project.text_algorithm.tags
        self.reverse_tags = dict()

        # for annotate we'll have safe_tags = tags but here we need to get rid
        # of the "sw-"
        for tag in self.tags.values():
            self.safe_tags[tag] = tag.replace("sw-","")

        # when converting from token back into string format, for folger we
        # need to make sure that we are using the right, sw-safe tags. So we
        # need a special self.reverse_tags
        for key,tag in self.tags.items():
            assert isinstance(tag,str)
            self.reverse_tags[key] = self.safe_tags[tag]

    def __tokenize_individual_transcriptions__(self,cluster):
        """
        convert each individual string into a tokenized representation (so each
        tag is just one character)
        :param cluster:
        :return:
        """
        tokenized_strings = []
        for text in cluster["aligned_text"]:
            text = text.encode('ascii','ignore')
            for chr_representation,tag in self.tags.items():
                text = text.replace(tag,chr(chr_representation))

            tokenized_strings.append(text)

        return tokenized_strings

    def __generate_transcriptions_and_coordinates__(self,cluster):
        """
        yield of all of the individual transcriptions and coordinates
        :param cluster:
        :return:
        """
        for coords,text in zip(cluster["individual points"],cluster["aligned_text"]):
            text = text.encode('ascii','ignore')
            for original,safe in self.safe_tags.items():
                text = text.replace(original,safe)
            yield coords,text

        raise StopIteration()

class AnnotateOutput(TranscriptionOutput):
    def __init__(self, project, workflow_id=None):
        TranscriptionOutput.__init__(self, project, workflow_id)

        # set up the reverse tags - so we can take a token (representing a full
        # tag) and replace it with the original tag
        self.tags = self.project.text_algorithm.tags
        assert self.tags != {}

        # for annotate - we don't need to do anything special when converting
        # from token back into tag
        self.reverse_tags = self.tags

    def __generate_individual_transcriptions__(self,cluster):
        for annotation in cluster["cluster members"]:
            yield annotation[-2]

    def __tokenize_individual_transcriptions__(self,cluster):
        """
        convert each individual string into a tokenized representation (so each
        tag is just one character)
        :param cluster:
        :return:
        """
        tokenized_strings = []
        for transcription in cluster["cluster members"]:
            text = transcription[4]
            text = text.encode('ascii','ignore')
            for chr_representation,tag in self.tags.items():
                text = text.replace(tag,chr(chr_representation))

            tokenized_strings.append(text)

        return tokenized_strings

    def __generate_transcriptions_and_coordinates__(self,cluster):
        for ii, annotation in enumerate(cluster["cluster members"]):
            # I think annotation[5] is no variants of words - for folger
            coords = annotation[:4]
            individual_text = annotation[4]

            yield coords,individual_text

        raise StopIteration()
