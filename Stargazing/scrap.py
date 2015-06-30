#!/usr/bin/env python
__author__ = 'ggdhines'
import os
from postgres_aggregation import PanoptesAPI
from cassandra.cluster import Cluster
from cassandra.cqltypes import UUIDType
import psycopg2
import json

# for Greg running on either office/home - which computer am I on?
if os.path.exists("/home/ggdhines"):
    base_directory = "/home/ggdhines"
else:
    base_directory = "/home/greg"

conn = psycopg2.connect("dbname = 'supernova' host='localhost' user = 'panoptes' password='password'")

cur = conn.cursor()
try:
    cur.execute("DROP TABLE classifications")
except psycopg2.InternalError as e:
    print e
    print "I can't drop our test database!"

#cur.execute("CREATE TABLE classifications (Created_at TIMESTAMP PRIMARY KEY, User_id INT, User_ip INET, Subject_id Int, Annotations JSON)")
# cur.execute("CREATE INDEX subjects ON classifications (Subject_id)")
#
# #cur.execute("INSERT INTO Cars VALUES(1,'Audi',52642)")
# #conn.commit()
# # prepared_stmt = session.prepare("INSERT INTO classification_model (user_id,created_at,user_ip,annotations,subject_id, classification_id) VALUES (?, ?, ?, ?, ?, uuid())")
# #
# stargazing = PanoptesAPI()
# stargazing.__cleanup__()
#
# cur.execute("PREPARE myplan AS " "INSERT INTO classifications (created_at,user_id,user_ip,subject_id,annotations) values ($1,$2,$3,$4,$5)")
#
# for ii,t in enumerate(stargazing.__yield_classifications__()):
#     # print t[3]
#     # print t[3][0]
#     # print type(t[3][0])
#     # print type(t[3])
#     # print json.loads(str(t[3]))
#     #user_id,created_at,user_ip,annotations,subject_ids
#     #print t[4]
#     #print json.dumps(t[4])
#
#     try:
#         cur.execute("SAVEPOINT bulk_savepoint")
#         if t[4][0] == 337524:
#             print t
#         cur.execute("execute myplan (%s, %s, %s, %s,%s)", (t[1], t[0],t[2],t[4][0],json.dumps(t[3])))
#         cur.execute("RELEASE bulk_savepoint")
#     except psycopg2.IntegrityError as e:
#         print "double time stamp"
#         cur.execute("ROLLBACK TO SAVEPOINT bulk_savepoint")
#         continue
#
#     #if (ii%1000) == 0:
#     #    print ii
#
# conn.commit()