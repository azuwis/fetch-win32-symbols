#!/usr/bin/python
import json
import gzip
import csv
import glob
import os
import subprocess
import re
from datetime import datetime

import config

this_dir = os.path.dirname(__file__)
timestamp = os.path.join(this_dir, "timestamp")

# reset symbols csv file
open(config.csv_url, "w").close()

if not os.path.exists(timestamp):
    open(timestamp, "wa").close()
    last_processed = 0
else:
    last_processed = os.path.getmtime(timestamp)

most_recent = last_processed

# glob .jsonz of the current month
jsonzs = glob.glob("%s/%s*/name/*/*/*.jsonz" % (config.processed_crash, datetime.now().strftime("%Y%m")))

saved_releases=set()
generated_releases=set()
new_releases=set()

# load releases_csv into saved_releases
try:
    with open(config.releases_csv, "rb") as csvfile:
        csvreader = csv.reader(csvfile)
        for row in csvreader:
            saved_releases.add(tuple(row))
except IOError:
    pass

with open(config.csv_url, "wb") as csvfile:
    csvwriter = csv.writer(csvfile, quoting=csv.QUOTE_NONE)
    # parse all new jsonz, and save modules to csv file
    for jsonz in jsonzs:
        this_mtime = os.path.getmtime(jsonz)
        if this_mtime <= last_processed:
            continue
        if this_mtime > most_recent:
            most_recent = this_mtime
        crash = json.load(gzip.open(jsonz))

        product = crash["product"]
        version = crash["version"]
        build = crash["build"]
        # check if product exist in config.versions and version matched
        if (product in config.versions.keys() and re.match(config.versions[product], version)):
            generated_releases.add((product, version, build))

        dump = crash["dump"].split("\n")
        reader = csv.reader(dump, delimiter='|', quoting=csv.QUOTE_NONE)
        for row in reader:
            if (len(row) > 4 and row[0] == "Module"):
                csvwriter.writerow([row[1], row[3], row[4]])

new_releases = generated_releases - saved_releases

# add new releases to releases_csv
try:
    with open(config.releases_csv, "wb") as csvfile:
        csvwriter = csv.writer(csvfile)
        for row in new_releases | saved_releases:
            csvwriter.writerow(row)
except IOError:
    print "error writing releases_csv"
    pass

subprocess.call(["python", os.path.join(this_dir, "symsrv-fetch.py")])

os.utime(timestamp, (most_recent, most_recent))
