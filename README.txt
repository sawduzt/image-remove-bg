remove bg
=========
right-click background removal for windows. no window, no app to open.


what it does
------------
adds  Remove Background  to the right-click menu for image files, with three
quality settings. the cut-out lands next to the original as
<name>_bgremoved.png

   Fast       about a second, fine for graphics and hard edges
   Balanced   about five seconds, the sensible default
   HQ         about thirty seconds, best on hair and fur


install
-------
1. unzip this folder somewhere
2. double click install.bat
3. that is it

it copies itself to %LOCALAPPDATA%\RemoveBG and adds the menu entries for
jpg jpeg png bmp gif webp tif tiff heic heif avif. no admin needed, nothing
else to download, python is not required.


requirements
------------
windows 10 or 11, 64-bit. that is all.

the models download themselves the first time you use a setting, each one
once, into %USERPROFILE%\.rembg :

   Fast       4.6 MB
   Balanced   176 MB
   HQ         1.02 GB

that download shows a progress window. after the first time it is offline.


windows 11
----------
microsoft moved third party menu entries into the second menu. right click an
image, choose Show more options, and Remove Background is there. that is a
windows change, not something this tool can avoid without shipping a signed
shell extension.


if something goes wrong
-----------------------
you get one dialog with a code, RBG-W25 and so on, and the details go to
removebg.log in the install folder. the codes mean:

   W05 no file was passed in
   W10 the file was not found
   W11 the image could not be read, usually locked by another program
   W15 a bundled component is damaged, re-run install.bat
   W20 the model could not be loaded or downloaded
   W25 the image could not be processed
   W30 the result could not be saved, folder read-only or disk full
   W31 another run is still working on something
   W99 something unexpected

to check an install end to end, run in the install folder:

   removebg.exe --verify

that writes verify.txt with what it found.


uninstall
---------
run uninstall.bat. it takes the menu entries out and tells you which folders
to delete. the models live in %USERPROFILE%\.rembg and are the only big thing.


how it works
------------
the cut-out is done by an onnx segmentation model running on onnxruntime, on
your machine, offline. nothing is uploaded anywhere.


source and issues
-----------------
https://github.com/sawduzt/image-remove-bg
