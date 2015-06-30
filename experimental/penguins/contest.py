#!/usr/bin/env python
__author__ = 'greghines'
import datetime
import pymongo
from geoip import geolite2
from pytz import timezone
import pytz
import time
import IP2Location
from time import mktime
import pygeoip
import csv
import geoip2.webservice
import socket

# connect to the mongodb server
client = pymongo.MongoClient()
db = client['penguin_2015-06-01']
subjects = db["penguin_subjects"]
classifications = db["penguin_classifications"]
users = db["penguin_users"]
gmt = timezone("GMT")

ballots = {}

to_skip = []
from tzwhere import tzwhere
w = tzwhere.tzwhere()

ip_to_tmz = {}

print "first batch"

with open("/home/greg/Databases/batch-request-c2f9da3a-0952-11e5-a81d-689f178bad51/batch-lookup.csv","rb") as f:
    ips = csv.reader(f, delimiter=',', quotechar='|')
    next(f)
    for row in ips:
        # ip address, lat,long
        try:
            ip_address,lat,long = row[0],float(row[10]),float(row[11])
            # print ip_address
            tmz = w.tzNameAt(lat, long)
            ip_to_tmz[str(ip_address)] = timezone(tmz)
        except (ValueError,AttributeError) as e:
            # print row
            continue

print "second batch"

with open("/home/greg/Databases/batch-request-91297ad0-09d7-11e5-910c-6ed4178bad51/batch-lookup.csv","rb") as f:
    ips = csv.reader(f, delimiter=',', quotechar='|')
    next(f)
    for row in ips:
        # ip address, lat,long
        try:
            ip_address,lat,long = row[0],float(row[10]),float(row[11])
            # print ip_address
            tmz = w.tzNameAt(lat, long)
            # assert str(ip_address) not in ip_to_tmz

            ip_to_tmz[str(ip_address)] = timezone(tmz)
        except (ValueError,AttributeError) as e:
            # print row
            continue

print "third batch"
with open("/home/greg/Databases/batch-request-520e8ab6-09dc-11e5-90b4-27a7178bad51/batch-lookup.csv","rb") as f:
    ips = csv.reader(f, delimiter=',', quotechar='|')
    next(f)
    for row in ips:
        # ip address, lat,long
        try:
            ip_address,lat,long = row[0],float(row[10]),float(row[11])
            # print ip_address
            tmz = w.tzNameAt(lat, long)
            ip_to_tmz[str(ip_address)] = timezone(tmz)
        except (ValueError,AttributeError) as e:
            # print row
            continue


with open("/home/greg/Databases/timezones","rb") as f:
    ips = csv.reader(f, delimiter=' ')
    for ip_address,tmz in ips:
        print ip_address,tmz
        ip_to_tmz[str(ip_address)] = timezone(tmz)

# assert False

        # if tmz is None:
        #     print row
# assert False

# with open("/home/greg/Databases/geo_ips.txt","rb") as f:
#     #ips = csv.reader(f, delimiter='\t', quotechar='|')
#     l = "a"
#     while l:
#         l = f.readline()
#         if not l:
#             break
#
#         words = l.split("\t")
#         try:
#             socket.inet_aton(words[0])
#             print "ip :: " + words[0]
#
#             for i in range(4):
#                 words = f.readline().split("\t")
#                 print words
#             print
#         except socket.error:
#             print "not valid"
#
#         # words = [""]
#         # # while words[-1] != '\n':
#         # for i in range(4):
#         #     l = f.readline()
#         #     words = l.split("\t")
#         #
#         #     print words
#         # print
#
#
# assert False

# with open("/home/greg/bad_ipaddresses.txt","rb") as csvfile:
#     ips = csv.reader(csvfile, delimiter=',', quotechar='|')
#     for row in ips:
#         to_skip.append(row[0])

# print to_skip
bad_ips = set()
# unknown_ips = set()

gic = pygeoip.GeoIP('/home/greg/Databases/GeoLiteCity.dat',flags=pygeoip.const.MMAP_CACHE)
weird_ips = set()
# client = geoip2.webservice.Client("101664", '3Wcy5fQZpepH')

extra_info = {}

