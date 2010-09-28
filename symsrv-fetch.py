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
import StringIO
import gzip
import shutil
import ctypes
from collections import defaultdict
from tempfile import mkdtemp
from urllib import urlopen

# Just hardcoded here
MICROSOFT_SYMBOL_SERVER = "http://msdl.microsoft.com/download/symbols"

verbose = False

if len(sys.argv) > 1 and sys.argv[1] == "-v":
  verbose = True

logfile = open(os.path.join(os.path.dirname(__file__), "symsrv-fetch.log"),
               "a")
def log(msg):
  logfile.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg + "\n")

log("Started")

# Symbols that we know belong to us, so don't ask Microsoft for them.
blacklist=set()
try:
  bf = file('blacklist.txt', 'r')
  for line in bf:
      blacklist.add(line.strip().lower())
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
      s = line.split(None, 1)
      if len(s) != 2:
        continue
      (debug_id, debug_file) = s
      skiplist[debug_id] = debug_file.lower()
  sf.close()
except IOError:
  pass

modules = defaultdict(set)
if verbose:
  print "Loading module list URL..."
try:
  date = (datetime.date.today() - datetime.timedelta(1)).strftime("%Y%m%d")
  url = config.csv_url % {'date': date}
  for line in urlopen(url).readlines():
    line = line.rstrip()
    bits = line.split(',')
    if len(bits) != 3:
      continue
    dll, pdb, uuid = bits
    modules[pdb].add(uuid)
except IOError, e:
  log("Error fetching: %s" % e)
  sys.exit(1)

symbol_path = mkdtemp(dir=config.temp_dir)

if verbose:
  print "Fetching symbols..."
total = sum(len(ids) for ids in modules.values())
current = 0
# Now try to fetch all the unknown modules from the symbol server
for filename, ids in modules.iteritems():
  # Sometimes we get non-ascii in here. This is definitely not
  # correct, but it should at least stop us from throwing.
  filename = filename.encode('ascii', 'replace')

  if filename.lower() in blacklist:
    # This is one of our our debug files from Firefox/Thunderbird/etc
    current += len(ids)
    continue
  for id in ids:
    current += 1
    if verbose:
      sys.stdout.write("[%6d/%6d] %3d%% %-20s\r" % (current, total,
                                                    int(100 * current / total),
                                                    filename[:20]))
    if id in skiplist and skiplist[id] == filename.lower():
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
    stdout = open("NUL","w")
    proc = subprocess.Popen(["symsrv_convert.exe",
                             MICROSOFT_SYMBOL_SERVER,
                             symbol_path,
                             filename,
                             id],
                            stdout = stdout,
                            stderr = subprocess.STDOUT)
    # kind of lame, want to prevent it from running too long
    start = time.time()
    # 30 seconds should be more than enough time
    while proc.poll() is None and (time.time() - start) < 30:
      time.sleep(1)
    if proc.poll() is None:
      # kill it, it's been too long
      ctypes.windll.kernel32.TerminateProcess(int(proc._handle), -1)
    # Return code of 2 or higher is an error
    elif proc.returncode >= 2:
      skiplist[id] = filename
    # Otherwise we just assume it was written out, not much we can do
    # if it wasn't. We'll try again next time we see it anyway.

if verbose:
  sys.stdout.write("\n")

if len(os.listdir(symbol_path)) == 0:
  if verbose:
    print "No symbols downloaded!"
  log("No symbols downloaded")
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
                         "cd %s && unzip -n symbols.zip; rm -v symbols.zip" % config.symbol_path],
                        stdout = open("NUL","w"),
                        stderr = subprocess.STDOUT)
except Exception, ex:
  print "Error zipping or uploading symbols: ", ex
finally:
  if os.path.exists(zipfile):
    os.remove(zipfile)
  shutil.rmtree(symbol_path, True)

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
log("Finished, exiting")
