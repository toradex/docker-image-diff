"""This tool can be used to reduce the size of docker image updates.

It will compare a base image and a target one and generate 3rd image with the minimal set of
changes required to move from base to final image.
"""
import argparse
import filecmp
import json
import logging
import os
import sys
import shlex
import shutil
import tarfile
from typing import Any, List, Optional, Tuple
import docker
import docker.client
import docker.models.images
from quantiphy import Quantity

def split_tag(imagename: str) -> Tuple[str,Optional[str]]:
    """Split a tag string into repository and tag parts."""
    parts = imagename.split(":")

    tag:Optional[str]

    if len(parts) > 1:
        repository = ":".join(parts[:-1])
        tag = parts[-1:][0]
    else:
        repository = imagename
        tag = None

    return repository,tag


def save_image(
    image: docker.models.images.Image,
    name:str,
    folder: str) -> str:
    """Extract docker image contents in a folder."""
    tarpath=os.path.join(folder,name+".tar")

    if os.path.exists(tarpath):
        os.unlink(tarpath)

    with open(tarpath, 'wb') as output_file:
        image_data=image.save()
        for chunk in image_data:
            output_file.write(chunk)
        output_file.close()

    tarfolder=os.path.join(folder,name)

    if os.path.exists(tarfolder):
        shutil.rmtree(tarfolder)

    os.makedirs(tarfolder)

    with tarfile.open(name=tarpath) as tararchive:
        tararchive.extractall(tarfolder,numeric_owner=True)
    return tarfolder

def get_configuration(folder: str) -> Any:
    """Load image configuration from json manifest and config file."""
    manifestpath=os.path.join(folder,"manifest.json")

    with open(manifestpath) as manifest_file:
        manifest=json.load(manifest_file)

    configname=manifest[0]["Config"]
    configpath=os.path.join(folder,configname)

    with open(configpath) as config_file:
        return manifest[0],json.load(config_file)

def expand_layers(
    layers: List[str],
    folder: str,
    name: str) -> Tuple[str,int]:
    """Extract a sequence of layers and merge them in a folder."""
    size=0
    base_path=os.path.join(folder,name)
    layers_path=os.path.join(folder,name+"_layers")

    if os.path.exists(layers_path):
        shutil.rmtree(layers_path)

    os.makedirs(layers_path)

    for layer in layers:
        layertarpath=os.path.join(base_path,layer)
        size+=os.path.getsize(layertarpath)
        with tarfile.open(name=layertarpath) as tararchive:
            tararchive.extractall(layers_path,numeric_owner=True)

    return layers_path,size

def copy_element(source, destination) -> None:
    """Copy a file/folder."""
    if os.path.islink(source):
        shutil.copy(source,destination,follow_symlinks=False)
        logging.info(f"+l {source} {destination}")
    elif os.path.isdir(source):
        shutil.copytree(
            source,destination,symlinks=True,copy_function=os.link)
        logging.info(f"+d {source} {destination}")
    else:
        os.link(source,destination)
        logging.info(f"+f {source} {destination}")

def check_folder(dir: str):
    """Check if folder exists and if it doesn't create it."""
    if not os.path.exists(dir):
        os.makedirs(dir)

def process_folder(basepath,updatepath,output,missing_files,missing_dirs) -> None:
    """Generate update information for a specific folder.

    Compare two folders, create a folder with updates
    and lists for files and folders that should be deleted.
    It's called recursively on the different folders.
    """

    diff=filecmp.dircmp(basepath,updatepath,ignore=[])

    for obj in diff.right_only:
        source=os.path.join(updatepath,obj)
        destination=os.path.join(output,obj)

        check_folder(output)
        copy_element(source, destination)

    for obj in diff.left_only:
        source=os.path.join(basepath,obj)
        destination=os.path.join(output,obj)
        if os.path.isdir(source):
            missing_dirs.append(destination)
            logging.info(f"-d {destination}")
        else:
            missing_files.append(destination)
            logging.info(f"-f {destination}")

    for obj in diff.common_files:
        base=os.path.join(basepath,obj)
        update=os.path.join(updatepath,obj)
        destination=os.path.join(output,obj)

        if not filecmp.cmp(base,update,shallow=False):
            check_folder(output)
            os.link(update,destination)
            logging.info(f"+f {update} {destination}")

    for obj in diff.common_funny:
        base=os.path.join(basepath,obj)
        update=os.path.join(updatepath,obj)
        destination=os.path.join(output,obj)

        if os.path.isdir(base):
            missing_dirs.append(destination)
            logging.info(f"-d {destination}")
        else:
            if not os.path.islink(base):
                missing_files.append(destination)
                logging.info(f"-f {destination}")

        check_folder(output)
        copy_element(update,destination)

    for obj in diff.common_dirs:
        base=os.path.join(basepath,obj)
        update=os.path.join(updatepath,obj)
        destination=os.path.join(output,obj)

        process_folder(base,update,destination,missing_files,missing_dirs)

