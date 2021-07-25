import argparse
import os
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile

parser = argparse.ArgumentParser(
    description="Package LÖVE game for distribution on Linux (x64), Windows (x86 and x64), and macos (x64)",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)

subparsers = parser.add_subparsers(title="system", dest="system")
subparsers.required = True

parser_linux = subparsers.add_parser(
    "linux", formatter_class=argparse.ArgumentDefaultsHelpFormatter
)
parser_windows = subparsers.add_parser(
    "windows", formatter_class=argparse.ArgumentDefaultsHelpFormatter
)
parser_macos = subparsers.add_parser(
    "macos", formatter_class=argparse.ArgumentDefaultsHelpFormatter
)

for p in [parser_linux, parser_windows, parser_macos]:
    p.add_argument("name", help="name to use for the distribution")
    p.add_argument("file", help="path to love archive containing the game")
    p.add_argument("output_dir", help="path to the output directory")
    p.add_argument("-v", "--love_version", help="LÖVE version to use", default="11.3")

parser_macos.add_argument(
    "identifier", help='identifier for the macos app (to replace "org.love2d.love")'
)
parser_macos.add_argument(
    "copyright",
    help='copyright information for the macos app (to replace "© ... LÖVE Development Team")',
)

parser_windows.add_argument(
    "-a", "--arch", help="architecture to target", choices={"x86", "x64"}, default="x64"
)

for p in [parser_linux, parser_windows, parser_macos]:
    p.add_argument(
        "extra_files",
        help="path to tar archive containing any extra files to add to the distribution",
        nargs="?",
    )

args = parser.parse_args()

if not os.path.isfile(args.file):
    raise ValueError("The specified love archive does not exist")
args.file = os.path.realpath(args.file)

if args.extra_files:
    if not os.path.isfile(args.extra_files):
        raise ValueError("The specified tar archive does not exist")
    args.extra_files = os.path.realpath(args.extra_files)

args.output_dir = os.path.realpath(args.output_dir)

desktop_file = f"""
[Desktop Entry]
Name={args.name}
Exec=wrapper-love 
Type=Application
Categories=Development;Game;
Terminal=false
Icon=love
NoDisplay=true
"""

wrapper_love = """
#!/bin/sh

# For some reason this runs from the usr subdirectory
APPIMAGE_DIR="${PWD}/.."
cd "$OWD"
exec "${APPIMAGE_DIR}/love" --fused "${APPIMAGE_DIR}/game.love"
"""

with tempfile.TemporaryDirectory() as tmpdirname:
    os.chdir(tmpdirname)
    base_url = f"https://github.com/love2d/love/releases/download/{args.love_version}/love-{args.love_version}-"

    if args.system == "linux":
        # download LÖVE
        love_file = os.path.join(tmpdirname, "linux.AppImage")
        urllib.request.urlretrieve(base_url + "x86_64.AppImage", love_file)
        os.chmod(love_file, stat.S_IREAD | stat.S_IEXEC)

        # download appimagetool
        url = "https://github.com/AppImage/AppImageKit/releases/download/13/appimagetool-x86_64.AppImage"
        appimagetool = os.path.join(tmpdirname, "appimagetool.AppImage")
        urllib.request.urlretrieve(url, appimagetool)
        os.chmod(appimagetool, stat.S_IREAD | stat.S_IEXEC)

        # package
        os.system(f"{love_file} --appimage-extract")
        os.chdir("squashfs-root")
        shutil.copyfile(args.file, "game.love")
        if args.extra_files:
            with tarfile.open(args.extra_files) as tarf:
                tarf.extractall()
        with open("love.desktop", "w") as f:
            f.write(desktop_file)
        with open("usr/bin/wrapper-love", "w") as f:
            f.write(wrapper_love)
        os.chdir("..")
        os.system(f"{appimagetool} squashfs-root {args.name}-linux-x64.AppImage")

        with zipfile.ZipFile(f"{args.name}-linux-x64.zip", "w") as zipf:
            zipf.write(f"{args.name}-linux-x64.AppImage")

    if args.system == "windows":
        arch = "32" if args.arch == "x86" else "64"

        # download LÖVE
        love_file = os.path.join(tmpdirname, f"win{arch}.zip")
        urllib.request.urlretrieve(base_url + f"win{arch}.zip", love_file)

        # package
        with zipfile.ZipFile(f"win{arch}.zip") as zipf:
            zipf.extractall()
        os.rename(f"love-{args.love_version}-win{arch}", args.name)
        os.chdir(args.name)
        with open(f"{args.name}.exe", "wb") as output:
            with open("love.exe", "rb") as f:
                shutil.copyfileobj(f, output)
            with open(args.file, "rb") as f:
                shutil.copyfileobj(f, output)
        os.remove("love.exe")
        os.remove("lovec.exe")
        if args.extra_files:
            with tarfile.open(args.extra_files) as tarf:
                tarf.extractall()

        os.chdir("..")

        shutil.make_archive(
            f"{args.name}-windows-{args.arch}", "zip", base_dir=args.name
        )

    if args.system == "macos":
        # download LÖVE
        love_file = os.path.join(tmpdirname, "macos.zip")
        urllib.request.urlretrieve(base_url + "macos.zip", love_file)

        # package
        os.system("unzip macos.zip")
        os.chdir("love.app/Contents/Resources")
        shutil.copyfile(args.file, "game.love")
        if args.extra_files:
            with tarfile.open(args.extra_files) as tarf:
                tarf.extractall()
        os.chdir("../../..")

        with open("love.app/Contents/Info.plist", "r") as f:
            data = f.read()
        data = re.sub(
            r"(<key>CFBundleIdentifier</key>\s*<string>).*?(</string>)",
            rf"\1{args.identifier}\2",
            data,
        )
        data = re.sub(
            r"(<key>CFBundleName</key>\s*<string>).*?(</string>)",
            rf"\1{args.name}\2",
            data,
        )
        data = re.sub(
            r"(<key>NSHumanReadableCopyright</key>\s*<string>).*?(</string>)",
            rf"\1{args.copyright}\2",
            data,
        )
        data = re.sub(
            r"<key>UTExportedTypeDeclarations</key>\n\t*<array>[\s\S]*?\n\t</array>\n",
            "",
            data,
        )
        with open("love.app/Contents/Info.plist", "w") as f:
            f.write(data)

        os.rename("love.app", f"{args.name}.app")
        os.system(f"zip --symlinks -r {args.name}-macos-x64.zip -r {args.name}.app")

    # copy files to output folder
    if not os.path.isdir(args.output_dir):
        os.mkdir(args.output_dir)
    for suffix in ["linux-x64", "windows-x86", "windows-x64", "macos-x64"]:
        filename = f"{args.name}-{suffix}.zip"
        if os.path.isfile(filename):
            shutil.copyfile(filename, os.path.join(args.output_dir, filename))
