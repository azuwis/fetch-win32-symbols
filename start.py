#!/usr/bin/python
import json
import gzip
import csv
import glob
import os
import subprocess
from datetime import datetime

import config

this_dir = os.path.dirname(__file__)
timestamp = os.path.join(this_dir, "timestamp")

open(config.csv_url, "w").close()

if not os.path.exists(timestamp):
    open(timestamp, "wa").close()
    last_processed = 0
else:
    last_processed = os.path.getmtime(timestamp)

most_recent = last_processed

jsonzs = glob.glob("%s/%s*/name/*/*/*.jsonz" % (config.processed_crash, datetime.now().strftime("%Y%m")))

for jsonz in jsonzs:
    this_mtime = os.path.getmtime(jsonz)
    if this_mtime <= last_processed:
        continue
    if this_mtime > most_recent:
        most_recent = this_mtime
    dump = json.load(gzip.open(jsonz))["dump"].split("\n")
    reader = csv.reader(dump, delimiter='|', quoting=csv.QUOTE_NONE)
    with open(config.csv_url, "wb") as csvfile:
        csvwriter = csv.writer(csvfile, quoting=csv.QUOTE_NONE)
        for row in reader:
            if (len(row) > 4 and row[0] == "Module"):
                csvwriter.writerow([row[1], row[3], row[4]])

subprocess.call(["python", os.path.join(this_dir, "symsrv-fetch.py")])

os.utime(timestamp, (most_recent, most_recent))
