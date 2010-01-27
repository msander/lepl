#!/bin/bash

RELEASE=`egrep "version=" setup.py | sed -e "s/.*'\(.*\)'.*/\\1/"`
VERSION=`echo $RELEASE | sed -e "s/.*?\([0-9]\.[0-9]\).*/\\1/"`

sed -i -e "s/release = .*/release = '$RELEASE'/" doc-src/conf.py
sed -i -e "s/version = .*/version = '$VERSION'/" doc-src/conf.py

sed -i -e "s/__version__ = .*/__version__ = '$RELEASE'/" src/lepl/__init__.py

rm -fr doc

pushd doc-src
./index.sh
popd

sphinx-build -b html doc-src/ doc

# this is a bit of a hack, but people want to jump directly to the text
# so we skip the contents
pushd doc
sed -i -e 's/href="intro.html"/href="intro-1.html"/' index.html
sed -i -e 's/A Tutorial for LEPL/Tutorial Contents/' intro-1.html
popd

epydoc -v -o doc/api --html --graph=all --docformat=restructuredtext -v --exclude="_experiment" --exclude="_performance" --exclude="_example" --debug src/*

