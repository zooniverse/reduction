import psycopg2
import pymongo
import datetime
__author__ = 'greg'

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

serengeti_cursor.execute("drop table classifications")
# serengeti_cursor.execute("create table classifications(zooniverse_id character(10),blank bool)")
serengeti_cursor.execute("create table classifications(zooniverse_id text,blank bool,created_at timestamp)")
serengeti_cursor.execute("create index serengeti1 on classifications (zooniverse_id)")

for i,c in enumerate(classifications.find({"created_at":{"$gte":datetime.datetime(2015,2,1)}}).limit(15000000)):
    if "user_name" in c:
        user_name = c["user_name"]
    else:
        user_name = str(c["user_ip"])

    zooniverse_id = c["subjects"][0]["zooniverse_id"]

    assert len(zooniverse_id) == 10

    # h = hash(zooniverse_id)%2147483647

    if "species" in c["annotations"][0]:
        blank = False
    else:
        blank = True

    user_name = user_name.replace("'","")
    created_at = c["created_at"]
    # print "insert into classifications (zooniverse_id,blank) values ('"+str(zooniverse_id)+"',"+str(blank)+")"
    # print "insert into classifications (user_name,zooniverse_id,blank) values ('"+user_name+"','"+str(zooniverse_id)+"',"+str(blank)+")"
    # print "insert into classifications (h,user_name,zooniverse_id,blank) values (" + str(h) +",'"+user_name+"','"+str(zooniverse_id)+"',"+str(blank)+")"
    # serengeti_cursor.execute("insert into classifications (h,user_name,zooniverse_id,blank) values (" + str(h) +",'"+user_name+"','"+str(zooniverse_id)+"',"+str(blank)+")")
    serengeti_cursor.execute("insert into classifications (zooniverse_id,blank,created_at) values ('"+str(zooniverse_id)+"',"+str(blank)+",'" + str(created_at) + "')")
    if (i% 10000 == 0) and (i > 0):
        print i
        serengeti_conn.commit()
serengeti_conn.commit()

# mico_cur.execute("select * from subjects where mico_status = 'finished' limit 100")
#
# for c in mico_cur.fetchall():
#     zooniverse_id = c[1]
#     mico_results = c[7]
#
#     mico_blank =  mico_results["objects"] == []
#
#     if c[11] == "consensus_blank":
#         print "**"
#     actually_blank = c[11] == "blank"
#
#     serengeti_cursor.execute("select blank from classifications where zooniverse_id = '" + zooniverse_id +"'")
#     print serengeti_cursor.fetchall()
