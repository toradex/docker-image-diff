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

## Current state

ATM the POC extract file differences and dockerfile.
The files are not usable to generate input for an ADD statement, since there are broken symlinks and wrong user rights.
This is due to my usage of python's own tar lib, that doesn't care about those things... using tar cmd line (as we do for TCB) should fix that.
The tool also need to run as root (to be able to access files, change attributes, ownership etc.), this can be solved by containerizing it.
The script will run as root and access local docker via shared socket.
User can launch the container providing base-image (tag or sha), update image and output image.

## Limitations

Docker supports at most 128 layers, adding too many may slow down access to files, since overlayfs will have to check multiple folders.
We may add some "intelligence" to the tool so it could determine:
- if it's worth generating a diff image (maybe that won't save much compare to the update image)
- if image has too many layers (time to think about a big update)

## Others

Balena has an approach that uses full image diffs. This would probably lead to smaller downloads but will require an ad-hoc client and will generate "monolithic" images so requirements in terms of storage space and memory on the device will increase.
Our approach would probably lead to slightly bigger updates (no sub-file diffs), but keep storage/RAM usage at the same level as "normal" updates.
People can solve this manually, basically by generating their own update layers and adding COPY/ADD statements at the end of their dockerfiles. This will require a lot of manual work and will also lead to lots of overwrites between the layers (every time you update a file) that aren't probably good for storage usage and performances.
Since this approach work at the OCI image level it may work also with other container runtimes.