# print classifications.count()#{"created_at":{"$gte":datetime.datetime(2015, 4, 25)},"created_at":{"$lte":datetime.datetime(2015, 5, 25)}})
for ii,classification in enumerate(classifications.find({"created_at":{"$gte":datetime.datetime(2015, 4, 25),"$lte":datetime.datetime(2015, 5, 25)}})):
    #print classification

    print ii
    # try:
    try:
        user = classification["user_name"]
    except KeyError:
        continue

    our_time_stamp = classification["created_at"]

    ip_address = str(classification["user_ip"])
    # print ip_address

    match = geolite2.lookup(ip_address)
    # rec = gic.record_by_addr(ip_address)

    # print ip_address == "162.232.194.146"
    # print "162.232.194.146" in ip_to_tmz
    # print ip_to_tmz["162.232.194.146"]
    # print match

    if (match is None) or (match.timezone == 'None') or (match.timezone is None):
        # print "="
        try:
            tmz = ip_to_tmz[ip_address]
            # print "----"
        except KeyError:
            # print ip_address
            bad_ips.add(ip_address)
            print classification
            print "**"
            assert False
            continue
        # unknown_ips.add(ip_address)
        # if rec["time_zone"] is None:
        #     # print rec
        #     # response = client.insights(ip_address)
        #     # print response
        #     # assert False
        #     bad_ips.add(ip_address)

    else:
        try:
            tmz = timezone(match.timezone)
        except (pytz.exceptions.UnknownTimeZoneError,AttributeError) as e:
            bad_ips.add(ip_address)
            print match
            print ip_address
            print "-"
            assert False
            continue
        # print match
    # print match

    # time_index = ["finished_at" in ann for ann in classification["annotations"]].index(True)
    # finished_at_str = classification["annotations"][time_index]["finished_at"]
    #
    # started_at_str = classification["annotations"][time_index]["started_at"]
    # started_at = time.strptime(started_at_str,"%a, %d %b %Y %H:%M:%S %Z")
    #
    # started_at=datetime.datetime(2015,started_at.tm_mon,started_at.tm_mday,started_at.tm_hour,started_at.tm_min)
    #
    #
    #
    # # convert from str into datetime instance
    # finished_at = time.strptime(finished_at_str,"%a, %d %b %Y %H:%M:%S %Z")
    #
    # temp = datetime.datetime(2015,finished_at.tm_mon,finished_at.tm_mday,finished_at.tm_hour,finished_at.tm_min)
    #
    # # add the timezone
    # finished_at = gmt.localize(datetime.datetime(2015,finished_at.tm_mon,finished_at.tm_mday,finished_at.tm_hour,finished_at.tm_min))
    created_at = gmt.localize(our_time_stamp)

    # if our_time_stamp>temp:
    #     delta_t = our_time_stamp-temp
    # else:
    #     delta_t = temp-our_time_stamp

    # print delta_t.seconds
    # if delta_t.seconds >= 5000:
    #     print ip_address
    #     print classification["created_at"]
    #     print classification["updated_at"]
    #     print classification["annotations"]
    #     print temp
    #     print our_time_stamp
    #     print delta_t
    #     print
    #     weird_ips.add(ip_address)

    contest_start = datetime.datetime(2015, 4, 25)
    contest_start = tmz.localize(contest_start)

    contest_end = datetime.datetime(2015, 5, 25)
    contest_end = tmz.localize(contest_end)

    # normalize to the correct time zone
    # finished_at = finished_at.astimezone(tmz)
    created_at = created_at.astimezone(tmz)
    # print (created_at >= contest_start) and (created_at <= contest_end)

    # and convert it to the local timezone
    # print finished_at
    date = (created_at.month,created_at.day)

    if user not in ballots:
        ballots[user] = {}

    if date not in ballots[user]:
        ballots[user][date] = 1
    else:
        ballots[user][date] += 1

    if not user in extra_info:
        extra_info[user] = set()
    extra_info[user].add(created_at)

ballot_list = []
for user in ballots:
    for date in ballots[user]:
        if ballots[user][date] >= 10:
            # todo : check that they want to be in contest
            try:
                u = users.find_one({"name":user})
                preferences = u["preferences"]["penguin"]
                if ("competition_opt_in" in preferences) and (preferences["competition_opt_in"] == "true"):
                    ballot_list.append(user)
            except KeyError:
                print u
                continue


import random
winner = random.sample(ballot_list,1)
print winner
