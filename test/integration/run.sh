#!/bin/bash

BASE_DIR=$PWD
WORK_DIR=$PWD/workdir
TESTCASES_DIR=$BASE_DIR/testcases

REPORT_DIR=$WORK_DIR/reports
REPORT_FILE=$REPORT_DIR/$(date +"%Y%02m%02d%H%M%S").log

TESTCASES="\
$TESTCASES_DIR/tests.bats \
"

# BATS command
BATS_BIN="./bats/bats-core/bin/bats"
BATS_ERRORS_COUNT=0

set -o pipefail

print_message() {
    if [ "$DID_REPORT" = "1" ]; then
        echo $1 >> $REPORT_FILE
    fi
    echo $1
}

run_tests() {
    if [ "$DID_REPORT" = "1" ]; then
        $BATS_BIN --timing $@ 2>&1 | tee -a $REPORT_FILE
    else
        $BATS_BIN --timing $@
    fi
    if [ ! "$?" -eq "0" ]; then
        BATS_ERRORS_COUNT=$(expr $BATS_ERRORS_COUNT + 1)
    fi
}


if [ -z "$DID_IMAGE_NAME" ]; then
    export DID_IMAGE_NAME="docker-image-diff:latest"
fi

# check if setup.sh was sourced.
if [ -z "$DID_SETUP_LAUNCHED" ]; then
    print_message "Error: setup.sh was not sourced. Please execute 'source setup.sh' before running the test cases."
    exit 1
fi


mkdir -p $REPORT_DIR
export DID_TEMP_DIR=$WORK_DIR/temp

# prepare tests
cd $WORK_DIR

rm -fR $DID_TEMP_DIR
mkdir -p $DID_TEMP_DIR

run_tests $TESTCASES

if [ "$DID_REPORT" = "1" ]; then
    echo "Test report available in $REPORT_FILE"
fi

RETCODE=0

if [ "$BATS_ERRORS_COUNT" -eq "0" ]; then
    print_message "Integration test completed successfully"
else
    print_message "$BATS_ERRORS_COUNT test(s) failed."
    RETCODE=$BATS_ERRORS_COUNT
fi

cd $BASE_DIR
exit $RETCODE


