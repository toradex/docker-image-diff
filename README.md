# docker-image-diff

Small POC for the idea of generating a "diff" container, minimizing differences between a base image and an update.

## The issue

Docker takes a quite conservative approach when generating layers, so the exact same command executed in a different context (not rebuilding same dockerfile) creates a new layer.
This makes sense since running, for example, apt-get may lead to a different result when running at a different time (debian repo may have been updated in the meantime).
Same happens if you run commands on different machines or you pruned your system.
Our IDE extensions use template that re-generate dockerfiles on the fly and also have COPY/ADD statements that include whole folders. A single file changed in the folder would mean a completely new layer.
Having control of the dockerfile you may split COPY/ADD statements into multiple ones, putting files you change less frequently first, but still you will probably ship more than you need...

## The idea

Images can be exported as tar.gz with all the layers (docker save/load commands), this will be in OCI format with manifest and configuration files as json.
The tool can compare two images, check up to which layer they are the same, and then generate files for the layers that are different.
Then those can be compared, removing files that are not changed from base to updated image, keeping only the changed ones and a list of deleted entries.
We can also compare history, focusing on steps that don't generate a layer (those are covered by file comparison) and export additional commands (ENV, CMD, ENTRYPOINT etc.) that change the environment, but not the files.
In this way we may have a diff set (files) and some docker commands (deleted files/folders and additional commands) that could be used to generate a new image (by generating a dockerfile and tar.gz of the files to be added for new layers).
By building this image we could have an image that when pulled from docker hub on a system that already has the base one will pull the minimum set of files.

## How this can work for customers?

if customer has:

- my-image:base (what's running on the devices)
- my-image:update (what he just built)

he can generate:

- my-image-diff (with only the real changes)

and ship it to the devices, making it the new my-image:base for the next time the tool will run.

## How to build the tool

The tool must run from a container, to build it just run:

```
docker build -t docker-image-diff .
```

## How to run the tool

To run the tool you can start the container. Remember to share the docker socket to allow it to access local docker instance.

```
docker run -it --rm -v /var/run/docker.sock:/var/run/docker.sock docker-image-diff:latest
```

Running the tool with no arguments will show an help message.

You can generate an update image by running the tool in this way (--verbose will provide some information during the different phases of the comparison):

```
docker run -it --rm -v /var/run/docker.sock:/var/run/docker.sock docker-image-diff:latest --verbose node:16.2.0-buster node:16.3.0-buster node:16.2.0-to-16.3.0
```

Now you can run your new image and check that it actually runs node 16.3:

```
docker run -it --rm node:16.2.0-to-16.3.0
```

By default the tool will use images for the current achitecture, if you want to generate images for a different one, use the --platform command line switch:

```
docker run -it --rm -v /var/run/docker.sock:/var/run/docker.sock docker-image-diff:latest --verbose --platform linux-arm node:16.2.0-buster node:16.3.0-buster node:16.2.0-to-16.3.0
```

The tool will fail if the generated image is larger than a regular download of update image. You can change this behavior using --accept-bigger command line switch.

## Debugging with vscode

Just open the folder, VS will ask you if you want to open it in a container, reply yes and you'll be ready to run and debug the tool.

## Testing

Tests use BATS framework and can be executed using bash.

```
cd tests/integrations
. ./setup.sh
./run.sh
```

## Limitations

Docker supports at most 128 layers, adding too many may slow down access to files, since overlayfs will have to check multiple folders.
We may add some "intelligence" to the tool so it could determine:
- if it's worth generating a diff image (maybe that won't save much compare to the update image)
- if image has too many layers (time to think about a big update)

