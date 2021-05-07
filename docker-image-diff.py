import argparse
import os
from posix import listdir
import sys
import shutil
import tarfile
import json
import docker
import docker.client
import docker.models.images
import filecmp

def save_image(image,name,folder):

    tarpath=os.path.join(folder,name+".tar")

    if os.path.exists(tarpath):
        os.unlink(tarpath)

    f = open(tarpath, 'wb')
    image_data=image.save()
    for chunk in image_data:
        f.write(chunk)
    f.close()

    tararchive=tarfile.open(name=tarpath)

    tarfolder=os.path.join(folder,name)

    if os.path.exists(tarfolder):
        shutil.rmtree(tarfolder)

    os.makedirs(tarfolder)

    tararchive.extractall(tarfolder,numeric_owner=True)
    return tarfolder

def get_configuration(folder):
    manifestpath=os.path.join(folder,"manifest.json")

    with open(manifestpath) as f:
        manifest=json.load(f)

    configname=manifest[0]["Config"]
    configpath=os.path.join(folder,configname)

    with open(configpath) as f:
        return manifest[0],json.load(f)

def expand_layers(layers,folder,name):
    base_path=os.path.join(folder,name)
    layers_path=os.path.join(folder,name+"_layers")

    if os.path.exists(layers_path):
        shutil.rmtree(layers_path)

    os.makedirs(layers_path)

    for layer in layers:
        layertarpath=os.path.join(base_path,layer)
        tararchive=tarfile.open(name=layertarpath)
        tararchive.extractall(layers_path,numeric_owner=True)

    return layers_path

def process_folder(basepath,updatepath,output,files_to_be_removed,dirs_to_be_removed):
    os.makedirs(output)

    diff=filecmp.dircmp(basepath,updatepath,ignore=[])

    for obj in diff.right_only:
        source=os.path.join(updatepath,obj)
        destination=os.path.join(output,obj)

        if os.path.isdir(source):
            shutil.copytree(source,destination,symlinks=True)
        else:
            shutil.copy2(source,destination)

    for obj in diff.left_only:
        source=os.path.join(basepath,obj)
        destination=os.path.join(output,obj)
        if os.path.isdir(source):
            dirs_to_be_removed.append(destination)
        else:
            files_to_be_removed.append(destination)

    for obj in diff.common_files:
        base=os.path.join(basepath,obj)
        update=os.path.join(updatepath,obj)
        destination=os.path.join(output,obj)

        if not filecmp.cmp(base,update,shallow=False):
            shutil.copy2(update,destination)

    for obj in diff.common_funny:
        base=os.path.join(basepath,obj)
        update=os.path.join(updatepath,obj)
        destination=os.path.join(output,obj)

        if os.path.isdir(base):
            dirs_to_be_removed.append(destination)
        else:
            files_to_be_removed.append(destination)

        if os.path.isdir(update):
            shutil.copytree(update,destination,symlinks=True)
        else:
            shutil.copy2(update,destination)

    for obj in diff.common_dirs:
        base=os.path.join(basepath,obj)
        update=os.path.join(updatepath,obj)
        destination=os.path.join(output,obj)

        process_folder(base,update,destination,files_to_be_removed,dirs_to_be_removed)


parser=argparse.ArgumentParser()

parser.add_argument("basetag",help="Base image")
parser.add_argument("updatetag",help="Image that is used to generate the update")
parser.add_argument("outputfolder",help="Folder where dockerfile and contents are generated")

args=parser.parse_args()

docker=docker.from_env()

baseimg=docker.images.get(args.basetag)
updateimg=docker.images.get(args.updatetag)

outputfolder=args.outputfolder

if not os.path.exists(outputfolder):
    os.makedirs(outputfolder)
elif not os.path.isdir(outputfolder):
    print("Outputdir must be a valid folder path.")
    sys.exit(-1)

tempfolder=os.path.join(outputfolder,"temp")

if not os.path.exists(tempfolder):
    os.makedirs(tempfolder)

basefolder=save_image(baseimg,"base",tempfolder)
updatefolder=save_image(updateimg,"update",tempfolder)

basemanifest,baseconfig=get_configuration(basefolder)

if baseconfig["rootfs"]["type"] != "layers":
    print("base image does not use layers.")
    sys.exit(-1)

updatemanifest,updateconfig=get_configuration(updatefolder)

if updateconfig["rootfs"]["type"] != "layers":
    print("base image does not use layers.")
    sys.exit(-1)

if len(basemanifest["Layers"])>len(updatemanifest["Layers"]):
    print("base image has more layers than update one.")
    sys.exit(-1)

index=0
for baselayer,updatelayer in zip(basemanifest["Layers"],updatemanifest["Layers"]):
    if baselayer != updatelayer:
        break;
    index+=1

if index==0:
    print("Images don't share any common layer.")
    sys.exit(-1)

print(f"Images share first {index} layers.")

print("Common layers:")
for layer in basemanifest["Layers"][:index]:
    print(f"\t{layer}")

print("Layers to be merged:")

for layer in basemanifest["Layers"][index:]:
    print(f"\tbase {layer}")

for layer in updatemanifest["Layers"][index:]:
    print(f"\tupdate {layer}")

baselayerspath=expand_layers(basemanifest["Layers"][index:],tempfolder,"base")
updatelayerspath=expand_layers(updatemanifest["Layers"][index:],tempfolder,"update")

filesfolder=os.path.join(outputfolder,"files")

if os.path.exists(filesfolder):
    shutil.rmtree(filesfolder)

files_to_be_removed=[]
dirs_to_be_removed=[]

process_folder(baselayerspath,updatelayerspath,filesfolder,files_to_be_removed,dirs_to_be_removed)

lines=[]

lines.append(f"FROM {args.basetag}")

files_to_be_removed=list(map(lambda x:x[len(filesfolder):],files_to_be_removed))
dirs_to_be_removed=list(map(lambda x:x[len(filesfolder):],dirs_to_be_removed))

if len(files_to_be_removed)>0:
    cmd="RUN rm "+" ".join(files_to_be_removed)
    lines.append(cmd)

if len(dirs_to_be_removed)>0:
    cmd="RUN rm -fR "+" ".join(dirs_to_be_removed)
    lines.append(cmd)

if len(os.listdir(filesfolder)):
    lines.append("COPY files /")

index=0

for baseitem,updateitem in zip(baseconfig["history"],updateconfig["history"]):
    if baseitem["created_by"] != updateitem["created_by"]:
        break
    index+=1

for item in updateconfig["history"][index:]:
    if not "empty_layer" in item or not item["empty_layer"]:
        continue

    tag="#(nop)"
    command=item["created_by"]
    if not tag in command:
        continue

    lines.append(command[command.index(tag)+len(tag):].strip())

dockerfilepath=os.path.join(outputfolder,"Dockerfile")

with open(dockerfilepath,"w") as f:
    f.write(os.linesep.join(lines))
    f.close()

# shutil.rmtree(tempfolder)





