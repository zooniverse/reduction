#!/usr/bin/env python
__author__ = 'greghines'
import datetime
import pymongo
import hashlib
import bcrypt
import unicodedata
import bisect

# salts = {}

# connect to the mongodb server
client = pymongo.MongoClient()
db = client['cyclone_center_2015-06-01']
classifications = db["cyclone_center_classifications"]

t= str(datetime.datetime.now())

records = []
passwords = {}

all_ips = []

def index(a, x):
    'Locate the leftmost value exactly equal to x'
    i = bisect.bisect_left(a, x)
    if i != len(a) and a[i] == x:
        return i
    raise ValueError

for classification in classifications.find():
    ip_ = classification["user_ip"]
    try:
        records.append((classification["user_ip"],classification["user_name"],classification["created_at"]))
    except KeyError:
        records.append((classification["user_ip"],None,classification["created_at"]))



# print "done hat"



print "hashed ips\t user_name\tclassification timestamp"
for ip,name,date in records:
    # ip = classification["user_ip"]
    try:
        p = index(all_ips,ip)
    except ValueError:
        bisect.insort(all_ips,ip)
        p = index(all_ips,ip)
    # if ip not in passwords:
    #     passwords[ip] = bcrypt.hashpw(str(ip), bcrypt.gensalt())

    if name is None:
        # print passwords[ip] + "\tNone\t"+str(date)
        print str(p) + ",None,"+str(date)
    else:
        print str(p) + "," + unicodedata.normalize('NFKD', name).encode('ascii','ignore') +","+str(date)