NOP_TAG="#(nop)"

if __name__ == "__main__":
    parser=argparse.ArgumentParser()

    parser.add_argument(
        "basetag",help="Base image")
    parser.add_argument(
        "updatetag",help="Image that is used to generate the update")
    parser.add_argument(
        "outputtag",help="Tag of the generated update image")
    parser.add_argument(
        "--platform",help="Container platform (use docker ones)",default=None,type=str)
    parser.add_argument(
        "--verbose", help="Show detailed output.", action="store_true",default=False)
    parser.add_argument(
        "--no-pull", help="Fails if images are not available locally.", action="store_true",default=False)
    parser.add_argument(
        "--accept-bigger", help="Don't fail if the generated image will be larger than the update one.", action="store_true",default=False)
    parser.add_argument(
        "--max-layers", help="Maximum number of layers in the generated image.", type=int,default=128)
    parser.add_argument(
        "--keep-temp", help="Don't remove temporary folder (useful for debugging).", action="store_true",default=False)
    parser.add_argument(
        "--output-folder",help="Output folder",default="/out",type=str)

    args=parser.parse_args()

    if args.verbose:
        level=logging.INFO
    else:
        level=logging.WARN

    logging.basicConfig(level=level,format="%(levelname)s - %(message)s",stream=sys.stdout)

    docker=docker.from_env()

    baserepository,basetag=split_tag(args.basetag)
    updaterepository,updatetag=split_tag(args.updatetag)

    if args.no_pull:
        baseimg=docker.images.get(args.basetag)
        updateimg=docker.images.get(args.updatetag)
    else:
        logging.info(f"Pulling {args.basetag}...")
        baseimg=docker.images.pull(baserepository,tag=basetag,platform=args.platform)
        logging.info(f"Pulling {args.updatetag}...")
        updateimg=docker.images.pull(updaterepository,tag=updatetag,platform=args.platform)

    outputfolder=args.output_folder

    if not os.path.exists(outputfolder):
        os.makedirs(outputfolder)
    elif not os.path.isdir(outputfolder):
        logging.error("Outputdir must be a valid folder path.")
        sys.exit(-1)

    tempfolder=os.path.join(outputfolder,"temp")

    if not os.path.exists(tempfolder):
        os.makedirs(tempfolder)

    logging.info(f"Saving base image {baseimg.id}...")
    basefolder=save_image(baseimg,"base",tempfolder)
    logging.info(f"Saving update image {updateimg.id}...")
    updatefolder=save_image(updateimg,"update",tempfolder)

    logging.info(f"Comparing configuration to find common layers...")
    basemanifest,baseconfig=get_configuration(basefolder)

    if baseconfig["rootfs"]["type"] != "layers":
        logging.error("base image does not use layers.")
        sys.exit(-1)

    updatemanifest,updateconfig=get_configuration(updatefolder)

    if updateconfig["rootfs"]["type"] != "layers":
        logging.error("update image does not use layers.")
        sys.exit(-1)

    if len(basemanifest["Layers"])>len(updatemanifest["Layers"]):
        logging.error("base image has more layers than update one.")
        sys.exit(-1)

    index=0
    for baselayer,updatelayer in zip(basemanifest["Layers"],updatemanifest["Layers"]):
        if baselayer != updatelayer:
            break
        index+=1

    if index==0:
        logging.error("Images don't share any common layer.")
        sys.exit(-1)

    logging.info(f"Images share first {index} layers.")

    logging.info("Common layers:")
    for base_layer in basemanifest["Layers"][:index]:
        logging.info(f"\t{base_layer}")

    logging.info("Layers to be merged:")

    for base_layer in basemanifest["Layers"][index:]:
        logging.info(f"\tbase {base_layer}")

    for update_layer in updatemanifest["Layers"][index:]:
        logging.info(f"\tupdate {update_layer}")

    layers_count = index+1

    logging.info(f"extracting layers...")
    baselayerspath,_=expand_layers(basemanifest["Layers"][index:],tempfolder,"base")
    updatelayerspath,update_size=expand_layers(updatemanifest["Layers"][index:],tempfolder,"update")

    filesfolder=os.path.join(outputfolder,"files")

    if os.path.exists(filesfolder):
        shutil.rmtree(filesfolder)

    files_to_be_removed : List[str]=[]
    dirs_to_be_removed : List[str]=[]

    logging.info(f"Analyzing differences...")
    process_folder(
        baselayerspath,
        updatelayerspath,
        filesfolder,
        files_to_be_removed,
        dirs_to_be_removed)

    if len(os.listdir(filesfolder)):
        logging.info(f"Generating new layer...")
        outputtar=os.path.join(outputfolder,"files.tar")

        if os.path.exists(outputtar):
            os.unlink(outputtar)

        with tarfile.open(name=outputtar, mode="w") as tarfile:
            tarfile.add(filesfolder,arcname="/",recursive=True)

        output_size=os.path.getsize(outputtar)
    else:
        output_size=0

    logging.info(f"Creating dockerfile...")
    lines=[]

    lines.append(f"FROM {args.basetag}")

    files_to_be_removed=list(map(lambda x:x[len(filesfolder):],files_to_be_removed))
    dirs_to_be_removed=list(map(lambda x:x[len(filesfolder):],dirs_to_be_removed))

    if len(files_to_be_removed)>0:
        cmd="RUN rm "+" ".join(files_to_be_removed)
        lines.append(cmd)
        layers_count+=1

    if len(dirs_to_be_removed)>0:
        cmd="RUN rm -fR "+" ".join(dirs_to_be_removed)
        lines.append(cmd)
        layers_count+=1

    if len(os.listdir(filesfolder)):
        lines.append("ADD files.tar /")
        layers_count+=1

    if layers_count > args.max_layers:
        logging.error(f"Generated image will have {layers_count} layers, more than the maximum allowed ({args.max_layers}).")
        sys.exit(-3)

    index=0

    for baseitem,updateitem in zip(baseconfig["history"],updateconfig["history"]):
        if baseitem["created_by"] != updateitem["created_by"]:
            break
        index=index+1

    for item in updateconfig["history"][index:]:
        if not "empty_layer" in item or not item["empty_layer"]:
            continue

        command=item["created_by"]
        if not NOP_TAG in command:
            continue

        line = command[command.index(NOP_TAG)+len(NOP_TAG):].strip()

        if line.startswith("CMD") or line.startswith("ENTRYPOINT"):
            cmd=line.split()[0]
            cmdargs=line[len(cmd):].strip()
            if cmdargs.startswith("[") and cmdargs.endswith("]"):
                cmdargs=cmdargs[1:-1]
                cmdargs=shlex.split(cmdargs)
                cmdargs=map(lambda x:f"\"{x}\"",cmdargs)
                cmdargs=",".join(cmdargs)
                line=f"{cmd} [{cmdargs}]"

        lines.append(line)

    dockerfilepath=os.path.join(outputfolder,"Dockerfile")

    with open(dockerfilepath,"w") as outputfile:
        outputfile.write(os.linesep.join(lines))
        outputfile.close()

    if not args.keep_temp:
        logging.info(f"Cleaning temp folder...")
        shutil.rmtree(tempfolder)

    logging.info(f"Original update size: {Quantity(update_size)}, generated update size: {Quantity(output_size)}, diff: {Quantity(update_size-output_size)}.")

    if output_size > update_size:
        logging.error(f"Generated update is {output_size-update_size} bytes larger than the original one.")
        if args.accept_bigger:
            sys.exit(-2)

    logging.info(f"Building output image...")
    docker.images.build(path=outputfolder,tag=args.outputtag)
