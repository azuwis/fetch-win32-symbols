#!/bin/bash

# apt-get install wine cabextract curl
# wget http://google-breakpad.googlecode.com/svn/trunk/src/tools/windows/binaries/dump_syms.exe
# wine regsvr32 msdia80.dll

SYMSVR="$1"
SYMPATH="$2"
PDB="$3"
ID="$4"

EXECDIR=`dirname $0`

PDBDIR="$PDB/$ID"
PD_="${PDB/%pdb/pd_}"
FPD_="$SYMPATH/$PDBDIR/$PD_"

mkdir -p "$SYMPATH/$PDBDIR"

curl --silent --fail --location --user-agent "Microsoft-Symbol-Server/6.2.9200.16384" --output "$FPD_" "$SYMSVR/$PDBDIR/$PD_"

if [ -e "$FPD_" -a $(file --brief --mime-type "$FPD_") == "application/vnd.ms-cab-compressed" ]; then
	cabextract -q -d "$SYMPATH/$PDBDIR" "$FPD_"
	wine $EXECDIR/dump_syms.exe "$SYMPATH/$PDBDIR/$PDB" > "$SYMPATH/$PDBDIR/${PDB/%pdb/sym}"
else
	rmdir --ignore-fail-on-non-empty --parents "$SYMPATH/$PDBDIR"
	exit 1
fi
