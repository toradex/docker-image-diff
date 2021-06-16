load 'bats/bats-support/load.bash'
load 'bats/bats-assert/load.bash'
load 'bats/bats-file/load.bash'


setup_file() {
    export DID_CMD="docker run -v /var/run/docker.sock:/var/run/docker.sock -it $DID_IMAGE_NAME --verbose"

    export OLD_NODE=16.2.0-buster
    export NEW_NODE=16.3.0-buster
    export DIFF_TAG=$OLD_NODE-to-$NEW_NODE
}

prepare_for_comparison() {

    if [ -z "$4" ]; then
        CONTAINER1=$(docker create $1:$2)
        CONTAINER2=$(docker create $1:$3)
    else
        CONTAINER1=$(docker create --platform $4 $1:$2)
        CONTAINER2=$(docker create --platform $4 $1:$3)
    fi

    docker export $CONTAINER1 > $DID_TEMP_DIR/$2.tar
    docker export $CONTAINER2 > $DID_TEMP_DIR/$3.tar

    docker rm $CONTAINER1
    docker rm $CONTAINER2

    rm -rf $DID_TEMP_DIR/$2
    rm -rf $DID_TEMP_DIR/$3

    mkdir -p $DID_TEMP_DIR/$2
    mkdir -p $DID_TEMP_DIR/$3

    tar -xf $DID_TEMP_DIR/$2.tar -C $DID_TEMP_DIR/$2
    tar -xf  $DID_TEMP_DIR/$3.tar -C $DID_TEMP_DIR/$3
}

@test "docker-image-diff: node js test" {
    OLD_NODE=16.2.0-buster
    NEW_NODE=16.3.0-buster
    DIFF_TAG=$OLD_NODE-to-$NEW_NODE

    run $DID_CMD "node:$OLD_NODE" "node:$NEW_NODE" "node:$DIFF_TAG"
    assert_success

    prepare_for_comparison node $NEW_NODE $DIFF_TAG

    run diff -r $DID_TEMP_DIR/$NEW_NODE $DID_TEMP_DIR/$DIFF_TAG
    assert_success
}

@test "docker-image-diff: no pull" {
    run $DID_CMD --no-pull "node:$OLD_NODE" "node:$NEW_NODE" "node:$DIFF_TAG"
    assert_success

    prepare_for_comparison node $NEW_NODE $DIFF_TAG

    run diff -r $DID_TEMP_DIR/$NEW_NODE $DID_TEMP_DIR/$DIFF_TAG
    assert_success
}

@test "docker-image-diff: arm" {
    run $DID_CMD --platform=linux/arm "node:$OLD_NODE" "node:$NEW_NODE" "node:$DIFF_TAG"
    assert_success

    prepare_for_comparison node $NEW_NODE $DIFF_TAG linux/arm

    run diff -r $DID_TEMP_DIR/$NEW_NODE $DID_TEMP_DIR/$DIFF_TAG
    assert_success
}

@test "docker-image-diff: arm64" {
    run $DID_CMD --platform=linux/arm64 "node:$OLD_NODE" "node:$NEW_NODE" "node:$DIFF_TAG"
    assert_success

    prepare_for_comparison node $NEW_NODE $DIFF_TAG linux/arm64

    run diff -r $DID_TEMP_DIR/$NEW_NODE $DID_TEMP_DIR/$DIFF_TAG
    assert_success
}

function teardown_file() {
    docker rmi node:$OLD_NODE
    docker rmi node:$NEW_NODE
    docker rmi node:$DIFF_TAG
    docker system prune -f
}
