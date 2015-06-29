#!/usr/bin/env python
__author__ = 'greg'
import os
import psycopg2
import sys
from postgres_aggregation import PanoptesAPI
import csv
import matplotlib.pyplot as plt
import numpy as np
import datetime

if os.path.isdir("/home/greg"):
    baseDir = "/home/greg/"
else:
    baseDir = "/home/ggdhines/"


#stargazing = PanoptesAPI()
#stargazing.__yield_classifications__()
# stargazing.__find_user__("rjsmethurst")
# print
# stargazing.__find_user__("vrooje")
# print
# stargazing.__find_user__("mrniaboc")
# print
# #stargazing.__find_user__("DrRogg")
# # print
#stargazing.__find_user__("astopy")
# print
#assert False


sys.path.append(baseDir+"github/pyIBCC/python")
import ibcc

conn = psycopg2.connect("dbname = 'supernova' host='localhost' user = 'panoptes' password='password'")

cur = conn.cursor()

select = "SELECT * FROM users where email = 'fang.yuan@anu.edu.au'"
cur.execute(select)
print cur.fetchall()


select = "SELECT id,classifications_count FROM users where display_name = 'mrniaboc'"
print select
cur.execute(select)
r = cur.fetchall()[0]
expert_id = r[0]
count = r[1]
print expert_id,count

select = "SELECT id,classifications_count FROM users where display_name = 'vrooje'"
print select
cur.execute(select)
r = cur.fetchall()[0]
expert_id = r[0]
count = r[1]
print expert_id,count

select = "SELECT id,classifications_count FROM users where display_name = 'astopy'"
print select
cur.execute(select)
r = cur.fetchall()[0]
expert_id = r[0]
count = r[1]
print expert_id,count


#cur.execute("CREATE INDEX subject_index ON classifications (Subject_ids)")
#conn.commit()
#print "made index"
select = "SELECT user_id,user_ip,subject_ids,annotations,Created_at from classifications where user_id = " + str(expert_id)
# select = "SELECT user_id,user_ip,subject_ids,annotations,Created_at from classifications where user_id is not null order by subject_ids"
print select
cur.execute(select)
print "found " + str(len(cur.fetchall()))
#cur.execute("SELECT user_id,user_ip,subject_ids,annotations,Created_at from classifications")
# for r in cur.fetchall():
#     print r
#     break
#
# assert False


user_ids = []
classification_counts = []
current_subject_id = None
subject_index = -1

questions = ['centered_in_crosshairs','subtracted','circular','centered_in_host']
question_index = 1
gold_set = set()
select = "SELECT user_id,user_ip,subject_ids,annotations,Created_at from classifications  order by subject_ids" #where user_id is not null
cur.execute(select)
print select
with open(baseDir+"Databases/supernova_ibcc.csv","wb") as f, open(baseDir+"Databases/supernova_ibcc_gold.csv","wb") as f_gold:
    f.write("a,b,c\n")
    f_gold.write("a,b\n")
    for ii,r in enumerate(cur.fetchall()):

        if (len(r[3]) < (question_index+1)) or (r[3][question_index]["task"] != questions[question_index]):
            continue
        else:
            ann = r[3][question_index]["value"]
        if not(ann in [0,1]):
            print "skipping"
            continue

        user_id = r[0]
        if not(r[0] is None):
            user_id = r[0]
        else:
            continue

        # #if we want to look at users who have not logged in
        # if r[0] is None:
        #     user_id = r[1]
        # else:
        #     continue

        subject_id = r[2][0]

        if not(subject_id == current_subject_id):
            current_subject_id = subject_id
            subject_index += 1

        if (user_id in [10]) and (r[4] >= datetime.datetime(2015,3,19,18)):
            gold_set.add(subject_id)
            #f_gold.write(str(subject_index)+","+str(ann)+"\n")

        else:
            assert subject_index >= 0

            try:
                user_index = user_ids.index(user_id)
            except ValueError:
                user_ids.append(user_id)
                user_index = len(user_ids)-1
                classification_counts.append([0,0])

            classification_counts[user_index][ann] += 1

            assert user_index >= 0


            f.write(str(user_index)+","+str(subject_index)+","+str(ann)+"\n")

print "number of users " + str(len(user_ids))
print "number of gold labels " + str(len(list(gold_set)))
with open(baseDir+"Databases/supernova_ibcc.py",'wb') as f:
    f.write("import numpy as np\nscores = np.array([0,1])\n")
    f.write("nScores = len(scores)\n")
    f.write("nClasses =2\n")
    f.write("inputFile = '"+baseDir+"Databases/supernova_ibcc.csv'\n")
    f.write("outputFile =  '"+baseDir+"Databases/supernova_ibcc.out'\n")
    f.write("confMatFile = '"+baseDir+"Databases/supernova_ibcc.mat'\n")
    f.write("goldFile = '"+baseDir+"Databases/supernova_ibcc_gold.csv'\n")

os.remove(baseDir+"Databases/supernova_ibcc.csv.dat")

ibcc.runIbcc(baseDir+"Databases/supernova_ibcc.py")
print "done IBCC"
x_values = []
y_values = []
with open(baseDir+"Databases/supernova_ibcc.mat","rb") as f:
    reader = csv.reader(f,delimiter=" ")
    for user_index,r in enumerate(reader):
        count = classification_counts[user_index]

        if min(count) < 5:
            continue

        x = float(r[0])
        y = float(r[-1])

        x_values.append(x)
        y_values.append(y)

        plt.plot(x,y,'o',color="blue")

mean_x = np.mean(x_values)
mean_y = np.mean(y_values)
print mean_x,mean_y
plt.plot([0.5,0.5],[0,1],"--",color="red")
plt.plot([0,1],[0.5,0.5],"--",color="red")

plt.plot([mean_x,mean_x],[0,1],"-.",color="green")
plt.plot([0,1],[mean_y,mean_y],"-.",color="green")

plt.xlabel("% of positive examples correctly identified")
plt.ylabel("% of negative examples correctly identified")
plt.show()