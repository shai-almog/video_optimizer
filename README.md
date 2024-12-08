# Video Optimizer

This is a simple tool that you can point at a directory hierarchy containing videos. It will check if the bitrate of the video is within 10% of the desired bitrate and if it's above that it will re-encode the video using the H.265 codec. It relies on your system having ffmpeg installed. Running this on a typical video directory gave me roughly 4x reduction in size with no noticeable quality degredation (to my bad old eyes YMMV). This does take a long while to run so be patient... 

Parameters:

* `-d`, `--directory` - Path to the directory to scan (default: current directory)
* `-s`, `--max-size` - Maximum file size in MB (default: 200MB). Files below this size are ignored.
* `-b`, `--max-bitrate` - Maximum bitrate in kbps (default: 1000kbps). If the file has identical or lower bitrate (within a 10% range) it will be skipped. This is the bitrate we will use when re-encoding the file.
* `-v`, `--verbose` - Enable verbose FFmpeg output. This isn't recommended as ffmpeg over-shares information.
