import psycopg2
import pymongo
__author__ = 'greg'
import numpy as np
db_name = "serengeti"
date = "_2015-06-27"

client = pymongo.MongoClient()
db = client[db_name+date]
subjects = db[db_name+"_subjects"]
classifications = db[db_name+"_classifications"]

conn = psycopg2.connect("dbname='serengeti_demo' user='user' host='host' password='fail'")
mico_cur = conn.cursor()

serengeti_conn = psycopg2.connect("dbname='"+db_name+"' user='greg' host='localhost' password='apassword'")
serengeti_cursor = serengeti_conn.cursor()

# serengeti_cursor.execute("drop table classifications")
# serengeti_cursor.execute("create table classifications(zooniverse_id character(10),blank bool)")
# serengeti_cursor.execute("create table classifications(zooniverse_id character(10),blank bool)")
# serengeti_cursor.execute("create index serengeti1 on classifications (zooniverse_id)")
#
# for i,c in enumerate(classifications.find().limit(1000000)):
#     if "user_name" in c:
#         user_name = c["user_name"]
#     else:
#         user_name = str(c["user_ip"])
#
#     zooniverse_id = c["subjects"][0]["zooniverse_id"]
#
#     # h = hash(zooniverse_id)%2147483647
#
#     if "species" in c["annotations"][0]:
#         blank = False
#     else:
#         blank = True
#
#     user_name = user_name.replace("'","")
#     # print "insert into classifications (zooniverse_id,blank) values ('"+str(zooniverse_id)+"',"+str(blank)+")"
#     # print "insert into classifications (user_name,zooniverse_id,blank) values ('"+user_name+"','"+str(zooniverse_id)+"',"+str(blank)+")"
#     # print "insert into classifications (h,user_name,zooniverse_id,blank) values (" + str(h) +",'"+user_name+"','"+str(zooniverse_id)+"',"+str(blank)+")"
#     # serengeti_cursor.execute("insert into classifications (h,user_name,zooniverse_id,blank) values (" + str(h) +",'"+user_name+"','"+str(zooniverse_id)+"',"+str(blank)+")")
#     serengeti_cursor.execute("insert into classifications (zooniverse_id,blank) values ('"+str(zooniverse_id)+"',"+str(blank)+")")
#     if (i% 1000 == 0) and (i > 0):
#         print i
#         serengeti_conn.commit()
# serengeti_conn.commit()

# serengeti_cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")

mico_cur.execute("select * from subjects where mico_status = 'finished'")

false_blanks = 0
mico_retired = 0
total_retired = 0

num_to_retire = []
num_to_retire2 = []
non_blank = 0

for c in mico_cur.fetchall():
    zooniverse_id = c[1]
    # print zooniverse_id
    # print subjects.find_one({"zooniverse_id":zooniverse_id})
    # assert len(zooniverse_id) == 10
    mico_results = c[7]

    mico_blank =  mico_results["objects"] == []

    if c[11] == "consensus_blank":
        print "**"
    actually_blank = c[11] == "blank"

    serengeti_cursor.execute("select blank from classifications where zooniverse_id = '" + zooniverse_id +"'")
    f = serengeti_cursor.fetchall()

    if len(f) < 5:
        continue

    f = [f_[0] for f_ in f]

    if False:
        retire_blank = False not in f[:2]

        if retire_blank and not actually_blank:
            false_blanks += 1
            non_blank += 1

        if retire_blank:
            total_retired += 1
            mico_retired += 1

            num_to_retire.append(2)
        else:
            non_blank += 1
    else:
        alt = 3
        retire_blank = False not in f[:alt]
        if retire_blank:
            total_retired += 1
            num_to_retire.append(alt)

            if not actually_blank:
                false_blanks += 1
                non_blank += 1
        else:
            non_blank += 1

    if not actually_blank:
        if subjects.find_one({"zooniverse_id":zooniverse_id})["metadata"]["retire_reason"] == "consensus":
            num_to_retire2.append(15)
        else:
            num_to_retire2.append(25)

print false_blanks, mico_retired,total_retired,non_blank
print np.mean(num_to_retire),np.median(num_to_retire)
print sum(num_to_retire),sum(num_to_retire2),sum(num_to_retire)+sum(num_to_retire2)

# serengeti_cursor.execute("select distinct zooniverse_id from classifications")
# print serengeti_cursor.fetchall()
