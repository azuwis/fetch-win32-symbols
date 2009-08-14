#
# This script will read a feed of crash reports from Socorro, and try to retrieve
# missing symbols from Microsoft's symbol server. It honors a blacklist
# (blacklist.txt) of symbols that are known to be from our applications,
# and it maintains its own list of symbols that the MS symbol server
# doesn't have (skiplist.txt).
#
# The script must have installed alongside it:
# * msdia80.dll (from the DIA SDK, installed with Visual C++ 8)
# * dbghelp.dll (from WinDBG)
# * symsrv.dll  (also from WinDBG)
# * symsrv.yes  (a zero-byte file that indicates that you've accepted
#                the Microsoft symbol server EULA)
# * config.py   (create this from the template in config.py.in)
#
# The script also depends on having write access to the directory it is
# installed in, to write the skiplist text file.
#
# Finally, you must have 'zip' (Info-Zip), 'scp', and 'ssh' available in %PATH%.

import config
import sys
import os
import time, datetime
import subprocess
import feedparser
import StringIO
import gzip
import shutil
from collections import defaultdict
from tempfile import mkdtemp
from urllib import urlopen

try:
  import simplejson as json
except ImportError:
  import json

# Just hardcoded here
MICROSOFT_SYMBOL_SERVER = "http://msdl.microsoft.com/download/symbols"

verbose = False

if len(sys.argv) > 1 and sys.argv[1] == "-v":
  verbose = True

# Symbols that we know belong to us, so don't ask Microsoft for them.
blacklist=set()
try:
  bf = file('blacklist.txt', 'r')
  for line in bf:
      blacklist.add(line.strip())
  bf.close()
except IOError:
  pass

# Symbols that we've asked for in the past unsuccessfully
skiplist={}
try:
  sf = file('skiplist.txt', 'r')
  for line in sf:
      line = line.strip()
      if line == '':
          continue
      (debug_id, debug_file) = line.split(None, 1)
      skiplist[debug_id] = debug_file
  sf.close()
except IOError:
  pass

if verbose:
  print "Loading feed URL..."

try:
  f = feedparser.parse(config.feed_url)
except IOError:
  print >>sys.stderr, "Failed to parse feed from %s" % config.feed_url
  sys.exit(1)

modules = defaultdict(set)
symbol_path = mkdtemp()
if verbose:
  print "Parsing reports JSON... (x%d)" % len(f.entries)
# For each crash report in the feed, find the JSON file and parse it,
# then parse the module list from that data.
for e in f.entries:
  for l in e.links:
    if l.type == 'application/x-gzip':
      # parse l.href, read modules into modules
      try:
        u = urlopen(l.href)
        data = u.read()
        u.close()
        data = gzip.GzipFile(fileobj=StringIO.StringIO(data)).read()
        j = json.loads(data)
        u.close()
        for l in j['dump'].split('\n'):
          if l.startswith("Module|"):
            (debugfile, debugid) = l.split('|')[3:5]
            if debugfile and debugid:
              modules[debugfile].add(debugid)
      except IOError:
        pass

if verbose:
  print "Fetching symbols..."
# Now try to fetch all the unknown modules from the symbol server
for filename, ids in modules.iteritems():
  if filename in blacklist:
    # This is one of our our debug files from Firefox/Thunderbird/etc
    continue
  for id in ids:
    if id in skiplist and skiplist[id] == filename:
      # We've asked the symbol server previously about this, so skip it.
      continue
    sym_file = os.path.join(symbol_path, filename, id,
                            filename.replace(".pdb","") + ".sym")
    if os.path.exists(sym_file):
      # We already have this symbol
      continue
    if config.read_only_symbol_path != '' and \
       os.path.exists(os.path.join(config.read_only_symbol_path, filename, id,
                                   filename.replace(".pdb","") + ".sym")):
      # We already have this symbol
      continue
    # Not in the blacklist, skiplist, and we don't already have it, so
    # ask the symbol server for it.
    # This expects that symsrv_convert.exe and all its dependencies
    # are in the current directory.

    # Sometimes we get non-ascii in here. This is definitely not
    # correct, but it should at least stop us from throwing.
    filename = filename.encode('ascii', 'replace')
    if not verbose:
      stdout = open("NUL","w")
    else:
      stdout = None
      print "fetching %s %s" % (filename, id)
    rv = subprocess.call(["symsrv_convert.exe",
                          MICROSOFT_SYMBOL_SERVER,
                          symbol_path,
                          filename,
                          id],
                         stdout = stdout,
                         stderr = subprocess.STDOUT)
    # Return code of 2 or higher is an error
    if rv >= 2:
      skiplist[id] = filename
    # Otherwise we just assume it was written out, not much we can do
    # if it wasn't. We'll try again next time we see it anyway.

if len(os.listdir(symbol_path)) == 0:
  if verbose:
    print "No symbols downloaded!"
  sys.exit(0)

try:
  zipfile = os.path.join(os.path.dirname(symbol_path), "symbols.zip")
  if verbose:
    print "Zipping symbols..."
  subprocess.check_call(["zip", "-r9", zipfile, "*"],
                        cwd = symbol_path,
                        stdout = open("NUL","w"),
                        stderr = subprocess.STDOUT)
  if verbose:
    print "Uploading symbols..."

  def msyspath(path):
    "Translate Windows path |path| into an MSYS path"
    path = os.path.abspath(path)
    return "/" + path[0] + path[2:].replace("\\", "/")

  subprocess.check_call(["scp", "-i", msyspath(config.symbol_privkey),
                         msyspath(zipfile),
                         "%s@%s:%s" % (config.symbol_user,
                                       config.symbol_host,
                                       config.symbol_path)],
                        stdout = open("NUL","w"),
                        stderr = subprocess.STDOUT)
  if verbose:
    print "Unpacking symbols on remote host..."
  subprocess.check_call(["ssh", "-i", msyspath(config.symbol_privkey),
                         "-l", config.symbol_user, config.symbol_host,
                         "cd %s && unzip -o symbols.zip && rm -v symbols.zip" % config.symbol_path],
                        stdout = open("NUL","w"),
                        stderr = subprocess.STDOUT)
except Exception, ex:
  print "Error zipping or uploading symbols: ", ex
finally:
  if os.path.exists(zipfile):
    os.remove(zipfile)
  shutil.rmtree(symbol_path, True)
  pass

# Write out our new skip list
try:
  sf = file('skiplist.txt', 'w')
  for (debug_id,debug_file) in skiplist.iteritems():
      sf.write("%s %s\n" % (debug_id, debug_file))
  sf.close()
except IOError:
  print >>sys.stderr, "Error writing skiplist.txt"

if verbose:
  print "Done!"
