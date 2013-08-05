#!/usr/bin/python
import json
import gzip
import csv
import glob
import os
import subprocess
import re
import urllib,urllib2
from datetime import datetime
from distutils.version import LooseVersion

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

if len(new_releases) > 0:
    # add new release using middleware api
    sorted_new_releases = sorted(new_releases, key = lambda x: LooseVersion(x[1]))
    for release in sorted_new_releases:
        # set build id to current datetime if wrongly provided
        if re.match('^\d{10,14}$', release[2]):
            build_id = release[2]
        else:
            build_id = datetime.now().strftime("%Y%m%d%H%M%S")
        urllib2.urlopen("%s/products/builds/product/%s/version/%s/platform/Windows/build_id/%s/build_type/Release/repository/release" % (config.middleware_url, release[0], release[1], build_id), data="")

    # set featured release
    sorted_saved_release = sorted(saved_releases, key = lambda x: LooseVersion(x[1]))
    max_saved_release = ("", "0", "")
    if len(sorted_saved_release) > 0:
        max_saved_release = sorted_saved_release[-1]
    max_new_release = sorted_new_releases[-1]
    if LooseVersion(max_new_release[1]) > LooseVersion(max_saved_release[1]):
        opener = urllib2.build_opener(urllib2.HTTPHandler)
        request = urllib2.Request("%s/releases/featured/" % config.middleware_url, data=urllib.urlencode({max_new_release[0]: max_new_release[1]}))
        request.get_method = lambda: 'PUT'
        opener.open(request)

    # save releases_csv
    try:
        with open(config.releases_csv, "wb") as csvfile:
            csvwriter = csv.writer(csvfile)
            for row in sorted(new_releases | saved_releases, key=lambda x: LooseVersion(x[1])):
                csvwriter.writerow(row)
    except IOError:
        print "error writing releases_csv"
        pass

subprocess.call(["python", os.path.join(this_dir, "symsrv-fetch.py")])

os.utime(timestamp, (most_recent, most_recent))
